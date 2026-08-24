"""R31 portfolio-network optimizer and attribution tests."""

from __future__ import annotations

import pytest

from eurogas_nexus.domain.route_cost.portfolio_network import (
    ComposedPortfolioNetwork,
    optimize_composed_portfolio_network,
)
from eurogas_nexus.optimization.models import NetworkEdge, SaleOption, SupplyResource


def _composition(
    resources: list[SupplyResource],
    sale_options: list[SaleOption],
    edges: list[NetworkEdge],
) -> ComposedPortfolioNetwork:
    return ComposedPortfolioNetwork(
        resources=tuple(resources),
        sale_options=tuple(sale_options),
        edges=tuple(edges),
    )


def test_shared_route_capacity_is_enforced_across_contracts() -> None:
    composition = _composition(
        resources=[
            SupplyResource("contract-a", 80.0, 20.0, source_node="S"),
            SupplyResource("contract-b", 80.0, 22.0, source_node="S"),
        ],
        sale_options=[
            SaleOption("nbp", "NBP", 30.0, 100.0),
        ],
        edges=[
            NetworkEdge("route:main", "S", "NBP", 1.0, 100.0),
        ],
    )

    result = optimize_composed_portfolio_network(composition)

    assert result.status == "optimal"
    assert result.served_demand_mwh == 100.0
    assert result.unserved_demand_mwh == 0.0
    assert {item.edge_id: item.quantity_mwh for item in result.edge_flows} == {
        "route:main": 100.0
    }
    attribution_by_contract = {
        item.contract_id: item for item in result.contract_attributions
    }
    # The cheaper contract is fully used; only 20 MWh of the expensive one fits.
    assert attribution_by_contract["contract-a"].quantity_mwh == 80.0
    assert attribution_by_contract["contract-b"].quantity_mwh == 20.0
    assert sum(item.pnl_gbp for item in result.contract_attributions) == pytest.approx(
        result.objective_value_gbp
    )


def test_exhausted_cheap_path_reroutes_remaining_gas_to_alternate_route() -> None:
    composition = _composition(
        resources=[
            SupplyResource("contract", 30.0, 10.0, source_node="S"),
        ],
        sale_options=[
            SaleOption("premium", "D1", 40.0, 20.0),
            SaleOption("alternate", "D2", 20.0, 100.0),
        ],
        edges=[
            NetworkEdge("route:cheap", "S", "D1", 2.0, 20.0),
            NetworkEdge("route:expensive", "S", "D2", 5.0, 100.0),
        ],
    )

    result = optimize_composed_portfolio_network(composition)

    assert result.status == "optimal"
    allocations = {item.option_id: item.quantity_mwh for item in result.allocations}
    # Cheap path capacity 20 used first; the remaining 10 goes to the
    # alternate (lower netback but still positive) market.
    assert allocations == {"premium": 20.0, "alternate": 10.0}
    assert result.objective_value_gbp == pytest.approx(20 * 28 + 10 * 5)

    by_option = {
        item.option_id: item
        for item in result.contract_attributions[0].option_flows
    }
    assert by_option["premium"].network_cost_gbp == pytest.approx(40.0)
    assert by_option["alternate"].network_cost_gbp == pytest.approx(50.0)


def test_local_sale_and_cross_border_sale_are_compared_on_one_graph() -> None:
    composition = _composition(
        resources=[
            SupplyResource("contract", 10.0, 15.0, source_node="TTF"),
        ],
        sale_options=[
            SaleOption("route:local", "TTF", 20.0, 100.0),
            SaleOption("route:export", "NBP", 22.0, 100.0),
        ],
        edges=[
            NetworkEdge("route:export", "TTF", "NBP", 4.0, 100.0),
        ],
    )

    result = optimize_composed_portfolio_network(composition)

    assert result.status == "optimal"
    # Local netback 5, export netback 3: all volume stays local.
    assert [item.option_id for item in result.allocations] == ["route:local"]
    assert result.contract_attributions[0].pnl_gbp == pytest.approx(50.0)


def test_negative_margin_route_is_not_served() -> None:
    composition = _composition(
        resources=[
            SupplyResource("contract", 10.0, 15.0, source_node="S"),
        ],
        sale_options=[
            SaleOption("loss-making", "D", 18.0, 100.0),
        ],
        edges=[
            NetworkEdge("route:loss", "S", "D", 5.0, 100.0),
        ],
    )

    result = optimize_composed_portfolio_network(composition)

    assert result.status == "optimal"
    assert result.served_demand_mwh == 0.0
    assert result.allocations == ()
    assert result.contract_attributions == ()


def test_contract_attribution_sums_to_portfolio_objective() -> None:
    composition = _composition(
        resources=[
            SupplyResource("contract-a", 40.0, 10.0, source_node="S1"),
            SupplyResource("contract-b", 30.0, 12.0, source_node="S2"),
        ],
        sale_options=[
            SaleOption("ttf", "TTF", 25.0, 100.0),
            SaleOption("nbp", "NBP", 23.0, 100.0),
        ],
        edges=[
            NetworkEdge("s1-ttf", "S1", "TTF", 2.0, 20.0),
            NetworkEdge("s1-nbp", "S1", "NBP", 3.0, 100.0),
            NetworkEdge("s2-ttf", "S2", "TTF", 1.0, 100.0),
            NetworkEdge("s2-nbp", "S2", "NBP", 4.0, 100.0),
        ],
    )

    result = optimize_composed_portfolio_network(composition)

    assert result.status == "optimal"
    assert result.objective_value_gbp == pytest.approx(
        sum(item.pnl_gbp for item in result.contract_attributions)
    )
    assert sum(item.quantity_mwh for item in result.allocations) == pytest.approx(
        result.served_demand_mwh
    )
    assert result.diagnostics["solver_objective_gbp"] == pytest.approx(
        result.objective_value_gbp
    )


def test_input_order_is_deterministic() -> None:
    composition_a = _composition(
        resources=[
            SupplyResource("a", 10.0, 10.0, source_node="S"),
            SupplyResource("b", 10.0, 9.0, source_node="S"),
        ],
        sale_options=[
            SaleOption("d1", "D1", 20.0, 100.0),
            SaleOption("d2", "D2", 19.0, 100.0),
        ],
        edges=[
            NetworkEdge("to-d1", "S", "D1", 1.0, 100.0),
            NetworkEdge("to-d2", "S", "D2", 1.0, 100.0),
        ],
    )
    composition_b = _composition(
        resources=list(reversed(composition_a.resources)),
        sale_options=list(reversed(composition_a.sale_options)),
        edges=list(reversed(composition_a.edges)),
    )

    first = optimize_composed_portfolio_network(composition_a)
    second = optimize_composed_portfolio_network(composition_b)

    assert first == second


def test_incomplete_composition_raises_instead_of_running_solver() -> None:
    composition = ComposedPortfolioNetwork(
        blockers=("SALE_OPTIONS_UNAVAILABLE",),
    )

    with pytest.raises(ValueError, match="composition is blocked"):
        optimize_composed_portfolio_network(composition)


def test_resources_without_source_node_are_rejected() -> None:
    composition = _composition(
        resources=[SupplyResource("contract", 10.0, 10.0)],
        sale_options=[SaleOption("sale", "NBP", 20.0, 100.0)],
        edges=[NetworkEdge("edge", "S", "NBP", 1.0, 100.0)],
    )

    with pytest.raises(ValueError, match="must have a source node"):
        optimize_composed_portfolio_network(composition)
