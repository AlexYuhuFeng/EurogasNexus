"""Migration 0062 DDL round trip on SQLite: expand-only, and a downgrade keeps history safe."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text

ROOT = Path(__file__).resolve().parents[2]
MIGRATION_PATH = ROOT / "alembic" / "versions" / "0062_observation_revisions.py"
TABLES = ("flow_observations", "capacity_observations", "storage_observations", "lng_observations")


def _apply(connection, function_name: str) -> None:
    spec = importlib.util.spec_from_file_location("tests.migration_0062", MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.op = Operations(MigrationContext.configure(connection=connection))
    getattr(module, function_name)()


def _schema(connection) -> None:
    for table in TABLES:
        connection.execute(
            text(
                f"CREATE TABLE {table} (observation_id VARCHAR(64) PRIMARY KEY, "
                "observed_at_utc TIMESTAMP)"
            )
        )
        connection.execute(text(f"INSERT INTO {table} VALUES ('kept', '2026-11-12 11:56:00')"))


def test_chain_and_head() -> None:
    from eurogas_nexus.release.constants import DB_SCHEMA_REVISION

    source = MIGRATION_PATH.read_text()
    assert 'down_revision = "0061_audit_keyset_index"' in source
    assert DB_SCHEMA_REVISION == "0062_observation_revisions"


def test_upgrade_adds_history_table_and_column_and_downgrade_reverses_it() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    try:
        with engine.begin() as connection:
            _schema(connection)
            _apply(connection, "upgrade")
            inspector = inspect(connection)
            assert "observation_revisions" in inspector.get_table_names()
            for table in TABLES:
                column = next(
                    c for c in inspector.get_columns(table) if c["name"] == "revised_at_utc"
                )
                assert column["nullable"] is True
                # Existing rows are untouched: no revision time is invented.
                assert connection.execute(
                    text(f"SELECT observation_id, revised_at_utc FROM {table}")
                ).all() == [("kept", None)]
            indexes = {i["name"] for i in inspector.get_indexes("observation_revisions")}
            assert {
                "ix_observation_revisions_observation",
                "ix_observation_revisions_recorded",
            } <= indexes

            _apply(connection, "downgrade")
            inspector = inspect(connection)
            assert "observation_revisions" not in inspector.get_table_names()
            for table in TABLES:
                assert "revised_at_utc" not in {c["name"] for c in inspector.get_columns(table)}
                assert connection.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar() == 1
    finally:
        engine.dispose()


def test_downgrade_refuses_to_discard_recorded_revisions() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    try:
        with engine.begin() as connection:
            _schema(connection)
            _apply(connection, "upgrade")
            connection.execute(
                text(
                    "INSERT INTO observation_revisions VALUES ('rev-1', 'flow_observations', "
                    "'kept', 'ENTSOG', 'value_changed', '[]', '{}', '2026-11-12 11:56:00', "
                    "'2026-11-13 14:00:00', 'a', 'b', '2026-11-13 14:00:00')"
                )
            )
            with pytest.raises(RuntimeError, match="superseded values"):
                _apply(connection, "downgrade")
            assert "observation_revisions" in inspect(connection).get_table_names()
    finally:
        engine.dispose()
