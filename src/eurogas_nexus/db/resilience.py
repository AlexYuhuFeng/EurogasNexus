"""How the application behaves while its database fails over.

Decision record 2026-11-26 runs PostgreSQL as a primary with a hot standby. During a failover
the primary disappears for seconds to minutes and a standby is promoted. Four rules:

1. **Start-up waits with backoff.** A worker or the API that starts while the database is
   unreachable retries ``SELECT 1`` with exponential backoff and jitter for a bounded time
   (:func:`wait_for_database`) instead of crashing in a restart loop or starting half-ready.
2. **A lost connection is not a crash.** Pooled connections are checked before use
   (``pool_pre_ping`` in :func:`eurogas_nexus.db.session.get_engine`), so after a failover the
   pool replaces dead connections on its own; a request that meets the outage gets a ``503``
   with a retry code, never a ``500``, and readiness fails until the database answers.
3. **No silent write loss.** A write is never retried behind the caller's back, because a retry
   after an interrupted commit could apply it twice. Instead the caller is told precisely:
   a failure **before** commit means nothing was saved (``runtime_db_unavailable``: safe to
   retry); a connection lost **during** commit means the outcome is unknown
   (:class:`CommitOutcomeUnknown`, ``runtime_db_commit_unconfirmed``: check, then retry).
4. **Only a writable primary is used.** With ``EUROGAS_NEXUS_DB_FAILOVER_HOSTS`` set (the
   other database servers, ``host:port`` comma-separated), each new connection tries the URL's
   host and then those, and keeps the first that is **not in recovery** (the libpq
   ``target_session_attrs=read-write`` rule, which pg8000 lacks). A standby, or a fenced old
   primary restarted with ``standby.signal``, is skipped; after a promotion the application
   finds the new primary without a configuration change.
"""

from __future__ import annotations

import os
import random
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass

# One table of SQLSTATEs and codes, shared with the API's error mapping (core/db_errors.py).
from eurogas_nexus.core.db_errors import CONNECTION_SQLSTATES as _CONNECTION_SQLSTATES
from eurogas_nexus.core.db_errors import (
    DB_COMMIT_UNCONFIRMED_CODE,
    NO_WRITABLE_PRIMARY,
    READ_ONLY_SQLSTATE,
)

#: How long a starting process waits for its database by default (seconds).
DEFAULT_STARTUP_WAIT_SECONDS = 0.0
STARTUP_WAIT_ENV = "EUROGAS_NEXUS_DB_STARTUP_WAIT_SECONDS"
FAILOVER_HOSTS_ENV = "EUROGAS_NEXUS_DB_FAILOVER_HOSTS"

class CommitOutcomeUnknown(Exception):
    """The connection was lost while committing: the write may or may not have been applied.

    The caller must check (read the record back, or look up its idempotency key) before
    retrying; retrying blindly could apply the write twice.
    """

    code = DB_COMMIT_UNCONFIRMED_CODE


def _sqlstate(exc: BaseException) -> str | None:
    original = getattr(exc, "orig", exc)
    args = getattr(original, "args", ())
    if args and isinstance(args[0], dict):
        code = args[0].get("C")
        return str(code) if code else None
    return getattr(original, "pgcode", None) or getattr(original, "sqlstate", None)


def is_connection_error(exc: BaseException) -> bool:
    """True when ``exc`` means the database was unreachable or the connection dropped."""

    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, ConnectionError | TimeoutError):
            return True
        if isinstance(current, OSError) and not isinstance(current, FileNotFoundError):
            return True
        if getattr(current, "connection_invalidated", False):
            return True
        module = type(current).__module__ or ""
        name = type(current).__name__
        if module.startswith("sqlalchemy") and name in {"OperationalError", "InterfaceError"}:
            state = _sqlstate(current)
            if state is None or state in _CONNECTION_SQLSTATES:
                return True
        if module.startswith("pg8000") and name == "InterfaceError":
            return True
        if module.startswith("pg8000") and NO_WRITABLE_PRIMARY in str(current):
            return True
        if _sqlstate(current) in _CONNECTION_SQLSTATES:
            return True
        current = current.__cause__ or getattr(current, "orig", None) or current.__context__
    return False


