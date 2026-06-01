"""Repository helpers for governed market-positioning observation imports."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from eurogas_nexus.db.models import (
    AuditEventRecord,
    EntitlementDecisionRecord,
    IngestionRunRecord,
    PortfolioPnlSnapshotRecord,
    ScreenOrderObservationRecord,
)
from eurogas_nexus.domain.market_positioning import (
    PortfolioPnlSnapshot,
    ScreenOrderObservation,
)
from eurogas_nexus.domain.market_positioning_import import (
    MarketPositioningImportBatch,
    MarketPositioningImportResult,
    parse_utc,
    validate_market_positioning_import_batch,
)


def upsert_market_positioning_import_batch(
    session: Session,
    batch: MarketPositioningImportBatch,
    *,
    principal: str,
    now: datetime | None = None,
) -> MarketPositioningImportResult:
    """Validate and upsert imported screen-order/PnL observations.

    The whole batch is denied if any entitlement or validation check fails.
    Denied batches still write ingestion-run and audit records.
    """

    current_time = now or datetime.now(UTC)
    run_id = f"market-positioning-import-{uuid.uuid4().hex[:12]}"
    audit_event_id = f"audit-{uuid.uuid4().hex[:12]}"
    entitled_pairs = _load_entitled_pairs(session)
    errors = validate_market_positioning_import_batch(batch, entitled_pairs=entitled_pairs)

    if errors:
        _record_run_and_audit(
            session,
            batch=batch,
            run_id=run_id,
            audit_event_id=audit_event_id,
            principal=principal,
            now=current_time,
            status="failed",
            outcome="denied",
            severity="error",
            detail={"errors": errors},
            records_ingested=0,
        )
        session.commit()
        return MarketPositioningImportResult(
            batch_id=batch.batch_id,
            status="denied",
            ingestion_run_id=run_id,
            audit_event_id=audit_event_id,
            errors=errors,
            warnings=["No observation rows were written because the import failed validation."],
        )

    for order in batch.screen_orders:
        session.merge(_screen_order_record(order))
    for snapshot in batch.pnl_snapshots:
        session.merge(_pnl_snapshot_record(snapshot))

    records_ingested = len(batch.screen_orders) + len(batch.pnl_snapshots)
    _record_run_and_audit(
        session,
        batch=batch,
        run_id=run_id,
        audit_event_id=audit_event_id,
        principal=principal,
        now=current_time,
        status="succeeded",
        outcome="succeeded",
        severity="info",
        detail={
            "screen_orders_imported": len(batch.screen_orders),
            "pnl_snapshots_imported": len(batch.pnl_snapshots),
        },
        records_ingested=records_ingested,
    )
    session.commit()
    return MarketPositioningImportResult(
        batch_id=batch.batch_id,
        status="succeeded",
        screen_orders_imported=len(batch.screen_orders),
        pnl_snapshots_imported=len(batch.pnl_snapshots),
        ingestion_run_id=run_id,
        audit_event_id=audit_event_id,
    )


def _load_entitled_pairs(session: Session) -> set[tuple[str, str]]:
    rows = session.query(EntitlementDecisionRecord).filter(
        EntitlementDecisionRecord.granted.is_(True)
    )
    return {(row.source_system, row.source_dataset) for row in rows.all()}


def _record_run_and_audit(
    session: Session,
    *,
    batch: MarketPositioningImportBatch,
    run_id: str,
    audit_event_id: str,
    principal: str,
    now: datetime,
    status: str,
    outcome: str,
    severity: str,
    detail: dict,
    records_ingested: int,
) -> None:
    session.merge(
        IngestionRunRecord(
            run_id=run_id,
            source_name="market-positioning-import",
            status=status,
            started_at_utc=now,
            finished_at_utc=now,
            notes=json.dumps(
                {
                    "batch_id": batch.batch_id,
                    "source_reference": batch.source_reference,
                    "records_ingested": records_ingested,
                    **detail,
                },
                sort_keys=True,
            ),
        )
    )
    session.merge(
        AuditEventRecord(
            event_id=audit_event_id,
            event_type="market_positioning.import",
            severity=severity,
            principal=principal,
            action="import_observations",
            resource=batch.batch_id,
            outcome=outcome,
            detail=json.dumps(detail, sort_keys=True),
            event_ts_utc=now,
            source_system="market-positioning-import",
            human_review_required=True,
        )
    )


def _screen_order_record(order: ScreenOrderObservation) -> ScreenOrderObservationRecord:
    return ScreenOrderObservationRecord(
        order_observation_id=order.order_observation_id,
        provider_id=order.provider_id,
        venue=order.venue,
        account_label=order.account_label,
        external_order_id=order.external_order_id,
        side=order.side,
        order_type=order.order_type,
        hub=order.hub,
        product=order.product,
        contract_code=order.contract_code,
        delivery_start_utc=parse_utc(order.delivery_start_utc),
        delivery_end_utc=parse_utc(order.delivery_end_utc),
        price=order.price,
        currency=order.currency,
        unit=order.unit,
        quantity_mwh=order.quantity_mwh,
        filled_quantity_mwh=order.filled_quantity_mwh,
        remaining_quantity_mwh=order.remaining_quantity_mwh,
        status=order.status,
        observed_at_utc=parse_utc(order.observed_at_utc),
        source_system=order.source_system,
        source_reference=order.source_reference,
        linked_strategy_id=order.linked_strategy_id,
        linked_resource_id=order.linked_resource_id,
        research_only=True,
        human_review_required=True,
    )


def _pnl_snapshot_record(snapshot: PortfolioPnlSnapshot) -> PortfolioPnlSnapshotRecord:
    return PortfolioPnlSnapshotRecord(
        pnl_snapshot_id=snapshot.pnl_snapshot_id,
        portfolio_id=snapshot.portfolio_id,
        resource_id=snapshot.resource_id,
        strategy_id=snapshot.strategy_id,
        valuation_time_utc=parse_utc(snapshot.valuation_time_utc),
        realized_pnl_gbp=snapshot.realized_pnl_gbp,
        unrealized_pnl_gbp=snapshot.unrealized_pnl_gbp,
        indicative_pnl_gbp=snapshot.indicative_pnl_gbp,
        cash_value_gbp=snapshot.cash_value_gbp,
        market_value_gbp=snapshot.market_value_gbp,
        quantity_mwh=snapshot.quantity_mwh,
        valuation_basis=snapshot.valuation_basis,
        source_system=snapshot.source_system,
        source_reference=snapshot.source_reference,
        warnings=snapshot.warnings,
        research_only=True,
        human_review_required=True,
    )
