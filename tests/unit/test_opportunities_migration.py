"""Migration 0067: the opportunity store (CP-08)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect
from sqlalchemy.engine import Connection

VERSIONS = Path(__file__).resolve().parents[2] / "alembic" / "versions"
TABLES = {
    "opportunities",
    "opportunity_versions",
    "opportunity_legs",
    "opportunity_checks",
    "opportunity_dependencies",
    "opportunity_user_states",
    "opportunity_evaluations",
    "opportunity_settings",
}


def _module():
    spec = importlib.util.spec_from_file_location(
        "tests.migration_0067", VERSIONS / "0067_opportunities.py"
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
    assert module.revision == "0067_opportunities"
    assert module.down_revision == "0066_commercial_assumptions"


def test_upgrade_creates_the_tables_and_downgrade_removes_only_them() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE keep_me (id INTEGER PRIMARY KEY)")
        _run(connection, "upgrade")
        assert TABLES <= set(inspect(connection).get_table_names())
        _run(connection, "downgrade")
        assert set(inspect(connection).get_table_names()) == {"keep_me"}
