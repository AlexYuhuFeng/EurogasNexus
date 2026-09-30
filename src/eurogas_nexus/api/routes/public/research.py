"""Research computation API routes — POST endpoints for all research workflows.

Research endpoints are explicit what-if sandboxes: client-supplied inputs are
allowed, and responses carry ``decision_context: SANDBOX_SCENARIO``. Requests
claiming RUNTIME_DECISION semantics are rejected (audit item 2).

``/api/research/cash-valuation`` adapts the one shared cash-flow engine
(``domain/research/cash_valuation.py``) to HTTP: caller-supplied business
references and caller-supplied amounts, FX rates and discount factors are
transmitted as exact decimal *strings*, and responses serialize every Decimal
as an exact string with ISO dates (no binary-float step anywhere). The route
never resolves, infers or entitles a supplied reference, never persists, and
never claims customer approval.
"""

import re
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from eurogas_nexus.api.dependencies.sandbox import (
    SANDBOX_SCENARIO,
    require_sandbox_scenario,
)
from eurogas_nexus.domain.ontology.actions import ActionKind
from eurogas_nexus.domain.ontology.semantic_kernel import CanonicalId
from eurogas_nexus.domain.research.allocation import (
    AllocationCandidate,
    AllocationInput,
    compute_allocation,
)
from eurogas_nexus.domain.research.backtest import (
    BacktestInput,
    compute_backtest,
)
from eurogas_nexus.domain.research.cash_valuation import (
    CASH_VALUATION_MODEL_VERSION,
    CashFlowLegCategory,
    CashValuationDiscountFactorInput,
    CashValuationError,
    CashValuationFxInput,
    CashValuationInput,
    CashValuationLegInput,
    CashValuationResult,
    compute_cash_valuation,
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


# --- Shared cash valuation wire contract --------------------------------------
#
# The dated cash valuation contract is exact by construction: amounts, FX rates
# and discount factors travel as decimal *strings* and are parsed with an
# explicit plain-decimal grammar, so a JSON number (which has already passed
# through a binary float before any backend code sees it) is never accepted.
# The shared engine (``domain/research/cash_valuation.py``) remains the single
# owner of every semantic rule, rounding step and refusal code; this module only
# reads the wire syntax. Unknown request fields are refused (``extra="forbid"``),
# so a request cannot smuggle an authority claim such as a persona or work mode
# the backend never reads.


class CashValuationFxRequest(BaseModel):
    """Explicit FX reference of one cross-currency cash-flow leg.

    Attributes:
        rate_reporting_per_leg: Exact decimal string: reporting-currency amount
            per one leg-currency unit, in the direction the engine declares.
        source_reference: Mandatory provenance of the quoted rate.
        as_of: Quote date as ``YYYY-MM-DD``; never after the valuation date.
    """

    model_config = ConfigDict(extra="forbid")

    rate_reporting_per_leg: str = Field(max_length=64)
    source_reference: str = Field(max_length=256)
    as_of: str = Field(max_length=32)


class CashValuationLegRequest(BaseModel):
    """One signed, dated cash-flow leg of a cash-valuation request.

    Attributes:
        leg_id: Unique identity of the leg within the request.
        category: Cash-flow-leg vocabulary value (``CashFlowLegCategory``).
        payment_date: Cash date as ``YYYY-MM-DD``.
        signed_amount: Exact decimal string; inflow positive, outflow negative.
        currency: Uppercase three-letter currency code of the leg amount.
        source_reference: Mandatory provenance of the amount.
        fx: Cross-currency FX block; must be absent for same-currency legs.
        description: Optional human label, never used in arithmetic.
    """

    model_config = ConfigDict(extra="forbid")

    leg_id: str = Field(max_length=128)
    category: str = Field(max_length=64)
    payment_date: str = Field(max_length=32)
    signed_amount: str = Field(max_length=64)
    currency: str = Field(max_length=8)
    source_reference: str = Field(max_length=256)
    fx: CashValuationFxRequest | None = None
    description: str = Field(default="", max_length=500)


class CashValuationDiscountFactorRequest(BaseModel):
    """One explicit discount factor for one payment date.

    Attributes:
        payment_date: Cash date the factor discounts, as ``YYYY-MM-DD``.
        factor: Exact decimal string; explicit, never inferred from a curve.
        curve_reference: Mandatory curve reference the factor came from.
        source_reference: Mandatory provenance of the factor.
        as_of: Factor date as ``YYYY-MM-DD``; never after the valuation date.
    """

    model_config = ConfigDict(extra="forbid")

    payment_date: str = Field(max_length=32)
    factor: str = Field(max_length=64)
    curve_reference: str = Field(max_length=256)
    source_reference: str = Field(max_length=256)
    as_of: str = Field(max_length=32)


class CashValuationRequest(BaseModel):
    """Sandbox cash-valuation request over caller-supplied business references.

    The business context arrives as canonical ``concept:value`` strings and is
    *never resolved*: the backend does not look up, infer or confirm that a
    supplied id names a persisted entity, and the response says so explicitly.

    Attributes:
        business_context: Non-empty canonical references the valuation is
            declared against; duplicates are refused by the engine. Bounded to
            keep the request size consistent with the other research routes.
        valuation_date: Valuation date as ``YYYY-MM-DD``.
        reporting_currency: Uppercase three-letter reporting currency.
        legs: Signed, dated cash-flow legs (bounded).
        discount_factors: Explicit per-payment-date discount factors (bounded).
        model_version: Engine model version; any unsupported value is refused
            with the engine's stable code rather than silently downgraded.
    """

    model_config = ConfigDict(extra="forbid")

    business_context: list[str] = Field(max_length=64)
    valuation_date: str = Field(max_length=32)
    reporting_currency: str = Field(max_length=8)
    legs: list[CashValuationLegRequest] = Field(max_length=256)
    discount_factors: list[CashValuationDiscountFactorRequest] = Field(max_length=256)
    model_version: str = Field(default=CASH_VALUATION_MODEL_VERSION, max_length=64)


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


@router.post("/cash-valuation")
def post_cash_valuation(body: CashValuationRequest, request: Request) -> dict:
    """Value explicit signed cash flows through the one shared cash engine.

    Sandbox-only adaptation of ``domain/research/cash_valuation.py``: every
    business reference is caller-supplied and unverified, every amount, FX rate
    and discount factor arrives as an exact decimal string, and the response is
    a deterministic payload whose Decimals are serialized as exact strings and
    whose dates are ISO dates. The route never looks up a persisted entity,
    never resolves or entitles a supplied reference, never persists anything,
    never calls a provider and carries no trade/nomination/settlement meaning;
    refusals carry stable machine codes instead of partial results.

    Args:
        body: The sandbox request; see :class:`CashValuationRequest`.
        request: The incoming request (shared route signature; the sandbox
            dependency has already labelled its decision context).

    Returns:
        ``{"data": ..., "meta": ...}`` with exact string decimals, ISO dates
        and explicit caller-supplied / unverified-reference / research /
        human-review / not-customer-approval metadata.

    Raises:
        HTTPException: 422 ``cash_valuation_input_invalid`` when the request
            text cannot be read as the declared exact contract; 422
            ``cash_valuation_refused`` when the shared engine refuses the
            supplied inputs (stable engine codes in ``detail.codes``).
    """

    violations: list[tuple[str, str]] = []
    input_ = _cash_valuation_input(body, violations)
    if violations:
        raise _cash_valuation_refusal(
            "cash_valuation_input_invalid",
            (
                "The request text is not the declared exact cash-valuation"
                " contract; nothing was computed."
            ),
            violations,
        )
    try:
        result = compute_cash_valuation(input_)
    except CashValuationError as exc:
        raise _cash_valuation_refusal(
            "cash_valuation_refused",
            (
                "The shared cash valuation engine refused the supplied inputs;"
                " nothing was computed."
            ),
            list(exc.violations),
        ) from exc
    return _cash_valuation_envelope(result)


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


# --- Cash valuation helpers ---------------------------------------------------

# Plain-decimal grammar of the wire contract. Exponent notation, underscores,
# whitespace, ``NaN``/``Infinity`` and JSON numbers are all refused: a JSON
# number has already passed through a binary float, and the shared engine's
# arithmetic must never receive a value the caller did not state exactly.
_PLAIN_DECIMAL_PATTERN = re.compile(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)\Z")
_ISO_CALENDAR_DATE_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}\Z")


