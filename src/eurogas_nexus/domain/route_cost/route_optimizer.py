"""Capacity-constrained route and sale-market recommendation.

本模块是"容量约束下的路线/销售市场推荐"唯一实现：先对候选路线做
TSO 准入、容量、成本/净回值评估（fail-closed），再按经济性排序分配
需求量；结果永远带 assumptions/warnings 且要求人工复核。
"""

from __future__ import annotations

from collections.abc import Sequence

from pydantic import BaseModel, Field, model_validator

from eurogas_nexus.domain.constraints.access import (
    inaccessible_tsos,
    tso_access_status,
)
from eurogas_nexus.domain.constraints.route_economics import netback
from eurogas_nexus.domain.ontology.vocabulary import (
    AccessStatus,
    CapacityStatus,
    StatusKind,
)
from eurogas_nexus.domain.route_cost.enums import (
    BusinessModel,
    CapacityProduct,
    DeliveryMode,
    Firmness,
    SourceResourceType,
)
from eurogas_nexus.domain.route_cost.route_cost_service import calculate_route_cost
from eurogas_nexus.domain.route_cost.schemas import RouteCostScenario, RouteTariffLeg
from eurogas_nexus.domain.route_cost.tariff_models import CapacityTariff


class RouteOptionCandidate(BaseModel):
    """One candidate route or sale-market option for the recommendation.

    Attributes:
        route_id: Stable candidate id.
        route_name: Display name.
        destination_market: Target market/hub, or None.
        sale_price: Sale price when known; enables netback ranking.
        price_currency: ISO 4217 code of the sale price.
        price_unit: Unit of the sale price (e.g. ``GBP/MWh``).
        required_tso_access: TSO access codes the route requires.
        available_capacity_mwh_per_day: Known capacity, or None.
        capacity_status: Capacity state; see the validator below.
        tariff_legs: Tariff legs for route-cost estimation.
        manual_cost: Operator-supplied route cost override, or None.
        cost_currency: Currency of the manual cost.
        cost_unit: Unit of the manual cost.
        notes: Free notes (display only).
    """

    route_id: str
    route_name: str
    destination_market: str | None = None
    sale_price: float | None = None
    price_currency: str | None = None
    price_unit: str | None = None
    required_tso_access: list[str] = Field(default_factory=list)
    available_capacity_mwh_per_day: float | None = None
    capacity_status: CapacityStatus = CapacityStatus.UNKNOWN
    tariff_legs: list[RouteTariffLeg] = Field(default_factory=list)
    manual_cost: float | None = None
    cost_currency: str | None = None
    cost_unit: str | None = None
    notes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _infer_capacity_status(self) -> RouteOptionCandidate:
        """A supplied capacity value implies KNOWN status (fail-closed default).

        ``None`` capacity with UNKNOWN status must be treated as a blocker by
        callers; only explicit NOT_REQUIRED means no capacity is needed.

        容量状态推断：给了容量值即视为 KNOWN；未给容量且未声明
        NOT_REQUIRED 的候选在分配阶段会被 BLOCKED（未知即不可放量）。
        """

        if self.available_capacity_mwh_per_day is not None:
            self.capacity_status = CapacityStatus.KNOWN
        return self


class RouteRecommendationRequest(BaseModel):
    """Input request: source point, required volume, candidates.

    Attributes:
        request_id: Stable request id.
        source_point_id: Source point of the volume.
        target_point_id: Target point, or None.
        required_quantity_mwh_per_day: Volume to allocate, MWh/d.
        gas_year: Gas year of the allocation.
        capacity_product: Capacity product requested.
        firmness: Firmness requested.
        company_accessible_tsos: Company's accessible TSOs, or None.
        candidates: Candidate routes/sale options to evaluate.
    """

    request_id: str
    source_point_id: str
    target_point_id: str | None = None
    required_quantity_mwh_per_day: float
    gas_year: str
    capacity_product: CapacityProduct
    firmness: Firmness
    company_accessible_tsos: list[str] | None = None
    candidates: list[RouteOptionCandidate] = Field(default_factory=list)


