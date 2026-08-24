"""R34A API tests for runtime storage/nomination composition."""

from __future__ import annotations

from datetime import UTC, datetime, time

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.api.app import create_app
from eurogas_nexus.core.config import Settings
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import (
    FxObservationRecord,
    MarketObservationRecord,
    NominationWindowMasterRecord,
    StorageFacilityMasterRecord,
    StorageInventoryObservationRecord,
)

GAS_DAY = "2026-01-01"


def _seed(session: Session) -> None:
    now = datetime(2026, 1, 1, 6, 0, tzinfo=UTC)
    session.add(
        StorageFacilityMasterRecord(
            facility_id="fac-runtime",
            name="Runtime Storage",
            market_hub="TTF",
            country="NL",
            minimum_inventory_mwh=0.0,
            maximum_inventory_mwh=200.0,
            maximum_injection_mwh=50.0,
            maximum_withdrawal_mwh=50.0,
            injection_efficiency=1.0,
            withdrawal_efficiency=1.0,
            injection_cost_gbp_mwh=0.0,
            withdrawal_cost_gbp_mwh=0.0,
            terminal_inventory_mwh=100.0,
            valid_from_utc=datetime(2025, 1, 1, tzinfo=UTC),
            valid_to_utc=None,
            source_system="operator",
            source_reference="test_fixture:not_customer_data",
            active=True,
            created_at_utc=now,
        )
    )
    session.add(
        StorageInventoryObservationRecord(
            observation_id="inv-runtime",
            facility_id="fac-runtime",
            inventory_mwh=100.0,
            observed_at_utc=now,
            period_start_utc=now,
            source_system="operator",
            source_reference="test_fixture:not_customer_data",
            research_only=True,
            human_review_required=True,
        )
    )
    for i, price in enumerate([30.0, 40.0]):
        session.add(
            MarketObservationRecord(
                observation_id=f"m-runtime-{i}",
                market_venue="EEX",
                product="TTF Day-Ahead",
                price=price,
                unit="EUR/MWh",
                currency="EUR",
                period_start_utc=now + __import__("datetime").timedelta(days=i),
                period_end_utc=now + __import__("datetime").timedelta(days=i + 1),
                observed_at_utc=now,
                source_system="EEX_Sim",
                source_reference="sim:test",
                source_record_id=f"sim-{i}",
                freshness="simulated_live",
                quality_score=0.9,
                research_only=True,
                metadata_json={"hub": "TTF", "tenor": "day-ahead"},
            )
        )
    session.add(
        FxObservationRecord(
            observation_id="fx-runtime",
            pair="EURGBP",
            base_currency="EUR",
            quote_currency="GBP",
            rate=0.85,
            rate_type="reference",
            value_date=GAS_DAY,
            observed_at_utc=now,
            source_system="ECB",
            source_reference="ecb:test",
            source_record_id="fx-runtime",
            freshness="live",
            research_only=True,
            metadata_json={},
        )
    )
    session.add(
        NominationWindowMasterRecord(
            window_id="w-runtime",
            name="Runtime Within-day",
            country="NL",
            opens_at=time(0, 0),
            closes_at=time(6, 0),
            maximum_change_mwh=10.0,
            maximum_change_pct=None,
            valid_from_utc=datetime(2025, 1, 1, tzinfo=UTC),
            valid_to_utc=None,
            source_system="operator",
            source_reference="test_fixture:not_customer_data",
            active=True,
            created_at_utc=now,
        )
    )
    session.commit()


def _configure(tmp_path, monkeypatch) -> str:
    db_path = tmp_path / "runtime-storage-nomination.sqlite"
    engine = create_engine(f"sqlite+pysqlite:///{db_path.as_posix()}", future=True)
    Base.metadata.create_all(engine)
    database_url = f"sqlite+pysqlite:///{db_path.as_posix()}"
    with Session(engine) as session:
        _seed(session)
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", database_url)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)
    return database_url


def test_storage_runtime_decision_uses_db_composition(tmp_path, monkeypatch) -> None:
    _configure(tmp_path, monkeypatch)
    client = TestClient(create_app(Settings(api_profile="development")))

    response = client.post(
        "/api/optimization/storage-dispatch",
        json={
            "decision_context": "RUNTIME_DECISION",
            "facility_id": "fac-runtime",
            "gas_day": GAS_DAY,
            "max_periods": 2,
            "inventory_step_mwh": 25,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["data"]["status"] == "optimal"
    assert payload["meta"]["decision_context"] == "RUNTIME_DECISION"
    assert payload["meta"]["lineage"]
    run_id = payload["meta"]["run_id"]
    assert run_id is not None

    evidence = client.get(f"/api/optimization/runs/{run_id}")
    assert evidence.status_code == 200
    snapshot = evidence.json()["data"]["input_snapshot"]
    assert snapshot["facility_id"] == "fac-runtime"
    assert snapshot["facility"]["initial_inventory_mwh"] == 100.0
    assert snapshot["periods"][0]["market_price_gbp_mwh"] == 25.5


def test_storage_runtime_decision_rejects_client_facility(tmp_path, monkeypatch) -> None:
    _configure(tmp_path, monkeypatch)
    client = TestClient(create_app(Settings(api_profile="development")))

    response = client.post(
        "/api/optimization/storage-dispatch",
        json={
            "decision_context": "RUNTIME_DECISION",
            "facility_id": "fac-runtime",
            "gas_day": GAS_DAY,
            "facility": {
                "initial_inventory_mwh": 10,
                "minimum_inventory_mwh": 0,
                "maximum_inventory_mwh": 20,
                "maximum_injection_mwh": 5,
                "maximum_withdrawal_mwh": 5,
            },
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "runtime_decision_client_input_forbidden"


def test_nomination_runtime_decision_uses_db_windows(tmp_path, monkeypatch) -> None:
    _configure(tmp_path, monkeypatch)
    client = TestClient(create_app(Settings(api_profile="development")))

    response = client.post(
        "/api/optimization/nomination-window",
        json={
            "decision_context": "RUNTIME_DECISION",
            "gas_day": GAS_DAY,
            "initial_quantity_mwh": 100,
            "instructions": [
                {
                    "submitted_at": "2026-01-01T01:00:00+00:00",
                    "requested_quantity_mwh": 115,
                }
            ],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["data"]["final_quantity_mwh"] == 110
    assert payload["data"]["decisions"][0]["reason"] == "RENOMINATION_CHANGE_LIMIT_APPLIED"
    assert payload["meta"]["lineage"] == ["nomination_window_master:w-runtime"]
    run_id = payload["meta"]["run_id"]
    assert run_id is not None


def test_nomination_runtime_decision_rejects_client_windows(tmp_path, monkeypatch) -> None:
    _configure(tmp_path, monkeypatch)
    client = TestClient(create_app(Settings(api_profile="development")))

    response = client.post(
        "/api/optimization/nomination-window",
        json={
            "decision_context": "RUNTIME_DECISION",
            "gas_day": GAS_DAY,
            "initial_quantity_mwh": 100,
            "windows": [
                {
                    "window_id": "w-client",
                    "opens_at": "00:00",
                    "closes_at": "06:00",
                }
            ],
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "runtime_decision_client_input_forbidden"


def test_runtime_storage_requires_db(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("RUNTIME_STORE_DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)
    client = TestClient(create_app(Settings(api_profile="development")))

    response = client.post(
        "/api/optimization/storage-dispatch",
        json={
            "decision_context": "RUNTIME_DECISION",
            "facility_id": "fac-runtime",
            "gas_day": GAS_DAY,
        },
    )

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "runtime_db_not_configured"