def in_recovery(connection) -> bool:
    """True when the connected server is a standby in recovery (it refuses every write).

    One check for readiness (``api/routes/public/health.py``) and the metrics scrape
    (``eurogas_db_primary_writable``), so the two never disagree about a standby. A SQLAlchemy
    connection; any other database than PostgreSQL has no standby and answers False.
    """

    from sqlalchemy import text

    if connection.dialect.name != "postgresql":
        return False
    return bool(connection.execute(text("SELECT pg_is_in_recovery()")).scalar_one())


def is_read_only_error(exc: BaseException) -> bool:
    """A write refused because the server is a standby (``25006``): nothing was applied."""

    current: BaseException | None = exc
    for _ in range(4):
        if current is None:
            return False
        if _sqlstate(current) == READ_ONLY_SQLSTATE:
            return True
        current = getattr(current, "orig", None) or current.__cause__
    return False


@dataclass(frozen=True)
class WaitResult:
    ok: bool
    attempts: int
    waited_seconds: float
    last_error: str | None = None


def backoff_delays(
    *,
    initial: float = 0.5,
    maximum: float = 10.0,
    factor: float = 2.0,
    jitter: float = 0.2,
    rng: random.Random | None = None,
):
    """Exponential delays with +/- ``jitter`` (fraction), capped at ``maximum``; endless."""

    rng = rng or random.Random()
    delay = initial
    while True:
        spread = delay * jitter
        yield max(0.0, min(maximum, delay + rng.uniform(-spread, spread)))
        delay = min(maximum, delay * factor)


def startup_wait_seconds(environ: Mapping[str, str] | None = None, default: float | None = None):
    env = os.environ if environ is None else environ
    raw = (env.get(STARTUP_WAIT_ENV) or "").strip()
    fallback = DEFAULT_STARTUP_WAIT_SECONDS if default is None else default
    if not raw:
        return fallback
    try:
        return max(0.0, float(raw))
    except ValueError:
        return fallback


def wait_for_database(
    database_url: str | None = None,
    *,
    timeout_seconds: float,
    probe: Callable[[], None] | None = None,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
    delays=None,
    on_retry: Callable[[int, str, float], None] | None = None,
) -> WaitResult:
    """Probe the database until it answers or ``timeout_seconds`` pass (one probe at 0).

    ``probe`` defaults to ``SELECT 1`` on a fresh engine for ``database_url`` (disposed after
    each attempt, so a failover's new address is resolved again).
    """

    if probe is None:
        probe = _select_one_probe(database_url)
    delays = delays or backoff_delays()
    started = clock()
    attempts = 0
    last_error = None
    while True:
        attempts += 1
        try:
            probe()
            return WaitResult(True, attempts, round(clock() - started, 3))
        except Exception as exc:  # noqa: BLE001 - classified below
            if not is_connection_error(exc):
                raise
            last_error = exc.__class__.__name__
        elapsed = clock() - started
        if elapsed >= timeout_seconds:
            return WaitResult(False, attempts, round(elapsed, 3), last_error)
        delay = min(next(delays), max(0.0, timeout_seconds - elapsed))
        if on_retry is not None:
            on_retry(attempts, last_error or "", delay)
        sleep(delay)


def _select_one_probe(database_url: str | None) -> Callable[[], None]:
    def probe() -> None:
        from sqlalchemy import text

        from eurogas_nexus.db.session import get_engine

        # One connection, no pool: the connect bound, and a short socket bound for SELECT 1
        # so a peer that accepts and then hangs counts as one failed attempt (db/session.py).
        engine = get_engine(
            database_url,
            pool_pre_ping=False,
            one_off=True,
            statement_timeout=None,
            socket_timeout_seconds=10.0,
        )
        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1")).scalar_one()
        finally:
            engine.dispose()

    return probe


# --- failover hosts ---------------------------------------------------------------------