def _decimal_string(value: Decimal) -> str:
    """Serialize one Decimal exactly, as a fixed-point decimal string."""

    return format(value, "f")


def _exact_decimal(
    text: str, label: str, violations: list[tuple[str, str]]
) -> Decimal | None:
    """Parse one exact decimal string, or record a stable violation."""

    if not _PLAIN_DECIMAL_PATTERN.match(text):
        violations.append(
            (
                "DECIMAL_STRING_INVALID",
                f"{label}={text!r} must be a plain exact decimal string such as"
                " '-100' or '0.95'; non-finite values, exponent notation and"
                " JSON numbers are never accepted",
            )
        )
        return None
    return Decimal(text)


def _calendar_date(
    text: str, label: str, violations: list[tuple[str, str]]
) -> date | None:
    """Parse one ISO calendar date string, or record a stable violation."""

    if not _ISO_CALENDAR_DATE_PATTERN.match(text):
        violations.append(
            (
                "DATE_STRING_INVALID",
                f"{label}={text!r} must be an ISO calendar date (YYYY-MM-DD)",
            )
        )
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        violations.append(
            ("DATE_STRING_INVALID", f"{label}={text!r} is not a calendar date")
        )
        return None


def _leg_category(
    text: str, label: str, violations: list[tuple[str, str]]
) -> CashFlowLegCategory | None:
    """Map one category string onto the shared, reviewed leg vocabulary."""

    try:
        return CashFlowLegCategory(text)
    except ValueError:
        violations.append(
            (
                "LEG_CATEGORY_INVALID",
                f"{label}.category={text!r} is not a declared cash-flow leg category",
            )
        )
        return None


