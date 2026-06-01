"""Governed import contracts for market-positioning observations."""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, Field

from eurogas_nexus.domain.market_positioning import (
    PortfolioPnlSnapshot,
    ScreenOrderObservation,
)

SCREEN_ORDER_DATASET = "screen-orders"
PORTFOLIO_PNL_DATASET = "portfolio-pnl"


class MarketPositioningImportBatch(BaseModel):
    """Operator-supplied import batch for read-only observation records."""

    batch_id: str = Field(min_length=1, max_length=128)
    source_reference: str = Field(min_length=1, max_length=256)
    screen_orders: list[ScreenOrderObservation] = Field(default_factory=list)
    pnl_snapshots: list[PortfolioPnlSnapshot] = Field(default_factory=list)
    research_only: bool = True
    human_review_required: bool = True


class MarketPositioningImportResult(BaseModel):
    """Result of an internal market-positioning observation import."""

    batch_id: str
    status: str
    screen_orders_imported: int = 0
    pnl_snapshots_imported: int = 0
    ingestion_run_id: str
    audit_event_id: str
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    research_only: bool = True
    human_review_required: bool = True


def validate_market_positioning_import_batch(
    batch: MarketPositioningImportBatch,
    *,
    entitled_pairs: set[tuple[str, str]],
) -> list[str]:
    """Return validation errors for a market-positioning import batch."""

    errors: list[str] = []
    if not batch.research_only:
        errors.append("BATCH_RESEARCH_ONLY_MUST_BE_TRUE")
    if not batch.human_review_required:
        errors.append("BATCH_HUMAN_REVIEW_REQUIRED_MUST_BE_TRUE")
    if not batch.screen_orders and not batch.pnl_snapshots:
        errors.append("IMPORT_BATCH_EMPTY")

    order_ids: set[str] = set()
    for order in batch.screen_orders:
        if order.order_observation_id in order_ids:
            errors.append(f"DUPLICATE_SCREEN_ORDER_ID:{order.order_observation_id}")
        order_ids.add(order.order_observation_id)
        errors.extend(_validate_screen_order(order))
        if not _is_entitled(order.source_system, SCREEN_ORDER_DATASET, entitled_pairs):
            errors.append(f"ENTITLEMENT_MISSING:{order.source_system}:{SCREEN_ORDER_DATASET}")

    snapshot_ids: set[str] = set()
    for snapshot in batch.pnl_snapshots:
        if snapshot.pnl_snapshot_id in snapshot_ids:
            errors.append(f"DUPLICATE_PNL_SNAPSHOT_ID:{snapshot.pnl_snapshot_id}")
        snapshot_ids.add(snapshot.pnl_snapshot_id)
        errors.extend(_validate_pnl_snapshot(snapshot))
        if not _is_entitled(snapshot.source_system, PORTFOLIO_PNL_DATASET, entitled_pairs):
            errors.append(
                f"ENTITLEMENT_MISSING:{snapshot.source_system}:{PORTFOLIO_PNL_DATASET}"
            )

    return list(dict.fromkeys(errors))


def parse_utc(value: str) -> datetime:
    """Parse an ISO timestamp and normalize it to timezone-aware UTC."""

    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _validate_screen_order(order: ScreenOrderObservation) -> list[str]:
    errors: list[str] = []
    if not order.research_only:
        errors.append(f"SCREEN_ORDER_RESEARCH_ONLY_MUST_BE_TRUE:{order.order_observation_id}")
    if not order.human_review_required:
        errors.append(
            f"SCREEN_ORDER_HUMAN_REVIEW_REQUIRED_MUST_BE_TRUE:{order.order_observation_id}"
        )
    if order.quantity_mwh < 0 or order.filled_quantity_mwh < 0 or order.remaining_quantity_mwh < 0:
        errors.append(f"SCREEN_ORDER_NEGATIVE_QUANTITY:{order.order_observation_id}")
    if order.filled_quantity_mwh > order.quantity_mwh:
        errors.append(f"SCREEN_ORDER_FILLED_EXCEEDS_QUANTITY:{order.order_observation_id}")
    if order.remaining_quantity_mwh > order.quantity_mwh:
        errors.append(f"SCREEN_ORDER_REMAINING_EXCEEDS_QUANTITY:{order.order_observation_id}")
    if abs((order.filled_quantity_mwh + order.remaining_quantity_mwh) - order.quantity_mwh) > 0.001:
        errors.append(f"SCREEN_ORDER_QUANTITY_BALANCE_MISMATCH:{order.order_observation_id}")
    errors.extend(_timestamp_errors(order.order_observation_id, "SCREEN_ORDER", [
        order.delivery_start_utc,
        order.delivery_end_utc,
        order.observed_at_utc,
    ]))
    return errors


def _validate_pnl_snapshot(snapshot: PortfolioPnlSnapshot) -> list[str]:
    errors: list[str] = []
    if not snapshot.research_only:
        errors.append(f"PNL_SNAPSHOT_RESEARCH_ONLY_MUST_BE_TRUE:{snapshot.pnl_snapshot_id}")
    if not snapshot.human_review_required:
        errors.append(
            f"PNL_SNAPSHOT_HUMAN_REVIEW_REQUIRED_MUST_BE_TRUE:{snapshot.pnl_snapshot_id}"
        )
    if snapshot.quantity_mwh < 0:
        errors.append(f"PNL_SNAPSHOT_NEGATIVE_QUANTITY:{snapshot.pnl_snapshot_id}")
    errors.extend(
        _timestamp_errors(
            snapshot.pnl_snapshot_id,
            "PNL_SNAPSHOT",
            [snapshot.valuation_time_utc],
        )
    )
    return errors


def _timestamp_errors(record_id: str, prefix: str, values: list[str]) -> list[str]:
    errors: list[str] = []
    for value in values:
        try:
            parse_utc(value)
        except ValueError:
            errors.append(f"{prefix}_INVALID_TIMESTAMP:{record_id}:{value}")
    return errors


def _is_entitled(
    source_system: str,
    source_dataset: str,
    entitled_pairs: set[tuple[str, str]],
) -> bool:
    return (
        (source_system, source_dataset) in entitled_pairs
        or (source_system, "*") in entitled_pairs
    )
