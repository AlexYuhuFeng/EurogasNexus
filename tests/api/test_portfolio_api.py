"""Portfolio, screen order, and PnL observation API tests."""

from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.api.app import create_app
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import PortfolioPnlSnapshotRecord, ScreenOrderObservationRecord


def test_portfolio_screen_orders_fallback_is_read_only_decision_support(monkeypatch) -> None:
    monkeypatch.delenv("RUNTIME_STORE_DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)

    response = TestClient(create_app()).get("/api/v1/portfolio/screen-orders")

    assert response.status_code == 200
    body = response.json()
    assert body["meta"]["research_only"] is True
    assert body["meta"]["human_review_required"] is True
    assert body["meta"]["source_references"] == ["synthetic-fixture"]
    assert body["data"][0]["venue"] == "ICE OCM"
    assert body["data"][0]["research_only"] is True


def test_portfolio_live_summary_uses_runtime_db_when_configured(tmp_path, monkeypatch) -> None:
    database_url = f"sqlite+pysqlite:///{(tmp_path / 'portfolio.sqlite').as_posix()}"
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(engine)
    now = datetime(2026, 6, 1, 8, 30, tzinfo=UTC)
    with Session(engine) as session:
        session.add(
            ScreenOrderObservationRecord(
                order_observation_id="ord-obs-1",
                provider_id="ICE_OCM",
                venue="ICE OCM",
                account_label="demo-screen",
                external_order_id="demo-001",
                side="SELL",
                order_type="LIMIT",
                hub="NBP",
                product="Within-day",
                contract_code="NBP-WD-20260601",
                delivery_start_utc=now,
                delivery_end_utc=now,
                price=28.4,
                currency="GBP",
                unit="GBP/MWh",
                quantity_mwh=5000,
                filled_quantity_mwh=2500,
                remaining_quantity_mwh=2500,
                status="PARTIALLY_FILLED",
                observed_at_utc=now,
                source_system="fixture-runtime",
                source_reference="fixture:order",
                linked_strategy_id="sap-icis-ocm",
                linked_resource_id="easington-year",
                research_only=True,
                human_review_required=True,
            )
        )
        session.add(
            PortfolioPnlSnapshotRecord(
                pnl_snapshot_id="pnl-1",
                portfolio_id="portfolio-demo",
                resource_id="easington-year",
                strategy_id="sap-icis-ocm",
                valuation_time_utc=now,
                realized_pnl_gbp=1200,
                unrealized_pnl_gbp=4200,
                indicative_pnl_gbp=5400,
                cash_value_gbp=1800,
                market_value_gbp=142000,
                quantity_mwh=10000,
                valuation_basis="live-bid-mark",
                source_system="fixture-runtime",
                source_reference="fixture:pnl",
                warnings=["fixture valuation"],
                research_only=True,
                human_review_required=True,
            )
        )
        session.commit()
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", database_url)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)

    response = TestClient(create_app()).get("/api/v1/portfolio/live-summary")

    assert response.status_code == 200
    body = response.json()
    assert body["meta"]["source_references"] == ["runtime-postgresql"]
    assert body["data"]["portfolio_id"] == "portfolio-demo"
    assert body["data"]["open_order_count"] == 1
    assert body["data"]["total_indicative_pnl_gbp"] == 5400
    assert body["data"]["total_cash_value_gbp"] == 1800
