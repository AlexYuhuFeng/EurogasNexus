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

``/api/research/capacity-billing`` follows the same exact-wire convention for
one explicitly supplied capacity tariff and UTC billing window. It maps only to
``domain/research/capacity_billing.py``, keeps the original basis and exact
duration microseconds, and never converts a capacity charge into an energy fee,
claims booked rights or asserts physical readiness.
"""

import re
from datetime import date, datetime
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
from eurogas_nexus.domain.research.capacity_billing import (
    CAPACITY_BILLING_MODEL_VERSION,
    CapacityBillingError,
    CapacityBillingInput,
    CapacityBillingResult,
    compute_capacity_billing,
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
from eurogas_nexus.domain.research.lng_cargo_economics import (
    LNG_ECONOMICS_ONLY_MODEL_VERSION,
    LngDownstreamChargeBasis,
    LngEconomicsOnlyCostInput,
    LngEconomicsOnlyError,
    LngEconomicsOnlyInput,
    LngEconomicsOnlyResult,
    compute_lng_economics_only,
)
from eurogas_nexus.domain.research.lng_cash_valuation import (
    LngCashDiscountFactorInput,
)
from eurogas_nexus.domain.research.lng_energy_balance import (
    LngEnergyStage,
    LngEnergyStageKind,
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
        capital_base_eur: Capital at risk, used only as the denominator of
            ``max_drawdown_pct``. ``0`` means none is declared, and the percent
            is then reported only once the cumulative PnL has been positive.
    """

    strategy_name: str = ""
    start_utc: str = ""
    end_utc: str = ""
    trades: list[TradeRecordRequest] = Field(default_factory=list)
    capital_base_eur: float = Field(default=0.0, ge=0.0)


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


# --- Shared capacity-billing wire contract ------------------------------------
#
# One explicitly supplied capacity tariff over one explicit UTC billing window.
# Every numeric input travels as an exact decimal string and is parsed with the
# same plain-decimal grammar as the cash-valuation contract, so a JSON number
# (already rounded through a binary float) is never accepted. The shared
# ``domain/research/capacity_billing.py`` primitive remains the single owner of
# the exact rational arithmetic, bounds and stable refusal codes; this module
# only reads the wire syntax and maps the typed input/result.


class CapacityBillingRequest(BaseModel):
    """Sandbox capacity-billing request with an explicit, caller-supplied basis.

    Attributes:
        scenario_id: Caller-supplied scenario identifier. It is never resolved
            to a persisted entity.
        tariff_id: Caller-supplied tariff identifier. It is never looked up.
        tariff_rate: Exact decimal string of the rate in ``tariff_unit``.
        currency: Currency the tariff unit requires (``EUR`` or ``GBP``).
        tariff_unit: Explicit capacity unit: ``EUR/(MWh/h)/h``,
            ``GBP/(MWh/h)/h`` or ``p/(kWh/h)/h``.
        booked_capacity_mwh_per_h: Exact decimal string of booked capacity.
        delivered_energy_mwh: Exact decimal string of delivered energy.
        billed_capacity_energy_mwh: Exact decimal string of billed capacity
            energy; the engine verifies it against booked capacity * duration.
        billing_start: ISO-8601 timestamp with an explicit UTC offset.
        billing_end: ISO-8601 timestamp with an explicit UTC offset.
        source_references: Mandatory caller-supplied provenance references.
        model_version: Engine model version; an unsupported value is refused by
            the engine with its stable code.
    """

    model_config = ConfigDict(extra="forbid")

    scenario_id: str = Field(max_length=128)
    tariff_id: str = Field(max_length=128)
    tariff_rate: str = Field(max_length=64)
    currency: str = Field(max_length=8)
    tariff_unit: str = Field(max_length=32)
    booked_capacity_mwh_per_h: str = Field(max_length=64)
    delivered_energy_mwh: str = Field(max_length=64)
    billed_capacity_energy_mwh: str = Field(max_length=64)
    billing_start: str = Field(max_length=64)
    billing_end: str = Field(max_length=64)
    source_references: list[str] = Field(max_length=64)
    model_version: str = Field(default=CAPACITY_BILLING_MODEL_VERSION, max_length=64)


