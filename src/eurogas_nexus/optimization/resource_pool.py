"""Deterministic daily resource-pool optimization."""

from __future__ import annotations

from ._validation import validate_sale_options, validate_supply_resources
from .models import OptimizationResult, ResourceAllocation, SaleOption, SupplyResource


def _validate_inputs(resources: list[SupplyResource], sale_options: list[SaleOption]) -> None:
    validate_supply_resources(resources)
    validate_sale_options(sale_options)


def _partial_infeasible_allocation(
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


def optimize_resource_pool(resources, sale_options, accessible_tsos=None) -> OptimizationResult:
    """Solve minimum-take and discretionary allocation with the shared residual kernel.

    The old placement is retained solely for partial diagnostics when hard lower
    bounds are infeasible. Such a result always remains infeasible.
    """
    from .circulation import Arc, solve_circulation

    _validate_inputs(resources, sale_options)
    arcs, pairs = [], {}
    for resource in resources:
        arcs.append(
            Arc(
                f"s:{resource.resource_id}",
                "source",
                f"r:{resource.resource_id}",
                resource.minimum_take_mwh,
                resource.effective_maximum_mwh,
                resource.unit_cost_gbp_mwh,
            )
        )
        for option in sale_options:
            required = set(resource.required_tso_access) | set(option.required_tso_access)
            if accessible_tsos is not None and not required.issubset(accessible_tsos):
                continue
            arc_id = f"pair:{len(pairs)}"
            pairs[arc_id] = (resource, option)
            arcs.append(
                Arc(
                    arc_id,
                    f"r:{resource.resource_id}",
                    f"o:{option.option_id}",
                    0,
                    min(resource.effective_maximum_mwh, option.capacity_mwh),
                    0,
                )
            )
    for option in sale_options:
        arcs.append(
            Arc(
                f"o:{option.option_id}",
                f"o:{option.option_id}",
                "sink",
                0,
                option.capacity_mwh,
                option.variable_cost_gbp_mwh - option.sale_price_gbp_mwh,
            )
        )
    total = sum(r.effective_maximum_mwh for r in resources)
    arcs.append(Arc("return", "sink", "source", 0, total, 0))
    result = solve_circulation(arcs)
    if result["status"] == "infeasible":
        return _partial_infeasible_allocation(resources, sale_options, accessible_tsos)
    allocations = []
    for arc_id, (resource, option) in pairs.items():
        quantity = result["flows"][arc_id]
        if quantity <= 1e-9:
            continue
        margin = (
            option.sale_price_gbp_mwh - option.variable_cost_gbp_mwh - resource.unit_cost_gbp_mwh
        )
        allocations.append(
            ResourceAllocation(
                resource.resource_id, option.option_id, quantity, margin, quantity * margin
            )
        )
    unsold = total - sum(row.quantity_mwh for row in allocations)
    return OptimizationResult(
        status="optimal",
        objective_value_gbp=-result["cost"],
        allocations=tuple(allocations),
        unsold_volume_mwh=max(0, unsold),
        warnings=("Some available resource volume remains unallocated.",) if unsold > 1e-9 else (),
        diagnostics={
            "resource_count": len(resources),
            "sale_option_count": len(sale_options),
            "eligible_pair_count": len(pairs),
        },
    )
