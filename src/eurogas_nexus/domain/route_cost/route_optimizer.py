"""Capacity-constrained route and sale-market recommendation.

本模块是"容量约束下的路线/销售市场推荐"唯一实现：先对候选路线做
TSO 准入、容量、成本/净回值评估（fail-closed），再按经济性排序分配
需求量；结果永远带 assumptions/warnings 且要求人工复核。
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from datetime import date, datetime

from pydantic import BaseModel, Field, field_validator, model_validator

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
from eurogas_nexus.domain.route_cost.tariff_selection import (
    TARIFF_APPLICABILITY_NOT_ASSESSED,
)


def _explicit_calendar_date_value(value: object) -> object:
    """Refuse timestamp/numeric coercion into an asserted applicability date."""

    if value is None or (isinstance(value, date) and not isinstance(value, datetime)):
        return value
    if isinstance(value, str) and len(value) == 10:
        parsed = date.fromisoformat(value)
        if parsed.isoformat() == value:
            return value
    raise ValueError("tariff_applicability_date must be an explicit YYYY-MM-DD date")


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
        manual_cost: Operator-supplied route cost override, or None. ``None`` is
            unknown, never zero; only an explicit ``0.0`` is a known zero cost.
        cost_currency: Currency of the manual cost.
        cost_unit: Unit of the manual cost.
        tariff_applicability_date: The source option's own tariff date, when the
            caller knows it. It is evidence, not a second selector: a value that
            disagrees with the request-level date blocks the candidate.
        source_refs: Caller-supplied provenance references for this candidate.
            They are echoed on a selected allocation as unverified input
            provenance only; they grant no entitlement and are never used as an
            economic input.
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
    tariff_applicability_date: date | None = None
    source_refs: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)

    @field_validator("tariff_applicability_date", mode="before")
    @classmethod
    def _explicit_source_calendar_date(cls, value: object) -> object:
        """Refuse timestamp/numeric coercion into a source-option date."""

        return _explicit_calendar_date_value(value)

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
        gas_year: Gas year of the allocation. It filters tariff identity and is
            never used as a date proxy.
        tariff_applicability_date: Explicit calendar date the selected tariffs
            must cover, or None. None means applicability is not assessed; no
            clock, gas year or metadata instant is substituted.
        capacity_product: Capacity product requested.
        firmness: Firmness requested.
        company_accessible_tsos: Company's accessible TSOs, or None.
        candidates: Candidate routes/sale options to evaluate.
        analysis_snapshot_id: Optional Analysis Snapshot this run was computed
            against. When supplied the caller asserts the reproducibility
            reference; the result carries it so the produced recommendation can
            be reproduced from the same input versions.
    """

    request_id: str
    source_point_id: str
    target_point_id: str | None = None
    required_quantity_mwh_per_day: float
    gas_year: str
    tariff_applicability_date: date | None = None
    capacity_product: CapacityProduct
    firmness: Firmness
    company_accessible_tsos: list[str] | None = None
    candidates: list[RouteOptionCandidate] = Field(default_factory=list)
    analysis_snapshot_id: str | None = None

    @field_validator("tariff_applicability_date", mode="before")
    @classmethod
    def _explicit_calendar_date(cls, value: object) -> object:
        """Refuse timestamp/numeric coercion into an asserted applicability date."""

        return _explicit_calendar_date_value(value)


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
        source_refs: Provenance of the route cost actually used (tariff rows and
            their source documents), followed by caller-supplied references
            prefixed ``unverified_input:``. The prefixed references are
            provenance claims only: they are not entitlement evidence and are
            never used as an economic input.
        unverified_input_source_refs: The caller-supplied references exactly as
            received (no prefix), reported separately so they cannot be confused
            with backend-verified tariff provenance. They grant no rights.
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
    source_refs: list[str] = Field(default_factory=list)
    unverified_input_source_refs: list[str] = Field(default_factory=list)
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
        tariff_applicability_date: The explicit date the caller declared for
            tariff selection, or None when applicability was not assessed.
        analysis_snapshot_id: The Analysis Snapshot this result was computed
            against, echoed from the request; ``None`` when the caller supplied
            no reproducibility reference.
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
    tariff_applicability_date: date | None = None
    analysis_snapshot_id: str | None = None
    research_only: bool = True
    human_review_required: bool = True


