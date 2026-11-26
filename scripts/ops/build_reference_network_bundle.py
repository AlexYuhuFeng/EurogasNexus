"""Regenerate the shipped European reference network bundle from ENTSOG reference data.

Reads ENTSOG Transparency Platform reference metadata and writes
``src/eurogas_nexus/reference_data/nwe_reference_network.json`` (the file name predates the
all-Europe scope). Two inputs, one normalisation (the live read's own functions):

- saved ENTSOG responses (``--from-entsog-dir --entsog-dir DIR``, no database): DIR holds
  ``connectionpoints.json``, ``operatorpointdirections.json``, ``balancingzones.json`` and
  ``interconnections.json`` as ENTSOG answers ``/api/v1/<dataset>?limit=-1``;
- the live reference tables ``reference_nodes`` and ``reference_tso_access_points`` (from
  ``ingest_public_sources.py --source entsog-reference``), read-only.

Review the diff and commit the file with a new ``--version``.

Scope (``SCOPE_COUNTRIES``): points with an operator in a country of an ENTSOG market area
(``network_adjacency.MARKET_AREAS``: every active ENTSOG balancing zone, EU and its
neighbours), plus Norway's supply side. Distribution and final-consumer points are left out:
neither the map nor the balance uses them. The balance's landing points are always included.
A market area ENTSOG publishes no trading point for (Switzerland, Slovakia, Romania ...) gets a
zone node at ENTSOG's map position for the balancing zone (``BZ-<code>``).

Edges, two kinds:

- zone membership (``type: virtual``): each located point to the market area of every
  entry-exit zone one of its TSOs belongs to there (ENTSOG ``operatorpointdirections``
  ``tSOBalancingZone``). Membership of a market area, never drawn as a line;
- adjacency (``type: market_area_link`` and ``interconnector``): which market areas each
  interconnection point joins, derived from ENTSOG's ``interconnections`` and
  ``connectionpoints`` datasets by the rule in ``reference_data/network_adjacency.py``. Route
  pricing walks these edges; the map draws them.

ENTSOG publishes no route geometry through its API; every edge is schematic.

Presentation geometry (``--scigrid-dir``, the unpacked SciGRID_gas IGGIELGN ``data`` folder,
CC BY 4.0, doi:10.5281/zenodo.4767098): the generalised trunk lines of north-west Europe are
written to ``clients/web/public/map/context-pipelines.geojson`` (a faint layer under the
connections) and each drawn connection leg gets a ``presentation_path`` along them where one
runs close to both ends (``reference_data/reference_geometry.py``). Presentation only: route
pricing never reads it. Without ``--scigrid-dir`` a rebuild keeps the shipped paths of the legs
whose ends are unchanged. Only the geometry, on the shipped bundle:

    python scripts/ops/build_reference_network_bundle.py --presentation-only \
        --scigrid-dir IGGIELGN/data --version 2026-11-17

The whole bundle from saved ENTSOG responses, with the presentation geometry:

    python scripts/ops/build_reference_network_bundle.py --from-entsog-dir \
        --entsog-dir entsog/ --scigrid-dir IGGIELGN/data --version 2026-11-26 \
        --downloaded 2026-11-26

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
from collections import Counter, defaultdict
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from eurogas_nexus.application.pipeline_supply import LANDING_POINTS, SAME_PHYSICAL_POINT
from eurogas_nexus.db.models import ReferenceNode, ReferenceTsoAccessPoint
from eurogas_nexus.db.models.reference_network import REFERENCE_RETIRED_QUALITY
from eurogas_nexus.db.session import get_session_factory, resolve_database_url
from eurogas_nexus.reference_data.network_adjacency import (
    BZ_HUB,
    EXTERNAL_OPERATOR_ZONES,
    MARKET_AREAS,
    apply_to_bundle,
    canonical_zone,
    two_point_systems,
)
from eurogas_nexus.reference_data.network_bundle import (
    BUNDLE_SCHEMA,
    bundle_path,
    load_bundle,
    validate_bundle,
)
from eurogas_nexus.reference_data.reference_geometry import (
    SOURCE as SCIGRID_SOURCE,
)
from eurogas_nexus.reference_data.reference_geometry import (
    apply_presentation_geometry,
    context_geojson,
    context_pipelines,
    read_pipe_segments,
    trunk_segments,
)

ENTSOG_API = "https://transparency.entsog.eu/api/v1"

#: ENTSOG writes the United Kingdom as ``UK``; the bundle uses ISO 3166 ``GB`` throughout.
COUNTRY_ALIASES = {"UK": "GB", "EL": "GR"}
#: Every country with an ENTSOG market area (``MARKET_AREAS``), the countries whose zones
#: merged into one (LU into BeLux, SE into DK/SE, EE into EE/LV) and the Norwegian supply side.
SCOPE_COUNTRIES = tuple(
    sorted({area.country for area in MARKET_AREAS} | {"LU", "SE", "EE", "NO"})
)
#: Point families the map and the balance use (ENTSOG point key prefix -> node type).
KEPT_PREFIXES = {
    "ITP": "interconnection",
    "UGS": "storage",
    "LNG": "lng",
    "PRD": "entry_point",
    "VTP": "hub",
}
#: Fallback zone of an operator when ENTSOG's operator point directions name none at a point
#: (a store read before ``tso_balancing_zone`` was kept). The all-Europe build reads each
#: point's zone from ENTSOG (``operatorpointdirections.tSOBalancingZone``) instead.
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
#: Trading points kept besides the market areas' own. Others are left out: PEG SUD and the
#: TRS point were merged into PEG in 2018 (ENTSOG publishes PEG SUD at map position 0/0).
EXTRA_TRADING_POINTS = {"VTP-00029"}  # Zeebrugge Beach
AREA_BY_POINT = {area.point_key: area for area in MARKET_AREAS}
HUB_COUNTRY = {area.hub_point_key: area.country for area in MARKET_AREAS if area.hub_point_key}


def _country(value: str | None) -> str | None:
    text = (value or "").strip().upper()
    return COUNTRY_ALIASES.get(text, text) or None


def _hub_for(operator_key: str) -> str | None:
    if operator_key.startswith("DE-TSO-"):
        return DE_ZONE_HUB
    return ZONE_HUB_BY_OPERATOR.get(operator_key)


def _published_position(meta: dict) -> bool:
    """ENTSOG writes 0/0 for a point it has not placed; the transform would put it in Poland."""

    return not (
        float(meta.get("entsog_map_x") or 0.0) == 0.0
        and float(meta.get("entsog_map_y") or 0.0) == 0.0
    )


def zone_nodes(balancing_zones: list[dict]) -> list[dict]:
    """A node per market area ENTSOG publishes no trading point for, at ENTSOG's zone position.

    The position is ENTSOG's map position for the balancing zone (``balancingzones``
    ``tpMapX``/``tpMapY``, the label of the zone on ENTSOG's map), transformed as every other
    point; a zone ENTSOG has not placed is not located.
    """

    from eurogas_nexus.ingestion.public_sources import _entsog_map_to_lon_lat

    by_key = {str(row.get("bzKey")): row for row in balancing_zones}
    out = []
    for area in MARKET_AREAS:
        if area.hub_point_key:
            continue
        row = by_key.get(area.bz_key) or {}
        x, y = row.get("tpMapX"), row.get("tpMapY")
        lon, lat = _entsog_map_to_lon_lat(x, y)
        located = lon is not None and _published_position({"entsog_map_x": x, "entsog_map_y": y})
        out.append(
            {
                "id": f"entsog-{area.zone_point_key.lower()}",
                "point_key": area.zone_point_key,
                "balancing_zone_key": area.bz_key,
                "hub_code": area.code,
                "zone_only": True,
                "eic": (row.get("bzEicCode") or "").strip() or None,
                "name": str(row.get("bzLabelLong") or row.get("bzLabel") or area.code).strip(),
                "country": area.country,
                "country_basis": "zone_of_trading_point",
                "type": "hub",
                "point_type": "Balancing zone (no published trading point)",
                "infrastructure": None,
                "operators": [],
                "located": located,
                "lat": round(lat, 4) if located else None,
                "lon": round(lon, 4) if located else None,
                "coordinate_quality": "display_approximation" if located else None,
                "verified": False,
                "entsog_map_x": x,
                "entsog_map_y": y,
                "source_dataset": "balancingzones",
            }
        )
    return out


def build(session, *, version: str, downloaded: date, entsog_dir: Path | None = None) -> dict:
    """The bundle from a store holding a complete ENTSOG reference read."""

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
    return build_rows(
        nodes_by_key,
        access_by_key,
        read_entsog("balancingzones", entsog_dir),
        read_entsog("interconnections", entsog_dir),
        version=version,
        downloaded=downloaded,
    )


def build_from_entsog(entsog_dir: Path, *, version: str, downloaded: date) -> dict:
    """The bundle from saved ENTSOG responses, normalised exactly as the live read stores them.

    ``entsog_dir`` holds ``connectionpoints.json``, ``operatorpointdirections.json`` and
    ``balancingzones.json`` (``?limit=-1``, as ENTSOG answers).
    """

    from types import SimpleNamespace

    from eurogas_nexus.ingestion.public_sources import (
        entsog_reference_nodes_from_connectionpoints,
        entsog_tso_access_points_from_json,
    )

    def payload(name: str) -> dict:
        return json.loads((entsog_dir / f"{name}.json").read_text(encoding="utf-8"))

    nodes_by_key = {
        str(row["source_record_id"]): SimpleNamespace(**row)
        for row in entsog_reference_nodes_from_connectionpoints(payload("connectionpoints"))
    }
    access_by_key: dict[str, list] = defaultdict(list)
    for row in entsog_tso_access_points_from_json(payload("operatorpointdirections")):
        access_by_key[row["point_key"]].append(SimpleNamespace(**row))
    return build_rows(
        nodes_by_key,
        access_by_key,
        read_entsog("balancingzones", entsog_dir),
        read_entsog("interconnections", entsog_dir),
        version=version,
        downloaded=downloaded,
    )


def _zone_label_keys(balancing_zones: list[dict]) -> dict[str, str]:
    """ENTSOG balancing zone label (as operator point directions name it) to its key."""

    out: dict[str, str] = {}
    for row in balancing_zones:
        key = str(row.get("bzKey") or "")
        for label in (row.get("bzLabel"), row.get("bzLabelLong")):
            if label and key:
                out.setdefault(str(label).strip(), key)
    return out


def build_rows(
    nodes_by_key: dict,
    access_by_key: dict[str, list],
    balancing_zones: list[dict],
    interconnections: list[dict],
    *,
    version: str,
    downloaded: date,
) -> dict:
    landing = {point.point_id for point in LANDING_POINTS}
    area_hubs = {area.hub_point_key for area in MARKET_AREAS if area.hub_point_key}
    wanted = set()
    for key, rows in access_by_key.items():
        if key.split("-")[0] not in KEPT_PREFIXES:
            continue
        if key.startswith("VTP-") and key not in area_hubs and key not in EXTRA_TRADING_POINTS:
            continue
        if key in landing or any(_country(row.country) in SCOPE_COUNTRIES for row in rows):
            wanted.add(key)
    wanted |= area_hubs

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
        located = node is not None and _published_position(meta)
        item = {
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
        if key in AREA_BY_POINT:
            item["hub_code"] = AREA_BY_POINT[key].code
            item["balancing_zone_key"] = AREA_BY_POINT[key].bz_key
        nodes.append(item)
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
    nodes += zone_nodes(balancing_zones)
    nodes.sort(key=lambda node: node["point_key"])

    # Zone membership: the zone ENTSOG names for the operator at the point
    # (operatorpointdirections.tSOBalancingZone), else the operator's usual zone there. A
    # two-point pipeline's operator (IUK, BBL, GNI (UK)) belongs to no market area of its own.
    # A pipeline that crosses a border (its two ends in different countries: IUK, BBL, TAP) is
    # its operator's whole system; LBTG, both ends in Germany, sits inside THE.
    label_keys = _zone_label_keys(balancing_zones)
    pipelines = two_point_systems(interconnections)
    country_of = {node["point_key"]: node["country"] for node in nodes}
    pipeline_operators = {
        operator
        for (_label, operator), ends in pipelines.items()
        if all(end in country_of for end in ends) and len({country_of[end] for end in ends}) > 1
    }
    usual: dict[str, Counter] = defaultdict(Counter)
    zone_at: dict[tuple[str, str], set[str]] = defaultdict(set)
    for key, rows in access_by_key.items():
        for row in rows:
            label = str((getattr(row, "metadata_json", None) or {}).get("tso_balancing_zone") or "")
            zone = canonical_zone(label_keys.get(label.strip()))
            if zone in BZ_HUB:
                zone_at[(key, row.operator_key)].add(BZ_HUB[zone])
                usual[row.operator_key][BZ_HUB[zone]] += 1

    def member_hubs(key: str, operator: str) -> list[str]:
        if operator in pipeline_operators or "-TSO-" not in operator:
            return []
        if zone_at.get((key, operator)):
            return sorted(zone_at[(key, operator)])
        if usual.get(operator):
            return [usual[operator].most_common(1)[0][0]]
        if operator in EXTERNAL_OPERATOR_ZONES:
            return [BZ_HUB[EXTERNAL_OPERATOR_ZONES[operator]]]
        hub = _hub_for(operator)
        return [hub] if hub else []

    # A storage site, terminal or field ENTSOG lists with its own operator only (the Austrian
    # storage pools: no TSO row in operator point directions) belongs to the zone of the
    # transmission side ENTSOG's interconnections give it there.
    transmission_side: dict[str, set[tuple[str, str]]] = defaultdict(set)
    for row in interconnections:
        if row.get("isInvalid") or not row.get("pointKey"):
            continue
        for side in ("from", "to"):
            if row.get(f"{side}InfrastructureTypeLabel") != "Transmission":
                continue
            zone = canonical_zone(row.get(f"{side}BzKey"))
            operator = str(row.get(f"{side}OperatorKey") or "")
            if not zone and operator in EXTERNAL_OPERATOR_ZONES:
                zone = EXTERNAL_OPERATOR_ZONES[operator]
            if zone in BZ_HUB:
                transmission_side[str(row["pointKey"])].add((BZ_HUB[zone], operator))

    located_ids = {node["id"] for node in nodes if node["located"]}
    seen = set()
    for node in nodes:
        if not node["located"] or node["type"] == "hub":
            continue
        memberships = [
            (hub, operator)
            for operator in node["operators"]
            for hub in member_hubs(node["point_key"], operator)
        ]
        if not memberships and node["type"] != "interconnection":
            memberships = sorted(transmission_side.get(node["point_key"], set()))
        for hub, operator in memberships:
            hub_id = f"entsog-{hub.lower()}"
            if hub_id not in located_ids or hub_id == node["id"]:
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
                    "operator_key": operator or None,
                }
            )

    stamp = downloaded.strftime("%d-%m-%Y")
    return {
        "schema": BUNDLE_SCHEMA,
        "version": version,
        "built_at_utc": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "scope": {
            "region": "Europe (every active ENTSOG balancing zone)",
            "countries": list(SCOPE_COUNTRIES),
            "rule": (
                "ENTSOG interconnection, storage, LNG, production and trading points with an "
                "operator in a scope country, plus the balance's landing points, plus one node "
                "per market area ENTSOG publishes no trading point for (at ENTSOG's position "
                "for the balancing zone); distribution and final-consumer points are left out. "
                "A point ENTSOG places at map position 0/0 is not located."
            ),
        },
        "source": {
            "name": "ENTSOG Transparency Platform",
            "datasets": ["connectionpoints", "operatorpointdirections", "balancingzones"],
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


_READ_CACHE: dict[tuple[str, str], list[dict]] = {}


def read_entsog(name: str, entsog_dir: Path | None) -> list[dict]:
    """One ENTSOG dataset: the saved response in ``entsog_dir``, else read live (once)."""

    cache_key = (name, str(entsog_dir))
    if cache_key not in _READ_CACHE:
        if entsog_dir:
            payload = json.loads((entsog_dir / f"{name}.json").read_text(encoding="utf-8"))
            rows = next(value for key, value in payload.items() if key.lower() == name.lower())
        else:
            rows = fetch_entsog(name)
        _READ_CACHE[cache_key] = rows
    return _READ_CACHE[cache_key]


def entsog_rows(entsog_dir: Path | None) -> tuple[list[dict], list[dict]]:
    return read_entsog("interconnections", entsog_dir), read_entsog("connectionpoints", entsog_dir)


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
    if saved is not None:
        # Recorded beside the other saved responses, so a rebuild from them is the same build.
        saved.write_text(json.dumps(dict(sorted(out.items())), indent=0) + "\n", encoding="utf-8")
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


CONTEXT_PIPELINES_PATH = (
    Path(__file__).resolve().parents[2] / "clients/web/public/map/context-pipelines.geojson"
)


def with_presentation(
    bundle: dict, scigrid_dir: Path | None, previous: dict, context_out: Path
) -> dict:
    """The SciGRID_gas presentation paths; without a source, the shipped ones that still fit."""

    if scigrid_dir is None:
        kept = {
            edge["id"]: edge
            for edge in previous.get("edges") or []
            if edge.get("presentation_path")
        }
        edges = []
        for edge in bundle["edges"]:
            old = kept.get(edge["id"])
            if old and (old["from"], old["to"]) == (edge["from"], edge["to"]):
                edge = {**edge, "presentation_path": old["presentation_path"]}
            edges.append(edge)
        out = {**bundle, "edges": edges}
        if previous.get("presentation_geometry") and any(
            "presentation_path" in edge for edge in edges
        ):
            out["presentation_geometry"] = previous["presentation_geometry"]
        return out
    features, sha256 = read_pipe_segments(scigrid_dir)
    pipelines = context_pipelines(trunk_segments(features))
    provenance = {
        **SCIGRID_SOURCE,
        "file": "IGGIELGN_PipeSegments.geojson",
        "sha256": sha256,
        "trunk_lines": len(pipelines),
        "context_layer": "clients/web/public/map/context-pipelines.geojson",
    }
    context_out.parent.mkdir(parents=True, exist_ok=True)
    context_out.write_text(
        json.dumps(context_geojson(pipelines, provenance), separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    return apply_presentation_geometry(bundle, pipelines, provenance)


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
        help=(
            "saved ENTSOG responses (?limit=-1): interconnections, connectionpoints, "
            "balancingzones and, for --from-entsog-dir, operatorpointdirections"
        ),
    )
    parser.add_argument(
        "--from-entsog-dir",
        action="store_true",
        help="build the whole bundle from --entsog-dir, normalised as the live read (no database)",
    )
    parser.add_argument(
        "--scigrid-dir",
        type=Path,
        help="unpacked SciGRID_gas IGGIELGN data folder (presentation geometry)",
    )
    parser.add_argument(
        "--presentation-only",
        action="store_true",
        help="re-derive only the presentation geometry of the shipped bundle",
    )
    parser.add_argument("--context-out", type=Path, default=CONTEXT_PIPELINES_PATH)
    args = parser.parse_args(argv)
    previous = load_bundle()
    if args.from_entsog_dir and args.entsog_dir is None:
        print("--from-entsog-dir needs --entsog-dir", file=sys.stderr)
        return 2
    if args.presentation_only:
        if args.scigrid_dir is None:
            print("--presentation-only needs --scigrid-dir", file=sys.stderr)
            return 2
        bundle = with_presentation(
            {**previous, "version": args.version}, args.scigrid_dir, previous, args.context_out
        )
        problems = validate_bundle(bundle)
        if problems:
            print("bundle failed its checks:\n  " + "\n  ".join(problems[:20]), file=sys.stderr)
            return 1
        write(bundle, args.out)
        print(
            f"{args.out}: {bundle['presentation_geometry']['routed_edges']} connection legs "
            f"follow the trunk lines; {args.context_out}: "
            f"{bundle['presentation_geometry']['trunk_lines']} trunk lines"
        )
        return 0
    if args.adjacency_only:
        bundle = {**load_bundle(), "version": args.version}
    elif args.from_entsog_dir:
        bundle = build_from_entsog(
            args.entsog_dir, version=args.version, downloaded=args.downloaded
        )
    else:
        if not resolve_database_url():
            print("RUNTIME_STORE_DATABASE_URL is required", file=sys.stderr)
            return 2
        with get_session_factory()() as session:
            bundle = build(
                session,
                version=args.version,
                downloaded=args.downloaded,
                entsog_dir=args.entsog_dir,
            )
            session.rollback()  # read-only
    bundle = with_adjacency(bundle, args.entsog_dir, args.downloaded)
    bundle = with_presentation(bundle, args.scigrid_dir, previous, args.context_out)
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
