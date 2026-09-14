"""Portfolio, screen order, and PnL observation API tests."""

from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.api.app import create_app
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import PortfolioPnlSnapshotRecord, ScreenOrderObservationRecord


def test_portfolio_screen_orders_without_db_reports_missing_runtime_data(monkeypatch) -> None:
    monkeypatch.delenv("RUNTIME_STORE_DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)

    response = TestClient(create_app()).get("/api/portfolio/screen-orders")

    assert response.status_code == 200
    body = response.json()
    assert body["meta"]["research_only"] is True
    assert body["meta"]["human_review_required"] is True
    assert body["meta"]["source_references"] == ["runtime-db-not-configured"]
    assert "RUNTIME_DB_NOT_CONFIGURED" in body["meta"]["warnings"]
    assert body["data"] == []


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
                linked_resource_id="ttf-bbl-portfolio",
                research_only=True,
                human_review_required=True,
            )
        )
        session.add(
            PortfolioPnlSnapshotRecord(
                pnl_snapshot_id="pnl-1",
                portfolio_id="portfolio-demo",
                resource_id="ttf-bbl-portfolio",
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

    response = TestClient(create_app()).get("/api/portfolio/live-summary")

    assert response.status_code == 200
    body = response.json()
    assert body["meta"]["source_references"] == ["runtime-postgresql"]
    assert body["data"]["portfolio_id"] == "portfolio-demo"
    assert body["data"]["open_order_count"] == 1
    assert body["data"]["total_indicative_pnl_gbp"] == 5400
    assert body["data"]["total_cash_value_gbp"] == 1800


def test_portfolio_live_summary_configured_but_empty_reports_unknown_not_zero(
    tmp_path, monkeypatch
) -> None:
    """An empty runtime read must be unknown, not a measured ``GBP 0``.

    UX01-EXPOSURE-001: the database is configured and reachable, but holds no
    valuation evidence, so the four totals are ``null`` (unknown) while
    ``runtime-postgresql`` lineage, ``latest_valuation_time_utc=None`` and the
    ``VALUATION_EVIDENCE_MISSING`` warning are preserved.
    """

    database_url = f"sqlite+pysqlite:///{(tmp_path / 'portfolio-empty.sqlite').as_posix()}"
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(engine)
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", database_url)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)

    response = TestClient(create_app()).get("/api/portfolio/live-summary")

    assert response.status_code == 200
    body = response.json()
    assert body["meta"]["source_references"] == ["runtime-postgresql"]
    assert body["meta"]["research_only"] is True
    assert body["meta"]["human_review_required"] is True
    assert "RUNTIME_DB_NOT_CONFIGURED" not in body["meta"]["warnings"]
    assert "VALUATION_EVIDENCE_MISSING" in body["meta"]["warnings"]
    data = body["data"]
    assert data["portfolio_id"] == "unknown-portfolio"
    assert data["latest_valuation_time_utc"] is None
    assert data["total_realized_pnl_gbp"] is None
    assert data["total_unrealized_pnl_gbp"] is None
    assert data["total_indicative_pnl_gbp"] is None
    assert data["total_cash_value_gbp"] is None
    assert data["total_indicative_pnl_gbp"] != 0
    assert "VALUATION_EVIDENCE_MISSING" in data["warnings"]
    assert data["open_order_count"] == 0
    assert data["filled_order_count"] == 0
    assert data["research_only"] is True
    assert data["human_review_required"] is True


def test_portfolio_live_summary_without_db_reports_unknown_totals(monkeypatch) -> None:
    """The unconfigured runtime read is unknown too, and keeps its own lineage."""

    monkeypatch.delenv("RUNTIME_STORE_DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)

    response = TestClient(create_app()).get("/api/portfolio/live-summary")

    assert response.status_code == 200
    body = response.json()
    assert body["meta"]["source_references"] == ["runtime-db-not-configured"]
    assert "RUNTIME_DB_NOT_CONFIGURED" in body["meta"]["warnings"]
    assert "VALUATION_EVIDENCE_MISSING" in body["meta"]["warnings"]
    data = body["data"]
    assert data["latest_valuation_time_utc"] is None
    assert data["total_indicative_pnl_gbp"] is None
    assert data["total_cash_value_gbp"] is None
    assert data["total_realized_pnl_gbp"] is None
    assert data["total_unrealized_pnl_gbp"] is None
