"""The map's "Our book" view: what on the network relates to the firm's deals, and why.

Design basis 2, J.5. Three relevance classes, each item carrying the reasons it is there so the
map can say why ("delivery point of contract X", "reachable from TTF via BBL: spread a,
tariff b, net c"):

- **ours**: the delivery points, hubs, booked capacity and held storage of active contracts;
  the interconnection points on the path each contract is priced along to its allowed exits;
  expected cargoes with their terminal, and held regas slots;
- **reachable**: every neighbouring market area within two crossings of an "ours" hub along
  the proven ENTSOG adjacency (the graph route pricing walks), with the crossing points, their
  firm technical capacity where ENTSOG publishes it, the published tariffs the register holds
  for the legs and, when both hub prices and every tariff are held, the indicative spread net
  of those tariffs. A simulated price makes the figure simulated; a missing tariff or price is
  named, never estimated. No advice and no order: it is what the network makes reachable;
- **opportunity**: the paths of the caller's live opportunities from the opportunity core
  (``domain/opportunities``, ``application/opportunities/listing.visible_records``: the same
  book scope and entitlement as ``/api/opportunities``). An opportunity that buys at one hub
  and sells at another (``claim_fields`` ``buy_hub``/``sell_hub``: locational, held capacity)
  is drawn along the proven path between them, with its headline as the label on the far hub;
  actionable and indicative ones pop out, a watch-state one is a thin outline. The view adds
  no opportunity of its own and computes no margin: the figures are the core's.

Outages located at an "ours" or "reachable" point are listed as touching the book. Every input
is read from the store (contracts, capacity profiles, storage masters, cargoes, slots, tariffs,
market prices, FX) and the shipped reference bundle; nothing is a hand list.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import date, datetime
from typing import Any

#: The crossings a "reachable" market area may be away from an "ours" hub.
REACHABLE_MAX_CROSSINGS = 2

RULE = (
    "ours: delivery points, hubs, booked capacity and held storage of active contracts, the "
    "points on each contract's priced path to its allowed exits, expected cargoes and their "
    "terminals, held regas slots; reachable: market areas within two crossings of an ours hub "
    "along the proven ENTSOG adjacency, with published tariffs and an indicative spread net "
    "of them when both prices and every tariff are held; opportunity: from the opportunity "
    "core when it lands (none yet)."
)


#: Opportunity states the map draws: popped out, or (watch) as a thin outline.
DRAWN_OPPORTUNITY_STATES = {"actionable": "pop", "indicative": "pop", "watch": "outline"}


def book_opportunity_paths(
    session: Any,
    *,
    now: datetime,
    book_ids: set[str] | None,
    principal: Any = None,
    graph: Any = None,
) -> list[dict[str, Any]]:
    """The opportunity class: paths of the caller's live opportunities (see the module doc).

    Reads the core's stored records through its own visibility rule; without a principal (an
    internal caller) there are none. An opportunity without two hubs (a hedge gap, an event)
    has no path and is not drawn here; its own page lists it.
    """

    if principal is None:
        return []
    from eurogas_nexus.application.opportunities.listing import summary, visible_records
    from eurogas_nexus.domain.opportunities.model import TYPE_CODE, OpportunityType

    if graph is None:
        from eurogas_nexus.reference_data.network_adjacency import shipped_market_area_graph

        graph = shipped_market_area_graph()
    out: list[dict[str, Any]] = []
    for row in visible_records(session, principal):
        emphasis = DRAWN_OPPORTUNITY_STATES.get(str(row.state))
        fields = row.claim_fields or {}
        buy, sell = fields.get("buy_hub"), fields.get("sell_hub")
        if emphasis is None or not buy or not sell:
            continue
        start, target = graph.hub_for(str(buy)), graph.hub_for(str(sell))
        crossings = graph.route(start, target) if start and target else None
        if not crossings:
            continue
        out.append(
            {
                "opportunity_id": row.opportunity_id,
                "type": row.type,
                "type_code": TYPE_CODE[OpportunityType(row.type)],
                "state": row.state,
                "emphasis": emphasis,
                "claim": row.claim_text,
                # The core's own list-row figures (same rounding as /api/opportunities).
                "headline": summary(row)["headline"],
                "period": row.period_label,
                "simulated": bool(row.simulated),
                "from_hub": graph.hub_names.get(start, str(buy)),
                "to_hub": graph.hub_names.get(target, str(sell)),
                "path_node_ids": graph.path_node_ids(crossings),
                "via": [
                    str(graph.points.get(point, {}).get("name") or point)
                    for crossing in crossings
                    for point in crossing.points
                ],
            }
        )
    out.sort(key=lambda item: (item["emphasis"] != "pop", item["opportunity_id"]))
    return out


class _Collector:
    """Items by reference, each with the union of its reasons."""

    def __init__(self) -> None:
        self.items: dict[tuple[str, str], dict[str, Any]] = {}

    def add(
        self,
        kind: str,
        ref: str | None,
        name: str | None,
        location: dict[str, Any] | None,
        reason: dict[str, Any],
    ) -> None:
        if not ref:
            return
        item = self.items.setdefault(
            (kind, ref),
            {
                "kind": kind,
                "ref": ref,
                "name": name or ref,
                "location": (
                    {"lon": location["lon"], "lat": location["lat"]}
                    if location and location.get("lon") is not None
                    else None
                ),
                "reasons": [],
            },
        )
        if reason not in item["reasons"]:
            item["reasons"].append(reason)

    def values(self) -> list[dict[str, Any]]:
        return sorted(self.items.values(), key=lambda item: (item["kind"], item["name"]))


def _zone_hubs(bundle: dict[str, Any]) -> dict[str, set[str]]:
    """Point node id -> the hub node ids of the entry-exit zones it belongs to."""

    hubs = {node["id"] for node in bundle.get("nodes") or [] if node.get("type") == "hub"}
    out: dict[str, set[str]] = {}
    for edge in bundle.get("edges") or []:
        if edge.get("type") != "virtual":
            continue
        a, b = edge["from"], edge["to"]
        if b in hubs:
            out.setdefault(a, set()).add(b)
        elif a in hubs:
            out.setdefault(b, set()).add(a)
    return out


def _crossing_capacity(bundle: dict[str, Any]) -> dict[str, float]:
    """Point key -> ENTSOG firm technical capacity (kWh/d) where the bundle holds it."""

    out: dict[str, float] = {}
    for edge in bundle.get("edges") or []:
        value = edge.get("firm_technical_kwh_d")
        if isinstance(value, int | float) and value > 0 and edge.get("point_key"):
            out[str(edge["point_key"])] = max(out.get(str(edge["point_key"]), 0.0), float(value))
    return out


def build_book_relevance(
    session: Any,
    *,
    now: datetime,
    contracts: list[dict[str, Any]],
    cargoes: Iterable[dict[str, Any]],
    slots: Iterable[dict[str, Any]],
    outages: Iterable[dict[str, Any]],
    locate: Callable[[str], dict[str, Any] | None],
    entitled: Callable[[list], list],
    book_ids: set[str] | None,
    principal: Any = None,
) -> dict[str, Any]:
    """The three relevance classes for the caller's books (see the module docstring).

    ``contracts``, ``cargoes`` and ``slots`` are the map payload's own (already scoped to the
    caller's books); ``locate`` finds a place by name; ``entitled`` filters market rows by the
    caller's data scopes.
    """

    from eurogas_nexus.application.resource_pool import (
        candidate_route_cost,
        latest_market_price_by_point,
        value_in_gbp,
    )
    from eurogas_nexus.db.models import CapacityProfileRecord, FxObservationRecord
    from eurogas_nexus.db.models.risk_controls import CreditLineRecord
    from eurogas_nexus.db.models.storage_nomination import StorageFacilityMasterRecord
    from eurogas_nexus.db.repositories.market_intelligence import (
        list_market_observations_with_source_coverage,
    )
    from eurogas_nexus.db.repositories.route_cost import list_tso_tariffs
    from eurogas_nexus.domain.route_cost.route_adjacency import PROVEN, apply_route_adjacency
    from eurogas_nexus.reference_data.network_adjacency import shipped_market_area_graph
    from eurogas_nexus.reference_data.network_bundle import load_bundle

    graph = shipped_market_area_graph()
    bundle = load_bundle()
    zone_hubs = _zone_hubs(bundle)
    capacity_by_point = _crossing_capacity(bundle)
    node_by_id = {node["id"]: node for node in bundle.get("nodes") or []}
    hub_code_by_node = {
        info["node_id"]: graph.hub_names[key]
        for key, info in graph.points.items()
        if key in graph.hub_names
    }
    hub_node_by_code = {code: node for node, code in hub_code_by_node.items()}

    def hub_location(code: str) -> dict[str, Any] | None:
        node = node_by_id.get(hub_node_by_code.get(code, ""))
        return {"lon": node["lon"], "lat": node["lat"]} if node and node.get("located") else None

    def hub_of(name: str | None, ref: str | None) -> str | None:
        key = graph.hub_for(name)
        if key:
            return graph.hub_names[key]
        for hub_node in sorted(zone_hubs.get(ref or "", ())):
            if hub_node in hub_code_by_node:
                return hub_code_by_node[hub_node]
        first = (name or "").split(" ")[0]
        key = graph.hub_for(first)
        return graph.hub_names[key] if key else None

    counterparties: dict[str, str] = {}
    for line in session.query(CreditLineRecord).all():
        for contract_id in line.contract_ids or []:
            counterparties[str(contract_id)] = line.name or str(line.counterparty_id)

    ours = _Collector()
    ours_hubs: dict[str, list[str]] = {}
    contract_paths: list[dict[str, Any]] = []
    by_contract = {item["contract_id"]: item for item in contracts}
    for item in contracts:
        location = item.get("location") or {}
        if not location:
            # "NBP Easington": the hub's name, then the place; the place may still be located.
            words = str(item["delivery_point"]).split(" ", 1)
            location = (locate(words[1]) if len(words) == 2 else None) or {}
        ref = location.get("ref_id")
        reason = {
            "key": "delivery_point",
            "contract": item["contract_name"],
            "counterparty": counterparties.get(item["contract_id"]),
            "mwh_d": item.get("delivery_mwh_d"),
        }
        ours.add("point", ref, item["delivery_point"], location, reason)
        hub = hub_of(item["delivery_point"], ref)
        if hub:
            ours.add(
                "hub",
                hub_node_by_code.get(hub),
                hub,
                hub_location(hub),
                {"key": "contract_hub", "contract": item["contract_name"]},
            )
            ours_hubs.setdefault(hub, []).append(item["contract_name"])
        if item.get("entry_capacity_mwh_d"):
            ours.add(
                "capacity",
                ref,
                item["delivery_point"],
                location,
                {
                    "key": "held_capacity",
                    "contract": item["contract_name"],
                    "mwh_d": item["entry_capacity_mwh_d"],
                    "direction": "ENTRY",
                },
            )
        # The path each contract is priced along to the points it may be sold at.
        for exit_point in item.get("allowed_exit_points") or []:
            target = hub_of(exit_point, None)
            if not hub or not target or target == hub:
                continue
            routed = apply_route_adjacency(
                [
                    {
                        "route_id": f"book-{item['contract_id']}-{target}",
                        "start_point_name": hub,
                        "target_point_name": target,
                        "route_legs": [],
                    }
                ],
                graph,
            )[0]
            adjacency = routed.get("route_adjacency") or {}
            if adjacency.get("status") != PROVEN:
                continue
            contract_paths.append(
                {
                    "contract_id": item["contract_id"],
                    "contract": item["contract_name"],
                    "from_hub": hub,
                    "to_hub": target,
                    "mwh_d": item.get("delivery_mwh_d"),
                    "path_node_ids": adjacency.get("path_node_ids") or [],
                }
            )
            for crossing in adjacency.get("crossings") or []:
                for point_key, point_name in zip(
                    crossing["points"], crossing["point_names"], strict=False
                ):
                    info = graph.points.get(point_key) or {}
                    node = node_by_id.get(str(info.get("node_id")))
                    ours.add(
                        "point",
                        info.get("node_id"),
                        point_name,
                        node if node and node.get("located") else None,
                        {
                            "key": "contract_path",
                            "contract": item["contract_name"],
                            "from_hub": hub,
                            "to_hub": target,
                        },
                    )

    for profile in session.query(CapacityProfileRecord).all():
        contract = by_contract.get(profile.contract_id)
        if contract is None:
            continue
        valid_to = profile.valid_to_utc
        if valid_to is not None and valid_to.tzinfo is not None and valid_to < now:
            continue
        location = locate(profile.point_name)
        ours.add(
            "capacity",
            (location or {}).get("ref_id"),
            profile.point_name,
            location,
            {
                "key": "held_capacity",
                "contract": contract["contract_name"],
                "mwh_d": profile.capacity_mwh_per_day,
                "direction": profile.direction,
            },
        )

    for storage in session.query(StorageFacilityMasterRecord).all():
        if not storage.active:
            continue
        location = locate(storage.name)
        ours.add(
            "storage",
            (location or {}).get("ref_id") or f"storage:{storage.facility_id}",
            storage.name,
            location,
            {
                "key": "held_storage",
                "max_inventory_mwh": storage.maximum_inventory_mwh,
                "hub": storage.market_hub,
            },
        )

    for cargo in cargoes:
        if not cargo.get("own") or cargo.get("status") == "delivered":
            continue
        reason = {
            "key": "expected_cargo",
            "vessel": cargo["vessel_name"],
            "eta_utc": cargo.get("eta_utc"),
            "terminal": cargo.get("destination_terminal"),
        }
        ours.add("cargo", cargo["cargo_id"], cargo["vessel_name"], cargo.get("position"), reason)
        destination = cargo.get("destination") or {}
        ours.add(
            "terminal",
            destination.get("ref_id"),
            cargo.get("destination_terminal"),
            destination,
            reason,
        )
    for slot in slots:
        location = slot.get("location") or {}
        ours.add(
            "terminal",
            location.get("ref_id"),
            slot["terminal_name"],
            location,
            {
                "key": "regas_slot",
                "window_start_utc": slot["window_start_utc"],
                "window_end_utc": slot["window_end_utc"],
            },
        )

    # Reachable: neighbouring market areas within two crossings, priced as route pricing does.
    gas_day = now.date()
    tariffs = list_tso_tariffs(session)
    # Market rows by the caller's data scopes (the filter reads dict rows by source system).
    observed = list(list_market_observations_with_source_coverage(session, limit=2000))
    kept = entitled(
        [{"source_system": row.source_system, "row_index": i} for i, row in enumerate(observed)]
    )
    market_rows = [observed[int(view["row_index"])] for view in kept]
    prices = latest_market_price_by_point(market_rows)
    fx_rows = (
        session.query(FxObservationRecord)
        .order_by(FxObservationRecord.observed_at_utc.desc())
        .all()
    )
    reachable: list[dict[str, Any]] = []
    for hub in sorted(ours_hubs):
        start_key = graph.hub_for(hub)
        for target_key in sorted(graph.hub_names):
            target = graph.hub_names[target_key]
            if target_key == start_key:
                continue
            paths = graph.hub_paths(start_key, target_key, max_hops=REACHABLE_MAX_CROSSINGS)
            if not paths:
                continue
            routed = apply_route_adjacency(
                [
                    {
                        "route_id": f"book-reach-{hub}-{target}",
                        "start_point_name": hub,
                        "target_point_name": target,
                        "route_name": f"{hub} -> {target}",
                        "business_model": "CROSS_BORDER_TRANSFER",
                        "required_tso_access": [],
                        "route_legs": [{"capacity_product": "ANNUAL", "firmness": "FIRM"}],
                    }
                ],
                graph,
            )[0]
            adjacency = routed.get("route_adjacency") or {}
            if adjacency.get("status") != PROVEN:
                continue
            crossings = []
            for crossing in adjacency.get("crossings") or []:
                for point_key, point_name in zip(
                    crossing["points"], crossing["point_names"], strict=False
                ):
                    crossings.append(
                        {
                            "point_key": point_key,
                            "name": point_name,
                            "node_id": (graph.points.get(point_key) or {}).get("node_id"),
                            "pipeline": crossing.get("pipeline_operator"),
                            "firm_technical_gwh_d": (
                                round(capacity_by_point[point_key] / 1e6, 1)
                                if point_key in capacity_by_point
                                else None
                            ),
                        }
                    )
            reachable.append(
                {
                    "from_hub": hub,
                    "to_hub": target,
                    "crossings_count": len(adjacency.get("crossings") or []),
                    "via": [crossing["name"] for crossing in crossings],
                    "path_node_ids": adjacency.get("path_node_ids") or [],
                    "crossings": crossings,
                    "contracts": ours_hubs[hub],
                    **_indicative_spread(
                        routed,
                        prices.get(hub),
                        prices.get(target),
                        tariffs,
                        fx_rows,
                        gas_day,
                        candidate_route_cost,
                        value_in_gbp,
                    ),
                }
            )

    ours_items = ours.values()
    opportunities = book_opportunity_paths(
        session, now=now, book_ids=book_ids, principal=principal, graph=graph
    )
    touched_refs = (
        {item["ref"] for item in ours_items}
        | {crossing["node_id"] for path in reachable for crossing in path["crossings"]}
        | {node for item in opportunities for node in item["path_node_ids"]}
    )
    touching = sorted(
        str(outage.get("event_id"))
        for outage in outages
        if (outage.get("location") or {}).get("ref_id") in touched_refs
    )
    return {
        "rule": RULE,
        "ours": ours_items,
        "contract_paths": contract_paths,
        "reachable": reachable,
        "opportunities": opportunities,
        "outages_touching": touching,
    }


def _indicative_spread(
    routed: dict[str, Any],
    price_from: dict[str, Any] | None,
    price_to: dict[str, Any] | None,
    tariffs: list,
    fx_rows: list,
    gas_day: date,
    candidate_route_cost: Callable,
    value_in_gbp: Callable,
) -> dict[str, Any]:
    """Prices, published tariffs and the spread net of them, in GBP/MWh; gaps named."""

    def price_view(price: dict[str, Any] | None) -> dict[str, Any] | None:
        if price is None:
            return None
        return {
            "price": price["price"],
            "currency": price["currency"],
            "unit": price["unit"],
            "simulated": bool(price.get("simulated")),
            "observed_at_utc": price.get("observed_at_utc"),
        }

    out: dict[str, Any] = {
        "indicative": True,
        "price_from": price_view(price_from),
        "price_to": price_view(price_to),
        "tariff_gbp_mwh": None,
        "tariff_status": "not_assessed",
        "missing": [],
        "missing_legs": [],
        "spread_gbp_mwh": None,
        "net_gbp_mwh": None,
        "simulated": bool((price_from or {}).get("simulated") or (price_to or {}).get("simulated")),
    }
    currency = (price_to or price_from or {}).get("currency") or "EUR"
    unit = (price_to or price_from or {}).get("unit") or f"{currency}/MWh"
    cost, cost_currency, cost_unit, warnings, blockers, _refs = candidate_route_cost(
        routed,
        tariffs,
        price_currency=currency,
        price_unit=unit,
        tariff_applicability_date=gas_day,
    )
    if blockers:
        out["tariff_status"] = "missing"
        out["missing"] = sorted(set(blockers))
        text = " ".join(blockers)
        # The legs whose published tariff the register does not hold, as a desk names them.
        out["missing_legs"] = [
            f"{leg.get('tso')} {str(leg.get('direction') or '').lower()} {leg.get('point_name')}"
            for leg in routed.get("route_legs") or []
            if leg.get("leg_id") and str(leg["leg_id"]) in text
        ]
    else:
        tariff_gbp, _fx, _warning = value_in_gbp(cost, cost_currency, cost_unit, gas_day, fx_rows)
        out["tariff_gbp_mwh"] = tariff_gbp
        out["tariff_status"] = "held" if tariff_gbp is not None else "fx_missing"
        if any("SIMULATOR_ONLY" in str(warning) for warning in warnings):
            out["simulated"] = True
    if price_from is None or price_to is None:
        out["missing"].append(
            "MARKET_PRICE_MISSING:"
            + ",".join(
                hub for hub, price in (("from", price_from), ("to", price_to)) if price is None
            )
        )
        return out
    to_gbp, _fx_to, _w = value_in_gbp(
        price_to["price"], price_to["currency"], price_to["unit"], gas_day, fx_rows
    )
    from_gbp, _fx_from, _w = value_in_gbp(
        price_from["price"], price_from["currency"], price_from["unit"], gas_day, fx_rows
    )
    if to_gbp is None or from_gbp is None:
        out["missing"].append("MARKET_PRICE_FX_UNAVAILABLE")
        return out
    out["spread_gbp_mwh"] = round(to_gbp - from_gbp, 4)
    if out["tariff_gbp_mwh"] is not None:
        out["net_gbp_mwh"] = round(out["spread_gbp_mwh"] - out["tariff_gbp_mwh"], 4)
    return out
