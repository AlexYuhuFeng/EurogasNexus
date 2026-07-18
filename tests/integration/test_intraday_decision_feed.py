"""DB-to-API integration tests for the intraday decision feed."""

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.api.app import create_app
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import (
    CompanyTsoAccessRecord,
    IntradayOpportunityRecord,
    MarketQuoteRecord,
    RouteCandidateRecord,
    TsoTariffRecord,
)
from eurogas_nexus.db.repositories.market_intelligence import (
    list_intraday_opportunities,
)
from eurogas_nexus.ingestion.simulated_market_prices import (
    upsert_simulated_market_observations,
)


def _seed_intraday_runtime(database_url: str, observed_at: datetime) -> dict:
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add_all(
            [
                TsoTariffRecord(
                    tariff_id="test-bbl-forward-annual",
                    document_id="test-bbl-public-tariff",
                    country="NL",
                    tso="BBL Company",
                    market_area="BBL",
                    gas_year="2025+",
                    point_id="bbl-forward-nl-gb",
                    source_point_name="BBL Forward Flow NL to GB",
                    direction="EXIT",
                    capacity_product="ANNUAL",
                    firmness="FIRM",
                    tariff_value=1.0,
                    currency="EUR",
                    unit="EUR/MWh",
                    effective_from=observed_at - timedelta(days=30),
                    effective_to=None,
                    tariff_status="FINAL",
                    source_table="test fixture based on public tariff shape",
                    source_page=None,
                    source_refs=["test://bbl/public-tariff"],
                    manual_review_required=False,
                    created_at_utc=observed_at,
                ),
                RouteCandidateRecord(
                    route_id="test-ttf-bbl-nbp",
                    route_name="TTF -> BBL -> NBP",
                    start_point_name="TTF",
                    target_point_name="NBP",
                    business_model="CROSS_BORDER_TRANSFER",
                    route_legs=[
                        {
                            "leg_id": "bbl-forward",
                            "country": "NL",
                            "tso": "BBL Company",
                            "market_area": "BBL",
                            "point_name": "BBL Forward Flow NL to GB",
                            "direction": "EXIT",
                            "component_type": "EXIT_CAPACITY",
                            "gas_year": "2025+",
                            "capacity_product": "ANNUAL",
                            "firmness": "FIRM",
                            "available_capacity_mwh_per_day": 500.0,
                        }
                    ],
                    required_entry_point_name=None,
                    required_exit_point_name=None,
                    required_tso_access=["BBL Company"],
                    source_systems=["test_route", "BBL"],
                    active=True,
                    created_at_utc=observed_at,
                ),
                CompanyTsoAccessRecord(
                    access_id="test-bbl-access",
                    tso="BBL Company",
                    market_area="BBL",
                    status="ACTIVE",
                    valid_from_utc=observed_at - timedelta(days=1),
                    valid_to_utc=None,
                    source_reference="test://company-access/bbl",
                    notes="Synthetic company configuration for integration testing.",
                    updated_at_utc=observed_at,
                ),
            ]
        )
        summary = upsert_simulated_market_observations(
            session,
            observed_at_utc=observed_at,
            source_systems=("EEX_Sim",),
        )
        session.commit()
    return summary


def test_simulated_ticks_persist_actionable_route_adjusted_opportunity(tmp_path) -> None:
    observed_at = datetime(2026, 7, 18, 9, 30, tzinfo=UTC)
    database_url = f"sqlite+pysqlite:///{(tmp_path / 'intraday.sqlite').as_posix()}"

    summary = _seed_intraday_runtime(database_url, observed_at)

    engine = create_engine(database_url, future=True)
    with Session(engine) as session:
        quotes = session.query(MarketQuoteRecord).all()
        opportunities = session.query(IntradayOpportunityRecord).all()
        current = list_intraday_opportunities(
            session,
            now_utc=observed_at + timedelta(seconds=5),
        )

    assert summary["quotes_upserted"] == len(quotes)
    assert summary["opportunity_scan"]["opportunities_persisted"] > 0
    candidate = next(
        row
        for row in current
        if row["route_id"] == "test-ttf-bbl-nbp"
        and row["product"] == "day-ahead"
        and row["buy_hub"] == "TTF"
        and row["sell_hub"] == "NBP"
    )
    assert opportunities
    assert candidate["status"] == "ACTIONABLE_REVIEW"
    assert candidate["buy_ask"] < candidate["sell_bid"]
    assert candidate["net_margin"] > 0
    assert candidate["route_cost"] == 1.0
    assert candidate["max_quantity_mwh"] <= 500.0
    assert candidate["simulated"] is True
    assert candidate["human_review_required"] is True


def test_opportunity_read_model_expires_without_new_backend_ticks(tmp_path) -> None:
    observed_at = datetime(2026, 7, 18, 9, 30, tzinfo=UTC)
    database_url = f"sqlite+pysqlite:///{(tmp_path / 'expired.sqlite').as_posix()}"
    _seed_intraday_runtime(database_url, observed_at)

    engine = create_engine(database_url, future=True)
    with Session(engine) as session:
        rows = list_intraday_opportunities(
            session,
            now_utc=observed_at + timedelta(minutes=2),
        )

    assert rows
    assert all(row["status"] == "EXPIRED" for row in rows)
    assert all("OPPORTUNITY_EXPIRED" in row["warnings"] for row in rows)


def test_market_quote_and_opportunity_api_read_runtime_database(
    tmp_path,
    monkeypatch,
) -> None:
    observed_at = datetime.now(UTC)
    database_url = f"sqlite+pysqlite:///{(tmp_path / 'api.sqlite').as_posix()}"
    _seed_intraday_runtime(database_url, observed_at)
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", database_url)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)
    client = TestClient(create_app())

    quote_response = client.get("/api/market/quotes", params={"hub": "TTF"})
    opportunity_response = client.get("/api/market/opportunities")
    spread_response = client.get("/api/market/spreads")

    assert quote_response.status_code == 200
    assert opportunity_response.status_code == 200
    assert spread_response.status_code == 200
    assert quote_response.json()["meta"]["source_references"] == [
        "runtime-postgresql"
    ]
    assert all(row["hub"] == "TTF" for row in quote_response.json()["data"])
    assert any(
        row["status"] == "ACTIONABLE_REVIEW"
        for row in opportunity_response.json()["data"]
    )
    assert spread_response.json()["data"]
