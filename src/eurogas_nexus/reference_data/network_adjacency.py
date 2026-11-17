"""Which market areas each interconnection point joins: the commercial topology.

Route pricing needs the fact the map used to blur: a route from one hub to another passes
through a named interconnection point (or a chain of them), where the exit of one market area
and the entry of the next apply. This module derives those adjacencies from ENTSOG's published
``interconnections`` and ``connectionpoints`` datasets by a deterministic rule, and lists every
point whose other side it cannot prove. Nothing is inferred from names, distances or countries.

The rule (``ADJACENCY_RULE``)
-----------------------------

ENTSOG publishes one ``interconnections`` row per pair of sides at a point: the point
(``pointKey``) and, for each side, its system, balancing zone (``fromBzKey``/``toBzKey``),
operator and infrastructure type.

1. **One physical point is one point.** A key ENTSOG publishes as another key's alias
   (``SAME_PHYSICAL_POINT`` in ``application/pipeline_supply.py``: Dornum GASPOOL is Dornum /
   NETRA) is folded into its canonical key, and a physical point ENTSOG assigns to a virtual
   interconnection point (``connectionpoints.virtualPointKey``: Haanrade and Dinxperlo into VIP
   TTF-THE-L, Zandvliet H into VIP BENE, Blaregnies and Alveringem into VIRTUALYS) is folded into
   that VIP, where capacity is booked. One connection is never two.
2. **Each side resolves to a pipeline or a market area.**
   - A *two-point transmission system* is a side ``(systemLabel, operatorKey)`` run by a TSO
     (``-TSO-`` in the key) that ENTSOG lists, across all of Europe, at exactly two points: a
     pipeline with two ends (IUK: Bacton - Zeebrugge; BBL: Balgzand - Bacton). Its side resolves
     to the pipeline, whatever balancing zone ENTSOG files it under.
   - Otherwise a transmission side resolves to its balancing zone's trading point (``BZ_HUB``),
     or, for a zone with no trading point in the bundle (Austria, Czechia, Switzerland, Spain,
     Poland, Northern Ireland, the Belgian L-gas zone), to "outside".
   - A side that is not transmission (storage, LNG, production, distribution, final consumers)
     or has no balancing zone (the Norwegian upstream system) is supply or demand inside a market
     area, not a neighbouring one: the row proves no adjacency.
3. **A pipeline is in the network** when both its ends are located bundle points and each end
   also joins a market area of the bundle. Its two ends get one ``interconnector`` edge.
4. **A point is an adjacency** when it joins at least two in-network things (market areas or
   in-network pipelines): one ``market_area_link`` edge from the point to each market area it
   joins, with the operators on that market area's side and the ENTSOG row ids as evidence.
   Two sides in one market area (two TSOs inside THE) are an internal point: no edge.
5. **Only located points.** An edge needs both ends in the bundle with a position; a point
   ENTSOG publishes without one is listed with what it would join.
6. **One drawn line per pair of market areas.** Of the points joining the same two market areas,
   one is marked ``representative`` (the map draws it by default and pricing uses it when a
   route names no point): the largest firm technical capacity ENTSOG publishes for the build's
   gas day (``operationaldatas``, indicator Firm Technical), then a VIP (a point other points
   fold into, or ENTSOG ``commercialType`` Virtual), then the most ENTSOG rows, then the
   lowest point key. Pricing can use every edge.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from typing import Any

#: Balancing zone (ENTSOG ``BzKey``) to the ENTSOG point key of its virtual trading point.
BZ_HUB: dict[str, str] = {
    "NL---------": "VTP-00002",  # Netherlands: TTF
    "DE-THE-----": "VTP-00045",  # THE
    "BE-LUX------": "VTP-00016",  # BeLux H: ZTP
    "FR----------": "VTP-00039",  # TRF: PEG
    "UK---------": "VTP-00006",  # GB: NBP
    "DK-SE-------": "VTP-00001",  # Joint balancing zone DK/SE: GTF (ETF)
    "IE---------": "VTP-00005",  # Ireland: IBP
}

ADJACENCY_RULE = (
    "ENTSOG interconnections and connection points: aliases of one physical point and physical "
    "points of a virtual interconnection point are folded; each side of a valid row resolves to "
    "a pipeline (a TSO system ENTSOG lists at exactly two points) or to its balancing zone's "
    "trading point; a located point joining two in-network market areas or pipelines gets a "
    "market_area_link to each market area; a pipeline whose two located ends each join a market "
    "area gets an interconnector edge; one representative point per pair of market areas."
)

MARKET_AREA_LINK = "market_area_link"
INTERCONNECTOR = "interconnector"
ADJACENCY_EDGE_TYPES = frozenset({MARKET_AREA_LINK, INTERCONNECTOR})
TRANSMISSION = "Transmission"


def _valid(row: Mapping[str, Any]) -> bool:
    return not row.get("isInvalid") and bool(row.get("pointKey"))


def two_point_systems(rows: Iterable[Mapping[str, Any]]) -> dict[tuple[str, str], list[str]]:
    """TSO transmission systems ENTSOG lists at exactly two points: pipelines with two ends."""

    points: dict[tuple[str, str], set[str]] = defaultdict(set)
    for row in rows:
        if not _valid(row):
            continue
        for side in ("from", "to"):
            label, operator = row.get(f"{side}SystemLabel"), row.get(f"{side}OperatorKey")
            if not label or not operator or "-TSO-" not in str(operator):
                continue
            if row.get(f"{side}InfrastructureTypeLabel") != TRANSMISSION:
                continue
            points[(str(label), str(operator))].add(str(row["pointKey"]))
    return {key: sorted(value) for key, value in points.items() if len(value) == 2}


def virtual_point_folds(connection_points: Iterable[Mapping[str, Any]]) -> dict[str, str]:
    """Physical point key to the virtual interconnection point ENTSOG assigns it to."""

    folds: dict[str, str] = {}
    for row in connection_points:
        if row.get("isInvalid") or not row.get("hasVirtualPoint"):
            continue
        key, virtual = row.get("pointKey"), row.get("virtualPointKey")
        if key and virtual and key != virtual:
            folds[str(key)] = str(virtual)
    return folds


def derive_adjacency(
    rows: list[Mapping[str, Any]],
    nodes: list[Mapping[str, Any]],
    *,
    connection_points: list[Mapping[str, Any]] | None = None,
    aliases: Mapping[str, str] | None = None,
    operator_names: Mapping[str, str] | None = None,
    capacities: Mapping[str, float] | None = None,
    capacity_gas_day: str | None = None,
    downloaded: str,
) -> dict[str, Any]:
    """Adjacency edges and the points left unconnected, from ENTSOG's published data.

    Args:
        rows: ENTSOG ``interconnections`` rows: the whole dataset, so a system's point count
            is Europe-wide.
        nodes: The bundle's nodes (``point_key``, ``id``, ``type``, ``located``, ``name``).
        connection_points: ENTSOG ``connectionpoints`` rows (virtual point assignment and
            commercial type). Without them no point is folded into a VIP.
        aliases: Alias point key to canonical point key (one physical point).
        operator_names: Operator key to name, for edge labels.
        downloaded: Download date of the ENTSOG rows (YYYY-MM-DD), recorded on every edge.
        capacities: Point key to its largest firm technical capacity ENTSOG publishes for
            ``capacity_gas_day`` (kWh/d, any operator and direction): the first criterion for
            the point drawn for a pair of market areas.

    Returns:
        ``{"edges", "unconnected", "pipelines", "folded"}``, sorted, so the same input always
        gives the same output.
    """

    connection_points = list(connection_points or [])
    folds = {**virtual_point_folds(connection_points), **dict(aliases or {})}
    virtual_type = {
        str(row["pointKey"])
        for row in connection_points
        if row.get("pointKey") and row.get("commercialType") == "Virtual"
    }
    names = dict(operator_names or {})
    by_key = {str(node["point_key"]): node for node in nodes}
    hubs = {key for key, node in by_key.items() if node.get("type") == "hub"}
    hub_keys = set(BZ_HUB.values()) & hubs
    pipes = two_point_systems(rows)
    pipe_of = {key: f"pipeline:{key[1]}" for key in pipes}

    def canonical(key: str) -> str:
        seen = set()
        while key in folds and key not in seen:
            seen.add(key)
            key = folds[key]
        return key

    def resolve(row: Mapping[str, Any], side: str) -> tuple[str, str] | None:
        label, operator = row.get(f"{side}SystemLabel"), row.get(f"{side}OperatorKey")
        if label and operator and (str(label), str(operator)) in pipe_of:
            return ("pipeline", pipe_of[(str(label), str(operator))])
        if row.get(f"{side}InfrastructureTypeLabel") != TRANSMISSION:
            return None
        bz = row.get(f"{side}BzKey")
        if not bz:
            return None
        hub = BZ_HUB.get(str(bz))
        if hub and hub in hubs:
            return ("hub", hub)
        return ("outside", str(row.get(f"{side}BzLabel") or bz))

    joins: dict[str, set[tuple[str, str]]] = defaultdict(set)
    side_operators: dict[tuple[str, str], set[str]] = defaultdict(set)
    evidence: dict[str, set[str]] = defaultdict(set)
    folded_into: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        if not _valid(row):
            continue
        raw = str(row["pointKey"])
        point = canonical(raw)
        if point != raw:
            folded_into[point].add(raw)
        sides = [resolve(row, "from"), resolve(row, "to")]
        if sides[0] is None or sides[1] is None or sides[0] == sides[1]:
            continue
        for side, resolved in zip(("from", "to"), sides, strict=True):
            joins[point].add(resolved)
            operator = row.get(f"{side}OperatorKey")
            if operator:
                side_operators[(point, resolved[1])].add(str(operator))
        evidence[point].add(str(row.get("id") or ""))

    def located(key: str) -> bool:
        node = by_key.get(key)
        return bool(node and node.get("located"))

    pipe_ends = {
        pipe_of[key]: sorted({canonical(end) for end in ends}) for key, ends in pipes.items()
    }
    in_network_pipes = {
        pipe
        for pipe, ends in pipe_ends.items()
        if len(ends) == 2
        and all(located(end) for end in ends)
        and all(any(kind == "hub" for kind, _ in joins.get(end, set())) for end in ends)
    }

    edges: list[dict[str, Any]] = []
    unconnected: list[dict[str, Any]] = []
    for point in sorted(joins):
        node = by_key.get(point)
        areas = sorted(joins[point])
        hub_ends = [value for kind, value in areas if kind == "hub"]
        in_network = [value for kind, value in areas if kind == "hub" or value in in_network_pipes]
        others = [value for value in (v for _, v in areas) if value not in in_network]
        relevant = node is not None or any(value in hub_keys for _, value in areas)
        if not relevant or not in_network:
            continue
        if node is None or not node.get("located"):
            unconnected.append(
                {
                    "point_key": point,
                    "name": node.get("name") if node else None,
                    "joins": [value for _, value in areas],
                    "reason": "not in the bundle" if node is None else "no published position",
                }
            )
            continue
        if len(in_network) < 2:
            unconnected.append(
                {
                    "point_key": point,
                    "name": node.get("name"),
                    "joins": [value for _, value in areas],
                    "reason": "other side has no trading point in the bundle: " + ", ".join(others),
                }
            )
            continue
        for hub in hub_ends:
            edges.append(
                {
                    "id": f"adj-{point.lower()}-{hub.lower()}",
                    "from": node["id"],
                    "to": by_key[hub]["id"],
                    "type": MARKET_AREA_LINK,
                    "schematic": True,
                    "basis": "entsog_interconnection",
                    "point_key": point,
                    "hub_point_key": hub,
                    "joins": in_network,
                    "operators": sorted(side_operators[(point, hub)]),
                    "folded_points": sorted(folded_into.get(point, set())),
                    "evidence": sorted(evidence[point]),
                    "virtual_point": point in virtual_type or bool(folded_into.get(point)),
                    "firm_technical_kwh_d": (capacities or {}).get(point),
                    "capacity_gas_day": capacity_gas_day if (capacities or {}).get(point) else None,
                    "representative": False,
                    "downloaded": downloaded,
                }
            )
    for (label, operator), _ends in sorted(pipes.items()):
        pipe = pipe_of[(label, operator)]
        ends = pipe_ends[pipe]
        if not any(end in by_key for end in ends):
            continue
        name = names.get(operator, label)
        if pipe not in in_network_pipes:
            unconnected.append(
                {
                    "point_key": "/".join(ends),
                    "name": f"{name} pipeline",
                    "joins": ends,
                    "reason": (
                        "the pipeline does not join two market areas of the bundle at both ends"
                    ),
                }
            )
            continue
        a, b = by_key[ends[0]], by_key[ends[1]]
        edges.append(
            {
                "id": f"pipe-{operator.lower()}",
                "from": a["id"],
                "to": b["id"],
                "type": INTERCONNECTOR,
                "schematic": True,
                "basis": "entsog_two_point_system",
                "pipeline": pipe,
                "operator_key": operator,
                "system_label": label,
                "name": name,
                "point_keys": ends,
                "representative": True,
                "downloaded": downloaded,
            }
        )
    _mark_representatives(edges)
    return {
        "edges": sorted(edges, key=lambda edge: edge["id"]),
        "unconnected": sorted(unconnected, key=lambda item: item["point_key"]),
        "pipelines": [
            {
                "system": label,
                "operator_key": operator,
                "points": ends,
                "in_network": pipe_of[(label, operator)] in in_network_pipes,
            }
            for (label, operator), ends in sorted(pipes.items())
        ],
        "folded": {
            key: folds[key] for key in sorted(folds) if key in by_key or folds[key] in by_key
        },
    }


def _mark_representatives(edges: list[dict[str, Any]]) -> None:
    """Mark one point per pair of market areas (or market area and pipeline) as drawn."""

    by_point: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for edge in edges:
        if edge["type"] == MARKET_AREA_LINK:
            by_point[edge["point_key"]].append(edge)
    best: dict[tuple[str, ...], tuple[tuple[float, int, int, str], str]] = {}
    for point, point_edges in by_point.items():
        first = point_edges[0]
        pair = tuple(sorted(first["joins"]))
        # The busiest border point first: the largest firm technical capacity ENTSOG publishes
        # (VIP TTF-THE-H, 816 GWh/d, over the L-gas VIP); then a VIP, then the most rows.
        score = (
            float(first.get("firm_technical_kwh_d") or 0.0),
            1 if first["virtual_point"] else 0,
            len(first["evidence"]),
            _negated(point),
        )
        if pair not in best or score > best[pair][0]:
            best[pair] = (score, point)
    chosen = {point for _, point in best.values()}
    for edge in edges:
        if edge["type"] == MARKET_AREA_LINK:
            edge["representative"] = edge["point_key"] in chosen


def _negated(key: str) -> str:
    """Sort key that prefers the lowest point key under ``max``."""

    return "".join(chr(0x10FFFF - ord(char)) for char in key)


def apply_to_bundle(
    bundle: dict[str, Any],
    rows: list[Mapping[str, Any]],
    connection_points: list[Mapping[str, Any]],
    *,
    downloaded: str,
    aliases: Mapping[str, str] | None = None,
    capacities: Mapping[str, float] | None = None,
    capacity_gas_day: str | None = None,
) -> dict[str, Any]:
    """The bundle with its adjacency edges (re)derived; zone-membership edges are kept."""

    result = derive_adjacency(
        rows,
        bundle["nodes"],
        connection_points=connection_points,
        aliases=aliases,
        operator_names={
            key: str(value.get("name") or key)
            for key, value in (bundle.get("operators") or {}).items()
        },
        capacities=capacities,
        capacity_gas_day=capacity_gas_day,
        downloaded=downloaded,
    )
    kept = [
        edge for edge in bundle.get("edges") or [] if edge.get("type") not in ADJACENCY_EDGE_TYPES
    ]
    datasets = list((bundle.get("source") or {}).get("datasets") or [])
    if "interconnections" not in datasets:
        datasets.append("interconnections")
    return {
        **bundle,
        "source": {**(bundle.get("source") or {}), "datasets": datasets},
        "adjacency": {
            "rule": ADJACENCY_RULE,
            "downloaded": downloaded,
            "attribution": f"ENTSOG TP [{_dmy(downloaded)}] https://transparency.entsog.eu/",
            "market_area_hubs": dict(BZ_HUB),
            "pipelines": result["pipelines"],
            "folded": result["folded"],
            "unconnected": result["unconnected"],
        },
        "edges": kept + result["edges"],
    }


def _dmy(iso_day: str) -> str:
    year, month, day = iso_day.split("-")
    return f"{day}-{month}-{year}"


_GRAPH_CACHE: dict[str, Any] = {}


def shipped_market_area_graph():
    """The pricing graph of the shipped reference bundle (read once per process)."""

    from eurogas_nexus.domain.route_cost.market_area_graph import MarketAreaGraph
    from eurogas_nexus.reference_data.network_bundle import load_bundle

    if "graph" not in _GRAPH_CACHE:
        _GRAPH_CACHE["graph"] = MarketAreaGraph.from_bundle(load_bundle())
    return _GRAPH_CACHE["graph"]
