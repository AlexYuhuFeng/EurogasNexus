"""Read-only market positioning DTOs for screen orders and portfolio PnL."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ScreenOrderObservation(BaseModel):
    """Imported external screen/broker order state for decision support only."""

    order_observation_id: str
    provider_id: str
    venue: str
    account_label: str
    external_order_id: str
    side: str
    order_type: str
    hub: str
    product: str
    contract_code: str
    delivery_start_utc: str
    delivery_end_utc: str
    price: float
    currency: str
    unit: str
    quantity_mwh: float
    filled_quantity_mwh: float
    remaining_quantity_mwh: float
    status: str
    observed_at_utc: str
    source_system: str
    source_reference: str
    linked_strategy_id: str | None = None
    linked_resource_id: str | None = None
    research_only: bool = True
    human_review_required: bool = True


class PortfolioPnlSnapshot(BaseModel):
    """Indicative PnL valuation snapshot for a portfolio/resource/strategy."""

    pnl_snapshot_id: str
    portfolio_id: str
    resource_id: str | None = None
    strategy_id: str | None = None
    valuation_time_utc: str
    realized_pnl_gbp: float
    unrealized_pnl_gbp: float
    indicative_pnl_gbp: float
    cash_value_gbp: float
    market_value_gbp: float
    quantity_mwh: float
    valuation_basis: str
    source_system: str
    source_reference: str
    warnings: list[str] = Field(default_factory=list)
    research_only: bool = True
    human_review_required: bool = True


WARNING_VALUATION_EVIDENCE_MISSING = "VALUATION_EVIDENCE_MISSING"
"""Summary warning code for a portfolio read with no valuation evidence.

Emitted under the "never fabricate evidence" rule: an aggregate that was never
measured must be reported as unknown, not as a measured zero.
"""


class PortfolioLiveSummary(BaseModel):
    """Aggregated live portfolio posture for cockpit display.

    Why zero and unknown are different here
    ---------------------------------------
    Audit item ``UX01-EXPOSURE-001`` (``docs/ux/UI_DEBT_REGISTER.md``) exists
    because ``GBP 0`` summary metrics render next to unavailable rows and read
    as a *measured* zero. A portfolio that was deliberately valued at 0.0 and a
    portfolio that was never valued at all are different facts about the world,
    so the four valuation aggregates below are ``float | None``:

    * ``None`` - no valuation evidence was available to aggregate (empty
      snapshot list, or a degraded/unconfigured runtime read). The aggregate is
      unknown; callers MUST render Unknown/Missing, never ``0``.
    * ``0.0`` - real snapshot rows were aggregated and their true total is zero.

    Substituting ``0.0`` for ``None`` fabricates evidence, so no consumer may
    coerce a missing total with ``or 0`` / ``default=0``. Lineage stays visible
    through ``latest_valuation_time_utc`` (``None`` when nothing was valued),
    ``portfolio_id`` (``"unknown-portfolio"`` on an empty read) and
    ``warnings`` (``VALUATION_EVIDENCE_MISSING`` plus any source warnings).
    """

    portfolio_id: str
    latest_valuation_time_utc: str | None
    total_realized_pnl_gbp: float | None
    total_unrealized_pnl_gbp: float | None
    total_indicative_pnl_gbp: float | None
    total_cash_value_gbp: float | None
    open_order_count: int
    filled_order_count: int
    warnings: list[str] = Field(default_factory=list)
    research_only: bool = True
    human_review_required: bool = True


def summarize_portfolio(
    orders: list[ScreenOrderObservation],
    snapshots: list[PortfolioPnlSnapshot],
) -> PortfolioLiveSummary:
    """Aggregate order and PnL observations into a cockpit summary.

    汇总订单与 PnL 观测为驾驶舱展示摘要。

    Order counts are always measurable (an empty order list really does contain
    zero open and zero filled orders). The four GBP valuation aggregates are
    measurable only when at least one valuation snapshot exists: with no
    evidence they are returned as ``None`` (unknown) instead of ``sum([])``'s
    ``0``, which would render as a false "measured zero" (UX01-EXPOSURE-001).
    A populated portfolio whose true total is ``0.0`` still reports ``0.0``.

    Args:
        orders: Screen/broker order observations to count by status.
        snapshots: PnL valuation snapshots to aggregate.

    Returns:
        A PortfolioLiveSummary with the latest valuation time, summed PnL
        components (``None`` when no snapshot evidence exists), open/filled
        order counts (by status) and de-duplicated warnings. Empty or
        evidence-free inputs yield an explicit unknown summary carrying
        ``VALUATION_EVIDENCE_MISSING`` and ``latest_valuation_time_utc=None``.
    """

    # Empty input is unknown, not zero: there is no valuation evidence to
    # aggregate, so every GBP aggregate stays None and the unknown is declared
    # in warnings instead of being silently coerced to a measured 0.
    has_valuation_evidence = bool(snapshots)
    latest = max((snapshot.valuation_time_utc for snapshot in snapshots), default=None)
    portfolio_id = snapshots[0].portfolio_id if snapshots else "unknown-portfolio"
    open_statuses = {"WORKING", "PARTIALLY_FILLED", "PENDING", "LIVE"}
    filled_statuses = {"FILLED", "DONE"}
    warnings: list[str] = []
    for snapshot in snapshots:
        warnings.extend(snapshot.warnings)
    if not has_valuation_evidence:
        warnings.append(WARNING_VALUATION_EVIDENCE_MISSING)
    return PortfolioLiveSummary(
        portfolio_id=portfolio_id,
        latest_valuation_time_utc=latest,
        total_realized_pnl_gbp=(
            sum(snapshot.realized_pnl_gbp for snapshot in snapshots)
            if has_valuation_evidence
            else None
        ),
        total_unrealized_pnl_gbp=(
            sum(snapshot.unrealized_pnl_gbp for snapshot in snapshots)
            if has_valuation_evidence
            else None
        ),
        total_indicative_pnl_gbp=(
            sum(snapshot.indicative_pnl_gbp for snapshot in snapshots)
            if has_valuation_evidence
            else None
        ),
        total_cash_value_gbp=(
            sum(snapshot.cash_value_gbp for snapshot in snapshots)
            if has_valuation_evidence
            else None
        ),
        open_order_count=sum(1 for order in orders if order.status.upper() in open_statuses),
        filled_order_count=sum(1 for order in orders if order.status.upper() in filled_statuses),
        warnings=list(dict.fromkeys(warnings)),
    )
