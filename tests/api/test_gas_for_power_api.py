"""GET /api/market/gas-for-power joins ENTSO-E power, hub closes, EUA and API2 by day."""

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.api.app import create_app
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import FxObservationRecord, MarketObservationRecord
from eurogas_nexus.db.models.power import PowerObservationRecord
from eurogas_nexus.db.repositories.identity import (
    create_identity_api_key,
    create_identity_principal,
)
from eurogas_nexus.ingestion.commodity_settlements import parse_settlements


def test_daily_view_computes_clean_spreads_from_entitled_inputs(tmp_path, monkeypatch):
    url = f"sqlite+pysqlite:///{(tmp_path / 'gfp.sqlite').as_posix()}"
    engine = create_engine(url, future=True)
    Base.metadata.create_all(engine)
    now = datetime.now(UTC)
    today = now.date()
    day_start = datetime.combine(today, datetime.min.time(), tzinfo=UTC)
    with Session(engine) as session:
        owner = create_identity_principal(
            session, name="gfp", display_name="GfP", role="ANALYST", data_scopes=["*"]
        )
        _, bearer = create_identity_api_key(
            session, owner.principal_id, display_name="g", scopes=["*"]
        )
        for hour in range(24):
            start = day_start + timedelta(hours=hour)
            for metric, value in (
                ("day_ahead_price", 100.0),
                ("load_actual", 60_000.0),
                ("wind_onshore_generation", 15_000.0),
                ("solar_generation", 5_000.0),
            ):
                session.add(
                    PowerObservationRecord(
                        observation_id=f"{metric}-{hour}",
                        zone="DE_LU",
                        metric=metric,
                        process_type=None,
                        period_start_utc=start,
                        period_end_utc=start + timedelta(hours=1),
                        value=value,
                        unit="MW",
                        source_system="ENTSOE",
                        source_reference="t",
                        published_at_utc=now,
                        ingested_at_utc=now,
                    )
                )
        session.add(
            MarketObservationRecord(
                observation_id="the-da",
                market_venue="EEX",
                product="THE day-ahead",
                price=30.0,
                unit="EUR/MWh",
                currency="EUR",
                period_start_utc=day_start + timedelta(days=1),
                period_end_utc=day_start + timedelta(days=2),
                observed_at_utc=day_start + timedelta(hours=17),
                source_system="EEX",
                source_reference="t",
                freshness="end_of_day",
                quality_score=1.0,
                research_only=True,
                metadata_json={"hub": "THE", "tenor": "day-ahead"},
            )
        )
        year = today.year % 100
        settlements = parse_settlements(
            "date,market,product,settlement\n"
            f"{today.isoformat()},EUA,Dec-{year:02d},70\n"
            f"{today.isoformat()},EUA,Dec-{year + 1:02d},73\n"
            f"{today.isoformat()},API2,Dec-{year:02d},100\n",
            source_system="ICE_ENDEX",
            source_reference="t",
        )
        for row in settlements.rows:
            session.add(MarketObservationRecord(**row))
        session.add(
            FxObservationRecord(
                observation_id="ecb-usd",
                pair="EURUSD",
                base_currency="EUR",
                quote_currency="USD",
                rate=1.25,
                rate_type="reference",
                value_date=today.isoformat(),
                observed_at_utc=now,
                source_system="ECB",
                source_reference="t",
                freshness="daily",
                research_only=True,
            )
        )
        session.commit()
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", url)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)

    response = TestClient(
        create_app(),
        headers={"X-Eurogas-Identity": bearer, "X-Eurogas-Api-Key": "test-public-api-token"},
    ).get("/api/market/gas-for-power?zone=DE_LU&days=2")
    assert response.status_code == 200, response.text
    (row,) = response.json()["data"]
    assert row["power_price"] == 100.0 and row["residual_load_mw"] == 40_000
    assert row["gas_hub"] == "THE" and row["gas_price"] == 30.0
    assert row["carbon_price"] == 70.0  # front December, not the next one
    # CSS = 100 - 30/0.5 - 70*0.184/0.5 = 14.24
    assert row["clean_spark_spread"] == 14.24
    # Coal 100 USD/t at 1.25 USD/EUR = 80 EUR/t = 11.465 EUR/MWh
    assert row["coal_price_per_mwh"] == round(80 / 6.978, 3)
    assert row["clean_dark_spread"] is not None and row["fuel_switch_gas_price"] is not None
    # Implied burn from residual load: 40 GW x 24 h / 0.5 = 1,920 GWh
    assert row["implied_gas_burn_gwh"] == 1920.0 and row["burn_basis"] == ["residual_load"]


def test_unknown_zone_is_refused(monkeypatch):
    response = TestClient(create_app(), headers={"X-Eurogas-Api-Key": "test-public-api-token"}).get(
        "/api/market/gas-for-power?zone=TTF"
    )
    assert response.status_code in (401, 403, 422)
