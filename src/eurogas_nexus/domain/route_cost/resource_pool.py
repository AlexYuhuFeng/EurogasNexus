"""Portfolio resource-pool allocation and selling-option decision support."""

from __future__ import annotations

from pydantic import BaseModel, Field

from eurogas_nexus.domain.route_cost.enums import DeliveryMode, SourceResourceType


class PortfolioResource(BaseModel):
    resource_id: str
    resource_name: str
    resource_type: SourceResourceType
    delivery_mode: DeliveryMode
    location_point_name: str
    available_quantity_mwh_per_day: float
    contract_cost_gbp_mwh: float
    variable_cost_gbp_mwh: float = 0.0
    delivery_tolerance_pct: float | None = None
    nomination_tolerance_pct: float | None = None
    tolerance_risk_allowance_gbp_mwh: float = 0.0
    upstream_payment_lag_days: int = 20
    settlement_frequency: str = "monthly"
    required_tso_access: list[str] = Field(default_factory=list)
    accessible_tsos: list[str] | None = None
    pricing_method: str = "FIXED_PRICE"
    source_refs: list[str] = Field(default_factory=list)


class PortfolioSaleOption(BaseModel):
    option_id: str
    label: str
    delivery_mode: DeliveryMode
    target_point_name: str
    sale_price_gbp_mwh: float
    route_cost_gbp_mwh: float = 0.0
    capacity_limit_mwh_per_day: float | None = None
    screen_sale_cash_lag_days: int = 1
    required_tso_access: list[str] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)


class PortfolioOptimizationScenario(BaseModel):
    portfolio_id: str
    resources: list[PortfolioResource]
    sale_options: list[PortfolioSaleOption]
    annual_financing_rate_pct: float = 6.0
    objective: str = "MAX_DAILY_PNL"
    research_only: bool = True


class PortfolioAllocation(BaseModel):
    resource_id: str
    option_id: str
    allocated_quantity_mwh_per_day: float
    gross_sale_price_gbp_mwh: float
    total_cost_gbp_mwh: float
    early_cash_value_gbp_mwh: float
    net_margin_gbp_mwh: float
    net_pnl_gbp_per_day: float
    warnings: list[str] = Field(default_factory=list)


class PortfolioOptimizationResult(BaseModel):
    portfolio_id: str
    status: str
    total_allocated_mwh_per_day: float
    total_unallocated_mwh_per_day: float
    total_net_pnl_gbp_per_day: float
    allocations: list[PortfolioAllocation] = Field(default_factory=list)
    missing_inputs: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)
    research_only: bool = True
    human_review_required: bool = True