def _cash_valuation_input(
    body: CashValuationRequest, violations: list[tuple[str, str]]
) -> CashValuationInput:
    """Translate the wire contract into the shared engine's typed input.

    Only the *syntax* of the request is checked here (plain decimal text, ISO
    date text, canonical ``concept:value`` shape, declared category vocabulary).
    Every semantic rule - finiteness, magnitude, zero amounts, duplicate ids,
    past-dated flows, missing discount factors, FX direction and provenance -
    stays in the shared engine and is reported through its stable codes. Values
    that failed to parse are irrelevant because the caller refuses the request
    when ``violations`` is non-empty.
    """

    business_context: list[CanonicalId] = []
    for position, reference in enumerate(body.business_context):
        concept, separator, value = reference.partition(":")
        if not separator:
            violations.append(
                (
                    "BUSINESS_CONTEXT_REFERENCE_INVALID",
                    f"business_context[{position}]={reference!r} must be a canonical"
                    " 'concept:value' reference; the engine never coerces a plain"
                    " string",
                )
            )
            continue
        business_context.append(CanonicalId(concept, value))

    legs: list[CashValuationLegInput] = []
    for position, leg in enumerate(body.legs):
        label = f"legs[{position}]"
        fx = None
        if leg.fx is not None:
            fx = CashValuationFxInput(
                rate_reporting_per_leg=_exact_decimal(
                    leg.fx.rate_reporting_per_leg,
                    f"{label}.fx.rate_reporting_per_leg",
                    violations,
                ),
                source_reference=leg.fx.source_reference,
                as_of=_calendar_date(leg.fx.as_of, f"{label}.fx.as_of", violations),
            )
        legs.append(
            CashValuationLegInput(
                leg_id=leg.leg_id,
                category=_leg_category(leg.category, label, violations),
                payment_date=_calendar_date(
                    leg.payment_date, f"{label}.payment_date", violations
                ),
                signed_amount=_exact_decimal(
                    leg.signed_amount, f"{label}.signed_amount", violations
                ),
                currency=leg.currency,
                source_reference=leg.source_reference,
                fx=fx,
                description=leg.description,
            )
        )

    discount_factors: list[CashValuationDiscountFactorInput] = []
    for position, item in enumerate(body.discount_factors):
        label = f"discount_factors[{position}]"
        discount_factors.append(
            CashValuationDiscountFactorInput(
                payment_date=_calendar_date(
                    item.payment_date, f"{label}.payment_date", violations
                ),
                factor=_exact_decimal(item.factor, f"{label}.factor", violations),
                curve_reference=item.curve_reference,
                source_reference=item.source_reference,
                as_of=_calendar_date(item.as_of, f"{label}.as_of", violations),
            )
        )

    return CashValuationInput(
        business_context=tuple(business_context),
        valuation_date=_calendar_date(
            body.valuation_date, "valuation_date", violations
        ),
        reporting_currency=body.reporting_currency,
        legs=tuple(legs),
        discount_factors=tuple(discount_factors),
        model_version=body.model_version,
    )


