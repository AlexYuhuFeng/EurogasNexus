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
    # one upsert and one vanished-row scan for the non-empty node table; no delete
    assert session.execute.call_count == 2
    assert summary["retired"] == 0


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


def _gie_raw_payload() -> dict:
    return {
        "data": [
            {
                "code": "EU",
                "name": "EU",
                "gasDayStart": "2026-05-29",
                "gasDayEnd": "2026-05-30",
                "gasInStorage": "650.25",
                "workingGasVolume": "1100.50",
                "updatedAt": "2026-05-29 12:00:00",
            }
        ]
    }


def test_normalize_gie_page_attaches_page_lineage_and_receipt() -> None:
    from types import SimpleNamespace

    from eurogas_nexus.ingestion.gie_transport import GieProduct

    script = _load_script()
    receipt = datetime(2026, 10, 9, 22, 45, tzinfo=UTC)
    page = SimpleNamespace(
        raw_payload=_gie_raw_payload(),
        received_at_utc=receipt,
        page=1,
        size=300,
        last_page=193,
        total_on_page=1,
    )

    rows = script._normalize_gie_page(GieProduct.agsi(), page)

    assert len(rows) == 1
    assert rows[0]["observed_at_utc"] == receipt
    metadata = rows[0]["metadata_json"]
    assert metadata["source_page"] == 1
    assert metadata["source_page_size"] == 300
    assert metadata["provider_last_page"] == 193
    assert metadata["source_receipt_at_utc"] == receipt.isoformat()
    assert metadata["availability_basis"] == "response_receipt"


def _real_gie_row() -> dict:
    return {
        "observation_id": "gie-agsi-EU-2026-05-29",
        "source_system": "GIE",
        "metadata_json": {"availability_basis": "response_receipt"},
    }


def test_reject_synthetic_gie_rows_accepts_real_provider_rows() -> None:
    script = _load_script()

    script._reject_synthetic_gie_rows([_real_gie_row()], product="AGSI")


@pytest.mark.parametrize(
    "override",
    [
        {"observation_id": "mock-gie-agsi-EU-2026-05-29"},
        {"observation_id": "sim-gie-agsi-EU-2026-05-29"},
        {"source_system": "EEX_Sim"},
        {"metadata_json": {"simulated": True}},
        {"metadata_json": {"mock": True}},
    ],
)
def test_reject_synthetic_gie_rows_refuses_mock_sim_and_cross_source(
    override: dict,
) -> None:
    script = _load_script()

    with pytest.raises(RuntimeError):
        script._reject_synthetic_gie_rows(
            [{**_real_gie_row(), **override}], product="AGSI"
        )


def test_reference_refresh_is_skipped_only_after_a_recent_complete_read() -> None:
    from datetime import timedelta

    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from eurogas_nexus.db.models import IngestionRunRecord

    script = _load_script()
    engine = create_engine("sqlite://")
    IngestionRunRecord.__table__.create(engine)
    now = datetime(2026, 11, 13, 12, 0, tzinfo=UTC)

    def run(run_id, status, hours_ago):
        at = now - timedelta(hours=hours_ago)
        return IngestionRunRecord(
            run_id=run_id,
            source_name="ENTSOG-reference",
            status=status,
            started_at_utc=at,
            finished_at_utc=at,
        )

    with Session(engine) as session:
        assert script._recent_reference_refresh(session, 24, now=now) is None
        session.add_all([run("failed", "failed", 1), run("old", "succeeded", 30)])
        session.flush()
        # A failed (e.g. partial) read never defers the next one; an old one is due.
        assert script._recent_reference_refresh(session, 24, now=now) is None
        session.add(run("fresh", "SUCCEEDED_WITH_WARNINGS", 3))
        session.flush()
        refreshed = script._recent_reference_refresh(session, 24, now=now)
        assert refreshed is not None and refreshed.replace(tzinfo=UTC) == now - timedelta(hours=3)
        # Without a max age the reference is always read (operator runs).
        assert script._recent_reference_refresh(session, None, now=now) is None
        with pytest.raises(ValueError):
            script._recent_reference_refresh(session, 0, now=now)


def test_fresh_reference_is_reported_skipped_without_a_read() -> None:
    from types import SimpleNamespace

    script = _load_script()
    script._recent_reference_refresh = lambda session, hours, *, now: now
    report = {"sources": {}, "warnings": [], "failures": []}
    client = MagicMock()
    script._ingest_entsog_source(
        client,
        MagicMock(),
        route="entsog-reference",
        args=SimpleNamespace(entsog_reference_max_age_hours=24, entsog_point_direction=()),
        started=datetime(2026, 11, 13, tzinfo=UTC),
        report=report,
    )
    detail = report["sources"]["ENTSOG-reference"]
    assert detail["status"] == "skipped_fresh" and detail["records"] == 0
    assert detail["complete"] is None and not report["failures"]
    client.get.assert_not_called()
