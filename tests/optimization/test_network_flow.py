"""Correctness tests for shared-capacity natural-gas network flow."""

from __future__ import annotations

import math

import pytest

from eurogas_nexus.optimization.models import NetworkEdge
from eurogas_nexus.optimization.network_flow import (
    FlowDemand,
    FlowSupply,
    optimize_network_flow,
)


def test_residual_reverse_arc_reroutes_a_locally_attractive_first_flow() -> None:
    """S1-D1 must be cancelled so both demands can be served."""

    result = optimize_network_flow(
        edges=[
            NetworkEdge("s1-d1", "S1", "D1", 0.0, 1.0),
            NetworkEdge("s1-d2", "S1", "D2", 1.0, 1.0),
            NetworkEdge("s2-d1", "S2", "D1", 1.0, 1.0),
        ],
        supplies=[FlowSupply("S1", 1.0), FlowSupply("S2", 1.0)],
        demands=[FlowDemand("D1", 1.0, 10.0), FlowDemand("D2", 1.0, 10.0)],
    )

    assert result.status == "optimal"
    assert result.served_demand_mwh == 2.0
    assert result.total_network_cost_gbp == 2.0
    assert result.total_objective_gbp == 18.0
    assert {item.edge_id: item.quantity_mwh for item in result.edge_flows} == {
        "s1-d2": 1.0,
        "s2-d1": 1.0,
    }


def test_shared_edge_capacity_is_enforced_across_demands() -> None:
    result = optimize_network_flow(
        edges=[
            NetworkEdge("trunk", "SOURCE", "JUNCTION", 0.5, 10.0),
            NetworkEdge("to-a", "JUNCTION", "A", 0.1, 10.0),
            NetworkEdge("to-b", "JUNCTION", "B", 0.1, 10.0),
        ],
        supplies=[FlowSupply("SOURCE", 20.0, 2.0)],
        demands=[FlowDemand("A", 8.0, 5.0), FlowDemand("B", 8.0, 4.0)],
    )

    flows = {item.edge_id: item.quantity_mwh for item in result.edge_flows}
    assert result.status == "feasible"
    assert result.served_demand_mwh == 10.0
    assert result.unserved_demand_mwh == 6.0
    assert flows["trunk"] == 10.0
    assert flows["to-a"] == 8.0
    assert flows["to-b"] == 2.0


def test_negative_margin_is_not_routed_but_zero_margin_is() -> None:
    result = optimize_network_flow(
        edges=[
            NetworkEdge("zero", "S", "D0", 1.0, 2.0),
            NetworkEdge("negative", "S", "D1", 2.0, 2.0),
        ],
        supplies=[FlowSupply("S", 4.0, 2.0)],
        demands=[FlowDemand("D0", 2.0, 3.0), FlowDemand("D1", 2.0, 3.0)],
    )

    assert result.served_demand_mwh == 2.0
    assert result.unserved_demand_mwh == 2.0
    assert result.total_objective_gbp == 0.0
    assert {item.edge_id for item in result.edge_flows} == {"zero"}


def test_access_filter_and_input_order_are_deterministic() -> None:
    edges = [
        NetworkEdge("allowed", "S", "D", 2.0, 4.0, "TSO-A"),
        NetworkEdge("blocked", "S", "D", 0.5, 4.0, "TSO-B"),
    ]
    supplies = [FlowSupply("S", 4.0, 1.0)]
    demands = [FlowDemand("D", 4.0, 5.0)]

    first = optimize_network_flow(
        edges,
        supplies,
        demands,
        accessible_tsos={"TSO-A"},
    )
    second = optimize_network_flow(
        list(reversed(edges)),
        list(reversed(supplies)),
        list(reversed(demands)),
        accessible_tsos={"TSO-A"},
    )

    assert first == second
    assert first.edge_flows[0].edge_id == "allowed"
    assert first.total_network_cost_gbp == 12.0
    assert first.total_objective_gbp == 8.0


def test_parallel_supply_records_on_one_node_are_not_overwritten() -> None:
    result = optimize_network_flow(
        edges=[NetworkEdge("route", "S", "D", 0.0, 5.0)],
        supplies=[FlowSupply("S", 2.0, 1.0), FlowSupply("S", 3.0, 2.0)],
        demands=[FlowDemand("D", 5.0, 4.0)],
    )

    assert result.served_demand_mwh == 5.0
    assert result.total_network_cost_gbp == 8.0
    assert result.total_objective_gbp == 12.0


@pytest.mark.parametrize(
    ("edges", "supplies", "demands", "message"),
    [
        (
            [
                NetworkEdge("duplicate", "A", "B", 1.0, 1.0),
                NetworkEdge("duplicate", "B", "C", 1.0, 1.0),
            ],
            [],
            [],
            "duplicate edge_id",
        ),
        ([NetworkEdge("negative", "A", "B", 1.0, -1.0)], [], [], "non-negative"),
        ([], [FlowSupply("S", math.nan)], [], "finite"),
        ([], [], [FlowDemand("D", -1.0)], "non-negative"),
    ],
)
def test_invalid_network_flow_inputs_fail_explicitly(
    edges: list[NetworkEdge],
    supplies: list[FlowSupply],
    demands: list[FlowDemand],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        optimize_network_flow(edges, supplies, demands)
