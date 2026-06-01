"""Integration tests for governed market-positioning observation imports."""

from datetime import UTC, datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import (
    AuditEventRecord,
    EntitlementDecisionRecord,
    IngestionRunRecord,
    PortfolioPnlSnapshotRecord,
    ScreenOrderObservationRecord,
)
from eurogas_nexus.db.repositories.market_positioning_import import (
    upsert_market_positioning_import_batch,
)
from eurogas_nexus.domain.market_positioning_import import MarketPositioningImportBatch


def test_market_positioning_import_succeeds_with_entitlement(tmp_path) -> None:
    engine = create_engine(f"sqlite+pysqlite:///{(tmp_path / 'import.sqlite').as_posix()}")
    Base.metadata.create_all(engine)
    now = datetime(2026, 6, 1, 10, tzinfo=UTC)

    with Session(engine) as session:
        _grant(session, "ICE_OCM", "screen-orders", now)
        _grant(session, "INTERNAL_PNL", "portfolio-pnl", now)
        result = upsert_market_positioning_import_batch(
            session,
            _batch(),
            principal="ops-user",
            now=now,
        )

        assert result.status == "succeeded"
        assert result.screen_orders_imported == 1
        assert result.pnl_snapshots_imported == 1
        assert session.get(ScreenOrderObservationRecord, "order-import-001") is not None
        assert session.get(PortfolioPnlSnapshotRecord, "pnl-import-001") is not None
        assert session.get(IngestionRunRecord, result.ingestion_run_id).status == "succeeded"
        audit = session.get(AuditEventRecord, result.audit_event_id)
        assert audit.outcome == "succeeded"
        assert audit.principal == "ops-user"


def test_market_positioning_import_fails_closed_without_entitlement(tmp_path) -> None:
    engine = create_engine(f"sqlite+pysqlite:///{(tmp_path / 'denied.sqlite').as_posix()}")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        result = upsert_market_positioning_import_batch(
            session,
            _batch(),
            principal="ops-user",
            now=datetime(2026, 6, 1, 10, tzinfo=UTC),
        )

        assert result.status == "denied"
        assert result.screen_orders_imported == 0
        assert result.pnl_snapshots_imported == 0
        assert "ENTITLEMENT_MISSING:ICE_OCM:screen-orders" in result.errors
        assert "ENTITLEMENT_MISSING:INTERNAL_PNL:portfolio-pnl" in result.errors
        assert session.query(ScreenOrderObservationRecord).count() == 0
        assert session.query(PortfolioPnlSnapshotRecord).count() == 0
        assert session.get(IngestionRunRecord, result.ingestion_run_id).status == "failed"
        audit = session.get(AuditEventRecord, result.audit_event_id)
        assert audit.outcome == "denied"
        assert audit.severity == "error"


def _grant(session: Session, source_system: str, source_dataset: str, now: datetime) -> None:
    session.add(
        EntitlementDecisionRecord(
            decision_id=f"grant-{source_system}-{source_dataset}",
            source_system=source_system,
            source_dataset=source_dataset,
            granted=True,
            scope="internal-research",
            reason="Synthetic test entitlement.",
            evaluated_at_utc=now,
            human_review_required=True,
        )
    )
    session.commit()


def _batch() -> MarketPositioningImportBatch:
    return MarketPositioningImportBatch(
        batch_id="batch-import-001",
        source_reference="synthetic-import-batch",
        screen_orders=[
            {
                "order_observation_id": "order-import-001",
                "provider_id": "ICE_OCM",
                "venue": "ICE OCM",
                "account_label": "synthetic-account",
                "external_order_id": "synthetic-readonly-order",
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
                "source_reference": "synthetic:ice-ocm:order",
                "linked_strategy_id": "nbp-window",
                "linked_resource_id": "easington-resource",
                "research_only": True,
                "human_review_required": True,
            }
        ],
        pnl_snapshots=[
            {
                "pnl_snapshot_id": "pnl-import-001",
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
                "source_reference": "synthetic:portfolio:pnl",
                "warnings": ["Synthetic import fixture."],
                "research_only": True,
                "human_review_required": True,
            }
        ],
    )
