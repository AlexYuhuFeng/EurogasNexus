"""Tests for the unified phase-two optimization facade."""

from __future__ import annotations

from eurogas_nexus.optimization import (
    CapacityProduct,
    NetworkEdge,
    PhaseTwoOptimizer,
    SaleOption,
    SupplyResource,
)


def test_phase_two_optimizer_applies_shared_tso_access() -> None:
    optimizer = PhaseTwoOptimizer(accessible_tsos={"TSO-1"})

    route = optimizer.optimize_route(
        edges=[
            NetworkEdge("allowed", "A", "B", 2.0, 100.0, "TSO-1"),
            NetworkEdge("blocked", "A", "B", 1.0, 100.0, "TSO-2"),
        ],
        source="A",
        target="B",
        required_capacity_mwh=20.0,
    )
    pool = optimizer.optimize_resource_pool(
        resources=[SupplyResource("resource", 50.0, 20.0, required_tso_access=("TSO-1",))],
        sale_options=[SaleOption("sale", "NBP", 30.0, 50.0)],
    )

    assert route.edge_ids == ("allowed",)
    assert pool.status == "optimal"
    assert sum(item.quantity_mwh for item in pool.allocations) == 50.0


def test_phase_two_optimizer_exposes_all_four_capabilities() -> None:
    optimizer = PhaseTwoOptimizer()

    capacity = optimizer.optimize_capacity(
        products=[CapacityProduct("firm", 100.0, 80.0)],
        required_capacity_mwh=50.0,
    )
    contracts = optimizer.optimize_contracts(
        resources=[SupplyResource("contract", 100.0, 20.0, minimum_take_mwh=10.0)],
        market_price_gbp_mwh=30.0,
        demand_limit_mwh=40.0,
    )

    assert capacity.status == "optimal"
    assert contracts.status == "optimal"
    assert contracts.dispatches[0].quantity_mwh == 40.0
