"""Capacity-feasible minimum-cost route optimization."""

from __future__ import annotations

import heapq
from collections import defaultdict

from .models import NetworkEdge, RouteResult


def find_min_cost_route(
    edges: list[NetworkEdge],
    source: str,
    target: str,
    required_capacity_mwh: float,
    accessible_tsos: set[str] | None = None,
) -> RouteResult:
    """Return the cheapest directed route satisfying capacity and TSO-access constraints."""

    if required_capacity_mwh < 0:
        raise ValueError("required_capacity_mwh must be non-negative")
    if source == target:
        return RouteResult(
            status="optimal",
            edge_ids=(),
            nodes=(source,),
            total_cost_gbp_mwh=0.0,
            bottleneck_capacity_mwh=None,
        )

    adjacency: dict[str, list[NetworkEdge]] = defaultdict(list)
    for edge in edges:
        if not edge.enabled or edge.available_capacity_mwh < required_capacity_mwh:
            continue
        if edge.tso and accessible_tsos is not None and edge.tso not in accessible_tsos:
            continue
        adjacency[edge.source].append(edge)

    distances: dict[str, float] = {source: 0.0}
    predecessor: dict[str, tuple[str, NetworkEdge]] = {}
    queue: list[tuple[float, str]] = [(0.0, source)]

    while queue:
        distance, node = heapq.heappop(queue)
        if distance != distances.get(node):
            continue
        if node == target:
            break
        for edge in adjacency.get(node, []):
            candidate = distance + edge.tariff_gbp_mwh
            if candidate >= distances.get(edge.target, float("inf")):
                continue
            distances[edge.target] = candidate
            predecessor[edge.target] = (node, edge)
            heapq.heappush(queue, (candidate, edge.target))

    if target not in distances:
        return RouteResult(
            status="infeasible",
            edge_ids=(),
            nodes=(),
            total_cost_gbp_mwh=None,
            bottleneck_capacity_mwh=None,
            warnings=("No capacity-feasible route is available under the current TSO-access set.",),
        )

    reversed_edges: list[NetworkEdge] = []
    reversed_nodes = [target]
    cursor = target
    while cursor != source:
        previous, edge = predecessor[cursor]
        reversed_edges.append(edge)
        reversed_nodes.append(previous)
        cursor = previous

    selected_edges = list(reversed(reversed_edges))
    nodes = tuple(reversed(reversed_nodes))
    bottleneck = min(edge.available_capacity_mwh for edge in selected_edges)
    return RouteResult(
        status="optimal",
        edge_ids=tuple(edge.edge_id for edge in selected_edges),
        nodes=nodes,
        total_cost_gbp_mwh=distances[target],
        bottleneck_capacity_mwh=bottleneck,
    )
