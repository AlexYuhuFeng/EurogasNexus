"""Shared-capacity multi-source, multi-sink gas network flow optimizer."""

from __future__ import annotations

from dataclasses import dataclass
from heapq import heappop, heappush

from .models import NetworkEdge, OptimizationStatus


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


def optimize_network_flow(
    edges: list[NetworkEdge],
    supplies: list[FlowSupply],
    demands: list[FlowDemand],
    *,
    accessible_tsos: set[str] | None = None,
) -> NetworkFlowResult:
    """Route portfolio volumes while enforcing shared residual edge capacities.

    The implementation uses successive cheapest augmenting paths. It is exact for
    linear single-commodity flow with the supplied source costs and demand values.
    """

    residual = {
        edge.edge_id: edge.available_capacity_mwh
        for edge in edges
        if edge.enabled
        and (
            accessible_tsos is None
            or edge.tso is None
            or edge.tso in accessible_tsos
        )
    }
    edge_by_id = {edge.edge_id: edge for edge in edges}
    remaining_supply = {item.node: item.available_mwh for item in supplies}
    supply_cost = {item.node: item.unit_cost_gbp_mwh for item in supplies}
    remaining_demand = {item.node: item.required_mwh for item in demands}
    demand_value = {item.node: item.value_gbp_mwh for item in demands}
    edge_totals: dict[str, float] = {}
    total_cost = 0.0
    total_value = 0.0

    while True:
        best: tuple[float, str, str, tuple[str, ...]] | None = None
        for source, available in remaining_supply.items():
            if available <= 1e-9:
                continue
            for target, required in remaining_demand.items():
                if required <= 1e-9:
                    continue
                path = _shortest_path(source, target, edges, residual, accessible_tsos)
                if path is None:
                    continue
                edge_ids, path_cost = path
                unit_objective = demand_value[target] - supply_cost[source] - path_cost
                candidate = (-unit_objective, source, target, edge_ids)
                if best is None or candidate < best:
                    best = candidate
        if best is None:
            break

        neg_objective, source, target, edge_ids = best
        unit_objective = -neg_objective
        if unit_objective < 0:
            break
        bottleneck = min(
            (residual[edge_id] for edge_id in edge_ids),
            default=float("inf"),
        )
        quantity = min(remaining_supply[source], remaining_demand[target], bottleneck)
        if quantity <= 1e-9:
            break
        path_cost = sum(edge_by_id[edge_id].tariff_gbp_mwh for edge_id in edge_ids)
        remaining_supply[source] -= quantity
        remaining_demand[target] -= quantity
        total_cost += quantity * (supply_cost[source] + path_cost)
        total_value += quantity * demand_value[target]
        for edge_id in edge_ids:
            residual[edge_id] -= quantity
            edge_totals[edge_id] = edge_totals.get(edge_id, 0.0) + quantity

    served = sum(item.required_mwh for item in demands) - sum(remaining_demand.values())
    unserved = sum(remaining_demand.values())
    status: OptimizationStatus = (
        "optimal"
        if unserved <= 1e-9
        else ("feasible" if served > 0 else "infeasible")
    )
    warnings = () if unserved <= 1e-9 else ("UNSERVED_DEMAND_REMAINS",)
    return NetworkFlowResult(
        status=status,
        served_demand_mwh=served,
        unserved_demand_mwh=unserved,
        total_network_cost_gbp=total_cost,
        total_objective_gbp=total_value - total_cost,
        edge_flows=tuple(
            EdgeFlow(edge_id, quantity)
            for edge_id, quantity in sorted(edge_totals.items())
        ),
        warnings=warnings,
    )


def _shortest_path(
    source: str,
    target: str,
    edges: list[NetworkEdge],
    residual: dict[str, float],
    accessible_tsos: set[str] | None,
) -> tuple[tuple[str, ...], float] | None:
    adjacency: dict[str, list[NetworkEdge]] = {}
    for edge in edges:
        if residual.get(edge.edge_id, 0.0) <= 1e-9:
            continue
        if not edge.enabled:
            continue
        if (
            accessible_tsos is not None
            and edge.tso is not None
            and edge.tso not in accessible_tsos
        ):
            continue
        adjacency.setdefault(edge.source, []).append(edge)
    queue: list[tuple[float, str, tuple[str, ...]]] = [(0.0, source, ())]
    best_cost: dict[str, float] = {source: 0.0}
    while queue:
        cost, node, path = heappop(queue)
        if node == target:
            return path, cost
        if cost > best_cost.get(node, float("inf")):
            continue
        for edge in adjacency.get(node, []):
            next_cost = cost + edge.tariff_gbp_mwh
            if next_cost < best_cost.get(edge.target, float("inf")):
                best_cost[edge.target] = next_cost
                heappush(queue, (next_cost, edge.target, (*path, edge.edge_id)))
    return None
