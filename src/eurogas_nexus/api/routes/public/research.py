"""Research computation API routes — POST endpoints for all research workflows.

Research endpoints are explicit what-if sandboxes: client-supplied inputs are
allowed, and responses carry ``decision_context: SANDBOX_SCENARIO``. Requests
claiming RUNTIME_DECISION semantics are rejected (audit item 2).
"""

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from eurogas_nexus.api.dependencies.sandbox import (
    SANDBOX_SCENARIO,
    require_sandbox_scenario,
)
from eurogas_nexus.domain.research.allocation import (
    AllocationCandidate,
    AllocationInput,
    compute_allocation,
)
from eurogas_nexus.domain.research.backtest import (
    BacktestInput,
    compute_backtest,
)
from eurogas_nexus.domain.research.feasibility import (
    FeasibilityInput,
    check_feasibility,
)
from eurogas_nexus.domain.research.monitoring import (
    MonitoringInput,
    MonitoringThreshold,
    generate_alerts,
)
from eurogas_nexus.domain.research.netback import (
    NetbackInput,
    compute_netback,
)
from eurogas_nexus.domain.research.nowcast import (
    NowcastInput,
    compute_nowcast,
)
from eurogas_nexus.domain.research.route_cost import (
    CostComponent,
    RouteCostInput,
    compute_route_cost,
)
from eurogas_nexus.domain.research.shadow_run import (
    ShadowRunInput,
    ShadowSignal,
    evaluate_shadow_run,
)

router = APIRouter(
    prefix="/api/research",
    tags=["research"],
    dependencies=[Depends(require_sandbox_scenario)],
)


# --- Request schemas ---------------------------------------------------------

# 所有研究端点都是"假设沙箱"：请求体携带的完整假设仅用于推演，
# 响应统一打 SANDBOX_SCENARIO 标记（见 require_sandbox_scenario 依赖）。


class CostComponentRequest(BaseModel):
    """One cost component of a route-cost research request.

    Attributes:
        component_type: Component kind (e.g. ``tariff``).
        amount: Component amount.
        unit: Unit (e.g. ``EUR/MWh``).
        currency: ISO 4217 currency code.
        description: Free description.
    """

    component_type: str = "tariff"
    amount: float = 0.0
    unit: str = "EUR/MWh"
    currency: str = "EUR"
    description: str = ""


class RouteCostRequest(BaseModel):
    """Route-cost research request.

    Attributes:
        route_name: Route display name.
        from_node_id: Source node id.
        to_node_id: Target node id.
        components: Cost components.
        route_km: Route length in km, or None.
    """

    route_name: str = ""
    from_node_id: str = ""
    to_node_id: str = ""
    components: list[CostComponentRequest] = Field(default_factory=list)
    route_km: float | None = None


class NetbackRequest(BaseModel):
    """Netback research request.

    Attributes:
        route_name: Route display name.
        from_market: Source market.
        to_market: Target market.
        market_price_eur_mwh: Destination market price.
        route_cost_eur_mwh: Route cost.
        fx_rate: FX multiplier applied to the result.
        fx_pair: FX pair label.
    """

    route_name: str = ""
    from_market: str = ""
    to_market: str = ""
    market_price_eur_mwh: float = 0.0
    route_cost_eur_mwh: float = 0.0
    fx_rate: float = 1.0
    fx_pair: str = ""


class FeasibilityRequest(BaseModel):
    """Route-feasibility research request.

    Attributes:
        route_name: Route display name.
        from_node_id: Source node id.
        to_node_id: Target node id.
        capacity_available_mcm_d: Available capacity, mcm/d.
        required_capacity_mcm_d: Required capacity, mcm/d.
        route_eligible: Whether the route is eligible.
        contract_active: Whether the contract is active.
        constraints: Extra constraint tags.
    """

    route_name: str = ""
    from_node_id: str = ""
    to_node_id: str = ""
    capacity_available_mcm_d: float = 0.0
    required_capacity_mcm_d: float = 0.0
    route_eligible: bool = True
    contract_active: bool = True
    constraints: list[str] = Field(default_factory=list)


class AllocationCandidateRequest(BaseModel):
    """One allocation candidate in a research request.

    Attributes:
        candidate_id: Stable candidate id.
        route_name: Route display name.
        from_node_id: Source node id.
        to_node_id: Target node id.
        capacity_available_boe_d: Available capacity, boe/d.
        cost_eur_mwh: Cost per MWh.
        rank: Candidate rank.
        eligible: Whether the candidate is eligible.
    """

    candidate_id: str = ""
    route_name: str = ""
    from_node_id: str = ""
    to_node_id: str = ""
    capacity_available_boe_d: float = 0.0
    cost_eur_mwh: float = 0.0
    rank: int = 0
    eligible: bool = True


