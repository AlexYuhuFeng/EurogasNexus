"""Lazy SQLAlchemy engine construction."""

from sqlalchemy import Engine, create_engine

from eurogas_nexus.db.settings import DatabaseSettings


def create_db_engine(settings: DatabaseSettings) -> Engine:
    """Create an engine only when explicitly called."""

    if not settings.dsn:
        raise ValueError("Database DSN is required to create engine.")

    return create_engine(
        settings.dsn,
        echo=settings.echo,
        pool_pre_ping=settings.pool_pre_ping,
        future=True,
    )