# --- Shared LNG economics-only wire contract ----------------------------------
#
# The economics-only composition takes explicit cash amounts and an explicit
# ordered energy-stage chain, and never assesses physical readiness. Every amount
# travels as an exact decimal string and every date as ``YYYY-MM-DD``; the shared
# ``domain/research/lng_cargo_economics.py`` composition remains the single owner
# of the formulas, bounds and stable refusal codes. This module only reads the
# wire syntax, maps the declared vocabularies and serializes the typed result.


class LngEconomicsOnlyDiscountFactorRequest(BaseModel):
    """One explicit discount factor supplied for one payment date.

    Attributes:
        payment_date: Cash date the factor discounts, as ``YYYY-MM-DD``.
        factor: Exact decimal string; explicit, never inferred from a curve.
        curve_reference: Mandatory curve reference the factor came from.
        source_reference: Mandatory provenance of the factor.
        as_of: Factor date as ``YYYY-MM-DD``.
    """

    model_config = ConfigDict(extra="forbid")

    payment_date: str = Field(max_length=32)
    factor: str = Field(max_length=64)
    curve_reference: str = Field(max_length=256)
    source_reference: str = Field(max_length=256)
    as_of: str = Field(max_length=32)


class LngEconomicsOnlyDownstreamCostRequest(BaseModel):
    """One explicitly invoiced downstream cash cost.

    Attributes:
        cost_id: Unique item id within the request; duplicates are refused.
        category: Cost category from the shared cash-leg vocabulary.
        amount_eur: Exact decimal string of the nonnegative EUR total.
        payment_date: Cash date as ``YYYY-MM-DD``.
        source_reference: Mandatory provenance of the invoiced amount.
        charge_basis: Declared charge nature; only ``invoiced_cash`` is a cash
            expense. ``in_kind`` and ``unknown`` are refused by the engine.
    """

    model_config = ConfigDict(extra="forbid")

    cost_id: str = Field(max_length=128)
    category: str = Field(max_length=64)
    amount_eur: str = Field(max_length=64)
    payment_date: str = Field(max_length=32)
    source_reference: str = Field(max_length=256)
    charge_basis: str = Field(max_length=32)


class LngEconomicsOnlyEnergyStageRequest(BaseModel):
    """One explicit stage of the ordered LNG cargo energy chain.

    Attributes:
        stage_id: Unique stage id within the chain; duplicates are refused.
        kind: Declared stage kind (``shipping``, ``storage``,
            ``regasification``, ``cargo_transfer`` or ``other``).
        input_energy_mwh: Exact decimal string of the positive stage input.
        output_energy_mwh: Exact decimal string of the positive stage output.
        consumed_energy_mwh: Exact decimal string of nonnegative consumed
            energy.
        physical_loss_energy_mwh: Exact decimal string of nonnegative physical
            loss.
        source_references: Mandatory provenance references for the stage.
    """

    model_config = ConfigDict(extra="forbid")

    stage_id: str = Field(max_length=128)
    kind: str = Field(max_length=64)
    input_energy_mwh: str = Field(max_length=64)
    output_energy_mwh: str = Field(max_length=64)
    consumed_energy_mwh: str = Field(max_length=64)
    physical_loss_energy_mwh: str = Field(max_length=64)
    source_references: list[str] = Field(max_length=64)


