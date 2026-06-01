"""Internal API tests for governed market-positioning imports."""

from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.api.app import create_app
from eurogas_nexus.core.config import Settings
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import (
    EntitlementDecisionRecord,
    PortfolioPnlSnapshotRecord,
    ScreenOrderObservationRecord,
)


def test_internal_profile_imports_market_positioning_observations(
    tmp_path,
    monkeypatch,
) -> None:
    db_path = tmp_path / "internal-import.sqlite"
    database_url = f"sqlite+pysqlite:///{db_path.as_posix()}"
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(engine)
    now = datetime(2026, 6, 1, 10, tzinfo=UTC)

    with Session(engine) as session:
        for source_system, source_dataset in (
            ("ICE_OCM", "screen-orders"),
            ("INTERNAL_PNL", "portfolio-pnl"),
        ):
            session.add(
                EntitlementDecisionRecord(
                    decision_id=f"grant-{source_system}-{source_dataset}",
                    source_system=source_system,
                    source_dataset=source_dataset,
                    granted=True,
                    scope="internal-research",
                    reason="Synthetic internal API test entitlement.",
                    evaluated_at_utc=now,
                    human_review_required=True,
                )
            )
        session.commit()

    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", database_url)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)

    client = TestClient(create_app(Settings(api_profile="internal")))
    response = client.post(
        "/api/internal/portfolio/import-observations",
        headers={"X-Eurogas-Principal": "ops-user"},
        json=_payload(),
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "succeeded"
    assert data["screen_orders_imported"] == 1
    assert data["pnl_snapshots_imported"] == 1
    with Session(engine) as session:
        assert session.get(ScreenOrderObservationRecord, "order-api-001") is not None
        assert session.get(PortfolioPnlSnapshotRecord, "pnl-api-001") is not None


def test_release_profile_does_not_expose_internal_import_route() -> None:
    client = TestClient(create_app(Settings(api_profile="release")))

    response = client.post("/api/internal/portfolio/import-observations", json=_payload())

    assert response.status_code == 404


def _payload() -> dict:
    return {
        "batch_id": "batch-api-001",
        "source_reference": "synthetic-api-import",
        "screen_orders": [
            {
                "order_observation_id": "order-api-001",
                "provider_id": "ICE_OCM",
                "venue": "ICE OCM",
                "account_label": "synthetic-account",
                "external_order_id": "synthetic-readonly-order-api",
                "side": "SELL",
                "order_type": "LIMIT",
                "hub": "NBP",
                "product": "Within-day",
                "contract_code": "NBP-WD-20260601",
                "delivery_start_utc": "2026-06-01T06:00:00Z",
                "delivery_end_utc": "2026-06-02T06:00:00Z",
                "price": 29.4,
                "currency": "GBP",
                "unit": "GBP/MWh",
                "quantity_mwh": 5000,
                "filled_quantity_mwh": 1500,
                "remaining_quantity_mwh": 3500,
                "status": "PARTIALLY_FILLED",
                "observed_at_utc": "2026-06-01T09:45:00Z",
                "source_system": "ICE_OCM",
                "source_reference": "synthetic:ice-ocm:api-order",
                "linked_strategy_id": "nbp-window",
                "linked_resource_id": "easington-resource",
                "research_only": True,
                "human_review_required": True,
            }
        ],
        "pnl_snapshots": [
            {
                "pnl_snapshot_id": "pnl-api-001",
                "portfolio_id": "uk-book",
                "resource_id": "easington-resource",
                "strategy_id": "nbp-window",
                "valuation_time_utc": "2026-06-01T09:45:00Z",
                "realized_pnl_gbp": 1200,
                "unrealized_pnl_gbp": 3300,
                "indicative_pnl_gbp": 4500,
                "cash_value_gbp": 900,
                "market_value_gbp": 147000,
                "quantity_mwh": 5000,
                "valuation_basis": "screen-import",
                "source_system": "INTERNAL_PNL",
                "source_reference": "synthetic:portfolio:api-pnl",
                "warnings": ["Synthetic import fixture."],
                "research_only": True,
                "human_review_required": True,
            }
        ],
    }
