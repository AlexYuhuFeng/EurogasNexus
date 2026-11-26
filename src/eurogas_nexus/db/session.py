"""Lazy SQLAlchemy engine and session factory helpers.

Pool sizing (several API processes; ``docs/operations/API_SERVING_AND_SHARED_CACHE.md``):
every process holds its own pool of ``EUROGAS_NEXUS_DB_POOL_SIZE`` connections plus at most
``EUROGAS_NEXUS_DB_MAX_OVERFLOW`` more. Sum over every process that connects (API processes on
every server, the workers, an operator's session) must stay under PostgreSQL's
``max_connections`` less its reserved connections. Inside an API process the request threads
(:func:`api_thread_limit`) are sized from the pool, so a request waits for a thread rather than
for a connection (a connection wait ends in an error after ``EUROGAS_NEXUS_DB_POOL_TIMEOUT``).

Every API connection carries a ``statement_timeout`` (:func:`use_api_statement_timeout`), so a
runaway read is cancelled instead of holding a connection while every other request queues.
The pool counts its checkouts, the ones that had to wait and the ones that timed out
(:func:`pool_counters`, published as ``eurogas_db_pool_*`` metrics), and the statements the
server cancelled and the connections lost (``eurogas_db_statement_timeouts``,
``eurogas_db_connections_lost``).

Timeouts, one meaning each (``docs/operations/DB_RUNTIME_HARDENING.md``, "Timeouts"):

* **connect**: opening a connection (TCP, TLS, authentication) waits at most
  :data:`CONNECT_TIMEOUT_SECONDS`;
* **statement**: PostgreSQL's own ``statement_timeout`` bounds each statement (30 s for the
  API; none for workers, the scheduler, the seed and operator commands; one hour for a
  migration, with a 10 s ``lock_timeout``). The server cancels the statement cleanly and the
  connection stays usable;
* **socket**: only a safety net for a network that stopped answering. pg8000 applies its
  ``timeout`` argument to every read of the socket, so a connect bound passed that way used to
  cut every statement off at 5 s on the client while the server went on running it. After the
  connection is made the socket's timeout becomes the statement timeout plus
  :data:`SOCKET_TIMEOUT_MARGIN_SECONDS` (none without a statement timeout), and TCP keepalives
  find a dead peer within about :data:`DEAD_PEER_SECONDS` either way.
"""

import os
import re
import threading
import time
from collections.abc import Mapping
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import QueuePool

from eurogas_nexus.db.connection_url import pg8000_ssl_arguments

DB_URL_ENV_VARS = (
    "RUNTIME_STORE_DATABASE_URL",
    "DATABASE_URL",
    "EUROGAS_NEXUS_DB_DSN",
)


#: Connections an API process uses beside its request threads: the live-update poller, the
#: warm views' two background refreshes and the two identity threads (``api/stream_hub.py``,
#: ``application/warm_views.py``, ``api/dependencies/identity.py``).
API_BACKGROUND_CONNECTIONS = 5
#: The statement timeout an API process applies when none is configured (milliseconds).
API_STATEMENT_TIMEOUT_MS = 30_000

#: Set by the API application (:func:`use_api_statement_timeout`).
_API_PROCESS = False

#: Opening a connection (TCP, TLS and authentication) waits at most this long.
CONNECT_TIMEOUT_SECONDS = 5
#: How much longer than the statement timeout the socket waits for an answer before it gives
#: the connection up: the server's cancellation always comes first.
SOCKET_TIMEOUT_MARGIN_SECONDS = 30
#: TCP keepalives on every connection: probes after this much silence, then every interval.
TCP_KEEPALIVE_IDLE_SECONDS = 30
TCP_KEEPALIVE_INTERVAL_SECONDS = 10
TCP_KEEPALIVE_COUNT = 5
#: A peer that stopped answering is found after about this long (idle + interval x count).
DEAD_PEER_SECONDS = (
    TCP_KEEPALIVE_IDLE_SECONDS + TCP_KEEPALIVE_INTERVAL_SECONDS * TCP_KEEPALIVE_COUNT
)


