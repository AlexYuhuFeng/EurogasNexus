"""SDK client for /api/research (POST computation endpoints)."""

import httpx
from pydantic import BaseModel


class RouteCostResult(BaseModel):
    route_name: str
    total_cost_eur_mwh: float
    total_cost_boe: float
    from_node_id: str
    to_node_id: str
    research_only: bool
    human_review_required: bool
    assumptions: list[str] = []
    warnings: list[str] = []


class NetbackResult(BaseModel):
    route_name: str
    from_market: str
    to_market: str
    market_price_eur_mwh: float
    route_cost_eur_mwh: float
    netback_eur_mwh: float
    netback_local_mwh: float
    research_only: bool
    human_review_required: bool


class FeasibilityResult(BaseModel):
    route_name: str
    status: str
    blockers: list[str] = []
    conditions: list[str] = []
    research_only: bool
    human_review_required: bool


class AllocationResult(BaseModel):
    scenario_name: str = ""
    total_demand_boe_d: float
    total_allocated_boe_d: float
    unallocated_boe_d: float
    research_only: bool
    human_review_required: bool


class MonitoringResult(BaseModel):
    entity_id: str
    entity_name: str
    total_alerts: int
    alerts: list[dict] = []
    research_only: bool
    human_review_required: bool


class NowcastResult(BaseModel):
    market: str
    base_demand_boe_d: float
    adjusted_demand_boe_d: float
    hdd: float
    cdd: float
    weather_adjustment_boe_d: float
    research_only: bool
    human_review_required: bool


class BacktestResult(BaseModel):
    strategy_name: str
    total_return_eur: float
    trade_count: int
    win_rate_pct: float
    sharpe_ratio: float | None = None
    research_only: bool
    human_review_required: bool


class ShadowRunResult(BaseModel):
    strategy_name: str
    status: str
    signal_count: int
    paper_pnl_eur: float
    research_only: bool
    human_review_required: bool


def _post(url: str, json_body: dict) -> dict:
    r = httpx.post(url, json=json_body, timeout=15)
    r.raise_for_status()
    return r.json()["data"]


def compute_route_cost(base_url: str, **kwargs) -> RouteCostResult:
    return RouteCostResult(**_post(f"{base_url}/api/research/route-cost", kwargs))

def compute_netback(base_url: str, **kwargs) -> NetbackResult:
    return NetbackResult(**_post(f"{base_url}/api/research/netback", kwargs))

def compute_feasibility(base_url: str, **kwargs) -> FeasibilityResult:
    return FeasibilityResult(**_post(f"{base_url}/api/research/feasibility", kwargs))

def compute_allocation(base_url: str, **kwargs) -> AllocationResult:
    return AllocationResult(**_post(f"{base_url}/api/research/allocation", kwargs))

def compute_monitoring(base_url: str, **kwargs) -> MonitoringResult:
    return MonitoringResult(**_post(f"{base_url}/api/research/monitoring", kwargs))

def compute_nowcast(base_url: str, **kwargs) -> NowcastResult:
    return NowcastResult(**_post(f"{base_url}/api/research/nowcast", kwargs))

def compute_backtest(base_url: str, **kwargs) -> BacktestResult:
    return BacktestResult(**_post(f"{base_url}/api/research/backtest", kwargs))

def evaluate_shadow_run(base_url: str, **kwargs) -> ShadowRunResult:
    return ShadowRunResult(**_post(f"{base_url}/api/research/shadow-run", kwargs))
