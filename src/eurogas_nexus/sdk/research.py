"""SDK client for /api/research (POST computation endpoints)."""

from pydantic import BaseModel, Field

from eurogas_nexus.sdk import _http


class RouteCostResult(BaseModel):
    """Cost of one route computed by the research endpoint.

    Attributes:
        route_name: Name of the route that was priced.
        total_cost_eur_mwh: Total route cost in EUR/MWh.
        total_cost_boe: Total route cost per barrel of oil equivalent.
        from_node_id: Reference-network id of the origin node.
        to_node_id: Reference-network id of the destination node.
        research_only: True when the payload is a research-only envelope.
        human_review_required: True when output needs human review before use.
        assumptions: Assumptions the computation relied on.
        warnings: Human-readable computation warnings.
    """

    route_name: str
    total_cost_eur_mwh: float
    total_cost_boe: float
    from_node_id: str
    to_node_id: str
    research_only: bool
    human_review_required: bool
    assumptions: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class NetbackResult(BaseModel):
    """Netback of one route between two markets.

    Attributes:
        route_name: Name of the route that was priced.
        from_market: Origin market of the route.
        to_market: Destination market of the route.
        market_price_eur_mwh: Reference market price at destination in EUR/MWh.
        route_cost_eur_mwh: Route cost in EUR/MWh.
        netback_eur_mwh: Netback in EUR/MWh (price minus cost).
        netback_local_mwh: Netback in the local market currency per MWh.
        research_only: True when the payload is a research-only envelope.
        human_review_required: True when output needs human review before use.
    """

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
    """Feasibility verdict for one route with blockers and conditions.

    Attributes:
        route_name: Name of the assessed route.
        status: Verdict of the feasibility assessment.
        blockers: Reasons the route is not feasible.
        conditions: Conditions under which the route becomes feasible.
        research_only: True when the payload is a research-only envelope.
        human_review_required: True when output needs human review before use.
    """

    route_name: str
    # 状态用字符串而非枚举：新状态由后端定义并会随业务演进增加，
    # 枚举会让 SDK 在未知状态上校验失败，字符串保持向前兼容。
    status: str
    blockers: list[str] = Field(default_factory=list)
    conditions: list[str] = Field(default_factory=list)
    research_only: bool
    human_review_required: bool


class AllocationResult(BaseModel):
    """Demand allocation across supply sources for one scenario.

    Attributes:
        scenario_name: Name of the allocation scenario.
        total_demand_boe_d: Total demand in barrels of oil equivalent per day.
        total_allocated_boe_d: Demand covered by the allocation per day.
        unallocated_boe_d: Demand left uncovered per day.
        research_only: True when the payload is a research-only envelope.
        human_review_required: True when output needs human review before use.
    """

    scenario_name: str = ""
    total_demand_boe_d: float
    total_allocated_boe_d: float
    unallocated_boe_d: float
    research_only: bool
    human_review_required: bool


class MonitoringResult(BaseModel):
    """Alert summary for one monitored entity.

    Attributes:
        entity_id: Identifier of the monitored entity.
        entity_name: Display name of the monitored entity.
        total_alerts: Total number of active alerts.
        alerts: Raw alert records.
        research_only: True when the payload is a research-only envelope.
        human_review_required: True when output needs human review before use.
    """

    entity_id: str
    entity_name: str
    total_alerts: int
    alerts: list[dict] = Field(default_factory=list)
    research_only: bool
    human_review_required: bool


class NowcastResult(BaseModel):
    """Weather-adjusted gas demand nowcast for one market.

    Attributes:
        market: Market the nowcast applies to.
        base_demand_boe_d: Demand before weather adjustment in boe per day.
        adjusted_demand_boe_d: Demand after weather adjustment in boe per day.
        hdd: Heating degree days used for the adjustment.
        cdd: Cooling degree days used for the adjustment.
        weather_adjustment_boe_d: Net weather effect in boe per day.
        research_only: True when the payload is a research-only envelope.
        human_review_required: True when output needs human review before use.
    """

    market: str
    base_demand_boe_d: float
    adjusted_demand_boe_d: float
    hdd: float
    cdd: float
    weather_adjustment_boe_d: float
    research_only: bool
    human_review_required: bool


