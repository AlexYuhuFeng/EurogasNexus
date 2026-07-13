"""Deterministic daily resource-pool optimization."""

from __future__ import annotations

from .models import OptimizationResult, ResourceAllocation, SaleOption, SupplyResource


def _validate_inputs(resources: list[SupplyResource], sale_options: list[SaleOption]) -> None:
    for resource in resources:
        if resource.available_mwh < 0 or resource.minimum_take_mwh < 0:
            raise ValueError("Resource quantities must be non-negative")
        if resource.minimum_take_mwh > resource.effective_maximum_mwh:
            raise ValueError(f"minimum take exceeds maximum for {resource.resource_id}")
    for option in sale_options:
        if option.capacity_mwh < 0:
            raise ValueError("Sale-option capacity must be non-negative")


def optimize_resource_pool(
    resources: list[SupplyResource],
    sale_options: list[SaleOption],
    accessible_tsos: set[str] | None = None,
) -> OptimizationResult:
    """Allocate resources to sale options by descending unit margin.

    The engine first attempts to place contractual minimum-take quantities, then
    allocates discretionary volume only where the unit margin is positive. This
    is the exact optimum for the current separable linear model without shared
    route constraints.
    """

    _validate_inputs(resources, sale_options)
    remaining_resource = {
        resource.resource_id: resource.effective_maximum_mwh for resource in resources
    }
    remaining_option = {option.option_id: option.capacity_mwh for option in sale_options}
    resource_by_id = {resource.resource_id: resource for resource in resources}

    eligible_pairs: list[tuple[float, str, str]] = []
    for resource in resources:
        for option in sale_options:
            required_access = set(resource.required_tso_access) | set(option.required_tso_access)
            if accessible_tsos is not None and not required_access.issubset(accessible_tsos):
                continue
            margin = (
                option.sale_price_gbp_mwh
                - option.variable_cost_gbp_mwh
                - resource.unit_cost_gbp_mwh
            )
            eligible_pairs.append((margin, resource.resource_id, option.option_id))
    eligible_pairs.sort(reverse=True)

    allocations: list[ResourceAllocation] = []

    def allocate(resource_id: str, option_id: str, quantity: float, margin: float) -> None:
        if quantity <= 0:
            return
        allocations.append(
            ResourceAllocation(
                resource_id=resource_id,
                option_id=option_id,
                quantity_mwh=quantity,
                unit_margin_gbp_mwh=margin,
                pnl_gbp=quantity * margin,
            )
        )
        remaining_resource[resource_id] -= quantity
        remaining_option[option_id] -= quantity

    unmet_minimum = 0.0
    for resource in resources:
        mandatory_remaining = resource.minimum_take_mwh
        for margin, resource_id, option_id in eligible_pairs:
            if resource_id != resource.resource_id or mandatory_remaining <= 0:
                continue
            quantity = min(
                mandatory_remaining,
                remaining_resource[resource_id],
                remaining_option[option_id],
            )
            allocate(resource_id, option_id, quantity, margin)
            mandatory_remaining -= quantity
        unmet_minimum += mandatory_remaining

    for margin, resource_id, option_id in eligible_pairs:
        if margin <= 0:
            continue
        quantity = min(remaining_resource[resource_id], remaining_option[option_id])
        allocate(resource_id, option_id, quantity, margin)

    objective = sum(allocation.pnl_gbp for allocation in allocations)
    unsold = sum(remaining_resource.values())
    warnings: list[str] = []
    if unmet_minimum > 0:
        warnings.append("Contractual minimum-take volume could not be fully placed.")
    if unsold > 0:
        warnings.append("Some available resource volume remains unallocated.")
    if not eligible_pairs and resources:
        warnings.append("No sale option satisfies the current TSO-access constraints.")

    status = "infeasible" if unmet_minimum > 0 else "optimal"
    return OptimizationResult(
        status=status,
        objective_value_gbp=objective,
        allocations=tuple(allocations),
        unmet_minimum_take_mwh=unmet_minimum,
        unsold_volume_mwh=unsold,
        warnings=tuple(warnings),
        diagnostics={
            "resource_count": len(resource_by_id),
            "sale_option_count": len(sale_options),
            "eligible_pair_count": len(eligible_pairs),
        },
    )