class LngEconomicsOnlyRequest(BaseModel):
    """Sandbox economics-only request with explicit cash and energy stages.

    The business references and every amount are caller-supplied and never
    resolved. The request deliberately carries no readiness scenario and no
    authority claim: the path never calls the regas readiness assessor.

    Attributes:
        contract_id / cargo_id / terminal_id / resource_id: Caller-supplied
            references; never looked up or entitled.
        valuation_date: Valuation date as ``YYYY-MM-DD``.
        reporting_currency: Explicit reporting currency; only ``EUR`` is
            supported.
        energy_basis_reference: Mandatory declared energy-basis reference.
        energy_unit: Explicit energy unit; only ``MWh`` is supported.
        purchased_energy_mwh: Exact decimal string of purchased energy.
        delivered_energy_mwh: Exact decimal string of delivered energy.
        purchase_unit_price_eur_per_mwh: Exact signed decimal string.
        sale_unit_price_eur_per_mwh: Exact signed decimal string.
        purchase_price_source_reference: Mandatory purchase-price provenance.
        sale_price_source_reference: Mandatory sale-price provenance.
        purchase_basis: Explicit purchase basis, exactly ``FOB`` or ``DES``.
        purchase_included_cost_items: Categories already included in the
            purchase price; itemizing them again is refused.
        cost_scope_statement: Mandatory statement of the cost scope.
        purchase_payment_date: Purchase cash date as ``YYYY-MM-DD``.
        sale_payment_date: Sale cash date as ``YYYY-MM-DD``.
        downstream_costs: Explicitly invoiced downstream cash costs.
        energy_stages: Ordered explicit energy stages; never inferred.
        discount_factors: Explicit per-payment-date discount factors.
        model_version: Engine model version; an unsupported value is refused
            with the engine's stable code.
    """

    model_config = ConfigDict(extra="forbid")

    contract_id: str = Field(max_length=128)
    cargo_id: str = Field(max_length=128)
    terminal_id: str = Field(max_length=128)
    resource_id: str = Field(max_length=128)
    valuation_date: str = Field(max_length=32)
    reporting_currency: str = Field(max_length=8)
    energy_basis_reference: str = Field(max_length=256)
    energy_unit: str = Field(max_length=32)
    purchased_energy_mwh: str = Field(max_length=64)
    delivered_energy_mwh: str = Field(max_length=64)
    purchase_unit_price_eur_per_mwh: str = Field(max_length=64)
    sale_unit_price_eur_per_mwh: str = Field(max_length=64)
    purchase_price_source_reference: str = Field(max_length=256)
    sale_price_source_reference: str = Field(max_length=256)
    purchase_basis: str = Field(max_length=8)
    purchase_included_cost_items: list[str] = Field(max_length=64)
    cost_scope_statement: str = Field(max_length=1000)
    purchase_payment_date: str = Field(max_length=32)
    sale_payment_date: str = Field(max_length=32)
    downstream_costs: list[LngEconomicsOnlyDownstreamCostRequest] = Field(
        max_length=256
    )
    energy_stages: list[LngEconomicsOnlyEnergyStageRequest] = Field(
        max_length=256
    )
    discount_factors: list[LngEconomicsOnlyDiscountFactorRequest] = Field(
        max_length=256
    )
    model_version: str = Field(
        default=LNG_ECONOMICS_ONLY_MODEL_VERSION, max_length=64
    )


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
        capital_base_eur=body.capital_base_eur,
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


@router.post("/capacity-billing")
def post_capacity_billing(body: CapacityBillingRequest, request: Request) -> dict:
    """Bill one explicitly supplied capacity tariff through the shared engine.

    Sandbox-only adaptation of ``domain/research/capacity_billing.py``: the
    tariff, booked capacity, delivered energy, billed capacity energy, UTC
    billing window and provenance are all caller-supplied and never resolved,
    looked up or inferred. Every numeric input arrives as an exact decimal
    string and every Decimal in the result is serialized as an exact string.
    The route performs no financial arithmetic of its own: the shared engine
    owns the formulas, bounds, rounding and stable refusal codes. It never
    persists anything, calls a provider or establishes booked rights,
    deliverability, invoice authority or physical readiness.

    Args:
        body: The sandbox request; see :class:`CapacityBillingRequest`.
        request: The incoming request (shared route signature; the sandbox
            dependency has already labelled its decision context).

    Returns:
        ``{"data": ..., "meta": ...}`` with exact string decimals, ISO UTC
        timestamps, the original explicit basis, exact duration microseconds,
        research/human-review flags and ``physical_readiness="NOT_ASSESSED"``.

    Raises:
        HTTPException: 422 ``capacity_billing_input_invalid`` when the request
            text cannot be read as the declared exact contract; 422
            ``capacity_billing_refused`` when the shared engine refuses the
            supplied inputs (stable engine codes in ``detail.codes``).
    """

    violations: list[tuple[str, str]] = []
    input_ = _capacity_billing_input(body, violations)
    if violations:
        raise _capacity_billing_refusal(
            "capacity_billing_input_invalid",
            (
                "The request text is not the declared exact capacity-billing"
                " contract; nothing was computed."
            ),
            violations,
        )
    try:
        result = compute_capacity_billing(input_)
    except CapacityBillingError as exc:
        raise _capacity_billing_refusal(
            "capacity_billing_refused",
            (
                "The shared capacity-billing engine refused the supplied inputs;"
                " nothing was computed."
            ),
            list(exc.violations),
        ) from exc
    return _capacity_billing_envelope(result)


