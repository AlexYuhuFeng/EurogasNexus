"""SDK client for European route-cost and resource optimization APIs."""

from __future__ import annotations

from urllib.parse import urlencode

import httpx
from pydantic import BaseModel, Field


class RouteCostTariff(BaseModel):
    tariff_id: str
    document_id: str
    country: str
    tso: str
    market_area: str
    gas_year: str
    point_id: str
    source_point_name: str
    direction: str
    capacity_product: str
    firmness: str
    tariff_value: float
    currency: str
    unit: str
    tariff_status: str
    source_refs: list[str] = Field(default_factory=list)


class RouteCostComponent(BaseModel):
    component_type: str
    amount: float | None = None
    currency: str | None = None
    unit: str | None = None
    tariff_id: str | None = None
    source_refs: list[str] = Field(default_factory=list)
    warning: str | None = None
    missing_input: str | None = None


class RouteCostResult(BaseModel):
    scenario_id: str
    status: str
    total_cost: float | None = None
    currency: str | None = None
    unit: str | None = None
    cost_breakdown: list[RouteCostComponent] = Field(default_factory=list)
    used_tariff_documents: list[str] = Field(default_factory=list)
    missing_inputs: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    tariff_status_summary: dict[str, int] = Field(default_factory=dict)
    required_tso_access: list[str] = Field(default_factory=list)
    company_accessible_tsos: list[str] | None = None
    inaccessible_tsos: list[str] = Field(default_factory=list)
    research_only: bool
    human_review_required: bool


class RouteAllocation(BaseModel):
    route_id: str
    route_name: str
    destination_market: str | None = None
    allocated_mwh_per_day: float
    route_cost: float | None = None
    currency: str | None = None
    unit: str | None = None
    sale_price: float | None = None
    netback: float | None = None
    rationale: list[str] = Field(default_factory=list)


class RouteRecommendationResult(BaseModel):
    request_id: str
    status: str
    total_requested_mwh_per_day: float
    total_allocated_mwh_per_day: float
    unallocated_mwh_per_day: float
    allocations: list[RouteAllocation] = Field(default_factory=list)
    excluded_routes: list[dict] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    research_only: bool
    human_review_required: bool


class LngRegasReadinessResult(BaseModel):
    contract_id: str
    cargo_id: str
    terminal_id: str
    terminal_name: str
    terminal_access_status: str
    delivery_mode: str
    physical_entry_delivery_required: bool
    physical_entry_point_name: str | None = None
    required_tso_access: list[str] = Field(default_factory=list)
    inaccessible_tsos: list[str] = Field(default_factory=list)
    pricing_basis_status: str
    estimated_regas_duration_days: float | None = None
    available_slot_days: float | None = None
    slot_capacity_mwh: float | None = None
    slot_capacity_shortfall_mwh: float | None = None
    crosses_month: bool = False
    month_allocations: list[dict] = Field(default_factory=list)
    missing_inputs: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)
    research_only: bool
    human_review_required: bool


class PortfolioOptimizationResult(BaseModel):
    portfolio_id: str
    status: str
    total_allocated_mwh_per_day: float
    total_unallocated_mwh_per_day: float
    total_net_pnl_gbp_per_day: float
    allocations: list[dict] = Field(default_factory=list)
    missing_inputs: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)
    research_only: bool
    human_review_required: bool


def _get(url: str) -> dict:
    response = httpx.get(url, timeout=10)
    response.raise_for_status()
    return response.json()["data"]


def _post(url: str, json_body: dict) -> dict:
    response = httpx.post(url, json=json_body, timeout=15)
    response.raise_for_status()
    return response.json()["data"]


def fetch_tso_tariffs(
    base_url: str,
    *,
    country: str | None = None,
    tso: str | None = None,
    market_area: str | None = None,
    point_name: str | None = None,
    direction: str | None = None,
    gas_year: str | None = None,
) -> list[RouteCostTariff]:
    params = [
        (key, value)
        for key, value in {
            "country": country,
            "tso": tso,
            "market_area": market_area,
            "point_name": point_name,
            "direction": direction,
            "gas_year": gas_year,
        }.items()
        if value is not None
    ]
    query = f"?{urlencode(params)}" if params else ""
    data = _get(f"{base_url}/api/route-cost/tso-tariffs{query}")
    return [RouteCostTariff(**row) for row in data["tariffs"]]


def fetch_route_candidates(base_url: str) -> list[dict]:
    data = _get(f"{base_url}/api/route-cost/route-candidates")
    return data["route_candidates"]


def calculate_route_cost(base_url: str, **kwargs) -> RouteCostResult:
    data = _post(f"{base_url}/api/route-cost/calculate", kwargs)
    return RouteCostResult(**data)


def recommend_route_allocation(base_url: str, **kwargs) -> RouteRecommendationResult:
    data = _post(f"{base_url}/api/route-cost/recommend", kwargs)
    return RouteRecommendationResult(**data)


def assess_lng_regas(base_url: str, **kwargs) -> LngRegasReadinessResult:
    data = _post(f"{base_url}/api/route-cost/lng-regas/assess", kwargs)
    return LngRegasReadinessResult(**data)


def optimize_resource_pool(base_url: str, **kwargs) -> PortfolioOptimizationResult:
    data = _post(f"{base_url}/api/route-cost/resource-pool/optimize", kwargs)
    return PortfolioOptimizationResult(**data)
