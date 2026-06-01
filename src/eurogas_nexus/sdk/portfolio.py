"""SDK client for read-only /api/v1/portfolio endpoints."""

from __future__ import annotations

import httpx
from pydantic import BaseModel, Field


class ScreenOrderObservation(BaseModel):
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
    response = httpx.get(url, timeout=10)
    response.raise_for_status()
    return response.json()


def fetch_screen_orders(base_url: str) -> list[ScreenOrderObservation]:
    """Fetch read-only imported screen order observations."""

    data = _get(f"{base_url.rstrip('/')}/api/v1/portfolio/screen-orders")["data"]
    return [ScreenOrderObservation(**item) for item in data]


def fetch_pnl_snapshots(base_url: str) -> list[PortfolioPnlSnapshot]:
    """Fetch indicative portfolio PnL snapshots."""

    data = _get(f"{base_url.rstrip('/')}/api/v1/portfolio/pnl-snapshots")["data"]
    return [PortfolioPnlSnapshot(**item) for item in data]


def fetch_live_summary(base_url: str) -> PortfolioLiveSummary:
    """Fetch cockpit portfolio summary from backend API."""

    data = _get(f"{base_url.rstrip('/')}/api/v1/portfolio/live-summary")["data"]
    return PortfolioLiveSummary(**data)
