"""Audit the reference network's topology, market area by market area, against ENTSOG.

For every market area of ``network_adjacency.MARKET_AREAS`` (every active ENTSOG balancing
zone) the audit prints, as a Markdown table:

- **node**: whether the bundle holds the area's node (its VTP, or its ``BZ-`` zone node) and
  whether it has a position to draw from;
- **neighbours**: the market areas the bundle joins it to (what the map draws and the route
  pricing walks), and the neighbours ENTSOG proves but the bundle cannot draw, with the reason
  (``expected`` is the same adjacency rule run as if every ENTSOG point had a position);
- **one-way**: neighbours whose border points list only one direction on one side
  (``hub_directions``, from ENTSOG operator point directions);
- **LNG / storage**: the bundle's LNG and storage points that are members of the area, and,
  with ``--gie-dir``, the facilities GIE ALSI / AGSI+ list for the area's country;
- **IPs**: the ENTSOG point drawn for each neighbour;
- **flows**: of the area's border points, how many ENTSOG marks as publishing data
  (``connectionpoints.hasData``), with ``--entsog-dir``.

Read-only; writes nothing. Inputs are saved ENTSOG responses (``?limit=-1``) and the GIE
``/api/about?show=listing`` responses (``agsi_about.json``, ``alsi_about.json``)::

    python scripts/ops/audit_reference_topology.py --entsog-dir entsog/ --gie-dir gie/
    python scripts/ops/audit_reference_topology.py --bundle old.json --entsog-dir entsog/
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

from eurogas_nexus.application.pipeline_supply import SAME_PHYSICAL_POINT
from eurogas_nexus.reference_data.network_adjacency import (
    MARKET_AREAS,
    derive_adjacency,
)
from eurogas_nexus.reference_data.network_bundle import load_bundle

GIE_COUNTRY = {"GB": "GB", "UK": "GB"}


def _read(directory: Path | None, name: str) -> list[dict[str, Any]] | None:
    if directory is None or not (directory / f"{name}.json").exists():
        return None
    payload = json.loads((directory / f"{name}.json").read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return payload
    return next(value for key, value in payload.items() if key.lower() == name.lower())


def _pairs(edges: list[dict[str, Any]]) -> dict[frozenset[str], set[str]]:
    """Pairs of market-area point keys and the points joining them (direct and pipeline)."""

    by_point: dict[str, set[str]] = defaultdict(set)
    pipes: dict[str, tuple[str, str]] = {}
    for edge in edges:
        if edge.get("type") == "market_area_link":
            by_point[str(edge["point_key"])].add(str(edge["hub_point_key"]))
        elif edge.get("type") == "interconnector":
            ends = tuple(edge.get("point_keys") or ())
            if len(ends) == 2:
                pipes[str(edge["operator_key"])] = (str(ends[0]), str(ends[1]))
    pairs: dict[frozenset[str], set[str]] = defaultdict(set)
    for point, hubs in by_point.items():
        for a in hubs:
            for b in hubs - {a}:
                pairs[frozenset((a, b))].add(point)
    for a, b in pipes.values():
        for x in by_point.get(a, set()):
            for y in by_point.get(b, set()) - {x}:
                pairs[frozenset((x, y))].add(f"{a}/{b}")
    return pairs


def expected_pairs(
    interconnections: list[dict[str, Any]], connection_points: list[dict[str, Any]]
) -> dict[frozenset[str], set[str]]:
    """The adjacency ENTSOG proves when every point has a position (same rule as the build)."""

    keys = {str(row["pointKey"]) for row in interconnections if row.get("pointKey")}
    nodes = [
        {"point_key": key, "id": f"entsog-{key.lower()}", "type": "interconnection",
         "located": True, "name": key}
        for key in sorted(keys)
    ] + [
        {"point_key": area.point_key, "id": f"entsog-{area.point_key.lower()}", "type": "hub",
         "located": True, "name": area.code}
        for area in MARKET_AREAS
    ]
    result = derive_adjacency(
        interconnections,
        nodes,
        connection_points=connection_points,
        aliases={key: alias.canonical for key, alias in SAME_PHYSICAL_POINT.items()},
        downloaded="0000-00-00",
    )
    return _pairs(result["edges"])


def audit(
    bundle: dict[str, Any],
    *,
    interconnections: list[dict[str, Any]] | None = None,
    connection_points: list[dict[str, Any]] | None = None,
    gie: dict[str, list[dict[str, Any]]] | None = None,
) -> list[dict[str, Any]]:
    nodes = {str(node["point_key"]): node for node in bundle.get("nodes") or []}
    node_by_id = {str(node["id"]): node for node in bundle.get("nodes") or []}
    edges = list(bundle.get("edges") or [])
    drawn = _pairs(edges)
    expected = (
        expected_pairs(interconnections, connection_points or [])
        if interconnections is not None
        else {}
    )
    unconnected = {
        str(item["point_key"]): item
        for item in (bundle.get("adjacency") or {}).get("unconnected") or []
    }
    has_data = {
        str(row.get("pointKey")): bool(row.get("hasData")) for row in connection_points or []
    }
    code_of = {area.point_key: area.code for area in MARKET_AREAS}
    members: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for edge in edges:
        if edge.get("type") == "virtual":
            node = node_by_id.get(str(edge["from"]))
            hub = node_by_id.get(str(edge["to"]))
            if node and hub:
                members[str(hub["point_key"])][str(node["type"])] += 1
    links: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for edge in edges:
        if edge.get("type") == "market_area_link":
            links[(str(edge["point_key"]), str(edge["hub_point_key"]))].append(edge)

    rows = []
    for area in MARKET_AREAS:
        key = area.point_key
        node = nodes.get(key)
        neighbours = sorted(
            (next(iter(pair - {key})), points) for pair, points in drawn.items() if key in pair
        )
        missing = []
        for pair, points in sorted(expected.items(), key=lambda item: sorted(item[0])):
            if key not in pair or pair in drawn:
                continue
            other = next(iter(pair - {key}))
            reasons = sorted(
                {
                    f"{point}: {unconnected[point]['reason']}"
                    if point in unconnected
                    else f"{point}: not in the bundle"
                    for point in points
                }
            )
            missing.append(f"{code_of.get(other, other)} ({'; '.join(reasons)})")
        one_way = []
        border_points: set[str] = set()
        for other, points in neighbours:
            direct = sorted(point for point in points if "/" not in point)
            border_points |= set(direct)
            if not direct:
                continue
            both = any(
                set(_directions(links, point, key)) == {"entry", "exit"}
                and set(_directions(links, point, other)) == {"entry", "exit"}
                for point in direct
            )
            if not both:
                one_way.append(code_of.get(other, other))
        drawn_points = []
        for other, points in neighbours:
            rep = sorted(
                point
                for point in points
                if any(edge.get("representative") for edge in links.get((point, key), []))
            ) or sorted(points)
            drawn_points.append(f"{code_of.get(other, other)}: {rep[0]}")
        flows = (
            f"{sum(1 for p in border_points if has_data.get(p))}/{len(border_points)}"
            if connection_points is not None and border_points
            else "-"
        )
        gie_counts = "-"
        if gie:
            country = area.country
            storage = sum(1 for f in gie.get("agsi", []) if f.get("country") == country)
            lng = sum(1 for f in gie.get("alsi", []) if f.get("country") == country)
            gie_counts = f"{lng} / {storage}"
        rows.append(
            {
                "area": f"{area.code} ({area.bz_key.rstrip('-')})",
                "node": (
                    "missing"
                    if node is None
                    else ("yes" if node.get("located") else "no position")
                )
                + ("" if area.hub_point_key else " (zone)"),
                "neighbours": ", ".join(code_of.get(o, o) for o, _ in neighbours) or "NONE",
                "missing": "; ".join(missing) or "-",
                "one_way": ", ".join(one_way) or "-",
                "lng_storage": f"{members[key].get('lng', 0)} / {members[key].get('storage', 0)}",
                "gie_lng_storage": gie_counts,
                "ips": ", ".join(drawn_points) or "-",
                "flows": flows,
            }
        )
    return rows


def _directions(links, point: str, hub: str) -> list[str]:
    edges = links.get((point, hub), [])
    return sorted({d for edge in edges for d in edge.get("hub_directions") or []})


def _gie_facilities(gie_dir: Path | None) -> dict[str, list[dict[str, Any]]] | None:
    if gie_dir is None:
        return None
    out: dict[str, list[dict[str, Any]]] = {}
    for name in ("agsi", "alsi"):
        path = gie_dir / f"{name}_about.json"
        if not path.exists():
            continue
        companies = json.loads(path.read_text(encoding="utf-8"))
        facilities = []
        for company in companies if isinstance(companies, list) else []:
            for facility in company.get("facilities") or []:
                name_text = str(facility.get("name") or "").lower()
                if "historical" in name_text:
                    continue
                country = GIE_COUNTRY.get(str(facility.get("country")), facility.get("country"))
                facilities.append({**facility, "country": country})
        out[name] = facilities
    return out


def markdown(rows: list[dict[str, Any]]) -> str:
    head = (
        "| Market area | (a) node | (b) neighbours drawn | (b) ENTSOG neighbour not drawn "
        "| one-way border | (c) LNG / storage points | GIE LNG / storage | (d) drawn IP "
        "(ENTSOG id) | (e) IPs with ENTSOG data |"
    )
    lines = [head, "|" + "---|" * 9]
    for row in rows:
        lines.append(
            "| "
            + " | ".join(
                str(row[key])
                for key in (
                    "area",
                    "node",
                    "neighbours",
                    "missing",
                    "one_way",
                    "lng_storage",
                    "gie_lng_storage",
                    "ips",
                    "flows",
                )
            )
            + " |"
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--bundle", type=Path, help="a bundle file (default: the shipped one)")
    parser.add_argument("--entsog-dir", type=Path, help="saved ENTSOG responses")
    parser.add_argument("--gie-dir", type=Path, help="saved GIE listings")
    parser.add_argument("--json", action="store_true", help="rows as JSON instead of Markdown")
    args = parser.parse_args(argv)
    bundle = load_bundle(args.bundle)
    rows = audit(
        bundle,
        interconnections=_read(args.entsog_dir, "interconnections"),
        connection_points=_read(args.entsog_dir, "connectionpoints"),
        gie=_gie_facilities(args.gie_dir),
    )
    print(json.dumps(rows, indent=1) if args.json else markdown(rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