@router.post("/lng-economics-only")
def post_lng_economics_only(
    body: LngEconomicsOnlyRequest, request: Request
) -> dict:
    """Compose explicit LNG economics without assessing physical readiness.

    Sandbox-only adaptation of ``domain/research/lng_cargo_economics.py``: the
    ordered energy-stage chain, invoiced downstream cash costs, signed prices,
    references and provenance are caller-supplied and never resolved, inferred
    or validated against a persisted entity. Every numeric input arrives as an
    exact decimal string and every amount in the response is serialized as an
    exact string. The domain composition owns all formulas, bounds, cash-leg
    construction and stable refusal codes; this route performs no financial
    arithmetic.

    The economics-only path never calls the regas readiness assessor and never
    fabricates terminal, slot, storage, TSO or nomination evidence. Its response
    explicitly reports ``physical_readiness='NOT_ASSESSED'`` and
    ``readiness_assessed=False``, with research-only and human-review metadata.
    It never persists anything, calls a provider or establishes delivery
    feasibility, booked rights or customer approval.

    Args:
        body: The sandbox request; see :class:`LngEconomicsOnlyRequest`.
        request: The incoming request (shared route signature; the sandbox
            dependency has already labelled its decision context).

    Returns:
        ``{"data": ..., "meta": ...}`` with exact string decimals, ISO dates,
        the mapped ordered energy chain, the embedded cash valuation and
        explicit not-assessed readiness metadata.

    Raises:
        HTTPException: 422 ``lng_economics_only_input_invalid`` when the request
            text cannot be read as the declared exact contract; 422
            ``lng_economics_only_refused`` when the shared composition refuses
            the supplied inputs (stable domain codes in ``detail.codes``).
    """

    violations: list[tuple[str, str]] = []
    input_ = _lng_economics_only_input(body, violations)
    if violations:
        raise _lng_economics_only_refusal(
            "lng_economics_only_input_invalid",
            (
                "The request text is not the declared exact LNG economics-only"
                " contract; nothing was computed."
            ),
            violations,
        )
    try:
        result = compute_lng_economics_only(input_)
    except LngEconomicsOnlyError as exc:
        raise _lng_economics_only_refusal(
            "lng_economics_only_refused",
            (
                "The shared LNG economics-only composition refused the supplied"
                " inputs; nothing was computed."
            ),
            list(exc.violations),
        ) from exc
    return _lng_economics_only_envelope(result)


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
        data["max_drawdown_eur"] = result.max_drawdown_eur
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


# --- Capacity billing helpers -------------------------------------------------

# The billing window is a pair of explicit ISO-8601 timestamps. The shape check
# accepts an optional explicit offset and then refuses naive values, so the
# exact UTC duration always comes from an aware instant rather than a local
# wall-clock subtraction. Fractional seconds are capped at microseconds, the
# precision the shared engine retains.
_ISO_DATETIME_PATTERN = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})?\Z"
)


def _aware_datetime(
    text: str, label: str, violations: list[tuple[str, str]]
) -> datetime | None:
    """Parse one ISO-8601 timestamp and require an explicit UTC offset."""

    if not _ISO_DATETIME_PATTERN.match(text):
        violations.append(
            (
                "DATETIME_STRING_INVALID",
                f"{label}={text!r} must be an ISO-8601 timestamp such as"
                " '2026-01-01T00:00:00+00:00'",
            )
        )
        return None
    try:
        value = datetime.fromisoformat(text)
    except ValueError:
        violations.append(
            ("DATETIME_STRING_INVALID", f"{label}={text!r} is not a valid timestamp")
        )
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        violations.append(
            (
                "DATETIME_AWARENESS_REQUIRED",
                f"{label}={text!r} must include an explicit UTC offset; a naive"
                " time has no well-defined UTC duration",
            )
        )
        return None
    return value


