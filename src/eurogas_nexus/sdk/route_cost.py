"""SDK client for DB-first route-cost and contract decision-support APIs."""

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


class EasingtonOptionPnl(BaseModel):
    option_id: str
    label: str
    business_model: str
    sale_price_gbp_mwh: float
    contract_cost_gbp_mwh: float
    entry_capacity_charge_gbp_mwh: float
    exit_capacity_charge_gbp_mwh: float
    commodity_charge_gbp_mwh: float
    tolerance_risk_allowance_gbp_mwh: float
    early_cash_value_gbp_mwh: float
    total_charges_gbp_mwh: float
    net_margin_gbp_mwh: float
    net_pnl_gbp_per_day: float
    source_refs: list[str] = Field(default_factory=list)
    route_legs: list[dict] = Field(default_factory=list)
    tariff_status_summary: dict[str, int] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
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


class EasingtonContractOptionsResult(BaseModel):
    contract_id: str
    gas_year: str
    delivery_point_name: str
    delivery_quantity_mwh_per_day: float
    delivery_tolerance_pct: float
    nomination_tolerance_pct: float
    delivery_tolerance_mwh: float
    nomination_tolerance_mwh: float
    options: list[EasingtonOptionPnl] = Field(default_factory=list)
    missing_inputs: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)
    research_only: bool
    human_review_required: bool


class LiveStrategySignal(BaseModel):
    suggestion_type: str
    suggested_action: str
    rationale: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    human_review_required: bool


class LiveOptionMarkResult(BaseModel):
    option_id: str
    venue: str
    hub: str
    product: str
    status: str
    mark_price_gbp_mwh: float | None = None
    live_net_margin_gbp_mwh: float | None = None
    live_net_pnl_gbp_per_day: float | None = None
    missing_inputs: list[str] = Field(default_factory=list)
    signal: LiveStrategySignal
    human_review_required: bool


class EasingtonLivePnlResult(EasingtonContractOptionsResult):
    live_marks: list[LiveOptionMarkResult] = Field(default_factory=list)


def _get(url: str) -> dict:
    response = httpx.get(url, timeout=10)
    response.raise_for_status()
    return response.json()["data"]


def _post(url: str, json_body: dict) -> dict:
    response = httpx.post(url, json=json_body, timeout=15)
    response.raise_for_status()
    return response.json()["data"]


def fetch_uk_easington_tariffs(base_url: str) -> list[RouteCostTariff]:
    data = _get(f"{base_url}/api/v1/route-cost/uk/tariffs/easington")
    return [RouteCostTariff(**row) for row in data["tariffs"]]


def fetch_uk_nts_tariffs(
    base_url: str,
    *,
    point_name: str | None = None,
    direction: str | None = None,
    gas_year: str | None = None,
) -> list[RouteCostTariff]:
    params = []
    if point_name:
        params.append(("point_name", point_name))
    if direction:
        params.append(("direction", direction))
    if gas_year:
        params.append(("gas_year", gas_year))
    query = f"?{urlencode(params)}" if params else ""
    data = _get(f"{base_url}/api/v1/route-cost/uk/tariffs{query}")
    return [RouteCostTariff(**row) for row in data["tariffs"]]


def fetch_route_candidates(base_url: str) -> list[dict]:
    data = _get(f"{base_url}/api/v1/route-cost/route-candidates")
    return data["route_candidates"]


def calculate_uk_nts_route_cost(base_url: str, **kwargs) -> RouteCostResult:
    data = _post(f"{base_url}/api/v1/route-cost/calculate", kwargs)
    return RouteCostResult(**data)


def assess_lng_regas(base_url: str, **kwargs) -> LngRegasReadinessResult:
    data = _post(f"{base_url}/api/v1/route-cost/lng-regas/assess", kwargs)
    return LngRegasReadinessResult(**data)


def optimize_resource_pool(base_url: str, **kwargs) -> PortfolioOptimizationResult:
    data = _post(f"{base_url}/api/v1/route-cost/resource-pool/optimize", kwargs)
    return PortfolioOptimizationResult(**data)


def compare_easington_contract_options(base_url: str, **kwargs) -> EasingtonContractOptionsResult:
    data = _post(f"{base_url}/api/v1/route-cost/uk/easington/options", kwargs)
    return EasingtonContractOptionsResult(**data)


def mark_easington_live_pnl(base_url: str, **kwargs) -> EasingtonLivePnlResult:
    data = _post(f"{base_url}/api/v1/route-cost/uk/easington/live-pnl", kwargs)
    return EasingtonLivePnlResult(**data)