class RouteAllocation(BaseModel):
    """One allocated slice on a selected route.

    Attributes:
        route_id: Selected route id.
        route_name: Selected route name.
        destination_market: Destination market, or None.
        allocated_mwh_per_day: Allocated volume, MWh/d.
        available_capacity_mwh_per_day: Route capacity used as the cap.
        route_cost: Estimated route cost, or None.
        currency: Cost currency, or None.
        unit: Cost unit, or None.
        sale_price: Sale price, or None.
        netback: Executable netback, or None.
        rationale: Machine-readable selection rationale tags.
    """

    route_id: str
    route_name: str
    destination_market: str | None = None
    allocated_mwh_per_day: float
    available_capacity_mwh_per_day: float | None = None
    route_cost: float | None = None
    currency: str | None = None
    unit: str | None = None
    sale_price: float | None = None
    netback: float | None = None
    rationale: list[str] = Field(default_factory=list)


class ExcludedRoute(BaseModel):
    """One candidate excluded from allocation, with its blockers.

    Attributes:
        route_id: Excluded route id.
        route_name: Excluded route name.
        blockers: Stable blocker codes (TSO/capacity/cost/margin).
        route_cost: Estimated route cost when computable, or None.
        netback: Netback when computable, or None.
    """

    route_id: str
    route_name: str
    blockers: list[str] = Field(default_factory=list)
    route_cost: float | None = None
    netback: float | None = None


class RouteRecommendationResult(BaseModel):
    """Decision-support result of one recommendation run.

    Attributes:
        request_id: Echoed request id.
        status: SUCCESS / PARTIAL / BLOCKED (see StatusKind).
        total_requested_mwh_per_day: Requested volume.
        total_allocated_mwh_per_day: Allocated volume.
        unallocated_mwh_per_day: Volume not allocated.
        allocations: Per-route allocation slices.
        excluded_routes: Candidates excluded with reasons.
        warnings: Aggregated warnings.
        assumptions: Explicit modelling assumptions.
        research_only: Always True — decision support only.
        human_review_required: Always True — never auto-acts.
    """

    request_id: str
    status: str
    total_requested_mwh_per_day: float
    total_allocated_mwh_per_day: float
    unallocated_mwh_per_day: float
    allocations: list[RouteAllocation] = Field(default_factory=list)
    excluded_routes: list[ExcludedRoute] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    research_only: bool = True
    human_review_required: bool = True


class _EvaluatedRoute(BaseModel):
    """Internal evaluation of one candidate (cost, netback, blockers)."""

    candidate: RouteOptionCandidate
    route_cost: float | None
    currency: str | None
    unit: str | None
    netback: float | None
    blockers: list[str] = Field(default_factory=list)