def _capacity_billing_input(
    body: CapacityBillingRequest, violations: list[tuple[str, str]]
) -> CapacityBillingInput:
    """Translate the wire contract into the shared engine's typed input.

    Only wire syntax is checked here: plain decimal text and aware ISO-8601
    timestamps. Every semantic rule - bounds, identifier shape, provenance,
    unit/currency agreement, duration and the exact billed-energy
    cross-multiplication - stays in the shared engine and is reported through
    its stable codes. Values that failed to parse are irrelevant because the
    caller refuses the request when ``violations`` is non-empty.
    """

    return CapacityBillingInput(
        scenario_id=body.scenario_id,
        tariff_id=body.tariff_id,
        tariff_rate=_exact_decimal(body.tariff_rate, "tariff_rate", violations),
        currency=body.currency,
        tariff_unit=body.tariff_unit,
        booked_capacity_mwh_per_h=_exact_decimal(
            body.booked_capacity_mwh_per_h,
            "booked_capacity_mwh_per_h",
            violations,
        ),
        delivered_energy_mwh=_exact_decimal(
            body.delivered_energy_mwh,
            "delivered_energy_mwh",
            violations,
        ),
        billed_capacity_energy_mwh=_exact_decimal(
            body.billed_capacity_energy_mwh,
            "billed_capacity_energy_mwh",
            violations,
        ),
        billing_start=_aware_datetime(
            body.billing_start, "billing_start", violations
        ),
        billing_end=_aware_datetime(body.billing_end, "billing_end", violations),
        source_references=tuple(body.source_references),
        model_version=body.model_version,
    )


