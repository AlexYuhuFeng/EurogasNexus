"""Re-run-safety tests for the public-source ingestion script helpers."""

import importlib.util
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest

SCRIPT_PATH = (
    Path(__file__).resolve().parents[2] / "scripts" / "ops" / "ingest_public_sources.py"
)


def _load_script():
    spec = importlib.util.spec_from_file_location("ingest_public_sources", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _node_row() -> dict:
    return {
        "id": "entsog-be-zee",
        "name": "Zeebrugge",
        "node_type": "interconnection",
        "country": "BE",
        "lat": 51.34,
        "lon": 3.21,
        "capacity_boe_d": None,
        "source_system": "ENTSOG",
        "source_dataset": "connectionpoints",
        "source_reference": "entsog-connectionpoints",
        "source_record_id": "be-zee",
        "data_quality": "display_approximation",
        "metadata_json": {},
    }


def test_reference_replace_with_all_empty_payloads_raises_and_keeps_topology() -> None:
    script = _load_script()
    session = MagicMock()

    with pytest.raises(RuntimeError, match="existing topology was kept"):
        script._replace_reference_network(
            session,
            nodes=[],
            facilities=[],
            hubs=[],
            tso_access_points=[],
        )
    session.execute.assert_not_called()


def test_reference_replace_skips_empty_tables_and_reports_them() -> None:
    script = _load_script()
    session = MagicMock()

    summary = script._replace_reference_network(
        session,
        nodes=[_node_row()],
        facilities=[],
        hubs=[],
        tso_access_points=[],
    )

    assert summary["replaced"] == 1
    assert summary["skipped_tables"] == [
        "reference_facilities",
        "reference_market_hubs",
        "reference_tso_access_points",
    ]
    # one delete + one upsert for the non-empty node table
    assert session.execute.call_count == 2


def test_record_run_writes_run_row_and_audit_event() -> None:
    script = _load_script()
    session = MagicMock()

    script._record_run(
        session,
        "ECB",
        "succeeded",
        datetime(2026, 5, 29, 15, 0, tzinfo=UTC),
        12,
        "ecb-eurofxref-daily",
    )

    assert session.merge.call_count == 1
    run_record = session.merge.call_args.args[0]
    assert run_record.source_name == "ECB"
    assert run_record.status == "succeeded"
    assert "upserted" in run_record.notes
    # the audit helper appends one audit event
    assert session.add.call_count == 1
    audit_event = session.add.call_args.args[0]
    assert audit_event.event_type == "ingestion"
    assert audit_event.action == "public_source_ingest"
    assert audit_event.principal == "operator"
    assert audit_event.outcome == "succeeded"
