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
(:func:`pool_counters`, published as ``eurogas_db_pool_*`` metrics).
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


class PoolCounters:
    """Checkouts, waits and timeouts of every pool in this process (thread-safe)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.checkouts = 0
        self.waits = 0
        self.timeouts = 0
        self.wait_seconds = 0.0

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

    def snapshot(self) -> dict[str, float]:
        with self._lock:
            return {
                "checkouts": self.checkouts,
                "waits": self.waits,
                "timeouts": self.timeouts,
                "wait_seconds": self.wait_seconds,
            }


_POOL_COUNTERS = PoolCounters()


def pool_counters() -> PoolCounters:
    return _POOL_COUNTERS


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


def get_engine(
    database_url: str | None = None,
    *,
    echo: bool = False,
    pool_pre_ping: bool = True,
    connect_timeout_seconds: int = 5,
    pool_size: int | None = None,
    max_overflow: int | None = None,
    pool_timeout_seconds: float | None = None,
    pool_recycle_seconds: int | None = None,
) -> Engine:
    """Create a SQLAlchemy engine lazily without opening a connection."""

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
    if parsed_url.get_backend_name() == "postgresql":
        bounded_timeout = max(1, int(connect_timeout_seconds))
        timeout_parameter = (
            "timeout" if parsed_url.drivername.endswith("+pg8000") else "connect_timeout"
        )
        engine_options["connect_args"] = {timeout_parameter: bounded_timeout, **ssl_arguments}
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
    timeout_ms = statement_timeout_ms()
    if parsed_url.get_backend_name() == "postgresql" and timeout_ms:
        from sqlalchemy import event

        def _set_statement_timeout(connection, _record) -> None:
            cursor = connection.cursor()
            try:
                cursor.execute(f"SET statement_timeout = {int(timeout_ms)}")
            finally:
                cursor.close()
            connection.commit()

        event.listen(engine, "connect", _set_statement_timeout)
    if parsed_url.drivername.endswith("+pg8000"):
        from sqlalchemy import event

        from eurogas_nexus.db.pg8000_decoding import register

        # Dates and timestamps decoded with fromisoformat, not strptime (pg8000_decoding.py).
        event.listen(engine, "connect", lambda connection, _record: register(connection))
    return engine


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Return a configured session factory."""

    return sessionmaker(bind=engine, autocommit=False, autoflush=False, class_=Session)


_CACHED_ENGINES: list[Engine] = []


@lru_cache(maxsize=16)
def _cached_session_factory(database_url: str) -> sessionmaker[Session]:
    """Reuse one bounded SQLAlchemy pool for each resolved runtime database."""

    engine = get_engine(database_url)
    _CACHED_ENGINES.append(engine)
    return create_session_factory(engine)


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