def _capacity_billing_refusal(
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


def _capacity_billing_envelope(result: CapacityBillingResult) -> dict:
    """Serialize one engine result with exact strings and explicit metadata.

    Decimals are emitted as exact fixed-point strings, timestamps as ISO UTC
    offsets and duration as exact integer microseconds, so no JSON encoder ever
    converts a value to a binary float. The metadata states the boundary out
    loud: the basis is caller-supplied and unverified, no booked right or
    physical readiness is established, the output is research with mandatory
    human review and it is not customer approval.
    """

    basis = result.basis
    source_references = list(result.source_references)
    warnings = list(result.warnings)
    data = {
        "research_only": result.research_only,
        "human_review_required": result.human_review_required,
        "model_version": result.model_version,
        "scenario_id": result.scenario_id,
        "tariff_id": result.tariff_id,
        "currency": result.currency,
        "tariff_unit": result.tariff_unit,
        "tariff_rate": _decimal_string(result.tariff_rate),
        "booked_capacity_mwh_per_h": _decimal_string(
            result.booked_capacity_mwh_per_h
        ),
        "billed_capacity_energy_mwh": _decimal_string(
            result.billed_capacity_energy_mwh
        ),
        "delivered_energy_mwh": _decimal_string(result.delivered_energy_mwh),
        "billing_start": result.billing_start.isoformat(),
        "billing_end": result.billing_end.isoformat(),
        "duration_microseconds": basis.duration_microseconds,
        "duration_hours": _decimal_string(result.duration_hours),
        "total_cost": _decimal_string(result.total_cost),
        "cost_per_delivered_mwh": _decimal_string(result.cost_per_delivered_mwh),
        "basis": {
            "tariff_rate": _decimal_string(basis.tariff_rate),
            "tariff_unit": basis.tariff_unit,
            "booked_capacity_mwh_per_h": _decimal_string(
                basis.booked_capacity_mwh_per_h
            ),
            "billed_capacity_energy_mwh": _decimal_string(
                basis.billed_capacity_energy_mwh
            ),
            "delivered_energy_mwh": _decimal_string(basis.delivered_energy_mwh),
            "billing_start_utc": basis.billing_start_utc.isoformat(),
            "billing_end_utc": basis.billing_end_utc.isoformat(),
            "duration_microseconds": basis.duration_microseconds,
        },
        "provenance": list(result.provenance),
        "source_references": source_references,
        "assumptions": list(result.assumptions),
        "warnings": warnings,
        "lineage": list(result.lineage),
        "physical_readiness": result.physical_readiness,
    }
    return {
        "data": data,
        "meta": {
            "research_only": True,
            "human_review_required": True,
            "decision_context": SANDBOX_SCENARIO,
            "caller_supplied": True,
            "references_verified": False,
            "booked_rights_established": False,
            "physical_readiness": result.physical_readiness,
            "customer_approval": False,
            "source_references": source_references,
            "warnings": warnings,
        },
    }


# --- LNG economics-only helpers ----------------------------------------------


def _declared_enum(enum_type: type, value: str) -> object:
    """Map a declared wire token to its domain enum, leaving unknown text intact.

    Unknown text is deliberately passed through unchanged so the shared domain
    composition reports its own stable refusal code (for example
    ``COST_CATEGORY_INVALID`` or ``STAGE_KIND_INVALID``) instead of this module
    inventing a parallel vocabulary or refusal.
    """

    try:
        return enum_type(value)
    except ValueError:
        return value


def _lng_economics_only_input(
    body: LngEconomicsOnlyRequest, violations: list[tuple[str, str]]
) -> LngEconomicsOnlyInput:
    """Translate the wire contract into the shared composition's typed input.

    Only wire syntax is read here: plain decimal text, ISO calendar-date text
    and the declared enum tokens. Every semantic rule - references, magnitudes,
    conservation, chain adjacency, charged-basis acceptance, duplicate/in-kind
    double charging, dates, discount coverage and cash-leg construction - stays
    in the shared domain composition and is reported through its stable codes.
    Values that failed to parse are irrelevant because the caller refuses the
    request when ``violations`` is non-empty.
    """

    downstream_costs = tuple(
        LngEconomicsOnlyCostInput(
            cost_id=cost.cost_id,
            category=_declared_enum(CashFlowLegCategory, cost.category),
            amount_eur=_exact_decimal(
                cost.amount_eur, f"downstream_costs[{position}].amount_eur", violations
            ),
            payment_date=_calendar_date(
                cost.payment_date,
                f"downstream_costs[{position}].payment_date",
                violations,
            ),
            source_reference=cost.source_reference,
            charge_basis=_declared_enum(
                LngDownstreamChargeBasis, cost.charge_basis
            ),
        )
        for position, cost in enumerate(body.downstream_costs)
    )
    energy_stages = tuple(
        LngEnergyStage(
            stage_id=stage.stage_id,
            kind=_declared_enum(LngEnergyStageKind, stage.kind),
            input_energy_mwh=_exact_decimal(
                stage.input_energy_mwh,
                f"energy_stages[{position}].input_energy_mwh",
                violations,
            ),
            output_energy_mwh=_exact_decimal(
                stage.output_energy_mwh,
                f"energy_stages[{position}].output_energy_mwh",
                violations,
            ),
            consumed_energy_mwh=_exact_decimal(
                stage.consumed_energy_mwh,
                f"energy_stages[{position}].consumed_energy_mwh",
                violations,
            ),
            physical_loss_energy_mwh=_exact_decimal(
                stage.physical_loss_energy_mwh,
                f"energy_stages[{position}].physical_loss_energy_mwh",
                violations,
            ),
            source_references=tuple(stage.source_references),
        )
        for position, stage in enumerate(body.energy_stages)
    )
    discount_factors = tuple(
        LngCashDiscountFactorInput(
            payment_date=_calendar_date(
                item.payment_date,
                f"discount_factors[{position}].payment_date",
                violations,
            ),
            factor=_exact_decimal(
                item.factor, f"discount_factors[{position}].factor", violations
            ),
            curve_reference=item.curve_reference,
            source_reference=item.source_reference,
            as_of=_calendar_date(
                item.as_of, f"discount_factors[{position}].as_of", violations
            ),
        )
        for position, item in enumerate(body.discount_factors)
    )

    return LngEconomicsOnlyInput(
        contract_id=body.contract_id,
        cargo_id=body.cargo_id,
        terminal_id=body.terminal_id,
        resource_id=body.resource_id,
        valuation_date=_calendar_date(
            body.valuation_date, "valuation_date", violations
        ),
        reporting_currency=body.reporting_currency,
        energy_basis_reference=body.energy_basis_reference,
        energy_unit=body.energy_unit,
        purchased_energy_mwh=_exact_decimal(
            body.purchased_energy_mwh, "purchased_energy_mwh", violations
        ),
        delivered_energy_mwh=_exact_decimal(
            body.delivered_energy_mwh, "delivered_energy_mwh", violations
        ),
        purchase_unit_price_eur_per_mwh=_exact_decimal(
            body.purchase_unit_price_eur_per_mwh,
            "purchase_unit_price_eur_per_mwh",
            violations,
        ),
        sale_unit_price_eur_per_mwh=_exact_decimal(
            body.sale_unit_price_eur_per_mwh,
            "sale_unit_price_eur_per_mwh",
            violations,
        ),
        purchase_price_source_reference=body.purchase_price_source_reference,
        sale_price_source_reference=body.sale_price_source_reference,
        purchase_basis=body.purchase_basis,
        purchase_included_cost_items=tuple(
            _declared_enum(CashFlowLegCategory, item)
            for item in body.purchase_included_cost_items
        ),
        cost_scope_statement=body.cost_scope_statement,
        purchase_payment_date=_calendar_date(
            body.purchase_payment_date, "purchase_payment_date", violations
        ),
        sale_payment_date=_calendar_date(
            body.sale_payment_date, "sale_payment_date", violations
        ),
        downstream_costs=downstream_costs,
        energy_stages=energy_stages,
        discount_factors=discount_factors,
        model_version=body.model_version,
    )


def _lng_economics_only_refusal(
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


def _lng_cash_leg_payload(leg) -> dict:
    """Serialize one embedded cash-valuation leg with exact strings."""

    return {
        "leg_id": leg.leg_id,
        "category": leg.category.value,
        "payment_date": leg.payment_date.isoformat(),
        "currency": leg.currency,
        "signed_amount": _decimal_string(leg.signed_amount),
        "cash_amount_reporting_ccy": _decimal_string(
            leg.cash_amount_reporting_ccy
        ),
        "present_value_reporting_ccy": _decimal_string(
            leg.present_value_reporting_ccy
        ),
        "discount_factor": _decimal_string(leg.discount_factor),
        "discount_curve_reference": leg.discount_curve_reference,
        "discount_source_reference": leg.discount_source_reference,
        "discount_as_of": leg.discount_as_of.isoformat(),
        "source_reference": leg.source_reference,
        "fx_rate_reporting_per_leg": _decimal_string(
            leg.fx_rate_reporting_per_leg
        ),
        "fx_source_reference": leg.fx_source_reference,
        "fx_as_of": leg.fx_as_of.isoformat() if leg.fx_as_of is not None else None,
        "description": leg.description,
    }


def _lng_cash_valuation_payload(result) -> dict:
    """Serialize the embedded bounded cash-valuation result exactly."""

    return {
        "model_version": result.model_version,
        "contract_id": result.contract_id,
        "cargo_id": result.cargo_id,
        "terminal_id": result.terminal_id,
        "resource_id": result.resource_id,
        "valuation_date": result.valuation_date.isoformat(),
        "reporting_currency": result.reporting_currency,
        "leg_valuations": [
            _lng_cash_leg_payload(leg) for leg in result.leg_valuations
        ],
        "total_undiscounted_cash_reporting_ccy": _decimal_string(
            result.total_undiscounted_cash_reporting_ccy
        ),
        "net_present_value_reporting_ccy": _decimal_string(
            result.net_present_value_reporting_ccy
        ),
        "assumptions": list(result.assumptions),
        "warnings": list(result.warnings),
        "source_references": list(result.source_references),
        "lineage": list(result.lineage),
        "research_only": result.research_only,
        "human_review_required": result.human_review_required,
    }


def _lng_energy_stage_payload(stage) -> dict:
    """Serialize one explicit energy stage with exact strings."""

    return {
        "stage_id": stage.stage_id,
        "kind": stage.kind.value,
        "input_energy_mwh": _decimal_string(stage.input_energy_mwh),
        "output_energy_mwh": _decimal_string(stage.output_energy_mwh),
        "consumed_energy_mwh": _decimal_string(stage.consumed_energy_mwh),
        "physical_loss_energy_mwh": _decimal_string(
            stage.physical_loss_energy_mwh
        ),
        "source_references": list(stage.source_references),
    }


def _lng_energy_balance_payload(result) -> dict:
    """Serialize the explicit ordered energy balance exactly."""

    return {
        "model_version": result.model_version,
        "purchased_energy_mwh": _decimal_string(result.purchased_energy_mwh),
        "delivered_energy_mwh": _decimal_string(result.delivered_energy_mwh),
        "energy_basis_reference": result.energy_basis_reference,
        "energy_unit": result.energy_unit,
        "total_consumed_energy_mwh": _decimal_string(
            result.total_consumed_energy_mwh
        ),
        "physical_loss_energy_mwh": _decimal_string(
            result.physical_loss_energy_mwh
        ),
        "total_reduction_energy_mwh": _decimal_string(
            result.total_reduction_energy_mwh
        ),
        "stage_count": result.stage_count,
        "stages": [
            _lng_energy_stage_payload(stage) for stage in result.stages
        ],
        "warnings": list(result.warnings),
        "source_references": list(result.source_references),
        "research_only": result.research_only,
        "human_review_required": result.human_review_required,
    }


def _lng_economics_only_envelope(result: LngEconomicsOnlyResult) -> dict:
    """Serialize one economics-only result with exact strings and boundaries.

    Decimals are emitted as exact fixed-point strings and dates as ISO dates, so
    no JSON encoder ever converts a value to a binary float. The metadata states
    the boundary out loud: every input is caller-supplied and unverified, no
    physical readiness was assessed, and the output is research with mandatory
    human review, not customer approval or delivery feasibility.
    """

    source_references = list(result.source_references)
    warnings = list(result.warnings)
    data = {
        "research_only": result.research_only,
        "human_review_required": result.human_review_required,
        "model_version": result.model_version,
        "action": ActionKind.COMPUTE_CASH_FLOW.value,
        "contract_id": result.contract_id,
        "cargo_id": result.cargo_id,
        "terminal_id": result.terminal_id,
        "resource_id": result.resource_id,
        "valuation_date": result.valuation_date.isoformat(),
        "reporting_currency": result.reporting_currency,
        "energy_basis_reference": result.energy_basis_reference,
        "energy_unit": result.energy_unit,
        "purchased_energy_mwh": _decimal_string(result.purchased_energy_mwh),
        "delivered_energy_mwh": _decimal_string(result.delivered_energy_mwh),
        "total_consumed_energy_mwh": _decimal_string(
            result.total_consumed_energy_mwh
        ),
        "physical_loss_energy_mwh": _decimal_string(
            result.physical_loss_energy_mwh
        ),
        "total_reduction_energy_mwh": _decimal_string(
            result.total_reduction_energy_mwh
        ),
        "purchase_basis": result.purchase_basis,
        "purchase_included_cost_items": [
            item.value for item in result.purchase_included_cost_items
        ],
        "cost_scope_statement": result.cost_scope_statement,
        "purchase_unit_price_eur_per_mwh": _decimal_string(
            result.purchase_unit_price_eur_per_mwh
        ),
        "sale_unit_price_eur_per_mwh": _decimal_string(
            result.sale_unit_price_eur_per_mwh
        ),
        "unit_netback_eur_per_purchased_mwh": _decimal_string(
            result.unit_netback_eur_per_purchased_mwh
        ),
        "sale_basis_eur_per_delivered_mwh": _decimal_string(
            result.sale_basis_eur_per_delivered_mwh
        ),
        "purchase_outlay_eur": _decimal_string(result.purchase_outlay_eur),
        "sale_proceeds_eur": _decimal_string(result.sale_proceeds_eur),
        "total_downstream_costs_eur": _decimal_string(
            result.total_downstream_costs_eur
        ),
        "cargo_margin_eur": _decimal_string(result.cargo_margin_eur),
        "margin_reconciliation_gap_eur": _decimal_string(
            result.margin_reconciliation_gap_eur
        ),
        "margin_reconciliation_tolerance_eur": _decimal_string(
            result.margin_reconciliation_tolerance_eur
        ),
        "net_present_value_eur": _decimal_string(result.net_present_value_eur),
        "total_undiscounted_cash_eur": _decimal_string(
            result.total_undiscounted_cash_eur
        ),
        "cash_valuation": _lng_cash_valuation_payload(result.cash_valuation),
        "energy_balance": _lng_energy_balance_payload(result.energy_balance),
        "physical_readiness": result.physical_readiness,
        "readiness_assessed": result.readiness_assessed,
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
            "physical_readiness": result.physical_readiness,
            "readiness_assessed": result.readiness_assessed,
            "customer_approval": False,
            "source_references": source_references,
            "warnings": warnings,
        },
    }
