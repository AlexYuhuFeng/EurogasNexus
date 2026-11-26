"""Alembic environment configuration for Eurogas Nexus."""

from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context
from eurogas_nexus.db.connection_url import pg8000_ssl_arguments
from eurogas_nexus.db.registry import get_metadata
from eurogas_nexus.db.session import resolve_database_url


def _get_context_config():
    try:
        return context.config
    except Exception:
        return None


config = _get_context_config()

# The gated upgrade (scripts/ops/upgrade_database.py) runs Alembic in-process with its own
# logging; fileConfig would replace it (and disable the loggers that exist).
if (
    config is not None
    and config.config_file_name is not None
    and config.attributes.get("configure_logger", True)
):
    fileConfig(config.config_file_name)

target_metadata = get_metadata()


def _configured_database_url() -> str:
    if config is None:
        raise RuntimeError("Alembic config is unavailable outside an Alembic runtime.")

    from eurogas_nexus.db.session import default_driver_url

    url = resolve_database_url() or config.get_main_option("sqlalchemy.url")
    # ``postgresql://`` means the runtime's driver (pg8000), as for the server's engine.
    return default_driver_url(url) if url else url


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
    # A libpq ``sslmode`` becomes pg8000's ``ssl_context``; without one nothing changes.
    url, ssl_arguments = pg8000_ssl_arguments(_configured_database_url())
    section["sqlalchemy.url"] = url.render_as_string(hide_password=False)

    connectable = engine_from_config(
        section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        **({"connect_args": ssl_arguments} if ssl_arguments else {}),
    )

    with connectable.connect() as connection:
        if connection.dialect.name == "postgresql":
            # A migration waits at most lock_timeout for a lock (then fails and rolls back,
            # instead of queueing every reader and writer behind it) and runs each statement
            # at most statement_timeout (docs/operations/DATABASE_UPGRADE.md).
            from eurogas_nexus.db.migration_rules import migration_timeouts

            lock_timeout, statement_timeout = migration_timeouts(config.attributes)
            connection.exec_driver_sql(f"SET lock_timeout = '{lock_timeout}'")
            connection.exec_driver_sql(f"SET statement_timeout = '{statement_timeout}'")
            connection.commit()
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
