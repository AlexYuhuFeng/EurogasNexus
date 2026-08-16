"""Backend-normalized market view API tests."""

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.api.app import create_app
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import FxObservationRecord, MarketObservationRecord


def test_normalized_market_view_empty_when_db_unconfigured(monkeypatch) -> None:
    monkeypatch.delenv("RUNTIME_STORE_DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)

    response = TestClient(create_app()).get("/api/market/normalized")

    assert response.status_code == 200
    body = response.json()
    assert body["data"] == []
    assert body["meta"]["source_references"] == ["runtime-db-not-configured"]
    assert body["meta"]["human_review_required"] is True


def test_normalized_market_view_converts_fx_and_reports_unconvertible(
    tmp_path,
    monkeypatch,
) -> None:
    db_path = tmp_path / "normalized.sqlite"
    database_url = f"sqlite+pysqlite:///{db_path.as_posix()}"
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(engine)
    observed_at = datetime(2026, 7, 1, 10, 15, tzinfo=UTC)
    with Session(engine) as session:
        session.add(
            FxObservationRecord(
                observation_id="ecb-fx-gbp",
                pair="EURGBP",
                base_currency="EUR",
                quote_currency="GBP",
                rate=0.85,
                rate_type="reference",
                value_date="2026-07-01",
                observed_at_utc=observed_at,
                source_system="ECB",
                source_reference="ecb-eurofxref-daily",
                source_record_id="2026-07-01-GBP",
                freshness="live",
                research_only=True,
            )
        )
        session.add(
            MarketObservationRecord(
                observation_id="market-gbp",
                market_venue="EEX",
                product="NBP day-ahead",
                price=33.0,
                unit="EUR/MWh",
                currency="EUR",
                period_start_utc=observed_at,
                period_end_utc=observed_at + timedelta(days=1),
                observed_at_utc=observed_at,
                source_system="EEX_Sim",
                source_reference="fixture:gbp",
                freshness="fresh",
                quality_score=1.0,
                research_only=True,
                metadata_json={"hub": "NBP", "tenor": "day-ahead"},
            )
        )
        session.add(
            MarketObservationRecord(
                observation_id="market-pln",
                market_venue="TGE",
                product="TGE day-ahead",
                price=200.0,
                unit="PLN/MWh",
                currency="PLN",
                period_start_utc=observed_at,
                period_end_utc=observed_at + timedelta(days=1),
                observed_at_utc=observed_at,
                source_system="TGE_Sim",
                source_reference="fixture:pln",
                freshness="fresh",
                quality_score=1.0,
                research_only=True,
                metadata_json={"hub": "TGE", "tenor": "day-ahead"},
            )
        )
        session.commit()
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", database_url)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)

    response = TestClient(create_app()).get("/api/market/normalized")

    assert response.status_code == 200
    body = response.json()
    assert body["meta"]["source_references"] == ["runtime-postgresql"]
    rows = {row["observation_id"]: row for row in body["data"]}

    gbp = rows["market-gbp"]
    assert gbp["hub"] == "NBP"
    assert gbp["tenor"] == "day-ahead"
    assert gbp["is_gas_price"] is True
    assert round(gbp["price_gbp_mwh"], 6) == round(33.0 * 0.85, 6)

    pln = rows["market-pln"]
    assert pln["is_gas_price"] is True
    assert pln["price_gbp_mwh"] is None
    assert any("PLN->GBP" in warning for warning in body["meta"]["warnings"])
