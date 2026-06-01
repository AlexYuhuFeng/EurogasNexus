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


def demo_screen_order_observations() -> list[ScreenOrderObservation]:
    """Return synthetic external order observations for offline UI validation."""

    return [
        ScreenOrderObservation(
            order_observation_id="demo-ice-ocm-sell-001",
            provider_id="ICE_OCM",
            venue="ICE OCM",
            account_label="demo-screen",
            external_order_id="demo-readonly-001",
            side="SELL",
            order_type="LIMIT",
            hub="NBP",
            product="Within-day",
            contract_code="NBP-WD-20260601",
            delivery_start_utc="2026-06-01T06:00:00Z",
            delivery_end_utc="2026-06-02T06:00:00Z",
            price=28.4,
            currency="GBP",
            unit="GBP/MWh",
            quantity_mwh=5000,
            filled_quantity_mwh=2500,
            remaining_quantity_mwh=2500,
            status="PARTIALLY_FILLED",
            observed_at_utc="2026-06-01T08:30:00Z",
            source_system="synthetic-fixture",
            source_reference="fixture:ice-ocm-order-observation",
            linked_strategy_id="nbp-sap-icis-ocm-window",
            linked_resource_id="demo-easington-contract",
        ),
        ScreenOrderObservation(
            order_observation_id="demo-eex-da-sell-001",
            provider_id="EEX",
            venue="EEX",
            account_label="demo-screen",
            external_order_id="demo-readonly-002",
            side="SELL",
            order_type="LIMIT",
            hub="NBP",
            product="Day-ahead",
            contract_code="NBP-DA-20260602",
            delivery_start_utc="2026-06-02T06:00:00Z",
            delivery_end_utc="2026-06-03T06:00:00Z",
            price=27.95,
            currency="GBP",
            unit="GBP/MWh",
            quantity_mwh=5000,
            filled_quantity_mwh=0,
            remaining_quantity_mwh=5000,
            status="WORKING",
            observed_at_utc="2026-06-01T08:31:00Z",
            source_system="synthetic-fixture",
            source_reference="fixture:eex-order-observation",
            linked_strategy_id="nbp-sap-icis-ocm-window",
            linked_resource_id="demo-easington-contract",
        ),
    ]


def demo_pnl_snapshots() -> list[PortfolioPnlSnapshot]:
    """Return synthetic portfolio PnL snapshots for offline UI validation."""

    return [
        PortfolioPnlSnapshot(
            pnl_snapshot_id="demo-pnl-easington-001",
            portfolio_id="demo-uk-gas-book",
            resource_id="demo-easington-contract",
            strategy_id="nbp-sap-icis-ocm-window",
            valuation_time_utc="2026-06-01T08:30:00Z",
            realized_pnl_gbp=1250,
            unrealized_pnl_gbp=4150,
            indicative_pnl_gbp=5400,
            cash_value_gbp=1800,
            market_value_gbp=142000,
            quantity_mwh=10000,
            valuation_basis="live-bid-mark",
            source_system="synthetic-fixture",
            source_reference="fixture:portfolio-pnl",
            warnings=["Synthetic PnL snapshot. Replace with customer runtime imports."],
        )
    ]


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
