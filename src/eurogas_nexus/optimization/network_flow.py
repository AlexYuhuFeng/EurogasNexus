"""Shared-capacity natural-gas network flow optimization."""

from __future__ import annotations

import math
from dataclasses import dataclass

from ._validation import require_finite, validate_network_edges
from .models import NetworkEdge, OptimizationStatus

_TOLERANCE = 1e-9


@dataclass(frozen=True, slots=True)
class FlowSupply:
    node: str
    available_mwh: float
    unit_cost_gbp_mwh: float = 0.0


@dataclass(frozen=True, slots=True)
class FlowDemand:
    node: str
    required_mwh: float
    value_gbp_mwh: float = 0.0


@dataclass(frozen=True, slots=True)
class EdgeFlow:
    edge_id: str
    quantity_mwh: float


@dataclass(frozen=True, slots=True)
class NetworkFlowResult:
    status: OptimizationStatus
    served_demand_mwh: float
    unserved_demand_mwh: float
    total_network_cost_gbp: float
    total_objective_gbp: float
    edge_flows: tuple[EdgeFlow, ...]
    warnings: tuple[str, ...] = ()
    human_review_required: bool = True


@dataclass(slots=True)
class _ResidualArc:
    target: int
    reverse_index: int
    capacity: float
    unit_cost: float


@dataclass(frozen=True, slots=True)
class _ArcReference:
    source: int
    arc_index: int
    initial_capacity: float


def optimize_network_flow(
    edges: list[NetworkEdge],
    supplies: list[FlowSupply],
    demands: list[FlowDemand],
    *,
    accessible_tsos: set[str] | None = None,
) -> NetworkFlowResult:
    """Maximize portfolio net value on a shared directed gas network.

    The model is a linear, single-natural-gas-commodity minimum-cost flow. A
    super-source arc carries each supply acquisition cost, each physical edge
    carries its tariff, and each demand-to-super-sink arc carries negative sale
    value. Successive shortest augmenting paths operate on a residual graph
    containing reverse arcs, so an earlier allocation can be cancelled and
    rerouted when that improves the portfolio result.

    Strictly negative-margin flow is optional and therefore not routed.
    Zero-margin flow is routed deterministically.
    """

    _validate_inputs(edges, supplies, demands)
    active_edges = sorted(
        (
            edge
            for edge in edges
            if edge.enabled
            and edge.available_capacity_mwh > _TOLERANCE
            and (
                accessible_tsos is None
                or edge.tso is None
                or edge.tso in accessible_tsos
            )
        ),
        key=lambda edge: (edge.edge_id, edge.source, edge.target, edge.tso or ""),
    )
    ordered_supplies = sorted(
        supplies,
        key=lambda item: (item.node, item.unit_cost_gbp_mwh, item.available_mwh),
    )
    ordered_demands = sorted(
        demands,
        key=lambda item: (item.node, item.value_gbp_mwh, item.required_mwh),
    )

    node_names = sorted(
        {
            *(edge.source for edge in active_edges),
            *(edge.target for edge in active_edges),
            *(item.node for item in ordered_supplies),
            *(item.node for item in ordered_demands),
        }
    )
    super_source = 0
    super_sink = 1
    node_index = {name: index + 2 for index, name in enumerate(node_names)}
    graph: list[list[_ResidualArc]] = [[] for _ in range(len(node_names) + 2)]

    edge_references: dict[str, tuple[NetworkEdge, _ArcReference]] = {}
    for edge in active_edges:
        source = node_index[edge.source]
        arc_index = _add_residual_arc(
            graph,
            source,
            node_index[edge.target],
            edge.available_capacity_mwh,
            edge.tariff_gbp_mwh,
        )
        edge_references[edge.edge_id] = (
            edge,
            _ArcReference(source, arc_index, edge.available_capacity_mwh),
        )

    supply_references: list[tuple[FlowSupply, _ArcReference]] = []
    for supply in ordered_supplies:
        arc_index = _add_residual_arc(
            graph,
            super_source,
            node_index[supply.node],
            supply.available_mwh,
            supply.unit_cost_gbp_mwh,
        )
        supply_references.append(
            (
                supply,
                _ArcReference(super_source, arc_index, supply.available_mwh),
            )
        )

    demand_references: list[tuple[FlowDemand, _ArcReference]] = []
    for demand in ordered_demands:
        source = node_index[demand.node]
        arc_index = _add_residual_arc(
            graph,
            source,
            super_sink,
            demand.required_mwh,
            -demand.value_gbp_mwh,
        )
        demand_references.append(
            (
                demand,
                _ArcReference(source, arc_index, demand.required_mwh),
            )
        )

    while True:
        path = _shortest_residual_path(graph, super_source, super_sink)
        if path is None:
            break
        path_cost, predecessors = path
        if path_cost > _TOLERANCE:
            break
        quantity = _path_capacity(graph, predecessors, super_source, super_sink)
        if quantity <= _TOLERANCE:
            raise RuntimeError("Residual path has no augmentable capacity")
        _augment_path(graph, predecessors, super_source, super_sink, quantity)

    edge_flows = {
        edge_id: _flow_on_reference(graph, reference)
        for edge_id, (_, reference) in edge_references.items()
    }
    supply_usage = [
        (supply, _flow_on_reference(graph, reference))
        for supply, reference in supply_references
    ]
    demand_service = [
        (demand, _flow_on_reference(graph, reference))
        for demand, reference in demand_references
    ]
    _validate_final_flow(
        active_edges,
        edge_flows,
        supply_usage,
        demand_service,
    )

    served = sum(quantity for _, quantity in demand_service)
    required = sum(demand.required_mwh for demand in ordered_demands)
    unserved = max(required - served, 0.0)
    supply_cost = sum(
        quantity * supply.unit_cost_gbp_mwh for supply, quantity in supply_usage
    )
    pipeline_cost = sum(
        edge_flows[edge.edge_id] * edge.tariff_gbp_mwh for edge in active_edges
    )
    total_cost = supply_cost + pipeline_cost
    total_value = sum(
        quantity * demand.value_gbp_mwh for demand, quantity in demand_service
    )

    tolerance = _scale_tolerance(required)
    status: OptimizationStatus
    if unserved <= tolerance:
        status = "optimal"
    elif served > tolerance:
        status = "feasible"
    else:
        status = "infeasible"
    warnings = () if unserved <= tolerance else ("UNSERVED_DEMAND_REMAINS",)

    return NetworkFlowResult(
        status=status,
        served_demand_mwh=_clean_number(served),
        unserved_demand_mwh=_clean_number(unserved),
        total_network_cost_gbp=_clean_number(total_cost),
        total_objective_gbp=_clean_number(total_value - total_cost),
        edge_flows=tuple(
            EdgeFlow(edge_id, _clean_number(quantity))
            for edge_id, quantity in sorted(edge_flows.items())
            if quantity > tolerance
        ),
        warnings=warnings,
    )


