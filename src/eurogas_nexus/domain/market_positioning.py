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


class PortfolioLiveSummary(BaseModel):
    """Aggregated live portfolio posture for cockpit display."""

    portfolio_id: str
    latest_valuation_time_utc: str | None
    total_realized_pnl_gbp: float
    total_unrealized_pnl_gbp: float
    total_indicative_pnl_gbp: float
    total_cash_value_gbp: float
    open_order_count: int
    filled_order_count: int
    warnings: list[str] = Field(default_factory=list)
    research_only: bool = True
    human_review_required: bool = True


def summarize_portfolio(
    orders: list[ScreenOrderObservation],
    snapshots: list[PortfolioPnlSnapshot],
) -> PortfolioLiveSummary:
    """Aggregate order and PnL observations into a cockpit summary."""

    latest = max((snapshot.valuation_time_utc for snapshot in snapshots), default=None)
    portfolio_id = snapshots[0].portfolio_id if snapshots else "unknown-portfolio"
    open_statuses = {"WORKING", "PARTIALLY_FILLED", "PENDING", "LIVE"}
    filled_statuses = {"FILLED", "DONE"}
    warnings: list[str] = []
    for snapshot in snapshots:
        warnings.extend(snapshot.warnings)
    return PortfolioLiveSummary(
        portfolio_id=portfolio_id,
        latest_valuation_time_utc=latest,
        total_realized_pnl_gbp=sum(snapshot.realized_pnl_gbp for snapshot in snapshots),
        total_unrealized_pnl_gbp=sum(snapshot.unrealized_pnl_gbp for snapshot in snapshots),
        total_indicative_pnl_gbp=sum(snapshot.indicative_pnl_gbp for snapshot in snapshots),
        total_cash_value_gbp=sum(snapshot.cash_value_gbp for snapshot in snapshots),
        open_order_count=sum(1 for order in orders if order.status.upper() in open_statuses),
        filled_order_count=sum(1 for order in orders if order.status.upper() in filled_statuses),
        warnings=list(dict.fromkeys(warnings)),
    )