def recommend_route_allocation(
    request: RouteRecommendationRequest,
    tariffs: Sequence[CapacityTariff],
) -> RouteRecommendationResult:
    """Allocate volume to the best executable routes or sale markets.

    按可执行性分配需求量：先评估全部候选（TSO 准入/容量/成本/净回值），
    排除有阻断项者，再按经济性排序依次放量。

    When sale prices are supplied, ranking is by netback. When sale prices are
    unavailable, ranking falls back to lowest compatible route cost.

    Args:
        request: Recommendation request with candidates and required volume.
        tariffs: Available capacity tariffs for route-cost estimation.

    Returns:
        A RouteRecommendationResult with allocations, excluded routes,
        warnings and assumptions. Status is SUCCESS only when the full
        requested volume is allocated; PARTIAL when only part; BLOCKED when
        nothing could be allocated.

    Raises:
        No exceptions; all exclusions are reported in the result.
    """

    warnings: list[str] = []
    excluded: list[ExcludedRoute] = []
    evaluated: list[_EvaluatedRoute] = []

    for candidate in request.candidates:
        evaluation = _evaluate_candidate(request, candidate, tariffs)
        if evaluation.blockers:
            # 有阻断项：进 excluded 清单并带原因，不进排序池。
            excluded.append(
                ExcludedRoute(
                    route_id=candidate.route_id,
                    route_name=candidate.route_name,
                    blockers=evaluation.blockers,
                    route_cost=evaluation.route_cost,
                    netback=evaluation.netback,
                )
            )
        else:
            evaluated.append(evaluation)

    remaining = request.required_quantity_mwh_per_day
    allocations: list[RouteAllocation] = []
    ranked = sorted(evaluated, key=_ranking_key)
    selected_ids: set[str] = set()

    for route in ranked:
        if remaining <= 0:
            # 需求已满足：剩余合格候选按"经济性劣于已选"排除。
            excluded.append(
                ExcludedRoute(
                    route_id=route.candidate.route_id,
                    route_name=route.candidate.route_name,
                    blockers=["ECONOMICALLY_INFERIOR_TO_SELECTED_OPTIONS"],
                    route_cost=route.route_cost,
                    netback=route.netback,
                )
            )
            continue

        capacity = route.candidate.available_capacity_mwh_per_day
        if capacity is None and route.candidate.capacity_status is CapacityStatus.UNKNOWN:
            # 容量未知且未声明 NOT_REQUIRED：fail-closed 阻断。
            excluded.append(
                ExcludedRoute(
                    route_id=route.candidate.route_id,
                    route_name=route.candidate.route_name,
                    blockers=["ROUTE_CAPACITY_UNKNOWN"],
                    route_cost=route.route_cost,
                    netback=route.netback,
                )
            )
            continue
        allocatable = remaining if capacity is None else min(capacity, remaining)
        if allocatable <= 0:
            excluded.append(
                ExcludedRoute(
                    route_id=route.candidate.route_id,
                    route_name=route.candidate.route_name,
                    blockers=["ROUTE_CAPACITY_UNAVAILABLE"],
                    route_cost=route.route_cost,
                    netback=route.netback,
                )
            )
            continue

        selected_ids.add(route.candidate.route_id)
        remaining = round(remaining - allocatable, 6)
        allocations.append(
            RouteAllocation(
                route_id=route.candidate.route_id,
                route_name=route.candidate.route_name,
                destination_market=route.candidate.destination_market,
                allocated_mwh_per_day=round(allocatable, 6),
                available_capacity_mwh_per_day=capacity,
                route_cost=route.route_cost,
                currency=route.currency,
                unit=route.unit,
                sale_price=route.candidate.sale_price,
                netback=route.netback,
                rationale=_allocation_rationale(route),
            )
        )

    total_allocated = round(sum(item.allocated_mwh_per_day for item in allocations), 6)
    unallocated = round(max(request.required_quantity_mwh_per_day - total_allocated, 0.0), 6)
    if unallocated > 0:
        warnings.append("ROUTE_CAPACITY_SHORTFALL")

    status = (
        StatusKind.SUCCESS.value
        if unallocated == 0 and allocations
        else StatusKind.PARTIAL.value
    )
    if not allocations:
        status = StatusKind.BLOCKED.value

    if selected_ids:
        # 已选路线在后续循环中可能被重复记入 excluded，需去重。
        excluded = _deduplicate_exclusions(excluded, selected_ids)

    return RouteRecommendationResult(
        request_id=request.request_id,
        status=status,
        total_requested_mwh_per_day=request.required_quantity_mwh_per_day,
        total_allocated_mwh_per_day=total_allocated,
        unallocated_mwh_per_day=unallocated,
        allocations=allocations,
        excluded_routes=excluded,
        warnings=warnings,
        assumptions=[
            "Candidates with sale prices are ranked by executable netback.",
            "Candidates without sale prices are ranked by lowest route cost.",
            "The result is decision support only; it does not execute trades or nominations.",
        ],
        research_only=True,
        human_review_required=True,
    )


def _evaluate_candidate(
    request: RouteRecommendationRequest,
    candidate: RouteOptionCandidate,
    tariffs: Sequence[CapacityTariff],
) -> _EvaluatedRoute:
    """Evaluate one candidate: TSO access, cost, and netback.

    评估单条候选：先做 TSO 准入阻断检查，再估算路线成本（手动值优先，
    其次按费率腿计算），最后在币种/单位兼容时计算净回值。
    """

    blockers = _tso_access_blockers(candidate, request.company_accessible_tsos)
    route_cost, currency, unit, cost_blockers = _candidate_cost(request, candidate, tariffs)
    blockers.extend(cost_blockers)
    blockers = list(dict.fromkeys(blockers))
    netback = _candidate_netback(candidate, route_cost, currency, unit)
    if candidate.sale_price is not None and netback is None and not blockers:
        # 有售价却算不出净回值：口径不兼容，按阻断处理（不静默比较）。
        blockers.append("PRICE_COST_UNIT_MISMATCH")
    return _EvaluatedRoute(
        candidate=candidate,
        route_cost=route_cost,
        currency=currency,
        unit=unit,
        netback=netback,
        blockers=blockers,
    )