class AllocationRequest(BaseModel):
    """Allocation research request.

    Attributes:
        scenario_name: Scenario display name.
        total_demand_boe_d: Total demand, boe/d.
        candidates: Allocation candidates.
    """

    scenario_name: str = ""
    total_demand_boe_d: float = 0.0
    candidates: list[AllocationCandidateRequest] = Field(default_factory=list)


class MonitoringThresholdRequest(BaseModel):
    """One monitoring threshold in a research request.

    Attributes:
        field: Observation field to test.
        operator: Comparison operator (e.g. ``gt``).
        value: Threshold value.
        severity: Alert severity.
        message_template: Alert message template.
    """

    field: str = ""
    operator: str = "gt"
    value: float = 0.0
    severity: str = "warning"
    message_template: str = "{field} is {value} (threshold: {threshold})"


class MonitoringRequest(BaseModel):
    """Monitoring research request.

    Attributes:
        entity_id: Monitored entity id.
        entity_name: Monitored entity name.
        observations: Field -> value observations.
        thresholds: Threshold rules.
    """

    entity_id: str = ""
    entity_name: str = ""
    observations: dict[str, float] = Field(default_factory=dict)
    thresholds: list[MonitoringThresholdRequest] = Field(default_factory=list)


class NowcastRequest(BaseModel):
    """Demand-nowcast research request.

    Attributes:
        market: Market label.
        period_start_utc: Window start (ISO).
        period_end_utc: Window end (ISO).
        base_demand_boe_d: Base demand, boe/d.
        hdd: Heating degree days.
        cdd: Cooling degree days.
        hdd_sensitivity_boe_per_deg: HDD sensitivity.
        cdd_sensitivity_boe_per_deg: CDD sensitivity.
    """

    market: str = ""
    period_start_utc: str = ""
    period_end_utc: str = ""
    base_demand_boe_d: float = 0.0
    hdd: float = 0.0
    cdd: float = 0.0
    hdd_sensitivity_boe_per_deg: float = 150000.0
    cdd_sensitivity_boe_per_deg: float = 50000.0


class TradeRecordRequest(BaseModel):
    """One backtest trade record.

    Attributes:
        pnl_eur: Trade PnL in EUR.
        date: Trade date (ISO).
    """

    pnl_eur: float = 0.0
    date: str = ""


class BacktestRequest(BaseModel):
    """Backtest research request.

    Attributes:
        strategy_name: Strategy display name.
        start_utc: Backtest start (ISO).
        end_utc: Backtest end (ISO).
        trades: Trade records.
    """

    strategy_name: str = ""
    start_utc: str = ""
    end_utc: str = ""
    trades: list[TradeRecordRequest] = Field(default_factory=list)


class ShadowSignalRequest(BaseModel):
    """One shadow-run signal in a research request.

    Attributes:
        signal_id: Stable signal id.
        route_name: Route display name.
        action: Action tag (research-only).
        score: Signal score.
        note: Free note.
    """

    signal_id: str = ""
    route_name: str = ""
    action: str = "research_candidate"
    score: float = 0.0
    note: str = ""


class ShadowRunRequest(BaseModel):
    """Shadow-run research request.

    Attributes:
        strategy_name: Strategy display name.
        started_at_utc: Run start (ISO).
        signals: Shadow signals.
        paper_pnl_eur: Paper PnL in EUR.
    """

    strategy_name: str = ""
    started_at_utc: str = ""
    signals: list[ShadowSignalRequest] = Field(default_factory=list)
    paper_pnl_eur: float = 0.0


# --- Endpoints ---------------------------------------------------------------


@router.post("/route-cost")
def post_route_cost(body: RouteCostRequest, request: Request) -> dict:
    """Compute route cost from cost components."""
    input_ = RouteCostInput(
        route_name=body.route_name,
        from_node_id=body.from_node_id,
        to_node_id=body.to_node_id,
        components=[
            CostComponent(
                component_type=c.component_type,
                amount=c.amount,
                unit=c.unit,
                currency=c.currency,
                description=c.description,
            )
            for c in body.components
        ],
        route_km=body.route_km,
    )
    result = compute_route_cost(input_)
    return _envelope(result)