def failover_hosts(environ: Mapping[str, str] | None = None) -> list[tuple[str, int]]:
    """``EUROGAS_NEXUS_DB_FAILOVER_HOSTS`` as ``[(host, port)]`` (port 5432 by default)."""

    env = os.environ if environ is None else environ
    hosts = []
    for item in (env.get(FAILOVER_HOSTS_ENV) or "").split(","):
        item = item.strip()
        if not item:
            continue
        host, _, port = item.rpartition(":") if item.count(":") == 1 else (item, "", "")
        try:
            hosts.append((host or item, int(port) if port else 5432))
        except ValueError as exc:
            raise ValueError(f"{FAILOVER_HOSTS_ENV}: bad port in {item!r}") from exc
    return hosts


def install_primary_only_connect(engine, extra_hosts: list[tuple[str, int]]) -> None:
    """Make every new connection of ``engine`` land on a writable primary among its hosts.

    The URL's own host is tried first, then ``extra_hosts`` in order. A host that refuses the
    connection or is in recovery (a standby, or a fenced former primary) is skipped. When none
    is writable, the driver's own ``OperationalError`` is raised ("no writable primary"), which
    SQLAlchemy wraps like any failed connection: readiness and the request handlers answer
    ``503``.
    """

    from sqlalchemy import event

    url_host = engine.url.host or "localhost"
    url_port = engine.url.port or 5432
    candidates = [(url_host, url_port)]
    for host in extra_hosts:
        if host not in candidates:
            candidates.append(host)

    @event.listens_for(engine, "do_connect")
    def _connect_to_primary(dialect, conn_rec, cargs, cparams):  # noqa: ARG001
        failures = []
        for host, port in candidates:
            params = dict(cparams, host=host, port=port)
            try:
                connection = dialect.connect(*cargs, **params)
            except Exception as exc:  # noqa: BLE001 - try the next host
                failures.append(f"{host}:{port} {exc.__class__.__name__}")
                continue
            try:
                cursor = connection.cursor()
                cursor.execute("SELECT pg_is_in_recovery()")
                in_recovery = bool(cursor.fetchone()[0])
                cursor.close()
                if hasattr(connection, "commit"):
                    connection.commit()
            except Exception as exc:  # noqa: BLE001
                failures.append(f"{host}:{port} {exc.__class__.__name__}")
                _close_quietly(connection)
                continue
            if in_recovery:
                failures.append(f"{host}:{port} in_recovery")
                _close_quietly(connection)
                continue
            return connection
        dbapi = getattr(dialect, "loaded_dbapi", None) or dialect.dbapi
        raise dbapi.OperationalError(f"{NO_WRITABLE_PRIMARY}: " + "; ".join(failures))


def _close_quietly(connection) -> None:
    try:
        connection.close()
    except Exception:  # noqa: BLE001
        pass


def wait_for_database_at_startup(
    *,
    component: str,
    environ: Mapping[str, str] | None = None,
    emit: Callable[[str], None] = print,
    **overrides,
) -> WaitResult | None:
    """Wait up to ``EUROGAS_NEXUS_DB_STARTUP_WAIT_SECONDS`` for the database; report each try.

    Off (``None``) when the setting is 0, the default: a developer's process starts at once.
    The deployment stacks set it (60 s), so a stack started before its database, or during a
    failover, waits instead of failing. A process that is still not connected at the end
    starts anyway: readiness reports it unready and the next request or loop retries.
    """

    import json

    from eurogas_nexus.db.session import resolve_database_url

    timeout = startup_wait_seconds(environ)
    url = resolve_database_url(environ)
    if timeout <= 0 or not url:
        return None

    def on_retry(attempt: int, error: str, delay: float) -> None:
        emit(json.dumps({"event": "db.startup.retry", "component": component,
                         "attempt": attempt, "error_type": error,
                         "next_delay_seconds": round(delay, 2)}))

    result = wait_for_database(url, timeout_seconds=timeout, on_retry=on_retry, **overrides)
    emit(json.dumps({"event": "db.startup.ready" if result.ok else "db.startup.unavailable",
                     "component": component, "attempts": result.attempts,
                     "waited_seconds": result.waited_seconds,
                     "error_type": result.last_error}))
    return result
