"""Capacity-booking combination optimization."""

from __future__ import annotations

import math
from itertools import combinations

from ._validation import validate_capacity_products
from .models import CapacityBookingResult, CapacityProduct


def optimize_capacity_bookings(
    products: list[CapacityProduct],
    required_capacity_mwh: float,
    expected_throughput_mwh: float | None = None,
    allow_interruptible: bool = True,
    *,
    held_capacity_mwh: float = 0.0,
    held_cost_gbp: float | None = None,
) -> CapacityBookingResult:
    """Choose the lowest-cost product combination meeting required capacity.

    TAR-2: ``held_capacity_mwh`` the firm already holds covers the requirement first, at its
    contracted cost ``held_cost_gbp`` (``None``: not recorded, so the total is not given);
    products are chosen only for what is left. The result's ``layers`` list the contracted
    part, then the products bought.

    The MVP uses exact subset enumeration and is therefore intended for a
    commercially curated product set. It remains deterministic and dependency
    free; larger auction universes can later be delegated to a MILP solver.
    """

    validate_capacity_products(products)
    if not math.isfinite(required_capacity_mwh):
        raise ValueError("required_capacity_mwh must be finite")
    if required_capacity_mwh < 0:
        raise ValueError("required_capacity_mwh must be non-negative")
    if not math.isfinite(held_capacity_mwh) or held_capacity_mwh < 0:
        raise ValueError("held_capacity_mwh must be finite and non-negative")
    if held_cost_gbp is not None and (not math.isfinite(held_cost_gbp) or held_cost_gbp < 0):
        raise ValueError("held_cost_gbp must be finite and non-negative")
    if held_capacity_mwh > 0:
        held = min(held_capacity_mwh, required_capacity_mwh)
        rest = optimize_capacity_bookings(
            products,
            required_capacity_mwh - held,
            expected_throughput_mwh=None
            if expected_throughput_mwh is None
            else max(0.0, expected_throughput_mwh - held),
            allow_interruptible=allow_interruptible,
        )
        contracted = {
            "layer": "contracted",
            "capacity_mwh": held,
            "cost_gbp": held_cost_gbp,
            "source": "capacity the firm holds",
        }
        bought = {
            "layer": "public",
            "capacity_mwh": rest.total_capacity_mwh,
            "cost_gbp": rest.total_cost_gbp,
            "product_ids": list(rest.selected_product_ids),
        }
        total = (
            None
            if rest.total_cost_gbp is None or held_cost_gbp is None
            else held_cost_gbp + rest.total_cost_gbp
        )
        warnings = list(rest.warnings)
        if held_cost_gbp is None:
            warnings.append("The contracted cost of the held capacity is not recorded.")
        return CapacityBookingResult(
            status=rest.status,
            selected_product_ids=rest.selected_product_ids,
            total_capacity_mwh=held + rest.total_capacity_mwh,
            total_cost_gbp=total if rest.status == "optimal" else None,
            excess_capacity_mwh=rest.excess_capacity_mwh + max(
                0.0, held_capacity_mwh - required_capacity_mwh
            ),
            warnings=tuple(warnings),
            held_capacity_mwh=held,
            held_cost_gbp=held_cost_gbp,
            layers=(contracted, bought) if rest.total_capacity_mwh > 0 else (contracted,),
        )
    throughput = (
        required_capacity_mwh
        if expected_throughput_mwh is None
        else expected_throughput_mwh
    )
    if not math.isfinite(throughput):
        raise ValueError("expected_throughput_mwh must be finite")
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