def _candidate_cost(
    request: RouteRecommendationRequest,
    candidate: RouteOptionCandidate,
    tariffs: Sequence[CapacityTariff],
) -> tuple[float | None, str | None, str | None, list[str]]:
    """Estimate the candidate's route cost and its currency/unit/blockers.

    成本估算优先级：手动成本 > 费率腿计算 > 零成本（无腿时按 0 处理）。
    费率腿计算走 route_cost_service，其缺失输入与单位换算告警转为阻断项。
    """

    if candidate.manual_cost is not None:
        return candidate.manual_cost, candidate.cost_currency, candidate.cost_unit, []
    if not candidate.tariff_legs:
        return 0.0, candidate.price_currency, candidate.price_unit, []

    scenario = RouteCostScenario(
        scenario_id=f"{request.request_id}:{candidate.route_id}",
        source_resource_type=SourceResourceType.PIPELINE_IMPORT,
        start_point_id=request.source_point_id,
        target_hub_or_point_id=request.target_point_id or candidate.destination_market or "",
        business_model=BusinessModel.CROSS_BORDER_TRANSFER,
        delivery_mode=DeliveryMode.BORDER_TRANSFER,
        gas_year=request.gas_year,
        capacity_product=request.capacity_product,
        firmness=request.firmness,
        required_tso_access=candidate.required_tso_access,
        company_accessible_tsos=request.company_accessible_tsos,
        tariff_legs=candidate.tariff_legs,
    )
    result = calculate_route_cost(scenario, tariffs)
    blockers = [
        *result.missing_inputs,
        *[warning for warning in result.warnings if warning == "UNIT_CONVERSION_NOT_IMPLEMENTED"],
    ]
    return result.total_cost, result.currency, result.unit, blockers


def _candidate_netback(
    candidate: RouteOptionCandidate,
    route_cost: float | None,
    currency: str | None,
    unit: str | None,
) -> float | None:
    """Compute executable netback; None when price/cost units are incompatible."""

    return netback(
        candidate.sale_price,
        route_cost,
        price_currency=candidate.price_currency,
        cost_currency=currency,
        price_unit=candidate.price_unit,
        cost_unit=unit,
    )


def _tso_access_blockers(
    candidate: RouteOptionCandidate,
    accessible_tsos: Sequence[str] | None,
) -> list[str]:
    """TSO-access blocker codes for a candidate (fail-closed).

    返回 TSO 准入阻断码：未知状态逐 TSO 标记 UNKNOWN，缺失标记 MISSING；
    确认无阻断时返回空列表。
    """

    status = tso_access_status(candidate.required_tso_access, accessible_tsos)
    if status is AccessStatus.UNKNOWN:
        return [
            f"TSO_ACCESS_UNKNOWN:{tso}"
            for tso in candidate.required_tso_access
            if tso.strip()
        ]
    if status is AccessStatus.DENIED:
        return [
            f"TSO_ACCESS_MISSING:{tso}"
            for tso in inaccessible_tsos(candidate.required_tso_access, accessible_tsos)
        ]
    return []


def _ranking_key(route: _EvaluatedRoute) -> tuple[int, float, float, str]:
    """Sort key: netback desc > cost asc > no-price last; id breaks ties.

    排序键：有净回值者优先（净回值降序），其次按成本升序，无价格者最后；
    同键用 route_id 保证排序确定性。
    """

    if route.netback is not None:
        return (0, -route.netback, route.route_cost or 0.0, route.candidate.route_id)
    if route.route_cost is not None:
        return (1, route.route_cost, 0.0, route.candidate.route_id)
    return (2, 0.0, 0.0, route.candidate.route_id)


def _allocation_rationale(route: _EvaluatedRoute) -> list[str]:
    """Machine-readable rationale tags for one allocation."""

    rationale: list[str] = []
    if route.netback is not None:
        rationale.append("selected_by_highest_executable_netback")
    elif route.route_cost is not None:
        rationale.append("selected_by_lowest_route_cost")
    if route.candidate.available_capacity_mwh_per_day is not None:
        rationale.append("capacity_constrained_allocation")
    if not rationale:
        # 无明确经济依据时要求人工复核，而不是给出无依据的"推荐"。
        rationale.append("operator_review_required")
    return rationale


def _deduplicate_exclusions(
    excluded: Sequence[ExcludedRoute],
    selected_ids: set[str],
) -> list[ExcludedRoute]:
    """Deduplicate exclusions, dropping routes that were actually selected.

    去重排除清单：删除最终被选中的路线（循环中可能被误记一次），
    其余按 route_id 首次出现保留。
    """

    deduped: dict[str, ExcludedRoute] = {}
    for route in excluded:
        if route.route_id in selected_ids:
            continue
        deduped.setdefault(route.route_id, route)
    return list(deduped.values())