class PoolCounters:
    """Checkouts, waits and timeouts of every pool in this process (thread-safe)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.checkouts = 0
        self.waits = 0
        self.timeouts = 0
        self.wait_seconds = 0.0
        self.statement_timeouts = 0
        self.connections_lost = 0

    def record(self, waited: float, *, timed_out: bool, exhausted: bool) -> None:
        """One checkout: ``exhausted`` when no connection was idle and none could be opened,
        so it had to wait for one to come back (opening a new connection is not a wait)."""

        with self._lock:
            if timed_out:
                self.timeouts += 1
            else:
                self.checkouts += 1
            if exhausted:
                self.waits += 1
                self.wait_seconds += waited

    def record_failure(self, *, statement_timeout: bool, connection_lost: bool) -> None:
        """A statement the server cancelled, or a connection that was lost (and dropped)."""

        with self._lock:
            if statement_timeout:
                self.statement_timeouts += 1
            if connection_lost:
                self.connections_lost += 1

    def snapshot(self) -> dict[str, float]:
        with self._lock:
            return {
                "checkouts": self.checkouts,
                "waits": self.waits,
                "timeouts": self.timeouts,
                "wait_seconds": self.wait_seconds,
                "statement_timeouts": self.statement_timeouts,
                "connections_lost": self.connections_lost,
            }


_POOL_COUNTERS = PoolCounters()


def pool_counters() -> PoolCounters:
    return _POOL_COUNTERS


def _pool_number(pool, name: str) -> int:
    value = getattr(pool, name, None)
    if value is None:
        return 0
    if callable(value):
        try:
            value = value()
        except Exception:  # noqa: BLE001 - a metric must never break the scrape
            return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def pool_occupancy(pools) -> tuple[int, int, int]:
    """``(checked_out, size, overflow)`` summed over SQLAlchemy pools.

    ``QueuePool.checkedout``/``size`` are methods, so they are called (an earlier exporter
    printed the bound method's ``repr``, which made Prometheus reject the whole scrape).
    """

    checked_out = size = overflow = 0
    for pool in pools:
        inner = getattr(pool, "_pool", None)
        checked_out += _pool_number(pool, "checkedout")
        size += _pool_number(pool, "size") or _pool_number(inner, "maxsize")
        overflow += max(0, _pool_number(pool, "_max_overflow"))
    return checked_out, size, overflow


def pool_state(pools=None) -> dict[str, float]:
    """This process's pool state, the one source the pool metrics read: occupancy of
    ``pools`` (default: every cached engine's pool) and the :func:`pool_counters` totals."""

    checked_out, size, overflow = pool_occupancy(
        cached_engine_pools() if pools is None else pools
    )
    return {
        "checked_out": checked_out,
        "size": size,
        "overflow": overflow,
        **_POOL_COUNTERS.snapshot(),
    }


class CountingQueuePool(QueuePool):
    """SQLAlchemy's queue pool, counting waits for a connection and pool timeouts."""

    def _do_get(self):  # noqa: ANN202 - SQLAlchemy's signature
        from sqlalchemy.exc import TimeoutError as PoolTimeout

        exhausted = self._pool.qsize() == 0 and self._overflow >= self._max_overflow
        started = time.monotonic()
        try:
            connection = super()._do_get()
        except PoolTimeout:
            _POOL_COUNTERS.record(time.monotonic() - started, timed_out=True, exhausted=True)
            raise
        _POOL_COUNTERS.record(time.monotonic() - started, timed_out=False, exhausted=exhausted)
        return connection


def use_api_statement_timeout() -> None:
    """Called by the API application: its connections cancel a statement after
    ``EUROGAS_NEXUS_DB_STATEMENT_TIMEOUT_MS`` (default :data:`API_STATEMENT_TIMEOUT_MS`).

    Workers and operator scripts do not call it, so the setting (in the same environment file)
    does not reach them: an ingestion or a migration may legitimately run longer."""

    global _API_PROCESS
    _API_PROCESS = True


def statement_timeout_ms(environ: Mapping[str, str] | None = None) -> int | None:
    """The statement timeout new connections get (None: PostgreSQL's own, unlimited)."""

    if not _API_PROCESS:
        return None
    env = os.environ if environ is None else environ
    raw = (env.get("EUROGAS_NEXUS_DB_STATEMENT_TIMEOUT_MS") or "").strip()
    if not raw:
        return API_STATEMENT_TIMEOUT_MS
    try:
        value = int(raw)
    except ValueError:
        return API_STATEMENT_TIMEOUT_MS
    return value if value > 0 else None


def api_thread_limit(environ: Mapping[str, str] | None = None) -> int:
    """Request threads per API process: ``EUROGAS_NEXUS_API_THREADS``, else the pool's
    connections less the background ones, so no request thread waits for a connection."""

    env = os.environ if environ is None else environ
    raw = (env.get("EUROGAS_NEXUS_API_THREADS") or "").strip()
    if raw:
        try:
            value = int(raw)
        except ValueError:
            value = 0
        if value > 0:
            return value
    pool = max(1, _env_int("EUROGAS_NEXUS_DB_POOL_SIZE", 10, env))
    overflow = max(0, _env_int("EUROGAS_NEXUS_DB_MAX_OVERFLOW", 20, env))
    return max(4, pool + overflow - API_BACKGROUND_CONNECTIONS)


def resolve_database_url(environ: Mapping[str, str | None] | None = None) -> str | None:
    """Resolve the runtime DB URL using the approved precedence order."""

    env = os.environ if environ is None else environ
    for env_var in DB_URL_ENV_VARS:
        raw_value = env.get(env_var)
        if raw_value is None:
            continue

        value = raw_value.strip()
        if value:
            return value

    return None


def default_driver_url(url: str) -> str:
    """``postgres://`` or ``postgresql://`` without a driver means the runtime's, pg8000.

    Managed services and most guides write the URL without a driver, and SQLAlchemy then asks
    for psycopg2, which the product does not install. A URL that names its driver is kept.
    """

    scheme, separator, rest = url.partition("://")
    if separator and scheme.lower() in {"postgres", "postgresql"}:
        return f"postgresql+pg8000://{rest}"
    return url


def redact_database_url(database_url: str | None) -> str | None:
    """Return a DB URL safe for logs and reports."""

    if database_url is None:
        return None

    try:
        return make_url(database_url).render_as_string(hide_password=True)
    except Exception:
        return re.sub(r"(://[^:/?#]+:)[^@/?#]+(@)", r"\1***\2", database_url)


_FROM_ROLE = object()


def socket_timeout_for(statement_timeout_ms: int | None) -> float | None:
    """The socket's read timeout for a connection whose statements end after
    ``statement_timeout_ms``: that plus a margin, or none (keepalives alone) without one."""

    if not statement_timeout_ms:
        return None
    return statement_timeout_ms / 1000 + SOCKET_TIMEOUT_MARGIN_SECONDS


def driver_connect_args(drivername: str, connect_timeout_seconds: float) -> dict[str, object]:
    """The driver's connect arguments: a connect bound and TCP keepalives.

    pg8000's ``timeout`` is a socket timeout that stays on the socket for every later read;
    :func:`get_engine` replaces it as soon as the connection is made. libpq's
    ``connect_timeout`` (psycopg, psycopg2) bounds the connect only; its keepalive and
    ``tcp_user_timeout`` options find a dead peer.
    """

    bound = max(1, int(connect_timeout_seconds))
    if drivername.endswith("+pg8000"):
        return {"timeout": bound, "tcp_keepalive": True}
    return {
        "connect_timeout": bound,
        "keepalives": 1,
        "keepalives_idle": TCP_KEEPALIVE_IDLE_SECONDS,
        "keepalives_interval": TCP_KEEPALIVE_INTERVAL_SECONDS,
        "keepalives_count": TCP_KEEPALIVE_COUNT,
        "tcp_user_timeout": DEAD_PEER_SECONDS * 1000,
    }


def tune_pg8000_socket(dbapi_connection, socket_timeout: float | None) -> None:
    """After connecting: the socket's timeout becomes the safety net, keepalives are tuned.

    pg8000 has no public setting for this; its socket is ``_usock`` (pg8000 1.31). A
    connection without one (another driver, a test double) is left as it is.
    """

    import socket

    sock = getattr(dbapi_connection, "_usock", None)
    if sock is None:
        return
    sock.settimeout(socket_timeout)
    options = [(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)]
    for name, value in (
        ("TCP_KEEPIDLE", TCP_KEEPALIVE_IDLE_SECONDS),
        ("TCP_KEEPINTVL", TCP_KEEPALIVE_INTERVAL_SECONDS),
        ("TCP_KEEPCNT", TCP_KEEPALIVE_COUNT),
        # Unacknowledged data (a request sent to a peer that vanished) gives up after this.
        ("TCP_USER_TIMEOUT", DEAD_PEER_SECONDS * 1000),
    ):
        option = getattr(socket, name, None)
        if option is not None:
            options.append((socket.IPPROTO_TCP, option, value))
    for level, option, value in options:
        try:
            sock.setsockopt(level, option, value)
        except OSError:  # a Unix socket has no TCP options
            continue


def _count_failure(context) -> None:
    """Count a statement the server cancelled and a connection lost (the pool metrics)."""

    from eurogas_nexus.core.db_errors import is_statement_timeout

    timed_out = is_statement_timeout(context.original_exception)
    lost = bool(getattr(context, "is_disconnect", False))
    if timed_out or lost:
        _POOL_COUNTERS.record_failure(statement_timeout=timed_out, connection_lost=lost)


def get_engine(
    database_url: str | None = None,
    *,
    echo: bool = False,
    pool_pre_ping: bool = True,
    connect_timeout_seconds: float = CONNECT_TIMEOUT_SECONDS,
    pool_size: int | None = None,
    max_overflow: int | None = None,
    pool_timeout_seconds: float | None = None,
    pool_recycle_seconds: int | None = None,
    statement_timeout: int | None | object = _FROM_ROLE,
    socket_timeout_seconds: float | None | object = _FROM_ROLE,
    one_off: bool = False,
) -> Engine:
    """Create a SQLAlchemy engine lazily without opening a connection.

    ``connect_timeout_seconds`` bounds opening a connection only. ``statement_timeout``
    (milliseconds) defaults to this process's role (:func:`statement_timeout_ms`: the API's
    30 s, none elsewhere); ``socket_timeout_seconds`` defaults to that plus
    :data:`SOCKET_TIMEOUT_MARGIN_SECONDS` (none without a statement timeout). ``one_off``: a
    command's engine without a pool (each connection closed when released), with the same
    connect bound, keepalives and timeouts.
    """

    resolved_url = database_url.strip() if database_url else resolve_database_url()
    if not resolved_url:
        raise ValueError("Database URL is required to create an engine.")
    resolved_url = default_driver_url(resolved_url)

    engine_options: dict[str, object] = {
        "echo": echo,
        "pool_pre_ping": pool_pre_ping,
        "future": True,
    }
    # A libpq ``sslmode`` (as a managed PostgreSQL service issues it) becomes the
    # ``ssl_context`` pg8000 takes; a URL without one is left exactly as it was.
    parsed_url, ssl_arguments = pg8000_ssl_arguments(make_url(resolved_url))
    postgresql = parsed_url.get_backend_name() == "postgresql"
    if postgresql:
        engine_options["connect_args"] = {
            **driver_connect_args(parsed_url.drivername, connect_timeout_seconds),
            **ssl_arguments,
        }
    if postgresql and one_off:
        from sqlalchemy.pool import NullPool

        engine_options["poolclass"] = NullPool
    elif postgresql:
        engine_options["pool_size"] = max(
            1,
            pool_size
            if pool_size is not None
            else _env_int("EUROGAS_NEXUS_DB_POOL_SIZE", 10),
        )
        engine_options["max_overflow"] = max(
            0,
            max_overflow
            if max_overflow is not None
            else _env_int("EUROGAS_NEXUS_DB_MAX_OVERFLOW", 20),
        )
        engine_options["pool_timeout"] = max(
            1.0,
            pool_timeout_seconds
            if pool_timeout_seconds is not None
            else _env_float("EUROGAS_NEXUS_DB_POOL_TIMEOUT", 5.0),
        )
        engine_options["pool_recycle"] = max(
            60,
            pool_recycle_seconds
            if pool_recycle_seconds is not None
            else _env_int("EUROGAS_NEXUS_DB_POOL_RECYCLE", 1800),
        )
        engine_options["poolclass"] = CountingQueuePool

    engine = create_engine(parsed_url, **engine_options)
    if not postgresql:
        return engine
    from sqlalchemy import event

    from eurogas_nexus.db.resilience import failover_hosts, install_primary_only_connect

    # A primary and its standby (db/resilience.py): each new connection lands on the writable
    # one. Each host is tried with the same connect bound (``connect_args``); the socket
    # tuning below runs once the chosen connection is established.
    extra_hosts = failover_hosts()
    if extra_hosts:
        install_primary_only_connect(engine, extra_hosts)

    timeout_ms = statement_timeout_ms() if statement_timeout is _FROM_ROLE else statement_timeout
    socket_timeout = (
        socket_timeout_for(timeout_ms)  # type: ignore[arg-type]
        if socket_timeout_seconds is _FROM_ROLE
        else socket_timeout_seconds
    )
    if parsed_url.drivername.endswith("+pg8000"):

        def _tune_socket(connection, _record) -> None:
            tune_pg8000_socket(connection, socket_timeout)  # type: ignore[arg-type]

        # First, so every later set-up statement already runs under the long bound.
        event.listen(engine, "connect", _tune_socket, insert=True)
    if timeout_ms:

        def _set_statement_timeout(connection, _record) -> None:
            cursor = connection.cursor()
            try:
                cursor.execute(f"SET statement_timeout = {int(timeout_ms)}")  # type: ignore[arg-type]
            finally:
                cursor.close()
            connection.commit()

        event.listen(engine, "connect", _set_statement_timeout)
    event.listen(engine, "handle_error", _count_failure)
    if parsed_url.drivername.endswith("+pg8000"):
        from eurogas_nexus.db.pg8000_decoding import register

        # Dates and timestamps decoded with fromisoformat, not strptime (pg8000_decoding.py).
        event.listen(engine, "connect", lambda connection, _record: register(connection))
    return engine


class ResilientSession(Session):
    """A session that says whether an interrupted commit may have been applied.

    The pending changes are flushed first: a failure there means the transaction never
    reached ``COMMIT`` and PostgreSQL discards it (nothing was saved; the error propagates
    unchanged). A connection lost during ``COMMIT`` itself leaves the outcome unknown, and is
    raised as :class:`eurogas_nexus.db.resilience.CommitOutcomeUnknown` so no caller mistakes
    it for "not saved" and retries a write that may already be in the database.
    """

    def commit(self) -> None:
        from eurogas_nexus.db.resilience import CommitOutcomeUnknown, is_connection_error

        self.flush()
        try:
            super().commit()
        except Exception as exc:
            if is_connection_error(exc):
                raise CommitOutcomeUnknown(
                    "the database connection was lost while committing; the write may or may "
                    "not have been applied"
                ) from exc
            raise


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Return a configured session factory."""

    return sessionmaker(
        bind=engine, autocommit=False, autoflush=False, class_=ResilientSession
    )


_CACHED_ENGINES: list[Engine] = []


@lru_cache(maxsize=16)
def _cached_session_factory(database_url: str) -> sessionmaker[Session]:
    """Reuse one bounded SQLAlchemy pool for each resolved runtime database."""

    engine = get_engine(database_url)
    _CACHED_ENGINES.append(engine)
    return create_session_factory(engine)


def cached_engine_pools() -> list:
    """The connection pools this process's cached engines hold (for the pool metrics)."""

    return [engine.pool for engine in list(_CACHED_ENGINES)]


def dispose_cached_engines() -> int:
    """Close every pooled connection the cached session factories hold.

    Called when the API shuts down, so PostgreSQL sees each connection end cleanly
    instead of waiting for the socket to drop (a small managed plan counts every open
    connection against its limit). Returns the number of engines disposed.
    """

    disposed = 0
    while _CACHED_ENGINES:
        _CACHED_ENGINES.pop().dispose()
        disposed += 1
    _cached_session_factory.cache_clear()
    return disposed


def get_session_factory(
    *,
    engine: Engine | None = None,
    database_url: str | None = None,
) -> sessionmaker[Session]:
    """Return a session factory for an explicit or resolved engine."""

    if engine is not None:
        return create_session_factory(engine)

    resolved_url = database_url.strip() if database_url else resolve_database_url()
    if not resolved_url:
        raise ValueError("Database URL is required to create a session factory.")
    return _cached_session_factory(resolved_url)


def _env_int(name: str, default: int, environ: Mapping[str, str] | None = None) -> int:
    raw = (os.environ if environ is None else environ).get(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default
