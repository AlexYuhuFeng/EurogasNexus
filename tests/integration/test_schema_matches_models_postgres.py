"""The migrated PostgreSQL schema is at least as wide as the models say.

SQLite ignores VARCHAR lengths, so a model whose column grew without a migration passes
every SQLite test and fails in production (an ENTSOG run's status did exactly that). This
compares the models with a database migrated to head and fails on any string column that
the database holds narrower than the model, on missing tables and on missing columns.
"""

from __future__ import annotations

import os

import pytest
from sqlalchemy import String, create_engine, inspect

_POSTGRES_URL = os.environ.get("EUROGAS_NEXUS_TEST_POSTGRES_URL") or os.environ.get(
    "RUNTIME_STORE_DATABASE_URL", ""
)
pytestmark = pytest.mark.skipif(
    not _POSTGRES_URL.startswith("postgresql"),
    reason="Needs a PostgreSQL database migrated to head.",
)


def test_every_model_column_fits_the_migrated_schema():
    import eurogas_nexus.db.models  # noqa: F401 - registers every model
    from eurogas_nexus.db.base import Base

    inspector = inspect(create_engine(_POSTGRES_URL))
    tables = set(inspector.get_table_names())
    problems = []
    for table in Base.metadata.sorted_tables:
        if table.name not in tables:
            problems.append(f"{table.name}: table missing")
            continue
        columns = {column["name"]: column for column in inspector.get_columns(table.name)}
        for column in table.columns:
            stored = columns.get(column.name)
            if stored is None:
                problems.append(f"{table.name}.{column.name}: column missing")
                continue
            wanted = getattr(column.type, "length", None)
            held = getattr(stored["type"], "length", None)
            if isinstance(column.type, String) and wanted and held and held < wanted:
                problems.append(f"{table.name}.{column.name}: VARCHAR({held}) < model {wanted}")
    assert not problems, "\n".join(problems)