@router.post("/netback")
def post_netback(body: NetbackRequest, request: Request) -> dict:
    """Compute indicative netback from market price and route cost."""
    input_ = NetbackInput(
        route_name=body.route_name,
        from_market=body.from_market,
        to_market=body.to_market,
        market_price_eur_mwh=body.market_price_eur_mwh,
        route_cost_eur_mwh=body.route_cost_eur_mwh,
        fx_rate=body.fx_rate,
        fx_pair=body.fx_pair,
    )
    result = compute_netback(input_)
    return _envelope(result)


@router.post("/feasibility")
def post_feasibility(body: FeasibilityRequest, request: Request) -> dict:
    """Check route feasibility against capacity, eligibility, and contracts."""
    input_ = FeasibilityInput(
        route_name=body.route_name,
        from_node_id=body.from_node_id,
        to_node_id=body.to_node_id,
        capacity_available_mcm_d=body.capacity_available_mcm_d,
        required_capacity_mcm_d=body.required_capacity_mcm_d,
        route_eligible=body.route_eligible,
        contract_active=body.contract_active,
        constraints=body.constraints,
    )
    result = check_feasibility(input_)
    return _envelope(result)


@router.post("/allocation")
def post_allocation(body: AllocationRequest, request: Request) -> dict:
    """Distribute demand across eligible routes by rank order."""
    candidates = [
        AllocationCandidate(
            candidate_id=c.candidate_id,
            route_name=c.route_name,
            from_node_id=c.from_node_id,
            to_node_id=c.to_node_id,
            capacity_available_boe_d=c.capacity_available_boe_d,
            cost_eur_mwh=c.cost_eur_mwh,
            rank=c.rank,
            eligible=c.eligible,
        )
        for c in body.candidates
    ]
    input_ = AllocationInput(
        scenario_name=body.scenario_name,
        total_demand_boe_d=body.total_demand_boe_d,
        candidates=candidates,
    )
    result = compute_allocation(input_)
    return _envelope(result)


@router.post("/monitoring")
def post_monitoring(body: MonitoringRequest, request: Request) -> dict:
    """Generate research alerts from observations and thresholds."""
    thresholds = [
        MonitoringThreshold(
            field=t.field, operator=t.operator, value=t.value,
            severity=t.severity, message_template=t.message_template,
        )
        for t in body.thresholds
    ]
    input_ = MonitoringInput(
        entity_id=body.entity_id,
        entity_name=body.entity_name,
        observations=body.observations,
        thresholds=thresholds,
    )
    result = generate_alerts(input_)
    return _envelope(result)


@router.post("/nowcast")
def post_nowcast(body: NowcastRequest, request: Request) -> dict:
    """Compute weather-adjusted demand nowcast."""
    input_ = NowcastInput(
        market=body.market,
        period_start_utc=body.period_start_utc,
        period_end_utc=body.period_end_utc,
        base_demand_boe_d=body.base_demand_boe_d,
        hdd=body.hdd,
        cdd=body.cdd,
        hdd_sensitivity_boe_per_deg=body.hdd_sensitivity_boe_per_deg,
        cdd_sensitivity_boe_per_deg=body.cdd_sensitivity_boe_per_deg,
    )
    result = compute_nowcast(input_)
    return _envelope(result)


@router.post("/backtest")
def post_backtest(body: BacktestRequest, request: Request) -> dict:
    """Compute strategy backtest metrics from trade history."""
    input_ = BacktestInput(
        strategy_name=body.strategy_name,
        start_utc=body.start_utc,
        end_utc=body.end_utc,
        trades=[t.model_dump() for t in body.trades],
    )
    result = compute_backtest(input_)
    return _envelope(result)


@router.post("/shadow-run")
def post_shadow_run(body: ShadowRunRequest, request: Request) -> dict:
    """Evaluate a paper-trading shadow run (no real execution)."""
    signals = [
        ShadowSignal(
            signal_id=s.signal_id,
            route_name=s.route_name,
            action=s.action,
            score=s.score,
            note=s.note,
        )
        for s in body.signals
    ]
    input_ = ShadowRunInput(
        strategy_name=body.strategy_name,
        started_at_utc=body.started_at_utc,
        signals=signals,
        paper_pnl_eur=body.paper_pnl_eur,
    )
    result = evaluate_shadow_run(input_)
    return _envelope(result)


# --- Helpers -----------------------------------------------------------------