class _EvaluatedRoute(BaseModel):
    """Internal evaluation of one candidate (cost, netback, blockers)."""

    candidate: RouteOptionCandidate
    route_cost: float | None
    currency: str | None
    unit: str | None
    netback: float | None
    source_refs: list[str] = Field(default_factory=list)
    unverified_input_source_refs: list[str] = Field(default_factory=list)
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
    if request.tariff_applicability_date is None:
        # A request without a declared date keeps the legacy selection but must
        # say so at the recommendation level as well as on each priced leg.
        warnings.append(TARIFF_APPLICABILITY_NOT_ASSESSED)
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
        if capacity is None and route.candidate.capacity_status is not CapacityStatus.NOT_REQUIRED:
            # 容量缺失且未明确声明 NOT_REQUIRED：fail-closed 阻断。显式 UNKNOWN
            # 与缺失状态都不能被当作无限容量；只有调用方明确声明 NOT_REQUIRED
            # 的本地销售才允许无容量上限。
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
                source_refs=route.source_refs,
                unverified_input_source_refs=route.unverified_input_source_refs,
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
            "A candidate whose cost is missing or cannot be priced is excluded; "
            "an unknown cost is never treated as a zero charge.",
            "Caller-supplied source references are echoed as unverified input "
            "provenance only; they establish no entitlement and no economics.",
            "Tariff applicability is assessed only against the caller-declared "
            "tariff_applicability_date; no clock, gas year or metadata instant is "
            "substituted for it.",
            "The result is decision support only; it does not execute trades or nominations.",
        ],
        tariff_applicability_date=request.tariff_applicability_date,
        analysis_snapshot_id=request.analysis_snapshot_id,
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
    blockers.extend(_candidate_date_blockers(request, candidate))
    blockers.extend(_sale_price_metadata_blockers(candidate))
    route_cost, currency, unit, cost_blockers, source_refs = _candidate_cost(
        request, candidate, tariffs
    )
    unverified_input_source_refs = list(
        dict.fromkeys(ref for ref in candidate.source_refs if ref)
    )
    source_refs = _unverified_input_refs(source_refs, unverified_input_source_refs)
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
        source_refs=source_refs,
        unverified_input_source_refs=unverified_input_source_refs,
        blockers=blockers,
    )


