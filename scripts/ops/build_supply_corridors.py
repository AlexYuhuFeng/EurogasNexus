"""Build ``src/eurogas_nexus/reference_data/supply_corridors.json`` from ENTSOG and SciGRID_gas.

For each corridor of ``reference_data/supply_corridors.CORRIDORS``:

- landing positions, operator names: the saved ENTSOG ``connectionpoints`` and ``operators``
  responses (``--entsog-dir``, as for the reference bundle);
- capacity: ENTSOG ``operationaldatas`` Firm Technical at each entry series on ``--gas-day``;
- status: ENTSOG Physical Flow at each entry series over the last 30 closed gas days, and over
  the corridor's probe window when it has none (``supply_corridors.STATUS_RULE``);
- geometry: the SciGRID_gas IGGIELGN pipe segments (``--scigrid-dir``, CC BY 4.0) between the
  source and the landing, else a straight schematic line.

ENTSOG answers are read one point and window per query (the TP API manual asks for filtered
queries) and saved under ``<entsog-dir>/corridors/``; a rebuild reads the saved answers, so the
same inputs give the same file::

    python scripts/ops/build_supply_corridors.py --entsog-dir entsog/ \\
        --scigrid-dir IGGIELGN/data --gas-day 2026-11-25
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from eurogas_nexus.ingestion.public_sources import _entsog_map_to_lon_lat
from eurogas_nexus.reference_data.network_adjacency import MARKET_AREAS
from eurogas_nexus.reference_data.network_bundle import load_bundle
from eurogas_nexus.reference_data.reference_geometry import (
    SOURCE as SCIGRID_SOURCE,
)
from eurogas_nexus.reference_data.reference_geometry import (
    PipeGraph,
    context_pipelines,
    km,
    read_pipe_segments,
    trunk_segments,
)
from eurogas_nexus.reference_data.supply_corridors import (
    CORRIDORS,
    RECENT_DAYS,
    SCHEMA,
    STATUS_RULE,
    Corridor,
    classify_status,
    corridors_path,
    validate_corridors,
)

ENTSOG_API = "https://transparency.entsog.eu/api/v1"
#: A source within this distance of a SciGRID vertex takes the vertex's position.
SOURCE_SNAP_KM = 60.0
LANDING_SNAP_KM = 60.0
MAX_DETOUR = 1.6
MAX_EXTRA_KM = 80.0
EUROPE_AND_NEIGHBOURS = (-20.0, 25.0, 60.0, 72.0)


def _query(cache: Path, params: dict[str, str]) -> list[dict[str, Any]]:
    name = "_".join(params[key] for key in ("pointKey", "indicator", "from", "to"))
    path = cache / (name.replace(" ", "-") + ".json")
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    url = f"{ENTSOG_API}/operationaldatas?" + urllib.parse.urlencode(
        {**params, "periodType": "day", "limit": "-1"}
    )
    rows: list[dict[str, Any]] = []
    for attempt in range(1, 6):
        try:
            with urllib.request.urlopen(url, timeout=180) as response:  # noqa: S310 - fixed host
                rows = json.load(response).get("operationaldatas") or []
            break
        except urllib.error.HTTPError as exc:
            if exc.code == 404:  # ENTSOG answers "No result found" with a 404
                break
            if attempt == 5:
                raise
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            if attempt == 5:
                raise
        time.sleep(5 * attempt)
    keep = ("pointKey", "operatorKey", "directionKey", "periodFrom", "value", "unit", "id")
    rows = [{key: row.get(key) for key in keep} for row in rows]
    cache.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rows, separators=(",", ":")) + "\n", encoding="utf-8")
    time.sleep(2)
    return rows


def _series_rows(rows, series) -> list[dict[str, Any]]:
    return [
        row
        for row in rows
        if row.get("operatorKey") == series.operator_key
        and str(row.get("directionKey") or "").lower() == series.direction
    ]


def _positive(rows) -> list[str]:
    return sorted(
        str(row["periodFrom"])[:10]
        for row in rows
        if row.get("value") not in (None, "") and float(row["value"]) > 0
    )


def corridor_record(
    corridor: Corridor,
    *,
    points: dict[str, dict[str, Any]],
    operators: dict[str, dict[str, Any]],
    bundle_ids: set[str],
    cache: Path,
    gas_day: date,
    graph: PipeGraph | None,
    provenance: dict[str, Any] | None,
) -> dict[str, Any]:
    recent_from = (gas_day - timedelta(days=RECENT_DAYS - 1)).isoformat()
    stamp = gas_day.isoformat()
    flow_series, capacity_total, recent_days, last_days = [], 0.0, set(), []
    published_days: set[str] = set()
    capacity_rows = 0
    for series in corridor.entry_series:
        recent = _series_rows(
            _query(cache, {"pointKey": series.point_key, "indicator": "Physical Flow",
                           "from": recent_from, "to": stamp}),
            series,
        )
        firm = _series_rows(
            _query(cache, {"pointKey": series.point_key, "indicator": "Firm Technical",
                           "from": stamp, "to": stamp}),
            series,
        )
        firm_value = max(
            (float(row["value"]) for row in firm if row.get("value") not in (None, "")),
            default=None,
        )
        if firm_value is not None:
            capacity_total += firm_value
            capacity_rows += 1
        positive = _positive(recent)
        recent_days |= set(positive)
        published_days |= {str(row["periodFrom"])[:10] for row in recent}
        if positive:
            last_days.append(positive[-1])
        elif corridor.probe_from:
            probe = _series_rows(
                _query(cache, {"pointKey": series.point_key, "indicator": "Physical Flow",
                               "from": corridor.probe_from, "to": corridor.probe_to or stamp}),
                series,
            )
            older = _positive(probe)
            if older:
                last_days.append(older[-1])
        flow_series.append(
            {
                "point_key": series.point_key,
                "operator_key": series.operator_key,
                "operator_name": (operators.get(series.operator_key) or {}).get("operatorLabel"),
                "direction": series.direction,
                "indicator": "Physical Flow",
                "node_id": f"entsog-{series.point_key.lower()}",
                "published_days_last_30": len(recent),
                "flow_days_last_30": len(positive),
                "last_flow_day": positive[-1] if positive else None,
                "firm_technical_kwh_d": firm_value,
            }
        )
    status = classify_status(
        len(recent_days),
        max(last_days) if last_days else None,
        probe_from=corridor.probe_from,
        recent_from=recent_from,
        recent_published_days=len(published_days),
    )
    window = (
        f"{recent_from}..{stamp}"
        if status["status"] == "in_service"
        else f"{corridor.probe_from or recent_from}..{corridor.probe_to or stamp}"
    )
    landings = []
    for key in corridor.landing_points:
        cp = points.get(key) or {}
        x, y = cp.get("tpMapX"), cp.get("tpMapY")
        lon, lat = _entsog_map_to_lon_lat(x, y)
        placed = lon is not None and not (float(x or 0) == 0 and float(y or 0) == 0)
        landings.append(
            {
                "point_key": key,
                "name": cp.get("pointLabel"),
                "node_id": f"entsog-{key.lower()}",
                "in_reference_bundle": f"entsog-{key.lower()}" in bundle_ids,
                "lon": lon if placed else None,
                "lat": lat if placed else None,
                "coordinate_quality": "display_approximation" if placed else None,
            }
        )
    geometry, source = _geometry(corridor, landings, graph, provenance)
    operator = operators.get(corridor.operator_key or "") or {}
    return {
        "id": corridor.id,
        "shared_entry_point": corridor.shared_entry_point,
        "name": corridor.name,
        "group": corridor.group,
        "source_country": corridor.source_country,
        "source": source,
        "operator": {
            "operator_key": corridor.operator_key,
            "name": operator.get("operatorLabelLong") or operator.get("operatorLabel"),
            "basis": "ENTSOG operators (the upstream side at the landing point)"
            if corridor.operator_key
            else None,
        },
        "landing_points": landings,
        "into_market_areas": [],
        "flow_series": flow_series,
        "capacity": {
            "firm_technical_kwh_d": capacity_total if capacity_rows else None,
            "gas_day": stamp if capacity_rows else None,
            "series_with_value": capacity_rows,
            "basis": "sum of the entry series' Firm Technical capacity, as published",
            "citation": f"ENTSOG TP [{gas_day.strftime('%d-%m-%Y')}] "
            "https://transparency.entsog.eu/ (operationaldatas, Firm Technical)"
            if capacity_rows
            else None,
        },
        **status,
        "status_source": {
            "citation": f"ENTSOG TP [{date.today().strftime('%d-%m-%Y')}] "
            "https://transparency.entsog.eu/ (operationaldatas, Physical Flow)",
            "window": window,
            "flow_days_in_last_30": len(recent_days),
            "last_flow_day": max(last_days) if last_days else None,
        },
        "facts": dict(corridor.facts),
        "geometry": geometry,
        "notes": corridor.notes,
    }


def _geometry(corridor, landings, graph, provenance):
    placed = [item for item in landings if item["lon"] is not None]
    end = (placed[-1]["lon"], placed[-1]["lat"]) if placed else None
    if corridor.source_hint is not None:
        hint, place = corridor.source_hint, corridor.source_place
    elif len(placed) > 1:
        hint, place = (placed[0]["lon"], placed[0]["lat"]), placed[0]["name"]
    else:
        hint, place = None, corridor.source_place
    start = graph.nearest(hint, SOURCE_SNAP_KM) if graph is not None and hint else None
    source = {
        "place": place,
        "lon": round((start or hint)[0], 3) if hint else None,
        "lat": round((start or hint)[1], 3) if hint else None,
        "position_quality": (
            "scigrid_node" if start else ("display_approximation" if not corridor.source_hint
                                          else "approximate_place")
        )
        if hint
        else None,
    }
    if end is None or hint is None:
        return {"basis": "schematic", "coordinates": None}, source
    landing = graph.nearest(end, LANDING_SNAP_KM) if graph is not None else None
    if graph is not None and start and landing and start != landing:
        found = graph.shortest(start, landing)
        straight = km(start, end)
        if found and found[0] + km(landing, end) <= straight * MAX_DETOUR + MAX_EXTRA_KM:
            coords = [list(point) for point in found[1]]
            if coords[-1] != [round(end[0], 3), round(end[1], 3)]:
                coords.append([round(end[0], 3), round(end[1], 3)])
            return {
                "basis": "reference_pipeline_direction",
                "coordinates": coords,
                "source": provenance["name"],
                "licence": provenance["licence"],
                "attribution": provenance["attribution"],
                "use": "presentation only: the general direction of the corridor",
            }, source
    first = start or hint
    return {
        "basis": "schematic",
        "coordinates": [[round(first[0], 3), round(first[1], 3)],
                        [round(end[0], 3), round(end[1], 3)]],
        "note": "straight line from the source to the landing; not where the pipe runs",
    }, source


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--entsog-dir", type=Path, required=True)
    parser.add_argument("--scigrid-dir", type=Path)
    parser.add_argument("--gas-day", type=date.fromisoformat, required=True)
    parser.add_argument("--out", type=Path, default=corridors_path())
    args = parser.parse_args(argv)

    def read(name: str) -> list[dict[str, Any]]:
        payload = json.loads((args.entsog_dir / f"{name}.json").read_text(encoding="utf-8"))
        return next(value for key, value in payload.items() if key.lower() == name.lower())

    points = {row["pointKey"]: row for row in read("connectionpoints")}
    operators = {row["operatorKey"]: row for row in read("operators")}
    bundle = load_bundle()
    bundle_ids = {node["id"] for node in bundle["nodes"] if node.get("located")}
    graph, provenance = None, None
    if args.scigrid_dir:
        features, sha256 = read_pipe_segments(args.scigrid_dir)
        segments = trunk_segments(features, bbox=EUROPE_AND_NEIGHBOURS, min_diameter_mm=0.0)
        graph = PipeGraph(context_pipelines(segments))
        provenance = {**SCIGRID_SOURCE, "file": "IGGIELGN_PipeSegments.geojson", "sha256": sha256}
    member_of: dict[str, set[str]] = {}
    names = {node["id"]: node for node in bundle["nodes"]}
    for edge in bundle["edges"]:
        if edge["type"] == "virtual":
            hub = names.get(edge["to"]) or {}
            code = str(hub.get("hub_code") or hub.get("name"))
            member_of.setdefault(edge["from"], set()).add(code)
    records = []
    for corridor in CORRIDORS:
        record = corridor_record(
            corridor,
            points=points,
            operators=operators,
            bundle_ids=bundle_ids,
            cache=args.entsog_dir / "corridors",
            gas_day=args.gas_day,
            graph=graph,
            provenance=provenance,
        )
        # The market area the gas enters: the zone of the European operator whose entry the
        # series is (its ENTSOG country), else the landing point's zone membership.
        areas: set[str] = set()
        for series in record["flow_series"]:
            country = series["operator_key"].split("-")[0]
            area = next((a for a in MARKET_AREAS if country in a.operator_countries), None)
            if area is not None:
                areas.add(area.code)
            else:
                areas |= member_of.get(series["node_id"], set())
        record["into_market_areas"] = sorted(areas)
        records.append(record)
        print(
            f"{corridor.id}: {record['status']} {record.get('since') or ''} "
            f"cap={record['capacity']['firm_technical_kwh_d']} geom={record['geometry']['basis']}",
            file=sys.stderr,
        )
    stamp = args.gas_day.strftime("%d-%m-%Y")
    data = {
        "schema": SCHEMA,
        "built_at_utc": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "gas_day": args.gas_day.isoformat(),
        "source": {
            "name": "ENTSOG Transparency Platform",
            "datasets": ["connectionpoints", "operators", "operationaldatas"],
            "downloaded": date.today().isoformat(),
            "attribution": f"ENTSOG TP [{stamp}] https://transparency.entsog.eu/",
        },
        "geometry_source": provenance,
        "status_rule": STATUS_RULE,
        "use": "presentation and fundamentals; route pricing never reads it",
        "corridors": records,
    }
    problems = validate_corridors(data)
    if problems:
        print("corridors failed their checks:\n  " + "\n  ".join(problems), file=sys.stderr)
        return 1
    args.out.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{args.out}: {len(records)} corridors")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