def _envelope(result) -> dict:
    data = {
        "research_only": result.research_only,
        "human_review_required": result.human_review_required,
        "assumptions": result.assumptions,
        "missing_inputs": result.missing_inputs,
        "warnings": result.warnings,
        "source_references": result.source_references,
        "lineage": result.lineage,
        "generated_at_utc": result.generated_at_utc,
    }
    if hasattr(result, "route_name"):
        data["route_name"] = result.route_name
    if hasattr(result, "scenario_name"):
        data["scenario_name"] = result.scenario_name

    if hasattr(result, "total_cost_eur_mwh"):
        data["total_cost_eur_mwh"] = result.total_cost_eur_mwh
        data["total_cost_boe"] = result.total_cost_boe
        data["from_node_id"] = result.from_node_id
        data["to_node_id"] = result.to_node_id
        data["route_km"] = result.route_km
        data["components"] = [
            {
                "component_type": c.component_type,
                "amount": c.amount,
                "unit": c.unit,
                "currency": c.currency,
                "description": c.description,
            }
            for c in result.components
        ]

    if hasattr(result, "netback_eur_mwh"):
        data["from_market"] = result.from_market
        data["to_market"] = result.to_market
        data["market_price_eur_mwh"] = result.market_price_eur_mwh
        data["route_cost_eur_mwh"] = result.route_cost_eur_mwh
        data["netback_eur_mwh"] = result.netback_eur_mwh
        data["netback_local_mwh"] = result.netback_local_mwh
        data["fx_rate"] = result.fx_rate
        data["fx_pair"] = result.fx_pair

    if hasattr(result, "status") and hasattr(result, "blockers"):
        data["from_node_id"] = result.from_node_id
        data["to_node_id"] = result.to_node_id
        data["status"] = str(result.status)
        data["blockers"] = result.blockers
        data["conditions"] = result.conditions

    if hasattr(result, "total_allocated_boe_d"):
        data["total_demand_boe_d"] = result.total_demand_boe_d
        data["total_allocated_boe_d"] = result.total_allocated_boe_d
        data["unallocated_boe_d"] = result.unallocated_boe_d
        data["results"] = [
            {
                "candidate_id": r.candidate_id,
                "route_name": r.route_name,
                "allocated_boe_d": r.allocated_boe_d,
                "cost_eur_mwh": r.cost_eur_mwh,
                "rank": r.rank,
                "note": r.note,
            }
            for r in result.results
        ]

    if hasattr(result, "alerts") and hasattr(result, "total_alerts"):
        data["entity_id"] = result.entity_id
        data["entity_name"] = result.entity_name
        data["total_alerts"] = result.total_alerts
        data["alerts"] = [
            {
                "alert_id": a.alert_id,
                "alert_type": a.alert_type,
                "severity": str(a.severity),
                "message": a.message,
                "observed_value": a.observed_value,
                "threshold_value": a.threshold_value,
            }
            for a in result.alerts
        ]

    if hasattr(result, "adjusted_demand_boe_d"):
        data["market"] = result.market
        data["period_start_utc"] = result.period_start_utc
        data["period_end_utc"] = result.period_end_utc
        data["base_demand_boe_d"] = result.base_demand_boe_d
        data["hdd_adjustment_boe_d"] = result.hdd_adjustment_boe_d
        data["cdd_adjustment_boe_d"] = result.cdd_adjustment_boe_d
        data["weather_adjustment_boe_d"] = result.weather_adjustment_boe_d
        data["adjusted_demand_boe_d"] = result.adjusted_demand_boe_d
        data["hdd"] = result.hdd
        data["cdd"] = result.cdd

    if hasattr(result, "total_return_eur") and hasattr(result, "trade_count"):
        data["strategy_name"] = result.strategy_name
        data["start_utc"] = result.start_utc
        data["end_utc"] = result.end_utc
        data["total_return_eur"] = result.total_return_eur
        data["trade_count"] = result.trade_count
        data["win_count"] = result.win_count
        data["loss_count"] = result.loss_count
        data["win_rate_pct"] = result.win_rate_pct
        data["sharpe_ratio"] = result.sharpe_ratio
        data["max_drawdown_pct"] = result.max_drawdown_pct
        data["status"] = str(result.status)

    if hasattr(result, "signal_count"):
        data["strategy_name"] = result.strategy_name
        data["status"] = str(result.status)
        data["started_at_utc"] = result.started_at_utc
        data["elapsed_days"] = result.elapsed_days
        data["signal_count"] = result.signal_count
        data["paper_pnl_eur"] = result.paper_pnl_eur
        data["signals"] = [
            {
                "signal_id": s.signal_id,
                "route_name": s.route_name,
                "action": str(s.action),
                "score": s.score,
                "note": s.note,
            }
            for s in result.signals
        ]

    return {
        "data": data,
        "meta": {
            "research_only": True,
            "human_review_required": True,
            "decision_context": SANDBOX_SCENARIO,
        },
    }
