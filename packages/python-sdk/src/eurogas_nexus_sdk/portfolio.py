"""SDK client for read-only /api/portfolio endpoints."""

from __future__ import annotations

from pydantic import BaseModel, Field

from eurogas_nexus_sdk import _http


class ScreenOrderObservation(BaseModel):
    """One read-only imported screen order observation.

    Attributes:
        order_observation_id: Identifier of the observation.
        provider_id: Identifier of the data provider.
        venue: Venue the order was placed on.
        account_label: Account label the order belongs to.
        external_order_id: Order identifier in the provider system.
        side: Order side (buy/sell).
        order_type: Order type (e.g. limit/market).
        hub: Hub the order refers to.
        product: Traded product of the order.
        contract_code: Contract code of the order.
        delivery_start_utc: UTC start of the delivery window.
        delivery_end_utc: UTC end of the delivery window.
        price: Order price.
        currency: ISO currency code of the price.
        unit: Pricing unit of the price.
        quantity_mwh: Ordered quantity in MWh.
        filled_quantity_mwh: Filled quantity in MWh.
        remaining_quantity_mwh: Remaining unfilled quantity in MWh.
        status: Lifecycle status of the order.
        observed_at_utc: UTC time the observation was captured.
        source_system: System that produced the observation.
        source_reference: Reference of the observation in the source system.
        linked_strategy_id: Strategy linked to this order, when any.
        linked_resource_id: Resource linked to this order, when any.
        research_only: True when the observation is research-only.
        human_review_required: True when the observation needs human review.
    """

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
    # 状态为字符串而非枚举：订单状态由上游系统定义并会扩展，
    # 枚举会让 SDK 在未知状态上校验失败，字符串保持向前兼容。
    status: str
    observed_at_utc: str
    source_system: str
    source_reference: str
    linked_strategy_id: str | None = None
    linked_resource_id: str | None = None
    research_only: bool = True
    human_review_required: bool = True


class PortfolioPnlSnapshot(BaseModel):
    """One indicative PnL snapshot of a portfolio resource.

    Attributes:
        pnl_snapshot_id: Identifier of the snapshot.
        portfolio_id: Identifier of the portfolio the snapshot belongs to.
        resource_id: Resource the snapshot covers; None for portfolio-level
            views.
        strategy_id: Strategy the snapshot is attributed to, when any.
        valuation_time_utc: UTC time the snapshot was valued at.
        realized_pnl_gbp: Realized PnL in GBP.
        unrealized_pnl_gbp: Unrealized PnL in GBP.
        indicative_pnl_gbp: Indicative (marked) PnL in GBP.
        cash_value_gbp: Cash value of the position in GBP.
        market_value_gbp: Market value of the position in GBP.
        quantity_mwh: Quantity covered by the snapshot in MWh.
        valuation_basis: Basis used for the valuation (e.g. mark-to-market).
        source_system: System that produced the snapshot.
        source_reference: Reference of the snapshot in the source system.
        warnings: Human-readable snapshot warnings.
        research_only: True when the snapshot is research-only.
        human_review_required: True when the snapshot needs human review.
    """

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
    """Live cockpit summary for one portfolio.

    Attributes:
        portfolio_id: Identifier of the portfolio.
        latest_valuation_time_utc: UTC time of the newest snapshot; None when
            no snapshot exists yet.
        total_realized_pnl_gbp: Total realized PnL in GBP.
        total_unrealized_pnl_gbp: Total unrealized PnL in GBP.
        total_indicative_pnl_gbp: Total indicative PnL in GBP.
        total_cash_value_gbp: Total cash value in GBP.
        open_order_count: Number of open screen orders.
        filled_order_count: Number of filled screen orders.
        warnings: Human-readable summary warnings.
        research_only: True when the summary is research-only.
        human_review_required: True when the summary needs human review.
    """

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


def _get(url: str) -> dict:
    """GET one portfolio endpoint and return the full response envelope."""

    response = _http.get(url, timeout=10)
    response.raise_for_status()
    # 不同端点的 data 形状不同（列表或单对象），解包放在各 fetch 函数内，
    # _get 只负责返回信封本身，不假设载荷形状。
    return response.json()


def fetch_screen_orders(base_url: str) -> list[ScreenOrderObservation]:
    """Fetch read-only imported screen order observations."""

    data = _get(f"{base_url.rstrip('/')}/api/portfolio/screen-orders")["data"]
    return [ScreenOrderObservation(**item) for item in data]


def fetch_pnl_snapshots(base_url: str) -> list[PortfolioPnlSnapshot]:
    """Fetch indicative portfolio PnL snapshots."""

    data = _get(f"{base_url.rstrip('/')}/api/portfolio/pnl-snapshots")["data"]
    return [PortfolioPnlSnapshot(**item) for item in data]


def fetch_live_summary(base_url: str) -> PortfolioLiveSummary:
    """Fetch cockpit portfolio summary from backend API."""

    data = _get(f"{base_url.rstrip('/')}/api/portfolio/live-summary")["data"]
    return PortfolioLiveSummary(**data)