def _validate_inputs(
    edges: list[NetworkEdge],
    supplies: list[FlowSupply],
    demands: list[FlowDemand],
) -> None:
    validate_network_edges(edges)

    for supply in supplies:
        if not supply.node.strip():
            raise ValueError("supply node must not be empty")
        require_finite(supply.available_mwh, f"supply at {supply.node}")
        require_finite(supply.unit_cost_gbp_mwh, f"supply cost at {supply.node}")
        if supply.available_mwh < 0:
            raise ValueError(f"supply must be non-negative: {supply.node}")

    for demand in demands:
        if not demand.node.strip():
            raise ValueError("demand node must not be empty")
        require_finite(demand.required_mwh, f"demand at {demand.node}")
        require_finite(demand.value_gbp_mwh, f"demand value at {demand.node}")
        if demand.required_mwh < 0:
            raise ValueError(f"demand must be non-negative: {demand.node}")


def _add_residual_arc(
    graph: list[list[_ResidualArc]],
    source: int,
    target: int,
    capacity: float,
    unit_cost: float,
) -> int:
    forward_index = len(graph[source])
    reverse_index = len(graph[target])
    graph[source].append(
        _ResidualArc(
            target=target,
            reverse_index=reverse_index,
            capacity=capacity,
            unit_cost=unit_cost,
        )
    )
    graph[target].append(
        _ResidualArc(
            target=source,
            reverse_index=forward_index,
            capacity=0.0,
            unit_cost=-unit_cost,
        )
    )
    return forward_index


