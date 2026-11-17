"""Migration 0066: assumption sets, firm marks and valuation snapshots (CP-07)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect
from sqlalchemy.engine import Connection

VERSIONS = Path(__file__).resolve().parents[2] / "alembic" / "versions"
TABLES = {
    "assumption_sets",
    "assumption_set_versions",
    "assumption_values",
    "firm_marks",
    "valuation_snapshots",
    "valuation_snapshot_inputs",
}


def _module():
    spec = importlib.util.spec_from_file_location(
        "tests.migration_0066", VERSIONS / "0066_commercial_assumptions.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run(connection: Connection, step) -> None:
    module = _module()
    context = MigrationContext.configure(connection)
    with Operations.context(context):
        getattr(module, step)()


def test_chain() -> None:
    module = _module()
    assert module.revision == "0066_commercial_assumptions"
    assert module.down_revision == "0065_local_accounts"


def test_upgrade_creates_the_tables_and_downgrade_removes_only_them() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE keep_me (id INTEGER PRIMARY KEY)")
        _run(connection, "upgrade")
        assert TABLES <= set(inspect(connection).get_table_names())
        _run(connection, "downgrade")
        assert set(inspect(connection).get_table_names()) == {"keep_me"}
