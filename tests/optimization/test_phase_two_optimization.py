"""Behavior tests for the phase-two optimization engines."""

from __future__ import annotations

from eurogas_nexus.optimization import (
    CapacityProduct,
    NetworkEdge,
    SaleOption,
    SupplyResource,
    find_min_cost_route,
    optimize_capacity_bookings,
    optimize_contract_dispatch,
    optimize_resource_pool,
)


def test_route_optimizer_selects_cheapest_capacity_feasible_path() -> None:
    result = find_min_cost_route(
        edges=[
            NetworkEdge("direct", "A", "C", 4.0, 100.0, "TSO-1"),
            NetworkEdge("ab", "A", "B", 1.0, 100.0, "TSO-1"),
            NetworkEdge("bc", "B", "C", 1.5, 80.0, "TSO-2"),
        ],
        source="A",
        target="C",
        required_capacity_mwh=50.0,
        accessible_tsos={"TSO-1", "TSO-2"},
    )

    assert result.status == "optimal"
    assert result.edge_ids == ("ab", "bc")
    assert result.nodes == ("A", "B", "C")
    assert result.total_cost_gbp_mwh == 2.5
    assert result.bottleneck_capacity_mwh == 80.0
    assert result.human_review_required is True


def test_route_optimizer_rejects_missing_tso_access() -> None:
    result = find_min_cost_route(
        edges=[NetworkEdge("ab", "A", "B", 1.0, 100.0, "TSO-2")],
        source="A",
        target="B",
        required_capacity_mwh=10.0,
        accessible_tsos={"TSO-1"},
    )

    assert result.status == "infeasible"
    assert result.total_cost_gbp_mwh is None


def test_resource_pool_places_minimum_take_then_positive_margin_volume() -> None:
    result = optimize_resource_pool(
        resources=[
            SupplyResource("cheap", 100.0, 20.0, minimum_take_mwh=20.0),
            SupplyResource("expensive", 80.0, 35.0, minimum_take_mwh=10.0),
        ],
        sale_options=[
            SaleOption("nbp", "NBP", 40.0, 100.0, variable_cost_gbp_mwh=2.0),
            SaleOption("ttf", "TTF", 32.0, 100.0, variable_cost_gbp_mwh=1.0),
        ],
    )

    assert result.status == "optimal"
    assert result.unmet_minimum_take_mwh == 0.0
    assert sum(item.quantity_mwh for item in result.allocations) == 110.0
    assert result.objective_value_gbp > 0
    assert result.human_review_required is True


def test_resource_pool_reports_unmet_minimum_take() -> None:
    result = optimize_resource_pool(
        resources=[SupplyResource("supply", 100.0, 20.0, minimum_take_mwh=80.0)],
        sale_options=[SaleOption("sale", "NBP", 30.0, 50.0)],
    )

    assert result.status == "infeasible"
    assert result.unmet_minimum_take_mwh == 30.0
    assert result.warnings


def test_capacity_optimizer_selects_lowest_cost_covering_subset() -> None:
    result = optimize_capacity_bookings(
        products=[
            CapacityProduct("annual-small", 40.0, 100.0),
            CapacityProduct("annual-medium", 70.0, 180.0),
            CapacityProduct("monthly", 30.0, 40.0, variable_cost_gbp_mwh=1.0),
        ],
        required_capacity_mwh=90.0,
        expected_throughput_mwh=20.0,
    )

    assert result.status == "optimal"
    assert result.selected_product_ids == ("annual-medium", "monthly")
    assert result.total_capacity_mwh == 100.0
    assert result.total_cost_gbp == 240.0
    assert result.excess_capacity_mwh == 10.0


def test_capacity_optimizer_can_exclude_interruptible_capacity() -> None:
    result = optimize_capacity_bookings(
        products=[
            CapacityProduct("interruptible", 100.0, 10.0, firmness="interruptible"),
            CapacityProduct("firm", 100.0, 100.0, firmness="firm"),
        ],
        required_capacity_mwh=80.0,
        allow_interruptible=False,
    )

    assert result.selected_product_ids == ("firm",)


def test_contract_dispatch_uses_mandatory_and_positive_margin_flex() -> None:
    result = optimize_contract_dispatch(
        resources=[
            SupplyResource("contract-a", 100.0, 20.0, minimum_take_mwh=20.0),
            SupplyResource("contract-b", 80.0, 35.0, minimum_take_mwh=10.0),
        ],
        market_price_gbp_mwh=30.0,
        demand_limit_mwh=90.0,
    )

    dispatch_by_id = {item.resource_id: item for item in result.dispatches}
    assert result.status == "optimal"
    assert dispatch_by_id["contract-a"].quantity_mwh == 80.0
    assert dispatch_by_id["contract-b"].quantity_mwh == 10.0
    assert dispatch_by_id["contract-b"].discretionary_quantity_mwh == 0.0
    assert result.objective_value_gbp == 750.0