def _shortest_residual_path(
    graph: list[list[_ResidualArc]],
    source: int,
    target: int,
) -> tuple[float, list[tuple[int, int] | None]] | None:
    """Return a deterministic shortest path in a residual graph with negative arcs."""

    distances = [float("inf")] * len(graph)
    predecessors: list[tuple[int, int] | None] = [None] * len(graph)
    distances[source] = 0.0

    for _ in range(len(graph) - 1):
        changed = False
        for node, arcs in enumerate(graph):
            if math.isinf(distances[node]):
                continue
            for arc_index, arc in enumerate(arcs):
                if arc.capacity <= _TOLERANCE:
                    continue
                candidate = distances[node] + arc.unit_cost
                if candidate < distances[arc.target] - _TOLERANCE:
                    distances[arc.target] = candidate
                    predecessors[arc.target] = (node, arc_index)
                    changed = True
        if not changed:
            break

    for node, arcs in enumerate(graph):
        if math.isinf(distances[node]):
            continue
        for arc in arcs:
            if arc.capacity <= _TOLERANCE:
                continue
            if distances[node] + arc.unit_cost < distances[arc.target] - _TOLERANCE:
                raise RuntimeError("Negative residual cycle detected")

    if math.isinf(distances[target]):
        return None
    return distances[target], predecessors


def _path_capacity(
    graph: list[list[_ResidualArc]],
    predecessors: list[tuple[int, int] | None],
    source: int,
    target: int,
) -> float:
    capacity = float("inf")
    cursor = target
    visited: set[int] = set()
    while cursor != source:
        if cursor in visited:
            raise RuntimeError("Residual predecessor chain contains a cycle")
        visited.add(cursor)
        predecessor = predecessors[cursor]
        if predecessor is None:
            raise RuntimeError("Residual predecessor chain is incomplete")
        previous, arc_index = predecessor
        capacity = min(capacity, graph[previous][arc_index].capacity)
        cursor = previous
    return capacity


def _augment_path(
    graph: list[list[_ResidualArc]],
    predecessors: list[tuple[int, int] | None],
    source: int,
    target: int,
    quantity: float,
) -> None:
    cursor = target
    while cursor != source:
        predecessor = predecessors[cursor]
        if predecessor is None:
            raise RuntimeError("Residual predecessor chain is incomplete")
        previous, arc_index = predecessor
        arc = graph[previous][arc_index]
        reverse = graph[arc.target][arc.reverse_index]
        arc.capacity = max(arc.capacity - quantity, 0.0)
        reverse.capacity += quantity
        cursor = previous


def _flow_on_reference(
    graph: list[list[_ResidualArc]],
    reference: _ArcReference,
) -> float:
    residual_capacity = graph[reference.source][reference.arc_index].capacity
    return _clean_number(reference.initial_capacity - residual_capacity)


def _validate_final_flow(
    edges: list[NetworkEdge],
    edge_flows: dict[str, float],
    supply_usage: list[tuple[FlowSupply, float]],
    demand_service: list[tuple[FlowDemand, float]],
) -> None:
    total_volume = sum(quantity for _, quantity in supply_usage)
    tolerance = _scale_tolerance(total_volume)
    balance: dict[str, float] = {}

    for supply, quantity in supply_usage:
        if quantity < -tolerance or quantity > supply.available_mwh + tolerance:
            raise RuntimeError(f"Supply bound violated at {supply.node}")
        balance[supply.node] = balance.get(supply.node, 0.0) + quantity
    for demand, quantity in demand_service:
        if quantity < -tolerance or quantity > demand.required_mwh + tolerance:
            raise RuntimeError(f"Demand bound violated at {demand.node}")
        balance[demand.node] = balance.get(demand.node, 0.0) - quantity
    for edge in edges:
        quantity = edge_flows[edge.edge_id]
        if quantity < -tolerance or quantity > edge.available_capacity_mwh + tolerance:
            raise RuntimeError(f"Physical edge capacity violated: {edge.edge_id}")
        balance[edge.source] = balance.get(edge.source, 0.0) - quantity
        balance[edge.target] = balance.get(edge.target, 0.0) + quantity

    violations = {
        node: value for node, value in balance.items() if abs(value) > tolerance
    }
    if violations:
        detail = ", ".join(f"{node}={value:.12g}" for node, value in sorted(violations.items()))
        raise RuntimeError(f"Flow conservation failed: {detail}")


def _scale_tolerance(volume: float) -> float:
    return max(_TOLERANCE, abs(volume) * 1e-9)


def _clean_number(value: float) -> float:
    return 0.0 if abs(value) <= _TOLERANCE else float(value)
