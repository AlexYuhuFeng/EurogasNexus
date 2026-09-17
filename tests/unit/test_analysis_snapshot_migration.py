"""Analysis Snapshot migration DDL round trip (SQLite, no PostgreSQL needed).

The migration is expand-only and non-destructive; these tests apply its real
``upgrade()``/``downgrade()`` against a throw-away SQLite database so the DDL is
executed rather than merely read, and assert that no pre-existing table is
touched.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text

ROOT = Path(__file__).resolve().parents[2]
MIGRATION_PATH = ROOT / "alembic" / "versions" / "0034_analysis_snapshots.py"

EXPECTED_COLUMNS = {
    "snapshot_id",
    "schema_version",
    "as_of_utc",
    "gas_day",
    "gas_day_calendar",
    "time_basis",
    "created_at_utc",
    "created_by",
    "active_context_json",
    "market_data_versions_json",
    "network_capacity_version_json",
    "portfolio_version_json",
    "contract_resource_versions_json",
    "tariff_fx_json",
    "weather_demand_assumptions_json",
    "manual_assumptions_json",
    "model_calculation_versions_json",
    "entitlement_context_json",
    "field_availability_json",
    "source_refs",
    "warnings",
    "content_hash",
    "research_only",
    "human_review_required",
}


def _migration_module():
    spec = importlib.util.spec_from_file_location(
        "tests.analysis_snapshots_migration", MIGRATION_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _apply(connection, function_name: str) -> None:
    module = _migration_module()
    module.op = Operations(MigrationContext.configure(connection=connection))
    getattr(module, function_name)()


def test_upgrade_creates_the_descriptor_table_and_downgrade_removes_only_it() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    try:
        with engine.begin() as connection:
            # A pre-existing table standing in for an earlier revision's schema.
            connection.execute(text("CREATE TABLE ingestion_runs (run_id VARCHAR(64) PRIMARY KEY)"))
            before = set(inspect(connection).get_table_names())
            assert "analysis_snapshots" not in before

            _apply(connection, "upgrade")
            after = set(inspect(connection).get_table_names())
            assert after - before == {"analysis_snapshots"}
            assert before <= after

            columns = {
                column["name"]
                for column in inspect(connection).get_columns("analysis_snapshots")
            }
            assert columns == EXPECTED_COLUMNS

            indexes = {
                row["name"] for row in inspect(connection).get_indexes("analysis_snapshots")
            }
            assert indexes == {
                "ix_analysis_snapshots_created_at",
                "ix_analysis_snapshots_gas_day",
                "ix_analysis_snapshots_created_by",
            }

            _apply(connection, "downgrade")
            assert set(inspect(connection).get_table_names()) == before
    finally:
        engine.dispose()


def test_upgraded_schema_accepts_a_descriptor_row() -> None:
    from datetime import UTC, datetime

    from sqlalchemy.orm import Session

    from eurogas_nexus.db.base import Base
    from eurogas_nexus.db.models import AnalysisSnapshotRecord
    from eurogas_nexus.db.repositories.data_platform import get_analysis_snapshot

    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    try:
        Base.metadata.create_all(engine)
        with Session(engine) as session:
            session.add(
                AnalysisSnapshotRecord(
                    snapshot_id="asnap-test",
                    schema_version="analysis-snapshot.v1",
                    as_of_utc=datetime(2026, 1, 2, 10, 0, tzinfo=UTC),
                    gas_day="2026-01-02",
                    gas_day_calendar="EU-CAM-UTC-2025",
                    time_basis="gas_day",
                    created_at_utc=datetime(2026, 1, 2, 10, 1, tzinfo=UTC),
                    created_by="migration-test",
                    weather_demand_assumptions_json=None,
                    field_availability_json=[
                        {
                            "field": "weather_demand_assumptions",
                            "state": "unavailable",
                            "detail": "no producer",
                            "unavailable_reason": "WEATHER_SOURCE_NOT_CONFIGURED",
                        }
                    ],
                    content_hash="0" * 64,
                )
            )
            session.commit()

            payload = get_analysis_snapshot(session, "asnap-test")
        assert payload is not None
        assert payload["weather_demand_assumptions"] is None
        assert payload["field_availability"][0]["unavailable_reason"] == (
            "WEATHER_SOURCE_NOT_CONFIGURED"
        )
        assert payload["research_only"] is True
        assert payload["human_review_required"] is True
    finally:
        engine.dispose()
