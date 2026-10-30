"""API tests for the trader desk conventions: products, price conversion, storage target."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.api.app import create_app
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import FxObservationRecord, StorageObservationRecord


@pytest.fixture
def no_db(monkeypatch):
    for name in ("RUNTIME_STORE_DATABASE_URL", "DATABASE_URL", "EUROGAS_NEXUS_DB_DSN"):
        monkeypatch.delenv(name, raising=False)
    return TestClient(create_app())


@pytest.fixture
def runtime_db(tmp_path, monkeypatch):
    database_url = f"sqlite+pysqlite:///{(tmp_path / 'desk.sqlite').as_posix()}"
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(engine)
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", database_url)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)
    return engine


def _fx(pair: str, quote: str, rate: float) -> FxObservationRecord:
    return FxObservationRecord(
        observation_id=f"ecb-{pair}",
        pair=pair,
        base_currency="EUR",
        quote_currency=quote,
        rate=rate,
        rate_type="reference",
        value_date="2026-10-29",
        observed_at_utc=datetime(2026, 10, 29, 15, tzinfo=UTC),
        source_system="ECB",
        source_reference="ecb-eurofxref-daily",
        source_record_id=pair,
        freshness="live",
        research_only=True,
        metadata_json={},
    )


def _storage(code: str, day: datetime, inventory: float) -> StorageObservationRecord:
    return StorageObservationRecord(
        observation_id=f"gie-agsi-{code}-{day.date().isoformat()}",
        source_dataset="AGSI",
        facility_id=code,
        facility_name=code,
        country=code,
        inventory_twh=inventory,
        working_capacity_twh=1000.0,
        fill_pct=inventory / 10,
        injection_twh_d=3.0,
        withdrawal_twh_d=0.5,
        period_start_utc=day,
        period_end_utc=day + timedelta(days=1),
        observed_at_utc=day + timedelta(days=1, hours=13),
        source_system="GIE",
        source_reference="gie-agsi-api",
        source_record_id=code,
        freshness="live",
        research_only=True,
        metadata_json={},
    )


def test_products_strip_and_explicit_codes(no_db):
    strip = no_db.get("/api/market/products", params={"trade_date": "2026-10-30"})
    assert strip.status_code == 200
    body = strip.json()["data"]
    assert body["trade_date"] == "2026-10-30"
    codes = {item["code"]: item for item in body["products"]}
    assert codes["DA"]["first_gas_day"] == "2026-11-02"
    assert codes["M+1"]["label"] == "Nov-26"
    assert codes["S+1"]["label"] == "Sum-27"

    explicit = no_db.get(
        "/api/market/products",
        params=[("trade_date", "2026-10-30"), ("code", "Win-26"), ("code", "Cal-27")],
    )
    labels = [item["label"] for item in explicit.json()["data"]["products"]]
    assert labels == ["Win-26", "Cal-27"]
    assert explicit.json()["data"]["products"][0]["hours"] == 182 * 24 + 1 - 1


def test_products_refuse_unknown_code(no_db):
    response = no_db.get("/api/market/products", params={"code": "Q9-27"})
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "unknown_product_code"


def test_price_conversion_with_explicit_fx_and_without_db(no_db):
    response = no_db.get(
        "/api/market/price-conversion",
        params={"value": 35, "from_unit": "EUR/MWh", "gbp_per_eur": 0.85, "usd_per_eur": 1.1},
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["converted"]["GBp/th"] == pytest.approx(87.1889, rel=1e-5)
    assert data["converted"]["USD/MMBtu"] == pytest.approx(11.2833, rel=1e-4)
    assert data["fx"]["GBP"]["source"] == "request"

    partial = no_db.get(
        "/api/market/price-conversion", params={"value": 35, "from_unit": "EUR/MWh"}
    )
    assert partial.status_code == 200
    assert partial.json()["data"]["converted"]["GBp/th"] is None
    assert partial.json()["data"]["converted"]["EUR/GJ"] == pytest.approx(35 / 3.6)
    assert partial.json()["meta"]["warnings"]

    refused = no_db.get(
        "/api/market/price-conversion",
        params={"value": 35, "from_unit": "EUR/MWh", "to_unit": "GBp/th"},
    )
    assert refused.status_code == 422
    assert refused.json()["detail"]["code"] == "fx_rate_unavailable"


def test_price_conversion_uses_latest_ecb_rates(runtime_db):
    with Session(runtime_db) as session:
        session.add_all([_fx("EURGBP", "GBP", 0.85), _fx("EURUSD", "USD", 1.1)])
        session.commit()
    response = TestClient(create_app()).get(
        "/api/market/price-conversion",
        params={"value": 87.1889, "from_unit": "p/th", "to_unit": "EUR/MWh"},
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["from_unit"] == "GBp/th"
    assert data["converted"]["EUR/MWh"] == pytest.approx(35, rel=1e-5)
    assert data["fx"]["GBP"]["source"] == "ECB"


def test_storage_trajectory_from_runtime_rows(runtime_db):
    start = datetime(2026, 8, 1, 4, tzinfo=UTC)
    with Session(runtime_db) as session:
        session.add_all(
            [_storage("EU", start + timedelta(days=i), 700.0 + 2.5 * i) for i in range(8)]
        )
        session.commit()
    client = TestClient(create_app())
    response = client.get("/api/storage/target-trajectory", params={"code": "eu"})
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["code"] == "EU"
    assert data["as_of_gas_day"] == "2026-08-08"
    assert data["recent_net_injection_twh_d"] == pytest.approx(2.5)
    assert data["status"] == "on_track"
    assert data["deadline"] == "2026-12-01"

    missing = client.get("/api/storage/target-trajectory", params={"code": "DE"})
    assert missing.status_code == 404
    assert missing.json()["detail"]["code"] == "storage_series_unavailable"


def test_storage_trajectory_without_db_is_empty_with_warning(no_db):
    response = no_db.get("/api/storage/target-trajectory")
    assert response.status_code == 200
    assert response.json()["data"] is None
    assert response.json()["meta"]["warnings"]