def _candidate_cost(
    request: RouteRecommendationRequest,
    candidate: RouteOptionCandidate,
    tariffs: Sequence[CapacityTariff],
) -> tuple[float | None, str | None, str | None, list[str], list[str]]:
    """Estimate the candidate's route cost, currency/unit, blockers and sources.

    成本估算优先级：调用方明确给出的手动成本 > 费率腿计算。缺失成本既不是
    零成本，也不从售价币种/单位推断；无法定价的候选被阻断而不是按 0 分配。
    费率腿计算走 route_cost_service，其缺失输入与单位换算告警转为阻断项。
    The caller's explicit ``tariff_applicability_date`` is passed through
    unchanged; an out-of-period, gapped or ambiguous selection blocks the
    candidate instead of becoming a zero charge.
    """

    if candidate.manual_cost is not None:
        if not math.isfinite(candidate.manual_cost):
            return None, None, None, ["ROUTE_COST_INVALID"], []
        metadata_blockers = _manual_cost_metadata_blockers(candidate)
        if metadata_blockers:
            return None, None, None, metadata_blockers, []
        return candidate.manual_cost, candidate.cost_currency, candidate.cost_unit, [], []
    if not candidate.tariff_legs:
        # No manual cost and no leg the backend can price: the cost is unknown,
        # not zero. A candidate with no priceable legs is excluded rather than
        # allocated at an invented zero charge.
        return None, None, None, ["ROUTE_COST_MISSING"], []

    scenario = RouteCostScenario(
        scenario_id=f"{request.request_id}:{candidate.route_id}",
        source_resource_type=SourceResourceType.PIPELINE_IMPORT,
        start_point_id=request.source_point_id,
        target_hub_or_point_id=request.target_point_id or candidate.destination_market or "",
        business_model=BusinessModel.CROSS_BORDER_TRANSFER,
        delivery_mode=DeliveryMode.BORDER_TRANSFER,
        gas_year=request.gas_year,
        tariff_applicability_date=request.tariff_applicability_date,
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
    if result.total_cost is None and not blockers:
        # A blocked route with no stated reason must not be ranked or allocated
        # as if it cost nothing.
        blockers.append("ROUTE_COST_MISSING")
    source_refs = _route_cost_source_refs(result)
    return result.total_cost, result.currency, result.unit, blockers, source_refs


def _route_cost_source_refs(result) -> list[str]:
    """Provenance of the tariff rows and documents used by one route cost."""

    refs = [
        f"tariff_document:{document_id}"
        for document_id in result.used_tariff_documents
    ]
    for component in result.cost_breakdown:
        if component.tariff_id:
            refs.append(f"tariff:{component.tariff_id}")
        refs.extend(component.source_refs)
    return list(dict.fromkeys(refs))


def _candidate_date_blockers(
    request: RouteRecommendationRequest,
    candidate: RouteOptionCandidate,
) -> list[str]:
    """Block a source-option date that disagrees with the request's declared date.

    The request-level date remains the single selector. The candidate date is
    evidence of the option read the caller used; when it names a different day,
    the explicit cost derived for that old day cannot be reused under the new
    request context. A candidate that carries no date keeps the previous
    compatibility path.
    """

    declared = candidate.tariff_applicability_date
    requested = request.tariff_applicability_date
    if declared is None or requested is None or declared == requested:
        return []
    return [f"TARIFF_APPLICABILITY_DATE_MISMATCH:{declared.isoformat()}"]


def _sale_price_metadata_blockers(candidate: RouteOptionCandidate) -> list[str]:
    """Blockers for a supplied sale price whose basis is not usable.

    A sale price is a comparison input, so a missing or non-energy basis would
    let the allocator rank prices it cannot actually compare. The Web adapter
    always sends the backend-normalized GBP/MWh identity; a direct caller that
    omits it fails closed here instead of being treated as compatible.
    """

    if candidate.sale_price is None:
        return []
    if not math.isfinite(candidate.sale_price):
        return ["SALE_PRICE_INVALID"]
    currency = (candidate.price_currency or "").strip()
    unit = (candidate.price_unit or "").strip()
    if not currency or not unit:
        return ["SALE_PRICE_METADATA_MISSING"]
    if not unit.upper().endswith("/MWH"):
        return ["SALE_PRICE_UNIT_INCOMPATIBLE"]
    return []


def _manual_cost_metadata_blockers(candidate: RouteOptionCandidate) -> list[str]:
    """Blockers for a manual cost whose currency/unit identity is not usable.

    A numeric manual cost is an explicitly known amount, but it is only usable
    when the caller also stated the currency and an energy-price unit. Missing
    metadata is never defaulted (for example to EUR) and never inferred from a
    sale-price field; an incompatible unit is refused rather than converted.
    """

    currency = (candidate.cost_currency or "").strip()
    unit = (candidate.cost_unit or "").strip()
    if not currency or not unit:
        return ["ROUTE_COST_METADATA_MISSING"]
    if not unit.upper().endswith("/MWH"):
        return ["ROUTE_COST_UNIT_INCOMPATIBLE"]
    return []


def _unverified_input_refs(
    backend_refs: Sequence[str],
    caller_refs: Sequence[str],
) -> list[str]:
    """Append caller-supplied references as unverified input provenance.

    They are prefixed so a consumer can distinguish them from the tariff and
    document references the backend actually used. They are evidence of what the
    caller claimed, not entitlement and not an economic input.
    """

    refs = list(backend_refs)
    for ref in caller_refs:
        if not ref:
            continue
        refs.append(f"unverified_input:{ref}")
    return list(dict.fromkeys(refs))


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
