"""Alembic environment configuration for Eurogas Nexus."""

from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context
from eurogas_nexus.db.registry import get_metadata
from eurogas_nexus.db.session import resolve_database_url


def _get_context_config():
    try:
        return context.config
    except Exception:
        return None


config = _get_context_config()

if config is not None and config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = get_metadata()


def _configured_database_url() -> str:
    if config is None:
        raise RuntimeError("Alembic config is unavailable outside an Alembic runtime.")

    return resolve_database_url() or config.get_main_option("sqlalchemy.url")


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""

    url = _configured_database_url()
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""

    if config is None:
        raise RuntimeError("Alembic config is unavailable outside an Alembic runtime.")

    section = config.get_section(config.config_ini_section, {})
    section["sqlalchemy.url"] = _configured_database_url()

    connectable = engine_from_config(
        section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


def _run_migrations_when_invoked_by_alembic() -> None:
    if config is None:
        return

    try:
        offline_mode = context.is_offline_mode()
    except Exception:
        return

    if offline_mode:
        run_migrations_offline()
    else:
        run_migrations_online()


_run_migrations_when_invoked_by_alembic()
