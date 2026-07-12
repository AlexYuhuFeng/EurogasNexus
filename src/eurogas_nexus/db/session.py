"""Lazy SQLAlchemy engine and session factory helpers."""

import os
import re
from collections.abc import Mapping

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session, sessionmaker

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
) -> Engine:
    """Create a SQLAlchemy engine lazily without opening a connection."""

    resolved_url = database_url.strip() if database_url else resolve_database_url()
    if not resolved_url:
        raise ValueError("Database URL is required to create an engine.")

    engine_options: dict[str, object] = {
        "echo": echo,
        "pool_pre_ping": pool_pre_ping,
        "future": True,
    }
    parsed_url = make_url(resolved_url)
    if parsed_url.get_backend_name() == "postgresql":
        bounded_timeout = max(1, int(connect_timeout_seconds))
        timeout_parameter = (
            "timeout" if parsed_url.drivername.endswith("+pg8000") else "connect_timeout"
        )
        engine_options["connect_args"] = {timeout_parameter: bounded_timeout}
        engine_options["pool_timeout"] = bounded_timeout

    return create_engine(resolved_url, **engine_options)


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Return a configured session factory."""

    return sessionmaker(bind=engine, autocommit=False, autoflush=False, class_=Session)


def get_session_factory(
    *,
    engine: Engine | None = None,
    database_url: str | None = None,
) -> sessionmaker[Session]:
    """Return a session factory for an explicit or resolved engine."""

    resolved_engine = engine or get_engine(database_url)
    return create_session_factory(resolved_engine)
