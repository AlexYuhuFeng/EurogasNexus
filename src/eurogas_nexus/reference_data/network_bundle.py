"""The shipped north-west Europe reference network: load, check and seed.

A fresh installation has no network until ENTSOG is first read, and an installation with no
outbound network never reads it. The bundle closes that gap: a versioned file of ENTSOG
Transparency Platform reference metadata (connection points and operator point directions)
for the NWE scope, plus schematic zone links, loaded into an empty store through the same
reference upsert the live ENTSOG read uses (``upsert_reference_snapshot``: upsert in place,
retire rather than delete).

What the bundle is, and is not (``docs/legal/DATA_SOURCE_TERMS.md``, "Reference network
bundle"):

- **Points** carry ENTSOG's own point key, EIC, label, operators and the position ENTSOG's
  map gives them, transformed to an approximate lon/lat exactly as the live ingestion does
  (``coordinate_quality = display_approximation``, never ``verified``). A point ENTSOG
  publishes without a map position has ``lat``/``lon`` null: it is seeded as operator access
  rows only, and the map counts it as not located, never placed at a guessed position.
- **Edges** are not pipelines. ENTSOG publishes no route geometry through its API, and no
  openly licensed route geometry is used. Each edge links a point to the virtual trading
  point of an entry-exit zone its operator belongs to (``connection_basis =
  entry_exit_zone``, ``schematic = true``). It records zone membership: the map uses it to
  mark a hub's points when the hub is selected and never draws it as a line, because a
  trading point is a market area, not a place wired to its points.

The seed never overwrites a live read: when the store already holds ENTSOG reference points
that did not come from a bundle, it changes nothing (``skipped_live_reference_present``).
Once live ENTSOG reference data is ingested, it takes over the same ids.
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import UTC, datetime
from importlib import resources
from pathlib import Path
from typing import Any

from eurogas_nexus.reference_data.network_adjacency import (
    ADJACENCY_EDGE_TYPES,
    INTERCONNECTOR,
    MARKET_AREA_LINK,
)

BUNDLE_SCHEMA = "eurogas-nexus/reference-network-bundle/1"
BUNDLE_RESOURCE = "nwe_reference_network.json"
#: ``data_status`` the seed writes into node metadata: how a bundle row is told from a live one.
BUNDLE_DATA_STATUS = "reference_bundle"
#: ``source_system`` of the schematic zone links (derived here, not published by ENTSOG).
BUNDLE_EDGE_SOURCE = "EGN_REFERENCE_BUNDLE"
NODE_TYPES = frozenset({"interconnection", "storage", "lng", "entry_point", "hub"})
#: Zone membership (``virtual``) and the adjacency the route pricing walks.
EDGE_TYPES = frozenset({"virtual", MARKET_AREA_LINK, INTERCONNECTOR})
DIRECTIONS = frozenset({"entry", "exit"})


def bundle_path() -> Path:
    return Path(str(resources.files("eurogas_nexus.reference_data").joinpath(BUNDLE_RESOURCE)))


def load_bundle(path: str | Path | None = None) -> dict[str, Any]:
    """The bundle as stored (the shipped file unless ``path`` names another)."""

    target = Path(path) if path else bundle_path()
    return json.loads(target.read_text(encoding="utf-8"))


def validate_bundle(bundle: dict[str, Any]) -> list[str]:
    """Integrity problems, empty when the bundle is sound.

    Checks: schema and version present; unique node, access and edge ids; every node has a
    known type and a two-letter country; a located node has finite in-range coordinates, a
    display-approximation quality and ``verified`` false; an unlocated node has neither
    coordinate; every access row names a node; every edge joins two located nodes, is
    flagged schematic and is not a self-loop; no connection is listed twice.
    """

    problems: list[str] = []
    if bundle.get("schema") != BUNDLE_SCHEMA:
        problems.append(f"schema is {bundle.get('schema')!r}, expected {BUNDLE_SCHEMA!r}")
    if not bundle.get("version"):
        problems.append("version missing")
    if not (bundle.get("source") or {}).get("attribution"):
        problems.append("source attribution missing")
    nodes = bundle.get("nodes") or []
    if not nodes:
        problems.append("no nodes")
    counts = Counter(node.get("id") for node in nodes)
    problems += [f"duplicate node id {key}" for key, n in counts.items() if n > 1]
    located: set[str] = set()
    for node in nodes:
        nid = node.get("id")
        if node.get("type") not in NODE_TYPES:
            problems.append(f"{nid}: unknown type {node.get('type')!r}")
        country = node.get("country")
        if not (isinstance(country, str) and len(country) == 2 and country.isupper()):
            problems.append(f"{nid}: country {country!r} is not ISO alpha-2")
        if not node.get("name") or not node.get("point_key"):
            problems.append(f"{nid}: name or point key missing")
        lat, lon = node.get("lat"), node.get("lon")
        if node.get("located"):
            if not (
                isinstance(lat, int | float)
                and isinstance(lon, int | float)
                and -90 <= lat <= 90
                and -180 <= lon <= 180
            ):
                problems.append(f"{nid}: located without valid coordinates")
            if node.get("coordinate_quality") != "display_approximation":
                problems.append(f"{nid}: coordinate quality must be display_approximation")
            located.add(nid)
        elif lat is not None or lon is not None:
            problems.append(f"{nid}: unlocated node carries a coordinate")
        if node.get("verified") is not False:
            problems.append(f"{nid}: verified flag must be false (no surveyed position)")
    node_ids = set(counts)
    keys = {node.get("point_key") for node in nodes}
    access = bundle.get("access") or []
    access_counts = Counter(row.get("access_id") for row in access)
    problems += [f"duplicate access id {key}" for key, n in access_counts.items() if n > 1]
    for row in access:
        if row.get("point_key") not in keys:
            problems.append(f"access {row.get('access_id')}: unknown point {row.get('point_key')}")
        if row.get("operator_key") not in (bundle.get("operators") or {}):
            problems.append(f"access {row.get('access_id')}: unknown operator")
        flags = row.get("flags")
        if not (isinstance(flags, str) and len(flags) == 6 and set(flags) <= {"0", "1"}):
            problems.append(f"access {row.get('access_id')}: flags {flags!r}")
        if row.get("direction") not in DIRECTIONS:
            problems.append(f"access {row.get('access_id')}: direction {row.get('direction')!r}")
    edges = bundle.get("edges") or []
    edge_counts = Counter(edge.get("id") for edge in edges)
    problems += [f"duplicate edge id {key}" for key, n in edge_counts.items() if n > 1]
    pairs: set[tuple[str, str, str]] = set()
    for edge in edges:
        eid, ends = edge.get("id"), (edge.get("from"), edge.get("to"))
        for end in ends:
            if end not in node_ids:
                problems.append(f"edge {eid}: unknown node {end}")
            elif end not in located:
                problems.append(f"edge {eid}: node {end} has no position to draw from")
        if ends[0] == ends[1]:
            problems.append(f"edge {eid}: self-loop")
        if edge.get("schematic") is not True:
            problems.append(f"edge {eid}: schematic flag must be true")
        kind = edge.get("type")
        if kind not in EDGE_TYPES:
            problems.append(f"edge {eid}: unknown type {kind!r}")
        elif kind == "virtual" and edge.get("basis", "entry_exit_zone") != "entry_exit_zone":
            problems.append(f"edge {eid}: a zone link must have basis entry_exit_zone")
        elif kind in ADJACENCY_EDGE_TYPES and not (edge.get("downloaded") and edge.get("basis")):
            problems.append(f"edge {eid}: adjacency edge without provenance")
        if kind == MARKET_AREA_LINK and not edge.get("evidence"):
            problems.append(f"edge {eid}: market-area link without ENTSOG evidence")
        # Zone membership and adjacency may join the same pair (a border point is in a zone
        # and joins it to the next); within one kind a pair is listed once.
        pair = (str(kind), *sorted(str(end) for end in ends))
        if pair in pairs:
            problems.append(f"edge {eid}: duplicate connection {pair[1:]}")
        pairs.add(pair)
    has_adjacency = any(edge.get("type") in ADJACENCY_EDGE_TYPES for edge in edges)
    if has_adjacency and not bundle.get("adjacency"):
        problems.append("adjacency edges without the adjacency block (rule, download date)")
    return problems


def _node_metadata(bundle: dict[str, Any], node: dict[str, Any]) -> dict[str, Any]:
    source = bundle["source"]
    return {
        "source_system": "ENTSOG",
        "point_key": node["point_key"],
        "point_eic_code": node.get("eic"),
        "point_type": node.get("point_type"),
        "infrastructure_label": node.get("infrastructure"),
        "operators": node.get("operators") or [],
        "entsog_map_x": node.get("entsog_map_x"),
        "entsog_map_y": node.get("entsog_map_y"),
        "coordinate_source": "entsog-tp-map-transform",
        "coordinate_quality": "display_approximation",
        "coordinate_verification_status": "unverified",
        "country_basis": node.get("country_basis"),
        "data_status": BUNDLE_DATA_STATUS,
        "reference_bundle_version": bundle["version"],
        "attribution": source["attribution"],
    }


def reference_rows(bundle: dict[str, Any], *, now: datetime) -> dict[str, list[dict[str, Any]]]:
    """Rows for ``reference_nodes``, ``reference_facilities``, ``reference_tso_access_points``,
    ``reference_market_hubs`` (the trading points) and ``reference_edges``. Unlocated points
    become access rows with no ``point_id``."""

    version = bundle["version"]
    reference = f"egn-reference-bundle:{version}"
    nodes, facilities, access, edges, hubs = [], [], [], [], []
    located = {node["id"] for node in bundle["nodes"] if node.get("located")}
    by_key = {node["point_key"]: node for node in bundle["nodes"]}
    for node in bundle["nodes"]:
        if not node.get("located"):
            continue
        metadata = _node_metadata(bundle, node)
        row = {
            "id": node["id"],
            "name": node["name"][:128],
            "node_type": node["type"],
            "country": node["country"],
            "lat": float(node["lat"]),
            "lon": float(node["lon"]),
            "capacity_boe_d": None,
            "source_system": "ENTSOG",
            "source_dataset": "connectionpoints",
            "source_reference": reference,
            "source_record_id": node["point_key"],
            "data_quality": "display_approximation",
            "metadata_json": metadata,
            "created_at_utc": now,
        }
        nodes.append(row)
        if node["type"] == "hub":
            from eurogas_nexus.ingestion.public_sources import _market_hub_code

            hubs.append(
                {
                    "id": f"hub-{node['point_key'].lower()}",
                    "name": node["name"][:128],
                    "hub_code": _market_hub_code(node["name"], node["point_key"]),
                    "country": node["country"],
                    "market_area": None,
                    "valid_from_utc": None,
                    "valid_to_utc": None,
                    "superseded_by_hub_id": None,
                    "description": f"ENTSOG trading point {node['name']}",
                    "source_system": "ENTSOG",
                    "source_dataset": "connectionpoints",
                    "source_reference": reference,
                    "source_record_id": node["point_key"],
                    "data_quality": "display_approximation",
                    "metadata_json": metadata,
                    "created_at_utc": now,
                }
            )
        facility_type = {
            "lng": "lng_terminal",
            "storage": "storage",
            "entry_point": "entry_point",
            "interconnection": "border_point",
        }.get(node["type"])
        if facility_type:
            facilities.append(
                {
                    **row,
                    "id": f"fac-{node['id']}",
                    "facility_type": facility_type,
                }
            )
            facilities[-1].pop("node_type")
    operators = bundle.get("operators") or {}
    platforms = bundle.get("booking_platforms") or {}
    for item in bundle.get("access") or []:
        node = by_key[item["point_key"]]
        operator = operators[item["operator_key"]]
        flags = [char == "1" for char in item["flags"]]
        platform = item.get("booking_platform")
        access.append(
            {
                "access_id": item["access_id"],
                "point_id": node["id"] if node["id"] in located else None,
                "point_key": item["point_key"],
                "point_name": node["name"][:256],
                "country": operator["country"],
                "operator_key": item["operator_key"],
                "operator_name": operator["name"],
                "tso_eic_code": operator.get("tso_eic"),
                "direction": item["direction"],
                "adjacent_country": item.get("adjacent_country"),
                "adjacent_operator_key": item.get("adjacent_operator_key"),
                "connected_operators": item.get("connected_operators"),
                "booking_platform": platform,
                "booking_platform_url": platforms.get(platform) if platform else None,
                "annual_contracts_available": flags[0],
                "monthly_contracts_available": flags[1],
                "daily_contracts_available": flags[2],
                "day_ahead_contracts_available": flags[3],
                "is_cam_relevant": flags[4],
                "is_cmp_relevant": flags[5],
                "last_update_utc": None,
                "source_system": "ENTSOG",
                "source_dataset": "operatorpointdirections",
                "source_reference": reference,
                "source_record_id": item["access_id"],
                "data_quality": "source_metadata",
                "metadata_json": {
                    "data_status": BUNDLE_DATA_STATUS,
                    "reference_bundle_version": version,
                    "located": node["id"] in located,
                    "attribution": bundle["source"]["attribution"],
                },
                "created_at_utc": now,
            }
        )
    names = {node["id"]: node["name"] for node in bundle["nodes"]}
    adjacency = bundle.get("adjacency") or {}
    for edge in bundle.get("edges") or []:
        kind = edge["type"]
        metadata: dict[str, Any] = {
            "schematic": True,
            "connection_basis": edge.get("basis", "entry_exit_zone"),
            "operator_key": edge.get("operator_key"),
            "geometry_basis": "straight_line_between_endpoints",
            "verification_status": "schematic",
            "reference_bundle_version": version,
        }
        if kind == "virtual":
            metadata["name"] = f"{names[edge['from']]} - {names[edge['to']]} (zone link)"
            dataset = "entry-exit-zone-links"
        else:
            dataset = "entsog-interconnection-adjacency"
            metadata.update(
                {
                    "name": (
                        f"{edge.get('name')} ({names[edge['from']]} - {names[edge['to']]})"
                        if kind == INTERCONNECTOR
                        else f"{names[edge['from']]} - {names[edge['to']]}"
                    ),
                    "adjacency_rule": adjacency.get("rule"),
                    "entsog_downloaded": edge.get("downloaded"),
                    "attribution": adjacency.get("attribution"),
                    "representative": bool(edge.get("representative")),
                    **{
                        key: edge[key]
                        for key in (
                            "point_key",
                            "hub_point_key",
                            "joins",
                            "operators",
                            "folded_points",
                            "evidence",
                            "virtual_point",
                            "pipeline",
                            "system_label",
                            "point_keys",
                        )
                        if key in edge
                    },
                }
            )
        edges.append(
            {
                "id": edge["id"],
                "from_node_id": edge["from"],
                "to_node_id": edge["to"],
                "edge_type": kind,
                "length_km": None,
                "source_system": BUNDLE_EDGE_SOURCE,
                "source_dataset": dataset,
                "source_reference": reference,
                "source_record_id": edge["id"],
                "data_quality": "schematic",
                "metadata_json": metadata,
                "created_at_utc": now,
            }
        )
    return {
        "nodes": nodes,
        "facilities": facilities,
        "hubs": hubs,
        "access": access,
        "edges": edges,
    }


def live_reference_present(session) -> bool:
    """Whether the store holds current ENTSOG reference points that came from a live read."""

    from eurogas_nexus.db.models import ReferenceNode
    from eurogas_nexus.db.models.reference_network import REFERENCE_RETIRED_QUALITY

    rows = (
        session.query(ReferenceNode.metadata_json, ReferenceNode.data_quality)
        .filter(ReferenceNode.source_system == "ENTSOG")
        .all()
    )
    return any(
        (metadata or {}).get("data_status") != BUNDLE_DATA_STATUS
        for metadata, quality in rows
        if quality != REFERENCE_RETIRED_QUALITY
    )


def seed_reference_bundle(
    session, *, bundle: dict[str, Any] | None = None, now: datetime | None = None
) -> dict[str, Any]:
    """Load the bundle through ``upsert_reference_snapshot``; the caller commits.

    Idempotent: a repeat run converges on the same rows (first ``created_at_utc`` kept). A
    later bundle version retires the bundle rows it no longer carries. A store holding a live
    ENTSOG read is left as it is.
    """

    from eurogas_nexus.db.models import (
        ReferenceEdge,
        ReferenceFacility,
        ReferenceMarketHub,
        ReferenceNode,
        ReferenceTsoAccessPoint,
    )
    from eurogas_nexus.db.repositories.public_ingestion_upsert import upsert_reference_snapshot

    bundle = bundle if bundle is not None else load_bundle()
    problems = validate_bundle(bundle)
    if problems:
        raise ValueError("reference bundle failed its checks: " + "; ".join(problems[:5]))
    summary: dict[str, Any] = {"bundle_version": bundle["version"]}
    if live_reference_present(session):
        return {**summary, "status": "skipped_live_reference_present"}
    now = now or datetime.now(UTC)
    rows = reference_rows(bundle, now=now)
    # A hub code is unique: one another row already holds (an operator's own hub master) is
    # left to it rather than refused.
    held = dict(session.query(ReferenceMarketHub.hub_code, ReferenceMarketHub.id).all())
    rows["hubs"] = [
        row for row in rows["hubs"] if held.get(row["hub_code"], row["id"]) == row["id"]
    ]
    for name, model, source in (
        ("nodes", ReferenceNode, "ENTSOG"),
        ("facilities", ReferenceFacility, "ENTSOG"),
        ("hubs", ReferenceMarketHub, "ENTSOG"),
        ("access", ReferenceTsoAccessPoint, "ENTSOG"),
        ("edges", ReferenceEdge, BUNDLE_EDGE_SOURCE),
    ):
        outcome = upsert_reference_snapshot(
            session, model, rows[name], source_system=source, retired_at_utc=now
        )
        summary[name] = outcome
    session.flush()
    unlocated = sum(1 for node in bundle["nodes"] if not node.get("located"))
    return {**summary, "status": "seeded", "unlocated_points": unlocated}


_SHIPPED_EDGES: dict[str, list[dict[str, Any]]] = {}


def shipped_reference_edges() -> list[dict[str, Any]]:
    """The bundle's edges as reference-edge rows: zone links and market-area adjacency.

    One source of truth for every store. Route pricing builds its graph from the shipped
    bundle (``shipped_market_area_graph``); the edge reader serves these same rows in place of
    any stored bundle edges, so a store that holds a live ENTSOG read (where the bundle seed is
    skipped) draws the same adjacency the pricing walks, and a seeded store cannot drift from
    it. ``created_at_utc`` is the bundle's build instant.
    """

    if "edges" not in _SHIPPED_EDGES:
        bundle = load_bundle()
        built = str(bundle.get("built_at_utc") or "2026-11-14T00:00:00+00:00")
        rows = reference_rows(bundle, now=datetime.fromisoformat(built))["edges"]
        _SHIPPED_EDGES["edges"] = [
            {key: value for key, value in row.items() if key != "created_at_utc"} for row in rows
        ]
    return [dict(row) for row in _SHIPPED_EDGES["edges"]]
