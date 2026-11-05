"""Bounded minimum-cost circulation with explicit lower bounds.

Feasibility uses augmenting paths; residual negative-cycle cancellation then
minimizes cost. A result is optimal only when no improving residual cycle
remains. This energy-conserving kernel uses floating-point tolerances stated in
the result; it is not a generalized-flow solver for multiplicative losses.
"""

import math
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass

EPS = 1e-9
VERSION = "bounded-circulation/1"


@dataclass(frozen=True)
class Arc:
    arc_id: str
    source: str
    target: str
    lower: float
    upper: float
    cost: float


def solve_circulation(arcs: list[Arc], checkpoint: Callable[[], None] = lambda: None) -> dict:
    if len(arcs) > 2048 or len({a.arc_id for a in arcs}) != len(arcs):
        raise ValueError("arc identifiers must be unique; maximum 2048 arcs")
    nodes = sorted({n for arc in arcs for n in (arc.source, arc.target)})
    if len(nodes) > 512:
        raise ValueError("maximum 512 nodes")
    for arc in arcs:
        if (
            not all(math.isfinite(v) for v in (arc.lower, arc.upper, arc.cost))
            or arc.lower < 0
            or arc.upper < arc.lower
            or arc.source == arc.target
        ):
            raise ValueError("invalid circulation arc")
    ids = {node: i for i, node in enumerate(nodes)}
    n = len(nodes)
    graph = [[] for _ in range(n + 2)]
    balance = [0.0] * n
    links = {}

    def add(u, v, capacity, cost):
        index = len(graph[u])
        graph[u].append([v, len(graph[v]), capacity, cost])
        graph[v].append([u, index, 0.0, -cost])
        return u, index

    for arc in sorted(arcs, key=lambda a: a.arc_id):
        u, v = ids[arc.source], ids[arc.target]
        links[arc.arc_id] = add(u, v, arc.upper - arc.lower, arc.cost)
        balance[u] -= arc.lower
        balance[v] += arc.lower
    required = 0.0
    for node, value in enumerate(balance):
        if value > EPS:
            add(n, node, value, 0)
            required += value
        elif value < -EPS:
            add(node, n + 1, -value, 0)
    sent = 0.0
    while sent < required - EPS:
        checkpoint()
        previous = {n: None}
        queue = deque([n])
        while queue and n + 1 not in previous:
            u = queue.popleft()
            for i, (v, _, cap, _) in enumerate(graph[u]):
                if cap > EPS and v not in previous:
                    previous[v] = (u, i)
                    queue.append(v)
        if n + 1 not in previous:
            return {
                "status": "infeasible",
                "flows": {},
                "cost": None,
                "unsatisfied_lower_bound": required - sent,
                "engine": VERSION,
            }
        path, v = [], n + 1
        while v != n:
            u, i = previous[v]
            path.append((u, i))
            v = u
        amount = min(graph[u][i][2] for u, i in path)
        _augment(graph, path, amount)
        sent += amount
    for u in range(n + 2):
        for edge in graph[u]:
            if u >= n or edge[0] >= n:
                edge[2] = 0
    iterations = 0
    while True:
        checkpoint()
        distance, previous, last = [0.0] * n, [None] * n, None
        for _ in range(n):
            last = None
            for u in range(n):
                for i, (v, _, cap, cost) in enumerate(graph[u]):
                    if v < n and cap > EPS and distance[v] > distance[u] + cost + EPS:
                        distance[v], previous[v], last = distance[u] + cost, (u, i), v
            if last is None:
                break
        if last is None:
            break
        for _ in range(n):
            last = previous[last][0]
        cycle, v = [], last
        while True:
            u, i = previous[v]
            cycle.append((u, i))
            v = u
            if v == last:
                break
        _augment(graph, cycle, min(graph[u][i][2] for u, i in cycle))
        iterations += 1
        if iterations > 20_000:
            raise TimeoutError("circulation iteration budget exhausted")
    flows = {}
    for arc in arcs:
        u, i = links[arc.arc_id]
        v, reverse, _, _ = graph[u][i]
        flows[arc.arc_id] = arc.lower + graph[v][reverse][2]
    return {
        "status": "optimal",
        "flows": flows,
        "cost": sum(flows[a.arc_id] * a.cost for a in arcs),
        "engine": VERSION,
        "iterations": iterations,
        "tolerance": EPS,
    }


def _augment(graph, path, amount):
    for u, i in path:
        v, reverse, _, _ = graph[u][i]
        graph[u][i][2] -= amount
        graph[v][reverse][2] += amount
