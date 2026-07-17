"""Contract take and dispatch optimization."""

from __future__ import annotations

import math

from ._validation import validate_supply_resources
from .models import ContractDispatch, OptimizationResult, SupplyResource


def optimize_contract_dispatch(
    resources: list[SupplyResource],
    market_price_gbp_mwh: float,
    demand_limit_mwh: float,
) -> OptimizationResult:
    """Choose daily contract takes against one market netback.

    Minimum-take volumes are scheduled first. Remaining demand is filled from
    the highest-margin resources, while negative-margin discretionary volume is
    not selected.
    """

    validate_supply_resources(resources)
    if not math.isfinite(market_price_gbp_mwh):
        raise ValueError("market_price_gbp_mwh must be finite")
    if not math.isfinite(demand_limit_mwh):
        raise ValueError("demand_limit_mwh must be finite")
    if demand_limit_mwh < 0:
        raise ValueError("demand_limit_mwh must be non-negative")

    remaining_demand = demand_limit_mwh
    dispatch_quantities = {resource.resource_id: 0.0 for resource in resources}
    mandatory_quantities = {resource.resource_id: 0.0 for resource in resources}
    unmet_minimum = 0.0

    mandatory_order = sorted(
        resources,
        key=lambda resource: market_price_gbp_mwh - resource.unit_cost_gbp_mwh,
        reverse=True,
    )
    for resource in mandatory_order:
        quantity = min(resource.minimum_take_mwh, remaining_demand)
        dispatch_quantities[resource.resource_id] += quantity
        mandatory_quantities[resource.resource_id] = quantity
        remaining_demand -= quantity
        unmet_minimum += resource.minimum_take_mwh - quantity

    discretionary_order = sorted(
        resources,
        key=lambda resource: market_price_gbp_mwh - resource.unit_cost_gbp_mwh,
        reverse=True,
    )
    for resource in discretionary_order:
        margin = market_price_gbp_mwh - resource.unit_cost_gbp_mwh
        if margin <= 0 or remaining_demand <= 0:
            continue
        remaining_resource = (
            resource.effective_maximum_mwh - dispatch_quantities[resource.resource_id]
        )
        quantity = min(remaining_resource, remaining_demand)
        dispatch_quantities[resource.resource_id] += quantity
        remaining_demand -= quantity

    dispatches: list[ContractDispatch] = []
    for resource in resources:
        quantity = dispatch_quantities[resource.resource_id]
        if quantity <= 0:
            continue
        mandatory = mandatory_quantities[resource.resource_id]
        margin = market_price_gbp_mwh - resource.unit_cost_gbp_mwh
        dispatches.append(
            ContractDispatch(
                resource_id=resource.resource_id,
                quantity_mwh=quantity,
                mandatory_quantity_mwh=mandatory,
                discretionary_quantity_mwh=quantity - mandatory,
                unit_margin_gbp_mwh=margin,
                pnl_gbp=quantity * margin,
            )
        )

    warnings: list[str] = []
    if unmet_minimum > 0:
        warnings.append("Demand limit is below aggregate contractual minimum-take volume.")
    if remaining_demand > 0:
        warnings.append("Available positive-margin contract volume does not cover demand.")

    return OptimizationResult(
        status="infeasible" if unmet_minimum > 0 else "optimal",
        objective_value_gbp=sum(dispatch.pnl_gbp for dispatch in dispatches),
        dispatches=tuple(dispatches),
        unmet_minimum_take_mwh=unmet_minimum,
        unsold_volume_mwh=sum(
            resource.effective_maximum_mwh - dispatch_quantities[resource.resource_id]
            for resource in resources
        ),
        warnings=tuple(warnings),
        diagnostics={
            "demand_limit_mwh": demand_limit_mwh,
            "unserved_demand_mwh": remaining_demand,
            "market_price_gbp_mwh": market_price_gbp_mwh,
        },
    )
