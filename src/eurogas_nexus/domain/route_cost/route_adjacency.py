"""Route candidates checked and completed against the market-area graph before pricing.

Every reader of route candidates (``list_route_candidates``) passes them through
:func:`apply_route_adjacency`, so the resource pool, the route-cost API, the intraday economics,
the portfolio network and the scenario context all price the same thing:

- a **local** route (start and target are the same market area, no legs) is unchanged;
- a **network** route between two hubs is priced only along proven adjacency
  (:class:`~eurogas_nexus.domain.route_cost.market_area_graph.MarketAreaGraph`): its legs become
  the exit, pipeline and entry legs of every crossing on the path, in flow order. Points the
  candidate names (a leg's ``point_key``, or ``via_point_keys``) fix which crossing is used.
  The author's legs contribute the route's capacity (the smallest they state) and the
  booking product and firmness; the path's legs replace them, so nothing is charged twice;
- a network route with **no proven path**, or whose endpoints are not market areas of the
  network, gets no legs and a ``route_adjacency`` status saying why: every pricing path then
  blocks it (``ROUTE_TARIFF_LEGS_REQUIRED``) instead of pricing a connection that does not
  exist, or an incomplete one.

A crossing leg whose tariff the register does not hold is priced as missing by the route-cost
engine (``TARIFF_MISSING``); it is never priced at zero.
"""

from __future__ import annotations

from typing import Any

from eurogas_nexus.domain.route_cost.market_area_graph import (
    TARIFF_GAS_YEAR_BY_PERIOD,
    MarketAreaGraph,
)

PROVEN = "proven"
LOCAL = "local"
NO_PROVEN_CONNECTION = "no_proven_connection"
ENDPOINT_NOT_IN_NETWORK = "endpoint_not_in_network"

#: Blocker code a pricing consumer reports for an unproven route.
ROUTE_NOT_CONNECTED = "ROUTE_NOT_CONNECTED"


def apply_route_adjacency(
    candidates: list[dict[str, Any]],
    graph: MarketAreaGraph | None = None,
) -> list[dict[str, Any]]:
    """The candidates with their legs taken from the proven path (see the module docstring)."""

    if graph is None:
        from eurogas_nexus.reference_data.network_adjacency import shipped_market_area_graph

        graph = shipped_market_area_graph()
    return [_apply(candidate, graph) for candidate in candidates]


def _apply(candidate: dict[str, Any], graph: MarketAreaGraph) -> dict[str, Any]:
    out = dict(candidate)
    legs = [dict(leg) for leg in candidate.get("route_legs") or []]
    start_name = str(candidate.get("start_point_name") or "")
    target_name = str(candidate.get("target_point_name") or "")
    if start_name.strip().upper() == target_name.strip().upper() and not legs:
        out["route_adjacency"] = {"status": LOCAL}
        return out
    start, target = graph.hub_for(start_name), graph.hub_for(target_name)
    if start is None or target is None:
        out["route_legs"] = []
        out["route_adjacency"] = {
            "status": ENDPOINT_NOT_IN_NETWORK,
            "detail": "start or target is not a market area of the reference network",
            "unresolved": [
                name for name, hub in ((start_name, start), (target_name, target)) if hub is None
            ],
        }
        return out
    if start == target:
        out["route_adjacency"] = {"status": LOCAL, "start_hub": start, "target_hub": target}
        return out
    via = [str(leg["point_key"]) for leg in legs if leg.get("point_key")]
    via += [str(point) for point in candidate.get("via_point_keys") or []]
    crossings = graph.route(start, target, via_points=via)
    if crossings is None:
        out["route_legs"] = []
        out["route_adjacency"] = {
            "status": NO_PROVEN_CONNECTION,
            "detail": "no proven interconnection path"
            + (f" through {', '.join(via)}" if via else "")
            + f" from {graph.hub_names.get(start, start)} to {graph.hub_names.get(target, target)}",
            "start_hub": start,
            "target_hub": target,
        }
        return out
    # What the author's legs still say once the path fixes the legs: the capacity the route
    # has (the smallest any authored leg states), and the booking product and firmness.
    capacities = [
        float(leg["available_capacity_mwh_per_day"])
        for leg in legs
        if isinstance(leg.get("available_capacity_mwh_per_day"), int | float)
    ]
    booking = {
        name: next((leg[name] for leg in legs if leg.get(name)), None)
        for name in ("capacity_product", "firmness")
    }
    priced: list[dict[str, Any]] = []
    route_id = str(candidate.get("route_id") or "route")
    for hop, crossing in enumerate(crossings, start=1):
        for index, spec in enumerate(graph.legs(crossing), start=1):
            leg: dict[str, Any] = {
                "leg_id": f"{route_id}:{hop}.{index}:{spec.point_key}:{spec.direction.lower()}",
                "country": spec.country,
                "tso": spec.tso,
                "market_area": spec.market_area,
                "point_name": spec.point_name,
                "direction": spec.direction,
                # The tariff covering the delivery gas day, whatever its period (ENTSOG
                # publishes calendar-year and gas-year tariffs side by side).
                "gas_year": TARIFF_GAS_YEAR_BY_PERIOD,
                "point_key": spec.point_key,
                "role": spec.role,
            }
            if capacities:
                leg["available_capacity_mwh_per_day"] = min(capacities)
            leg.update({name: value for name, value in booking.items() if value})
            priced.append(leg)
    out["route_legs"] = priced
    out["route_adjacency"] = {
        "status": PROVEN,
        "start_hub": start,
        "target_hub": target,
        "crossings": [
            {
                "from_hub": graph.hub_names.get(crossing.from_hub, crossing.from_hub),
                "to_hub": graph.hub_names.get(crossing.to_hub, crossing.to_hub),
                "points": list(crossing.points),
                "point_names": [
                    str(graph.points.get(point, {}).get("name") or point)
                    for point in crossing.points
                ],
                "pipeline_operator": crossing.pipeline_operator,
            }
            for crossing in crossings
        ],
        "path_node_ids": graph.path_node_ids(crossings),
    }
    return out


def route_adjacency_blocker(candidate: dict[str, Any]) -> str | None:
    """The blocker a pricing consumer reports for an unproven route, or None."""

    status = (candidate.get("route_adjacency") or {}).get("status")
    if status in (NO_PROVEN_CONNECTION, ENDPOINT_NOT_IN_NETWORK):
        return f"{ROUTE_NOT_CONNECTED}:{candidate.get('route_id')}"
    return None
