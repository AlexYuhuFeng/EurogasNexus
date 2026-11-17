"""Regenerate the shipped NWE reference network bundle from the live reference tables.

Reads ``reference_nodes`` and ``reference_tso_access_points`` (both from the ENTSOG
Transparency Platform reference read, ``ingest_public_sources.py --source
entsog-reference``) and writes ``src/eurogas_nexus/reference_data/nwe_reference_network.json``.
Read-only against the store. Run it after a complete reference read, review the diff, and
commit the file with a new ``--version``.

Scope (``SCOPE_COUNTRIES``): points with an operator in BE, DE, DK, FR, GB, IE, LU, NL or NO
(the balance's NWE countries plus Ireland and the Norwegian supply side). Distribution and
final-consumer points are left out: neither the map nor the balance uses them. The
balance's landing points are always included.

Edges, two kinds:

- zone membership (``type: virtual``): each located point to the trading point of every
  entry-exit zone one of its operators belongs to (``ZONE_HUB_BY_OPERATOR``). Membership of a
  market area, never drawn as a line;
- adjacency (``type: market_area_link`` and ``interconnector``): which market areas each
  interconnection point joins, derived from ENTSOG's ``interconnections`` and
  ``connectionpoints`` datasets by the rule in ``reference_data/network_adjacency.py``. Route
  pricing walks these edges; the map draws them.

ENTSOG publishes no route geometry through its API; every edge is schematic.

    RUNTIME_STORE_DATABASE_URL=... python scripts/ops/build_reference_network_bundle.py \
        --version 2026-11-14 --downloaded 2026-11-14

Only the adjacency, on the shipped bundle (no database; ENTSOG read live, retried on a reset,
or from saved responses with ``--entsog-dir``):

    python scripts/ops/build_reference_network_bundle.py --adjacency-only --version 2026-11-16
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from eurogas_nexus.application.pipeline_supply import LANDING_POINTS, SAME_PHYSICAL_POINT
from eurogas_nexus.db.models import ReferenceNode, ReferenceTsoAccessPoint
from eurogas_nexus.db.models.reference_network import REFERENCE_RETIRED_QUALITY
from eurogas_nexus.db.session import get_session_factory, resolve_database_url
from eurogas_nexus.reference_data.network_adjacency import apply_to_bundle
from eurogas_nexus.reference_data.network_bundle import (
    BUNDLE_SCHEMA,
    bundle_path,
    load_bundle,
    validate_bundle,
)

ENTSOG_API = "https://transparency.entsog.eu/api/v1"

#: ENTSOG writes the United Kingdom as ``UK``; the bundle uses ISO 3166 ``GB`` throughout.
COUNTRY_ALIASES = {"UK": "GB", "EL": "GR"}
SCOPE_COUNTRIES = ("BE", "DE", "DK", "FR", "GB", "IE", "LU", "NL", "NO")
#: Point families the map and the balance use (ENTSOG point key prefix -> node type).
KEPT_PREFIXES = {
    "ITP": "interconnection",
    "UGS": "storage",
    "LNG": "lng",
    "PRD": "entry_point",
    "VTP": "hub",
}
#: Virtual trading point of each operator's entry-exit zone (ENTSOG point keys). Operators
#: not listed (Gassco, the Interconnector and BBL pipelines, Premier Transmission, GNI (UK))
#: run no NWE trading zone of their own here: their points link through the other side.
ZONE_HUB_BY_OPERATOR = {
    "NL-TSO-0001": "VTP-00002",  # GTS: TTF
    "BE-TSO-0001": "VTP-00016",  # Fluxys Belgium: ZTP
    "LU-TSO-0001": "VTP-00016",  # Creos: BeLux zone, ZTP
    "FR-TSO-0002": "VTP-00039",  # Terega: PEG
    "FR-TSO-0003": "VTP-00039",  # NaTran: PEG
    "UK-TSO-0001": "VTP-00006",  # National Gas: NBP
    "DK-TSO-0001": "VTP-00001",  # Energinet: GTF
    "IE-TSO-0002": "VTP-00005",  # GNI: IBP
}
DE_ZONE_HUB = "VTP-00045"  # every German TSO: THE
#: Trading points kept besides the zone hubs. Others in scope are left out: PEG SUD and the
#: TRS point were merged into PEG in 2018, and ENTSOG's map places PEG SUD in Poland.
EXTRA_TRADING_POINTS = {"VTP-00029"}  # Zeebrugge Beach
HUB_COUNTRY = {
    "VTP-00002": "NL",
    "VTP-00016": "BE",
    "VTP-00039": "FR",
    "VTP-00006": "GB",
    "VTP-00001": "DK",
    "VTP-00005": "IE",
    "VTP-00045": "DE",
}


def _country(value: str | None) -> str | None:
    text = (value or "").strip().upper()
    return COUNTRY_ALIASES.get(text, text) or None


def _hub_for(operator_key: str) -> str | None:
    if operator_key.startswith("DE-TSO-"):
        return DE_ZONE_HUB
    return ZONE_HUB_BY_OPERATOR.get(operator_key)


def build(session, *, version: str, downloaded: date) -> dict:
    nodes_by_key = {}
    for node in session.query(ReferenceNode).filter(ReferenceNode.source_system == "ENTSOG"):
        if node.data_quality == REFERENCE_RETIRED_QUALITY:
            continue
        key = str((node.metadata_json or {}).get("point_key") or node.source_record_id or "")
        if key:
            nodes_by_key[key] = node
    access_by_key: dict[str, list] = defaultdict(list)
    for row in session.query(ReferenceTsoAccessPoint).filter(
        ReferenceTsoAccessPoint.source_system == "ENTSOG"
    ):
        if row.data_quality != REFERENCE_RETIRED_QUALITY:
            access_by_key[row.point_key].append(row)

    landing = {point.point_id for point in LANDING_POINTS}
    wanted = set()
    for key, rows in access_by_key.items():
        if key.split("-")[0] not in KEPT_PREFIXES:
            continue
        if key.startswith("VTP-") and key not in HUB_COUNTRY and key not in EXTRA_TRADING_POINTS:
            continue
        if key in landing or any(_country(row.country) in SCOPE_COUNTRIES for row in rows):
            wanted.add(key)
    wanted |= set(HUB_COUNTRY)

    nodes, access, edges = [], [], []
    operators_seen: dict[str, dict] = {}
    platforms: dict[str, str | None] = {}
    for key in sorted(wanted):
        node = nodes_by_key.get(key)
        rows = sorted(access_by_key.get(key, []), key=lambda r: (r.operator_key, r.direction))
        if node is None and not rows:
            continue
        meta = (node.metadata_json or {}) if node is not None else {}
        operators = sorted({row.operator_key for row in rows})
        operator_countries = sorted(
            {c for c in (_country(row.country) for row in rows) if c in SCOPE_COUNTRIES}
        )
        if key in HUB_COUNTRY:
            country, basis = HUB_COUNTRY[key], "zone_of_trading_point"
        elif node is not None and _country(node.country) in SCOPE_COUNTRIES:
            country, basis = _country(node.country), "entsog_point"
        elif operator_countries:
            country, basis = operator_countries[0], "operator_country"
        else:
            country, basis = _country(rows[0].country) if rows else "EU", "operator_country"
        located = node is not None
        nodes.append(
            {
                "id": f"entsog-{key.lower()}",
                "point_key": key,
                "eic": meta.get("point_eic_code"),
                "name": node.name if node is not None else rows[0].point_name,
                "country": (country or "EU")[:2],
                "country_basis": basis,
                "type": KEPT_PREFIXES[key.split("-")[0]],
                "point_type": meta.get("point_type"),
                "infrastructure": meta.get("infrastructure_label"),
                "operators": operators,
                "located": located,
                "lat": round(node.lat, 4) if located else None,
                "lon": round(node.lon, 4) if located else None,
                "coordinate_quality": "display_approximation" if located else None,
                "verified": False,
                "entsog_map_x": meta.get("entsog_map_x"),
                "entsog_map_y": meta.get("entsog_map_y"),
            }
        )
        for row in rows:
            operators_seen[row.operator_key] = {
                "name": row.operator_name.strip(),
                "country": row.country,
                "tso_eic": row.tso_eic_code,
            }
            if row.booking_platform:
                platforms[row.booking_platform] = row.booking_platform_url
            item = {
                "access_id": row.access_id,
                "point_key": key,
                "operator_key": row.operator_key,
                "direction": row.direction,
                "adjacent_country": row.adjacent_country,
                "adjacent_operator_key": row.adjacent_operator_key,
                "connected_operators": row.connected_operators,
                "booking_platform": row.booking_platform,
                "flags": "".join(
                    "1" if value else "0"
                    for value in (
                        row.annual_contracts_available,
                        row.monthly_contracts_available,
                        row.daily_contracts_available,
                        row.day_ahead_contracts_available,
                        row.is_cam_relevant,
                        row.is_cmp_relevant,
                    )
                ),
            }
            access.append({k: v for k, v in item.items() if v is not None})

    located_ids = {node["id"] for node in nodes if node["located"]}
    seen = set()
    for node in nodes:
        if not node["located"] or node["type"] == "hub":
            continue
        for operator in node["operators"]:
            hub = _hub_for(operator)
            hub_id = f"entsog-{hub.lower()}" if hub else None
            if hub_id is None or hub_id not in located_ids or hub_id == node["id"]:
                continue
            pair = (node["id"], hub_id)
            if pair in seen:
                continue
            seen.add(pair)
            edges.append(
                {
                    "id": f"zone-{node['point_key'].lower()}-{hub.lower()}",
                    "from": node["id"],
                    "to": hub_id,
                    "type": "virtual",
                    "schematic": True,
                    "basis": "entry_exit_zone",
                    "operator_key": operator,
                }
            )

    stamp = downloaded.strftime("%d-%m-%Y")
    return {
        "schema": BUNDLE_SCHEMA,
        "version": version,
        "built_at_utc": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "scope": {
            "region": "north-west Europe",
            "countries": list(SCOPE_COUNTRIES),
            "rule": (
                "ENTSOG interconnection, storage, LNG, production and trading points with an "
                "operator in a scope country, plus the balance's landing points; distribution "
                "and final-consumer points are left out."
            ),
        },
        "source": {
            "name": "ENTSOG Transparency Platform",
            "datasets": ["connectionpoints", "operatorpointdirections"],
            "downloaded": downloaded.isoformat(),
            "attribution": f"ENTSOG TP [{stamp}] https://transparency.entsog.eu/",
            "terms": (
                "ENTSOG TP Privacy & T&C of Use, LAG0689-26 Rev. 3 (10 November 2026), "
                "Article 5; see docs/legal/DATA_SOURCE_TERMS.md"
            ),
        },
        "coordinate_rule": (
            "Positions are ENTSOG's map coordinates (tpMapX/tpMapY) transformed to an "
            "approximate lon/lat for display, as the live ingestion does; never surveyed. "
            "A point ENTSOG publishes without a map position has no coordinate and is "
            "counted as not located."
        ),
        "edge_rule": EDGE_RULE,
        "access_flags": "annual, monthly, daily, day-ahead products offered; CAM; CMP relevant",
        "operators": dict(sorted(operators_seen.items())),
        "booking_platforms": dict(sorted(platforms.items())),
        "nodes": nodes,
        "access": access,
        "edges": edges,
    }


EDGE_RULE = (
    "Zone membership (type virtual): each located point to the virtual trading point of each "
    "entry-exit zone its operators belong to; membership of a market area, never a line. "
    "Adjacency (types market_area_link, interconnector): which market areas each "
    "interconnection point joins, from ENTSOG interconnections (see the adjacency block); "
    "route pricing walks these and the map draws them. All edges are schematic."
)


def fetch_entsog(dataset: str, *, attempts: int = 5) -> list[dict]:
    """One ENTSOG dataset in full, retried on a reset or a timeout."""

    url = f"{ENTSOG_API}/{dataset}?limit=-1"
    for attempt in range(1, attempts + 1):
        try:
            with urllib.request.urlopen(url, timeout=180) as response:  # noqa: S310 - fixed host
                payload = json.load(response)
            # ENTSOG names the list after the dataset, in either case (connectionPoints).
            key = next((name for name in payload if name.lower() == dataset.lower()), None)
            if key is None:
                raise ValueError(f"no {dataset} in the response: {str(payload)[:200]}")
            return payload[key]
        except (
            urllib.error.URLError,
            TimeoutError,
            ConnectionError,
            json.JSONDecodeError,
            ValueError,
        ) as exc:
            if attempt == attempts:
                raise
            print(f"{dataset}: attempt {attempt} failed ({exc}); retrying", file=sys.stderr)
            time.sleep(5 * attempt)
    return []


def entsog_rows(entsog_dir: Path | None) -> tuple[list[dict], list[dict]]:
    if entsog_dir:
        def read(name: str) -> list[dict]:
            payload = json.loads((entsog_dir / f"{name}.json").read_text(encoding="utf-8"))
            return next(value for key, value in payload.items() if key.lower() == name.lower())

        return read("interconnections"), read("connectionpoints")
    return fetch_entsog("interconnections"), fetch_entsog("connectionpoints")


def firm_technical_capacities(
    points: list[str], gas_day: date, entsog_dir: Path | None
) -> dict[str, float]:
    """Largest firm technical capacity per point for one gas day (kWh/d), ENTSOG published."""

    saved = entsog_dir / "firm_technical.json" if entsog_dir else None
    if saved and saved.exists():
        return {key: float(value) for key, value in json.loads(saved.read_text()).items()}
    out: dict[str, float] = {}
    day = gas_day.isoformat()
    for point in points:
        url = (
            f"{ENTSOG_API}/operationaldatas?pointKey={point}&indicator=Firm%20Technical"
            f"&periodType=day&from={day}&to={day}&limit=-1"
        )
        for attempt in range(1, 6):
            try:
                with urllib.request.urlopen(url, timeout=180) as response:  # noqa: S310
                    rows = json.load(response).get("operationaldatas") or []
                break
            except urllib.error.HTTPError as exc:
                if exc.code == 404:  # ENTSOG answers "No result found" with a 404
                    rows = []
                    break
                if attempt == 5:
                    raise
            except (urllib.error.URLError, TimeoutError, ConnectionError):
                if attempt == 5:
                    raise
            time.sleep(5 * attempt)
        values = [float(row["value"]) for row in rows if row.get("value") not in (None, "")]
        if values:
            out[point] = max(values)
    return out


def with_adjacency(bundle: dict, entsog_dir: Path | None, downloaded: date) -> dict:
    interconnections, connection_points = entsog_rows(entsog_dir)
    aliases = {key: alias.canonical for key, alias in SAME_PHYSICAL_POINT.items()}
    first = apply_to_bundle(
        bundle, interconnections, connection_points,
        downloaded=downloaded.isoformat(), aliases=aliases,
    )
    # The capacity read ranks only the points of a pair with more than one.
    by_pair: dict[tuple, set[str]] = defaultdict(set)
    for edge in first["edges"]:
        if edge.get("type") == "market_area_link":
            by_pair[tuple(sorted(edge["joins"]))].add(edge["point_key"])
    contested = sorted(
        {point for points in by_pair.values() if len(points) > 1 for point in points}
    )
    capacity_day = downloaded - timedelta(days=1)
    capacities = firm_technical_capacities(contested, capacity_day, entsog_dir)
    return apply_to_bundle(
        bundle, interconnections, connection_points,
        downloaded=downloaded.isoformat(), aliases=aliases,
        capacities=capacities, capacity_gas_day=capacity_day.isoformat(),
    )


def write(bundle: dict, path: Path) -> None:
    """One record per line: small, and a refresh reads as a line diff."""

    head = {key: value for key, value in bundle.items() if key not in ("nodes", "access", "edges")}
    head["edge_rule"] = EDGE_RULE
    lines = ["{"]
    for key, value in head.items():
        lines.append(f"  {json.dumps(key)}: {json.dumps(value, ensure_ascii=False)},")
    for index, name in enumerate(("nodes", "access", "edges")):
        items = bundle[name]
        lines.append(f"  {json.dumps(name)}: [")
        for position, item in enumerate(items):
            comma = "," if position < len(items) - 1 else ""
            lines.append("    " + json.dumps(item, ensure_ascii=False, sort_keys=True) + comma)
        lines.append("  ]" + ("," if index < 2 else ""))
    lines.append("}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--version", required=True)
    parser.add_argument("--downloaded", type=date.fromisoformat, default=datetime.now(UTC).date())
    parser.add_argument("--out", type=Path, default=bundle_path())
    parser.add_argument(
        "--adjacency-only",
        action="store_true",
        help="re-derive only the adjacency edges of the shipped bundle (no database)",
    )
    parser.add_argument(
        "--entsog-dir",
        type=Path,
        help="saved interconnections.json and connectionpoints.json",
    )
    args = parser.parse_args(argv)
    if args.adjacency_only:
        bundle = {**load_bundle(), "version": args.version}
    else:
        if not resolve_database_url():
            print("RUNTIME_STORE_DATABASE_URL is required", file=sys.stderr)
            return 2
        with get_session_factory()() as session:
            bundle = build(session, version=args.version, downloaded=args.downloaded)
            session.rollback()  # read-only
    bundle = with_adjacency(bundle, args.entsog_dir, args.downloaded)
    problems = validate_bundle(bundle)
    if problems:
        print("bundle failed its checks:\n  " + "\n  ".join(problems[:20]), file=sys.stderr)
        return 1
    write(bundle, args.out)
    located = sum(1 for node in bundle["nodes"] if node["located"])
    print(
        f"{args.out}: {len(bundle['nodes'])} nodes ({located} located, "
        f"{len(bundle['nodes']) - located} without a published position), "
        f"{len(bundle['access'])} operator point directions, "
        f"{len(bundle['edges'])} schematic edges "
        f"({sum(1 for edge in bundle['edges'] if edge['type'] != 'virtual')} adjacency), "
        f"{len(bundle['adjacency']['unconnected'])} points listed as unconnected"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
