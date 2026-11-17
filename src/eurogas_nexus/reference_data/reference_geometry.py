"""Open reference pipeline geometry, for the general direction of the drawn connections.

Presentation only. SciGRID_gas IGGIELGN (DLR Institute of Networked Energy Systems, CC BY 4.0,
doi:10.5281/zenodo.4767098) is an abstracted European gas transmission network assembled from
open sources. The bundle build reads its pipe segments once and keeps two things:

- the trunk lines of north-west Europe, generalised, as a faint context layer the map draws
  under the connections (``context_pipelines``);
- for each drawn connection leg (interconnection point -> market area; not the subsea
  interconnectors, which stay straight between their landings), a path along those
  trunk lines when one runs close to both ends without a long detour
  (``presentation_path``), so a link between market areas roughly follows where pipes run.

Neither is a network fact. Route pricing walks the ENTSOG market-area adjacency only
(``domain/route_cost/market_area_graph.py``); no tariff, capacity or path is read from this
geometry, and the drawn links stay dashed (schematic, not surveyed).
"""

from __future__ import annotations

import hashlib
import heapq
import json
import math
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

Coordinate = tuple[float, float]  # (lon, lat)

SOURCE = {
    "name": "SciGRID_gas IGGIELGN",
    "version": "1.1.2",
    "publisher": "DLR Institute of Networked Energy Systems",
    "doi": "10.5281/zenodo.4767098",
    "url": "https://zenodo.org/records/4767098",
    "licence": "CC-BY-4.0",
    "attribution": "Pipelines: SciGRID_gas IGGIELGN (DLR), CC BY 4.0",
    "use": "presentation only: general direction of the drawn connections; never priced",
}

#: North-west Europe and the Norwegian shelf, with the neighbours the scope's borders reach.
BBOX = (-11.0, 46.5, 16.0, 63.0)  # min lon, min lat, max lon, max lat
#: Trunk lines only: transmission pipes of at least this diameter.
MIN_DIAMETER_MM = 600.0
#: Douglas-Peucker tolerance in degrees (about 2 km) and the stored coordinate precision.
SIMPLIFY_DEGREES = 0.02
PRECISION = 3
#: A connection end snaps to the trunk network only within this distance.
SNAP_KM = 45.0
#: A path is kept only when it is not much longer than the straight connection.
MAX_DETOUR = 1.5
MAX_EXTRA_KM = 40.0


def km(a: Coordinate, b: Coordinate) -> float:
    """Great-circle distance in km."""

    rad = math.pi / 180
    d_lat = (b[1] - a[1]) * rad
    d_lon = (b[0] - a[0]) * rad
    h = (
        math.sin(d_lat / 2) ** 2
        + math.cos(a[1] * rad) * math.cos(b[1] * rad) * math.sin(d_lon / 2) ** 2
    )
    return 6371.0 * 2 * math.asin(math.sqrt(min(1.0, h)))


def _inside(point: Coordinate, bbox: Sequence[float] = BBOX) -> bool:
    return bbox[0] <= point[0] <= bbox[2] and bbox[1] <= point[1] <= bbox[3]


def segment_coordinates(feature: dict[str, Any]) -> list[Coordinate]:
    """A segment's line: its two end nodes with the intermediate path the dataset records."""

    ends = feature["geometry"]["coordinates"]
    param = feature.get("properties", {}).get("param", {})
    middle = list(zip(param.get("path_long") or [], param.get("path_lat") or [], strict=False))
    return [tuple(ends[0]), *[(float(x), float(y)) for x, y in middle], tuple(ends[-1])]


def trunk_segments(
    features: Iterable[dict[str, Any]],
    *,
    bbox: Sequence[float] = BBOX,
    min_diameter_mm: float = MIN_DIAMETER_MM,
) -> list[dict[str, Any]]:
    """The trunk pipe segments of the region: large diameter, at least one end inside."""

    out = []
    for feature in features:
        param = feature.get("properties", {}).get("param", {})
        diameter = param.get("diameter_mm")
        if diameter is None or float(diameter) < min_diameter_mm:
            continue
        coords = segment_coordinates(feature)
        if not (_inside(coords[0], bbox) or _inside(coords[-1], bbox)):
            continue
        out.append(
            {
                "id": feature["properties"]["id"],
                "diameter_mm": float(diameter),
                "coordinates": coords,
            }
        )
    return out


