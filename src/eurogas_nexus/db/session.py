"""Lazy SQLAlchemy engine and session factory helpers."""

import os
import re
from collections.abc import Mapping
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session, sessionmaker

from eurogas_nexus.db.connection_url import pg8000_ssl_arguments

DB_URL_ENV_VARS = (
    "RUNTIME_STORE_DATABASE_URL",
    "DATABASE_URL",
    "EUROGAS_NEXUS_DB_DSN",
)


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

    engine = create_engine(parsed_url, **engine_options)
    if parsed_url.get_backend_name() == "postgresql":
        from eurogas_nexus.db.resilience import failover_hosts, install_primary_only_connect

        # A primary and its standby: each new connection lands on the writable one.
        extra_hosts = failover_hosts()
        if extra_hosts:
            install_primary_only_connect(engine, extra_hosts)
    if parsed_url.drivername.endswith("+pg8000"):
        from sqlalchemy import event

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


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
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
