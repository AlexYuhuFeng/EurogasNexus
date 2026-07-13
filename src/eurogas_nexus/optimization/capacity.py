"""Capacity-booking combination optimization."""

from __future__ import annotations

from itertools import combinations

from .models import CapacityBookingResult, CapacityProduct


def optimize_capacity_bookings(
    products: list[CapacityProduct],
    required_capacity_mwh: float,
    expected_throughput_mwh: float | None = None,
    allow_interruptible: bool = True,
) -> CapacityBookingResult:
    """Choose the lowest-cost product combination meeting required capacity.

    The MVP uses exact subset enumeration and is therefore intended for a
    commercially curated product set. It remains deterministic and dependency
    free; larger auction universes can later be delegated to a MILP solver.
    """

    if required_capacity_mwh < 0:
        raise ValueError("required_capacity_mwh must be non-negative")
    throughput = required_capacity_mwh if expected_throughput_mwh is None else expected_throughput_mwh
    if throughput < 0:
        raise ValueError("expected_throughput_mwh must be non-negative")

    eligible = [
        product
        for product in products
        if allow_interruptible or product.firmness == "firm"
    ]
    if required_capacity_mwh == 0:
        return CapacityBookingResult(
            status="optimal",
            selected_product_ids=(),
            total_capacity_mwh=0.0,
            total_cost_gbp=0.0,
            excess_capacity_mwh=0.0,
        )

    best: tuple[float, float, tuple[str, ...]] | None = None
    for count in range(1, len(eligible) + 1):
        for subset in combinations(eligible, count):
            capacity = sum(product.capacity_mwh for product in subset)
            if capacity < required_capacity_mwh:
                continue
            cost = sum(
                product.fixed_cost_gbp + product.variable_cost_gbp_mwh * throughput
                for product in subset
            )
            product_ids = tuple(sorted(product.product_id for product in subset))
            candidate = (cost, capacity, product_ids)
            if best is None or candidate < best:
                best = candidate

    if best is None:
        return CapacityBookingResult(
            status="infeasible",
            selected_product_ids=(),
            total_capacity_mwh=0.0,
            total_cost_gbp=None,
            excess_capacity_mwh=0.0,
            warnings=("Available capacity products do not cover the required quantity.",),
        )

    total_cost, total_capacity, product_ids = best
    warnings: list[str] = []
    selected = {product.product_id: product for product in eligible}
    if any(selected[product_id].firmness == "interruptible" for product_id in product_ids):
        warnings.append("Selected solution includes interruptible capacity.")
    return CapacityBookingResult(
        status="optimal",
        selected_product_ids=product_ids,
        total_capacity_mwh=total_capacity,
        total_cost_gbp=total_cost,
        excess_capacity_mwh=total_capacity - required_capacity_mwh,
        warnings=tuple(warnings),
    )
