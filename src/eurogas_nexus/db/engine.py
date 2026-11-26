"""Lazy SQLAlchemy engine construction."""

from sqlalchemy import Engine

from eurogas_nexus.db.settings import DatabaseSettings


def create_db_engine(settings: DatabaseSettings) -> Engine:
    """Create an engine only when explicitly called."""

    if not settings.dsn:
        raise ValueError("Database DSN is required to create engine.")

    # The runtime's engine: the connect bound, keepalives and statement/socket timeouts of
    # db/session.py, not a driver default that waits forever (or cuts statements off).
    from eurogas_nexus.db.session import get_engine

    return get_engine(settings.dsn, echo=settings.echo, pool_pre_ping=settings.pool_pre_ping)
