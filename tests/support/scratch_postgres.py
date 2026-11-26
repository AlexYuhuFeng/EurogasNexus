"""A fresh database on a scratch PostgreSQL server, for tests that need PostgreSQL itself.

Opt-in and separate from the runtime store: set ``EUROGAS_NEXUS_SCRATCH_PG_URL`` to a server
the tests may create and drop databases on (a throwaway container), for example
``postgresql+pg8000://postgres:secret@127.0.0.1:55432/postgres``. Each use creates a database
with a random name and drops it afterwards. Never point it at a store that holds data.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy.engine import make_url

SCRATCH_PG_ENV = "EUROGAS_NEXUS_SCRATCH_PG_URL"


@contextmanager
def scratch_postgres_database(server_url: str, *, prefix: str = "scratch") -> Iterator[str]:
    from sqlalchemy import create_engine
    from sqlalchemy.pool import NullPool

    from eurogas_nexus.db.session import default_driver_url

    base = make_url(default_driver_url(server_url))
    name = f"{prefix}_{uuid.uuid4().hex[:12]}"
    # CREATE and DROP DATABASE refuse to run in a transaction: autocommit on every connection.
    admin = create_engine(
        base.set(database="postgres"), isolation_level="AUTOCOMMIT", poolclass=NullPool
    )
    try:
        with admin.connect() as connection:
            connection.exec_driver_sql(f'CREATE DATABASE "{name}"')
        yield base.set(database=name).render_as_string(hide_password=False)
    finally:
        with admin.connect() as connection:
            connection.exec_driver_sql(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        admin.dispose()