def _perpendicular(point: Coordinate, start: Coordinate, end: Coordinate) -> float:
    dx, dy = end[0] - start[0], end[1] - start[1]
    if dx == 0 and dy == 0:
        return math.hypot(point[0] - start[0], point[1] - start[1])
    t = ((point[0] - start[0]) * dx + (point[1] - start[1]) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    return math.hypot(point[0] - (start[0] + t * dx), point[1] - (start[1] + t * dy))


def simplify(coords: Sequence[Coordinate], tolerance: float = SIMPLIFY_DEGREES) -> list[Coordinate]:
    """Douglas-Peucker: the fewest points within ``tolerance`` degrees of the line."""

    if len(coords) <= 2:
        return list(coords)
    index, distance = 0, 0.0
    for position in range(1, len(coords) - 1):
        candidate = _perpendicular(coords[position], coords[0], coords[-1])
        if candidate > distance:
            index, distance = position, candidate
    if distance <= tolerance:
        return [coords[0], coords[-1]]
    left = simplify(coords[: index + 1], tolerance)
    right = simplify(coords[index:], tolerance)
    return [*left[:-1], *right]


def _round(point: Coordinate) -> Coordinate:
    return (round(point[0], PRECISION), round(point[1], PRECISION))


def context_pipelines(segments: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """Generalised trunk lines; a segment recorded twice between the same ends is kept once."""

    seen: set[tuple[Coordinate, Coordinate]] = set()
    out = []
    for segment in sorted(segments, key=lambda item: item["id"]):
        coords = [_round(point) for point in simplify(segment["coordinates"])]
        key = tuple(sorted((coords[0], coords[-1])))
        if key in seen or coords[0] == coords[-1]:
            continue
        seen.add(key)  # type: ignore[arg-type]
        out.append(
            {
                "id": segment["id"],
                "diameter_mm": segment["diameter_mm"],
                "coordinates": coords,
            }
        )
    return out


class PipeGraph:
    """The trunk lines as a graph: segment ends are vertices, a segment is an edge."""

    def __init__(self, pipelines: Sequence[dict[str, Any]]) -> None:
        self.adjacent: dict[Coordinate, list[tuple[Coordinate, float, list[Coordinate]]]] = {}
        for pipe in pipelines:
            coords = [tuple(point) for point in pipe["coordinates"]]
            length = sum(km(a, b) for a, b in zip(coords, coords[1:], strict=False))
            start, end = coords[0], coords[-1]
            self.adjacent.setdefault(start, []).append((end, length, coords))
            self.adjacent.setdefault(end, []).append((start, length, coords[::-1]))

    def nearest(self, point: Coordinate, within_km: float = SNAP_KM) -> Coordinate | None:
        best, best_km = None, within_km
        for vertex in self.adjacent:
            distance = km(point, vertex)
            if distance <= best_km:
                best, best_km = vertex, distance
        return best

    def shortest(self, start: Coordinate, end: Coordinate) -> tuple[float, list[Coordinate]] | None:
        queue: list[tuple[float, Coordinate]] = [(0.0, start)]
        best: dict[Coordinate, float] = {start: 0.0}
        back: dict[Coordinate, tuple[Coordinate, list[Coordinate]]] = {}
        while queue:
            distance, vertex = heapq.heappop(queue)
            if vertex == end:
                break
            if distance > best.get(vertex, math.inf):
                continue
            for neighbour, length, coords in self.adjacent.get(vertex, []):
                candidate = distance + length
                if candidate < best.get(neighbour, math.inf):
                    best[neighbour] = candidate
                    back[neighbour] = (vertex, coords)
                    heapq.heappush(queue, (candidate, neighbour))
        if end not in best:
            return None
        path: list[Coordinate] = [end]
        vertex = end
        while vertex != start:
            previous, coords = back[vertex]
            path = [*coords[:-1], *path]
            vertex = previous
        return best[end], path


def presentation_path(
    graph: PipeGraph, start: Coordinate, end: Coordinate
) -> list[list[float]] | None:
    """A drawn connection along the trunk lines, or ``None`` to keep the straight line.

    The path runs from ``start`` to the nearest trunk vertex, along the trunk lines to the
    vertex nearest ``end``, and on to ``end``. It is kept only when both ends are within
    ``SNAP_KM`` of the trunk network and the whole is at most ``MAX_DETOUR`` times (plus
    ``MAX_EXTRA_KM``) the straight distance.
    """

    straight = km(start, end)
    first, last = graph.nearest(start), graph.nearest(end)
    if first is None or last is None or first == last:
        return None
    found = graph.shortest(first, last)
    if found is None:
        return None
    length, path = found
    total = km(start, first) + length + km(last, end)
    if total > straight * MAX_DETOUR + MAX_EXTRA_KM:
        return None
    coords = [_round(start), *simplify(path), _round(end)]
    out: list[list[float]] = []
    for point in coords:
        rounded = list(_round(point))
        if not out or out[-1] != rounded:
            out.append(rounded)
    return out if len(out) > 2 else None


def read_pipe_segments(scigrid_dir: Path) -> tuple[list[dict[str, Any]], str]:
    """The IGGIELGN pipe segments and the SHA-256 of the file they came from."""

    path = scigrid_dir / "IGGIELGN_PipeSegments.geojson"
    raw = path.read_bytes()
    return json.loads(raw)["features"], hashlib.sha256(raw).hexdigest()


def context_geojson(pipelines: Sequence[dict[str, Any]], provenance: dict[str, Any]) -> dict:
    """The context layer as GeoJSON, with its provenance in the collection's properties."""

    return {
        "type": "FeatureCollection",
        "properties": provenance,
        "features": [
            {
                "type": "Feature",
                "properties": {"id": pipe["id"], "diameter_mm": pipe["diameter_mm"]},
                "geometry": {"type": "LineString", "coordinates": pipe["coordinates"]},
            }
            for pipe in pipelines
        ],
    }


def apply_presentation_geometry(
    bundle: dict[str, Any],
    pipelines: Sequence[dict[str, Any]],
    provenance: dict[str, Any],
) -> dict[str, Any]:
    """Each drawn connection leg with a ``presentation_path`` where the trunk lines allow one."""

    graph = PipeGraph(pipelines)
    nodes = {node["id"]: node for node in bundle["nodes"]}
    edges = []
    routed = 0
    for edge in bundle["edges"]:
        edge = {key: value for key, value in edge.items() if key != "presentation_path"}
        # A subsea interconnector (IUK, BBL) runs nearly straight between its two landings:
        # the straight line is the better picture than the abstracted offshore path.
        if edge["type"] not in ("virtual", "interconnector"):
            start, end = nodes.get(edge["from"]), nodes.get(edge["to"])
            if start and end and start.get("located") and end.get("located"):
                path = presentation_path(
                    graph, (start["lon"], start["lat"]), (end["lon"], end["lat"])
                )
                if path:
                    edge["presentation_path"] = path
                    routed += 1
        edges.append(edge)
    return {
        **bundle,
        "presentation_geometry": {**provenance, "routed_edges": routed},
        "edges": edges,
    }