def optimize_resource_pool(
    scenario: PortfolioOptimizationScenario,
) -> PortfolioOptimizationResult:
    """Allocate portfolio resources to sale options by best available marginal PnL."""

    missing_inputs: list[str] = []
    warnings: list[str] = []
    source_refs = _unique(
        [
            *[ref for resource in scenario.resources for ref in resource.source_refs],
            *[ref for option in scenario.sale_options for ref in option.source_refs],
        ]
    )
    remaining_resource = {
        resource.resource_id: max(resource.available_quantity_mwh_per_day, 0.0)
        for resource in scenario.resources
    }
    remaining_option_capacity = {
        option.option_id: option.capacity_limit_mwh_per_day
        for option in scenario.sale_options
    }

    candidates: list[tuple[float, PortfolioResource, PortfolioSaleOption, list[str]]] = []
    for resource in scenario.resources:
        resource_warnings = _resource_warnings(resource)
        missing_inputs.extend(_resource_missing_inputs(resource))
        for option in scenario.sale_options:
            pair_warnings = [*resource_warnings]
            inaccessible_tsos = _inaccessible_tsos(
                _unique([*resource.required_tso_access, *option.required_tso_access]),
                resource.accessible_tsos,
            )
            if inaccessible_tsos:
                pair_warnings.append(
                    "TSO_ACCESS_MISSING:" + ",".join(inaccessible_tsos)
                )
                continue
            if not _delivery_modes_compatible(resource.delivery_mode, option.delivery_mode):
                continue
            early_cash = _early_cash_value_gbp_mwh(
                resource,
                option,
                annual_financing_rate_pct=scenario.annual_financing_rate_pct,
            )
            total_cost = (
                resource.contract_cost_gbp_mwh
                + resource.variable_cost_gbp_mwh
                + resource.tolerance_risk_allowance_gbp_mwh
                + option.route_cost_gbp_mwh
                - early_cash
            )
            margin = round(option.sale_price_gbp_mwh - total_cost, 4)
            candidates.append((margin, resource, option, pair_warnings))

    allocations: list[PortfolioAllocation] = []
    for margin, resource, option, pair_warnings in sorted(
        candidates,
        key=lambda item: item[0],
        reverse=True,
    ):
        if margin <= 0:
            warnings.append("NON_POSITIVE_MARGIN_OPTION_SKIPPED")
            continue
        available = remaining_resource[resource.resource_id]
        if available <= 0:
            continue
        option_capacity = remaining_option_capacity[option.option_id]
        allocatable = available if option_capacity is None else min(available, option_capacity)
        if allocatable <= 0:
            continue

        early_cash = _early_cash_value_gbp_mwh(
            resource,
            option,
            annual_financing_rate_pct=scenario.annual_financing_rate_pct,
        )
        total_cost = round(
            resource.contract_cost_gbp_mwh
            + resource.variable_cost_gbp_mwh
            + resource.tolerance_risk_allowance_gbp_mwh
            + option.route_cost_gbp_mwh
            - early_cash,
            4,
        )
        pnl = round(margin * allocatable, 4)
        allocations.append(
            PortfolioAllocation(
                resource_id=resource.resource_id,
                option_id=option.option_id,
                allocated_quantity_mwh_per_day=round(allocatable, 4),
                gross_sale_price_gbp_mwh=option.sale_price_gbp_mwh,
                total_cost_gbp_mwh=total_cost,
                early_cash_value_gbp_mwh=early_cash,
                net_margin_gbp_mwh=margin,
                net_pnl_gbp_per_day=pnl,
                warnings=_unique(pair_warnings),
            )
        )
        remaining_resource[resource.resource_id] = round(available - allocatable, 4)
        if option_capacity is not None:
            remaining_option_capacity[option.option_id] = round(option_capacity - allocatable, 4)

    total_allocated = round(sum(item.allocated_quantity_mwh_per_day for item in allocations), 4)
    total_available = round(
        sum(resource.available_quantity_mwh_per_day for resource in scenario.resources),
        4,
    )
    total_pnl = round(sum(item.net_pnl_gbp_per_day for item in allocations), 4)
    total_unallocated = round(max(total_available - total_allocated, 0.0), 4)
    if total_unallocated > 0:
        warnings.append("PORTFOLIO_VOLUME_UNALLOCATED")
    status = "SUCCESS" if allocations and not missing_inputs else "PARTIAL"
    if not allocations:
        status = "BLOCKED"

    return PortfolioOptimizationResult(
        portfolio_id=scenario.portfolio_id,
        status=status,
        total_allocated_mwh_per_day=total_allocated,
        total_unallocated_mwh_per_day=total_unallocated,
        total_net_pnl_gbp_per_day=total_pnl,
        allocations=allocations,
        missing_inputs=_unique(missing_inputs),
        warnings=_unique(warnings),
        source_refs=source_refs,
        research_only=True,
        human_review_required=True,
    )


def _delivery_modes_compatible(
    resource_mode: DeliveryMode,
    option_mode: DeliveryMode,
) -> bool:
    if resource_mode == option_mode:
        return True
    if resource_mode is DeliveryMode.PHYSICAL_ENTRY_DELIVERY and option_mode in {
        DeliveryMode.VIRTUAL_HUB_SALE,
        DeliveryMode.DOWNSTREAM_PHYSICAL_DELIVERY,
    }:
        return True
    if resource_mode is DeliveryMode.TERMINAL_TITLE_TRANSFER:
        return option_mode is DeliveryMode.TERMINAL_TITLE_TRANSFER
    return False


def _resource_missing_inputs(resource: PortfolioResource) -> list[str]:
    missing: list[str] = []
    if resource.delivery_tolerance_pct is None:
        missing.append(f"DELIVERY_TOLERANCE_MISSING:{resource.resource_id}")
    if resource.nomination_tolerance_pct is None:
        missing.append(f"NOMINATION_TOLERANCE_MISSING:{resource.resource_id}")
    return missing


def _resource_warnings(resource: PortfolioResource) -> list[str]:
    warnings: list[str] = []
    if resource.pricing_method.upper() not in {
        "FIXED_PRICE",
        "DAILY_INDEX",
        "MONTHLY_INDEX",
        "TTF",
        "NBP",
        "BRENT",
        "ICIS",
        "PLATTS",
        "FORMULA",
    }:
        warnings.append(f"UNKNOWN_PRICING_METHOD:{resource.resource_id}")
    return warnings


def _early_cash_value_gbp_mwh(
    resource: PortfolioResource,
    option: PortfolioSaleOption,
    *,
    annual_financing_rate_pct: float,
) -> float:
    lag_days = max(resource.upstream_payment_lag_days - option.screen_sale_cash_lag_days, 0)
    annual_rate = annual_financing_rate_pct / 100
    base_cost = resource.contract_cost_gbp_mwh + resource.variable_cost_gbp_mwh
    return round(base_cost * annual_rate * lag_days / 365, 4)


def _inaccessible_tsos(
    required_tso_access: list[str],
    company_accessible_tsos: list[str] | None,
) -> list[str]:
    if company_accessible_tsos is None:
        return []
    allowed = {item.strip().lower() for item in company_accessible_tsos if item.strip()}
    return [
        tso
        for tso in required_tso_access
        if tso.strip() and tso.strip().lower() not in allowed
    ]


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))