class BacktestResult(BaseModel):
    """Performance summary of one strategy backtest.

    Attributes:
        strategy_name: Name of the backtested strategy.
        total_return_eur: Total return of the backtest in EUR.
        trade_count: Number of trades executed in the backtest.
        win_rate_pct: Percentage of winning trades.
        sharpe_ratio: Sharpe ratio of the backtest; None when not computable.
        research_only: True when the payload is a research-only envelope.
        human_review_required: True when output needs human review before use.
    """

    strategy_name: str
    total_return_eur: float
    trade_count: int
    win_rate_pct: float
    sharpe_ratio: float | None = None
    research_only: bool
    human_review_required: bool


class ShadowRunResult(BaseModel):
    """Outcome of one paper-trading shadow run.

    Attributes:
        strategy_name: Name of the strategy that was shadow-run.
        status: Run status (e.g. ``COMPLETED``/``FAILED``).
        signal_count: Number of signals generated by the run.
        paper_pnl_eur: Paper PnL accumulated in EUR.
        research_only: True when the payload is a research-only envelope.
        human_review_required: True when output needs human review before use.
    """

    strategy_name: str
    status: str
    signal_count: int
    paper_pnl_eur: float
    research_only: bool
    human_review_required: bool


def _post(url: str, json_body: dict) -> dict:
    """POST one research payload and return the full response envelope."""

    r = _http.post(url, json=json_body, timeout=15)
    r.raise_for_status()
    # 与其余 SDK 模块统一：返回完整信封，调用方按端点形状解包 data。
    return r.json()


def compute_route_cost(base_url: str, **kwargs) -> RouteCostResult:
    """Compute the cost of a route via the research endpoint.

    Args:
        base_url: Base URL of the backend server.
        **kwargs: Computation inputs forwarded to the research API.

    Returns:
        Computed route cost with assumptions and warnings.
    """

    return RouteCostResult(**_post(f"{base_url}/api/research/route-cost", kwargs)["data"])

def compute_netback(base_url: str, **kwargs) -> NetbackResult:
    """Compute the netback of one route between two markets.

    Args:
        base_url: Base URL of the backend server.
        **kwargs: Computation inputs forwarded to the research API.

    Returns:
        Netback with the reference market price and route cost.
    """

    return NetbackResult(**_post(f"{base_url}/api/research/netback", kwargs)["data"])

def compute_feasibility(base_url: str, **kwargs) -> FeasibilityResult:
    """Assess the feasibility of one route.

    Args:
        base_url: Base URL of the backend server.
        **kwargs: Computation inputs forwarded to the research API.

    Returns:
        Feasibility verdict with blockers and conditions.
    """

    return FeasibilityResult(**_post(f"{base_url}/api/research/feasibility", kwargs)["data"])

def compute_allocation(base_url: str, **kwargs) -> AllocationResult:
    """Allocate demand across supply sources for one scenario.

    Args:
        base_url: Base URL of the backend server.
        **kwargs: Scenario inputs forwarded to the research API.

    Returns:
        Allocation with allocated and unallocated demand.
    """

    return AllocationResult(**_post(f"{base_url}/api/research/allocation", kwargs)["data"])

def compute_monitoring(base_url: str, **kwargs) -> MonitoringResult:
    """Compute an alert summary for one monitored entity.

    Args:
        base_url: Base URL of the backend server.
        **kwargs: Entity inputs forwarded to the research API.

    Returns:
        Alert summary for the monitored entity.
    """

    return MonitoringResult(**_post(f"{base_url}/api/research/monitoring", kwargs)["data"])

def compute_nowcast(base_url: str, **kwargs) -> NowcastResult:
    """Compute a weather-adjusted demand nowcast for one market.

    Args:
        base_url: Base URL of the backend server.
        **kwargs: Market and weather inputs forwarded to the research API.

    Returns:
        Weather-adjusted demand nowcast.
    """

    return NowcastResult(**_post(f"{base_url}/api/research/nowcast", kwargs)["data"])

def compute_backtest(base_url: str, **kwargs) -> BacktestResult:
    """Backtest one strategy and return its performance summary.

    Args:
        base_url: Base URL of the backend server.
        **kwargs: Strategy and market inputs forwarded to the research API.

    Returns:
        Backtest performance summary.
    """

    return BacktestResult(**_post(f"{base_url}/api/research/backtest", kwargs)["data"])

def evaluate_shadow_run(base_url: str, **kwargs) -> ShadowRunResult:
    """Run one paper-trading shadow run for a strategy.

    Args:
        base_url: Base URL of the backend server.
        **kwargs: Strategy and run parameters forwarded to the research API.

    Returns:
        Shadow-run outcome with signal count and paper PnL.
    """

    return ShadowRunResult(**_post(f"{base_url}/api/research/shadow-run", kwargs)["data"])
