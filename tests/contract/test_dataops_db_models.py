"""CR-09 data-operations DB and migration contracts."""

from __future__ import annotations

from pathlib import Path

from eurogas_nexus.db.models import IngestionRunRecord
from eurogas_nexus.db.registry import get_metadata, list_required_tables

ROOT = Path(__file__).resolve().parents[2]


def test_data_operations_migration_chains_to_shadow_runtime() -> None:
    migration = ROOT / "alembic" / "versions" / "0028_data_operations_v1.py"
    text = migration.read_text(encoding="utf-8")

    assert migration.is_file()
    assert 'revision: str = "0028_data_operations_v1"' in text
    assert 'down_revision: str | None = "0027_shadow_runtime_v1"' in text
    for token in [
        '"source_runtime_states"',
        '"ingestion_run_issues"',
        '"data_operations_heartbeat"',
        '"trigger_type"',
        '"scheduled_for_utc"',
        '"error_category"',
        '"adapter_version"',
        '"lineage_refs"',
    ]:
        assert token in text


def test_data_operations_tables_are_metadata_and_required_registry() -> None:
    metadata = get_metadata()
    required = set(list_required_tables())

    for table in (
        "source_runtime_states",
        "ingestion_run_issues",
        "data_operations_heartbeat",
    ):
        assert table in metadata.tables
        assert table in required


def test_ingestion_run_model_has_structured_operational_columns() -> None:
    columns = {column.name for column in IngestionRunRecord.__table__.columns}

    assert {
        "source_id",
        "dataset",
        "trigger_type",
        "requested_at_utc",
        "scheduled_for_utc",
        "window_start_utc",
        "window_end_utc",
        "attempt_number",
        "rows_received",
        "rows_accepted",
        "rows_rejected",
        "rows_inserted",
        "rows_updated",
        "duplicate_count",
        "quality_warning_count",
        "quality_error_count",
        "error_category",
        "error_code",
        "correlation_id",
        "adapter_version",
        "retry_of_run_id",
        "fallback_used",
        "lineage_refs",
    }.issubset(columns)


def test_scheduled_ingestion_unique_index_is_declared() -> None:
    indexes = {index.name: index for index in IngestionRunRecord.__table__.indexes}

    assert "uq_ingestion_runs_scheduled_source" in indexes
    assert indexes["uq_ingestion_runs_scheduled_source"].unique is True
