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


def _hub(point_key: str, name: str, code: str) -> dict:
    return {
        "id": f"hub-{point_key.lower()}", "name": name, "hub_code": code, "country": "FR",
        "description": f"ENTSOG trading point {name}", "source_system": "ENTSOG",
        "source_dataset": "connectionpoints", "source_reference": "entsog-connectionpoints",
        "source_record_id": point_key, "data_quality": "display_approximation",
        "metadata_json": {"point_key": point_key},
    }


def test_hub_codes_reconcile_by_identity_with_what_the_store_holds() -> None:
    """A complete live read names "PEG SUD" first and so derives ``PEG`` for it; the shipped
    bundle (a subset) gave ``PEG`` to the "PEG" point. Each id keeps the code it holds and a
    held code is never taken; nothing is invented and no other field changes."""

    from eurogas_nexus.ingestion.public_sources import reconcile_hub_codes

    live = [_hub("VTP-00009", "PEG SUD", "PEG"), _hub("VTP-00039", "PEG", "PEG-0039")]
    held = {"PEG": "hub-vtp-00039", "TTF": "hub-vtp-00002"}
    rows = reconcile_hub_codes(live, held)
    assert [(row["id"], row["hub_code"]) for row in rows] == [
        ("hub-vtp-00009", "PEG-0009"),
        ("hub-vtp-00039", "PEG"),
    ]
    assert {k: v for k, v in rows[0].items() if k != "hub_code"} == {
        k: v for k, v in live[0].items() if k != "hub_code"
    }
    # A store that took the live read first (the real store) keeps its codes unchanged.
    assert reconcile_hub_codes(live, {"PEG": "hub-vtp-00009", "PEG-0039": "hub-vtp-00039"}) == live
    # An empty store takes the derived codes as they are.
    assert reconcile_hub_codes(live, {}) == live


def test_live_reference_read_over_the_bundle_seeded_network_succeeds() -> None:
    """The demo store loads the bundle first; the ENTSOG reference read then upserted a hub
    code another id held and failed on ``reference_market_hubs_hub_code_key``."""

    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    import eurogas_nexus.db.models  # noqa: F401
    from eurogas_nexus.db.base import Base
    from eurogas_nexus.db.models import ReferenceMarketHub
    from eurogas_nexus.reference_data.network_bundle import seed_reference_bundle

    script = _load_script()
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        seed_reference_bundle(session)
        session.commit()
        bundle_codes = dict(session.query(ReferenceMarketHub.id, ReferenceMarketHub.hub_code))
        assert bundle_codes["hub-vtp-00039"] == "PEG"
        summary = script._replace_reference_network(
            session,
            nodes=[],
            facilities=[],
            hubs=[_hub("VTP-00009", "PEG SUD", "PEG"), _hub("VTP-00039", "PEG", "PEG-0039")],
            tso_access_points=[],
        )
        session.commit()
        codes = dict(session.query(ReferenceMarketHub.id, ReferenceMarketHub.hub_code))
    assert summary["replaced"] == 2
    assert codes["hub-vtp-00039"] == "PEG" and codes["hub-vtp-00009"] == "PEG-0009"
    assert len(set(codes.values())) == len(codes)
