"""Capacity-constrained route and sale-market recommendation."""

from __future__ import annotations

from collections.abc import Sequence

from pydantic import BaseModel, Field

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
    route_id: str
    route_name: str
    destination_market: str | None = None
    sale_price: float | None = None
    price_currency: str | None = None
    price_unit: str | None = None
    required_tso_access: list[str] = Field(default_factory=list)
    available_capacity_mwh_per_day: float | None = None
    tariff_legs: list[RouteTariffLeg] = Field(default_factory=list)
    manual_cost: float | None = None
    cost_currency: str | None = None
    cost_unit: str | None = None
    notes: list[str] = Field(default_factory=list)


class RouteRecommendationRequest(BaseModel):
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
    route_id: str
    route_name: str
    blockers: list[str] = Field(default_factory=list)
    route_cost: float | None = None
    netback: float | None = None


class RouteRecommendationResult(BaseModel):
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

    When sale prices are supplied, ranking is by netback. When sale prices are
    unavailable, ranking falls back to lowest compatible route cost.
    """

    warnings: list[str] = []
    excluded: list[ExcludedRoute] = []
    evaluated: list[_EvaluatedRoute] = []

    for candidate in request.candidates:
        evaluation = _evaluate_candidate(request, candidate, tariffs)
        if evaluation.blockers:
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

    status = "SUCCESS" if unallocated == 0 and allocations else "PARTIAL"
    if not allocations:
        status = "BLOCKED"

    if selected_ids:
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
    blockers = _tso_access_blockers(candidate, request.company_accessible_tsos)
    route_cost, currency, unit, cost_blockers = _candidate_cost(request, candidate, tariffs)
    blockers.extend(cost_blockers)
    blockers = list(dict.fromkeys(blockers))
    netback = _candidate_netback(candidate, route_cost, currency, unit)
    if candidate.sale_price is not None and netback is None and not blockers:
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
    if candidate.sale_price is None:
        return None
    if route_cost is None:
        return None
    if candidate.price_currency and currency and candidate.price_currency != currency:
        return None
    if candidate.price_unit and unit and candidate.price_unit != unit:
        return None
    return round(candidate.sale_price - route_cost, 6)


def _tso_access_blockers(
    candidate: RouteOptionCandidate,
    accessible_tsos: Sequence[str] | None,
) -> list[str]:
    if accessible_tsos is None:
        return []
    allowed = {item.strip().lower() for item in accessible_tsos if item.strip()}
    return [
        f"TSO_ACCESS_MISSING:{tso}"
        for tso in candidate.required_tso_access
        if tso.strip() and tso.strip().lower() not in allowed
    ]


def _ranking_key(route: _EvaluatedRoute) -> tuple[int, float, float, str]:
    if route.netback is not None:
        return (0, -route.netback, route.route_cost or 0.0, route.candidate.route_id)
    if route.route_cost is not None:
        return (1, route.route_cost, 0.0, route.candidate.route_id)
    return (2, 0.0, 0.0, route.candidate.route_id)


def _allocation_rationale(route: _EvaluatedRoute) -> list[str]:
    rationale: list[str] = []
    if route.netback is not None:
        rationale.append("selected_by_highest_executable_netback")
    elif route.route_cost is not None:
        rationale.append("selected_by_lowest_route_cost")
    if route.candidate.available_capacity_mwh_per_day is not None:
        rationale.append("capacity_constrained_allocation")
    if not rationale:
        rationale.append("operator_review_required")
    return rationale


def _deduplicate_exclusions(
    excluded: Sequence[ExcludedRoute],
    selected_ids: set[str],
) -> list[ExcludedRoute]:
    deduped: dict[str, ExcludedRoute] = {}
    for route in excluded:
        if route.route_id in selected_ids:
            continue
        deduped.setdefault(route.route_id, route)
    return list(deduped.values())