def _cash_valuation_refusal(
    code: str, message: str, violations: list[tuple[str, str]]
) -> HTTPException:
    """Build the stable typed refusal shared by both refusal stages."""

    return HTTPException(
        status_code=422,
        detail={
            "code": code,
            "message": message,
            "codes": [violation_code for violation_code, _ in violations],
            "violations": [
                {"code": violation_code, "detail": detail}
                for violation_code, detail in violations
            ],
            "research_only": True,
            "human_review_required": True,
        },
    )


def _cash_valuation_envelope(result: CashValuationResult) -> dict:
    """Serialize one engine result with exact strings and explicit metadata.

    Decimals are emitted as exact fixed-point strings and dates as ISO dates,
    so no JSON encoder ever converts a value to a binary float. The metadata
    states the boundary out loud: the inputs are caller-supplied, the business
    references are unverified (never looked up or entitled), the output is
    research with mandatory human review and it is not customer approval.
    """

    leg_valuations = [
        {
            "leg_id": leg.leg_id,
            "category": leg.category.value,
            "payment_date": leg.payment_date.isoformat(),
            "currency": leg.currency,
            "signed_amount": _decimal_string(leg.signed_amount),
            "cash_amount_reporting_ccy": _decimal_string(leg.cash_amount_reporting_ccy),
            "present_value_reporting_ccy": _decimal_string(
                leg.present_value_reporting_ccy
            ),
            "discount_factor": _decimal_string(leg.discount_factor),
            "discount_curve_reference": leg.discount_curve_reference,
            "discount_source_reference": leg.discount_source_reference,
            "discount_as_of": leg.discount_as_of.isoformat(),
            "source_reference": leg.source_reference,
            "fx_rate_reporting_per_leg": _decimal_string(leg.fx_rate_reporting_per_leg),
            "fx_source_reference": leg.fx_source_reference,
            "fx_as_of": leg.fx_as_of.isoformat() if leg.fx_as_of is not None else None,
            "description": leg.description,
        }
        for leg in result.leg_valuations
    ]
    source_references = list(result.source_references)
    warnings = list(result.warnings)
    data = {
        "research_only": result.research_only,
        "human_review_required": result.human_review_required,
        "model_version": result.model_version,
        "action": ActionKind.COMPUTE_CASH_FLOW.value,
        "business_context": [str(reference) for reference in result.business_context],
        "valuation_date": result.valuation_date.isoformat(),
        "reporting_currency": result.reporting_currency,
        "leg_valuations": leg_valuations,
        "total_undiscounted_cash_reporting_ccy": _decimal_string(
            result.total_undiscounted_cash_reporting_ccy
        ),
        "net_present_value_reporting_ccy": _decimal_string(
            result.net_present_value_reporting_ccy
        ),
        "assumptions": list(result.assumptions),
        "warnings": warnings,
        "source_references": source_references,
        "lineage": list(result.lineage),
    }
    return {
        "data": data,
        "meta": {
            "research_only": True,
            "human_review_required": True,
            "decision_context": SANDBOX_SCENARIO,
            "caller_supplied": True,
            "references_verified": False,
            "customer_approval": False,
            "source_references": source_references,
            "warnings": warnings,
        },
    }
