"""Governed import contracts for market-positioning observations.

市场定位观测（屏幕订单/PnL 快照）的内部导入契约：批量导入前先做
entitlement、数量守恒与时间戳校验，任何一项不合法都拒绝写入
（fail-closed），并记录审计事件。
"""

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
    """Operator-supplied import batch for read-only observation records.

    Attributes:
        batch_id: Operator-supplied batch id (1-128 chars).
        source_reference: Provenance reference (1-256 chars).
        screen_orders: Screen order observations to import.
        pnl_snapshots: PnL snapshot observations to import.
        research_only: Must be True (read-only observations).
        human_review_required: Must be True.
    """

    batch_id: str = Field(min_length=1, max_length=128)
    source_reference: str = Field(min_length=1, max_length=256)
    screen_orders: list[ScreenOrderObservation] = Field(default_factory=list)
    pnl_snapshots: list[PortfolioPnlSnapshot] = Field(default_factory=list)
    research_only: bool = True
    human_review_required: bool = True


class MarketPositioningImportResult(BaseModel):
    """Result of an internal market-positioning observation import.

    Attributes:
        batch_id: Echoed batch id.
        status: Import status tag.
        screen_orders_imported: Imported order count.
        pnl_snapshots_imported: Imported snapshot count.
        ingestion_run_id: Owning ingestion run id.
        audit_event_id: Written audit event id.
        errors: Validation errors (empty on success).
        warnings: Non-blocking warnings.
        research_only / human_review_required: Always True.
    """

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
    """Return validation errors for a market-positioning import batch.

    批量导入前置校验：信封标记、非空、重复 id、逐条观测校验与
    entitlement 检查；错误按稳定编码返回，去重保序。

    Args:
        batch: The import batch to validate.
        entitled_pairs: Known-entitled ``(source_system, dataset)`` pairs
            (``"*"`` matches any dataset).

    Returns:
        Deduplicated validation error codes; empty when the batch is valid.
    """

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
    """Parse an ISO timestamp and normalize it to timezone-aware UTC.

    解析并规范化 ISO 时间戳（含 ``Z`` 后缀；naive 按 UTC 解释）。

    Args:
        value: ISO timestamp string.

    Returns:
        Aware UTC datetime.

    Raises:
        ValueError: When the value is not a valid ISO timestamp.
    """

    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _validate_screen_order(order: ScreenOrderObservation) -> list[str]:
    """Validate one screen order: flags, quantities, timestamps.

    单条屏幕订单校验：research/review 标记、数量非负、已成交≤总量、
    剩余≤总量、数量守恒（filled+remaining=quantity，容差 0.001）与时间戳。
    """

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
    """Validate one PnL snapshot: flags, quantity, timestamps.

    单条 PnL 快照校验：research/review 标记、数量非负与时间戳合法性。
    """

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
    """Timestamp parse errors for the given fields (stable codes)."""

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
    """Whether the (system, dataset) pair is entitled (dataset ``*`` wildcard).

    entitlement 判定：精确配对或数据集通配符 ``*`` 均视为已授权。
    """

    return (
        (source_system, source_dataset) in entitled_pairs
        or (source_system, "*") in entitled_pairs
    )
