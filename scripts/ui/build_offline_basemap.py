"""Build the bundled offline basemap: Natural Earth land, clipped to the trading region.

    npm pack world-atlas@2.0.2 && tar xzf world-atlas-2.0.2.tgz
    python scripts/ui/build_offline_basemap.py package/land-50m.json

Borders and place labels for the bundled basemap (the ``bundled`` provider), from the Natural
Earth 1:50m GeoJSON (public domain; github.com/nvkelso/natural-earth-vector, ``geojson/``):
``ne_50m_admin_0_boundary_lines_land``, ``ne_50m_admin_0_countries`` (label points and names)
and ``ne_50m_populated_places`` (cities, with English and Chinese names):

    python scripts/ui/build_offline_basemap.py --natural-earth <folder with those three files>

These land in ``clients/web/public/basemaps/`` beside the land polygons; the glyphs their
labels are drawn with are built from the bundled Inter by ``scripts/ui/build_map_glyphs.mjs``.

Natural Earth is public domain (commercial use allowed, no attribution required; credited
anyway); world-atlas packages it as TopoJSON under ISC. The output is land polygons only,
with no country borders, clipped to Europe, North Africa and the Middle East
(``BBOX``). It therefore draws no Chinese territory and no disputed boundary, which keeps
it usable in a mainland China installation, where published maps of China need approval
(审图号), and in air-gapped networks, where no tile service is reachable.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

BBOX = (-35.0, 20.0, 62.0, 75.0)  # west, south, east, north
TOLERANCE = 0.01  # degrees, Douglas-Peucker
OUTPUT = Path("clients/web/public/basemaps/land-trading-region.geojson")


def _decode_arcs(topology: dict) -> list[list[tuple[float, float]]]:
    scale = topology.get("transform", {}).get("scale", [1, 1])
    translate = topology.get("transform", {}).get("translate", [0, 0])
    arcs = []
    for arc in topology["arcs"]:
        x = y = 0
        points = []
        for dx, dy in arc:
            x += dx
            y += dy
            points.append((x * scale[0] + translate[0], y * scale[1] + translate[1]))
        arcs.append(points)
    return arcs


def _ring(indexes: list[int], arcs: list[list[tuple[float, float]]]) -> list[tuple[float, float]]:
    ring: list[tuple[float, float]] = []
    for index in indexes:
        points = arcs[index] if index >= 0 else list(reversed(arcs[~index]))
        ring.extend(points[1:] if ring else points)
    return ring


def _clip(ring: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Sutherland-Hodgman against the bounding box (convex), valid for any polygon."""

    west, south, east, north = BBOX
    edges = [
        (lambda p: p[0] >= west, lambda a, b: _cross_x(a, b, west)),
        (lambda p: p[0] <= east, lambda a, b: _cross_x(a, b, east)),
        (lambda p: p[1] >= south, lambda a, b: _cross_y(a, b, south)),
        (lambda p: p[1] <= north, lambda a, b: _cross_y(a, b, north)),
    ]
    output = ring
    for inside, cross in edges:
        source, output = output, []
        if not source:
            break
        previous = source[-1]
        for point in source:
            if inside(point):
                if not inside(previous):
                    output.append(cross(previous, point))
                output.append(point)
            elif inside(previous):
                output.append(cross(previous, point))
            previous = point
    return output


def _cross_x(a, b, x):
    t = (x - a[0]) / (b[0] - a[0])
    return (x, a[1] + t * (b[1] - a[1]))


def _cross_y(a, b, y):
    t = (y - a[1]) / (b[1] - a[1])
    return (a[0] + t * (b[0] - a[0]), y)


def _simplify(ring: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Simplify a closed ring as two open lines split at the point farthest from the start."""

    if len(ring) < 5:
        return ring
    x0, y0 = ring[0]
    pivot = max(range(len(ring)), key=lambda i: (ring[i][0] - x0) ** 2 + (ring[i][1] - y0) ** 2)
    if pivot == 0:
        return ring
    return _simplify_line(ring[: pivot + 1])[:-1] + _simplify_line(ring[pivot:] + [ring[0]])


def _simplify_line(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    if len(points) < 3:
        return points
    keep = [False] * len(points)
    keep[0] = keep[-1] = True
    stack = [(0, len(points) - 1)]
    while stack:
        start, end = stack.pop()
        (ax, ay), (bx, by) = points[start], points[end]
        dx, dy = bx - ax, by - ay
        norm = (dx * dx + dy * dy) ** 0.5 or 1e-12
        best, index = 0.0, None
        for i in range(start + 1, end):
            px, py = points[i]
            distance = abs(dy * px - dx * py + bx * ay - by * ax) / norm
            if distance > best:
                best, index = distance, i
        if index is not None and best > TOLERANCE:
            keep[index] = True
            stack += [(start, index), (index, end)]
    return [point for point, kept in zip(points, keep, strict=True) if kept]


def build(source: Path) -> dict:
    topology = json.loads(source.read_text(encoding="utf-8"))
    arcs = _decode_arcs(topology)
    polygons = []
    for geometry in topology["objects"]["land"]["geometries"]:
        shapes = geometry["arcs"] if geometry["type"] == "MultiPolygon" else [geometry["arcs"]]
        for shape in shapes:
            rings = []
            for indexes in shape:
                ring = _simplify(_clip(_ring(indexes, arcs)))
                if len(ring) >= 4:
                    ring = [(round(x, 3), round(y, 3)) for x, y in ring]
                    if ring[0] != ring[-1]:
                        ring.append(ring[0])
                    rings.append(ring)
            if rings:
                polygons.append(rings)
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"source": "Natural Earth 1:50m land (public domain)"},
                "geometry": {"type": "MultiPolygon", "coordinates": polygons},
            }
        ],
    }


#: Place labels kept: cities up to this Natural Earth scale rank (0 = most prominent).
MAX_PLACE_RANK = 7
BORDERS_OUTPUT = OUTPUT.with_name("borders-trading-region.geojson")
PLACES_OUTPUT = OUTPUT.with_name("places-trading-region.geojson")


def _inside(lon: float, lat: float) -> bool:
    west, south, east, north = BBOX
    return west <= lon <= east and south <= lat <= north


def _clip_line(line: list[tuple[float, float]]) -> list[list[tuple[float, float]]]:
    """The parts of a line inside the bounding box (a part leaving it is cut at the edge)."""

    parts: list[list[tuple[float, float]]] = []
    current: list[tuple[float, float]] = []
    for point in line:
        if _inside(*point):
            current.append(point)
        elif current:
            parts.append(current)
            current = []
    if current:
        parts.append(current)
    return [part for part in parts if len(part) >= 2]


def build_borders(natural_earth: Path) -> dict:
    """Land boundaries between countries (de facto, as Natural Earth draws them), in region."""

    source = json.loads((natural_earth / "ne_50m_admin_0_boundary_lines_land.geojson").read_text())
    lines = []
    for feature in source["features"]:
        geometry = feature["geometry"]
        parts = (
            geometry["coordinates"]
            if geometry["type"] == "MultiLineString"
            else [geometry["coordinates"]]
        )
        for part in parts:
            for clipped in _clip_line([(float(x), float(y)) for x, y in part]):
                simplified = _simplify_line(clipped)
                lines.append([[round(x, 3), round(y, 3)] for x, y in simplified])
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"source": "Natural Earth 1:50m boundary lines (public domain)"},
                "geometry": {"type": "MultiLineString", "coordinates": lines},
            }
        ],
    }


def build_places(natural_earth: Path) -> dict:
    """Country names at their label point and the region's main cities, English and Chinese."""

    features = []
    countries = json.loads((natural_earth / "ne_50m_admin_0_countries.geojson").read_text())
    for feature in countries["features"]:
        props = feature["properties"]
        lon, lat = float(props["LABEL_X"]), float(props["LABEL_Y"])
        if not _inside(lon, lat):
            continue
        features.append(
            {
                "type": "Feature",
                "properties": {
                    "kind": "country",
                    "name_en": props.get("NAME_EN") or props["NAME"],
                    "name_zh": props.get("NAME_ZH") or props.get("NAME_EN") or props["NAME"],
                    "rank": int(props.get("LABELRANK") or 5),
                },
                "geometry": {"type": "Point", "coordinates": [round(lon, 3), round(lat, 3)]},
            }
        )
    places = json.loads((natural_earth / "ne_50m_populated_places.geojson").read_text())
    for feature in places["features"]:
        props = feature["properties"]
        lon, lat = float(props["LONGITUDE"]), float(props["LATITUDE"])
        rank = int(props.get("SCALERANK") or 10)
        if not _inside(lon, lat) or rank > MAX_PLACE_RANK:
            continue
        features.append(
            {
                "type": "Feature",
                "properties": {
                    "kind": "capital" if props.get("ADM0CAP") else "city",
                    "name_en": props.get("NAME_EN") or props["NAME"],
                    "name_zh": props.get("NAME_ZH") or props.get("NAME_EN") or props["NAME"],
                    "rank": rank,
                },
                "geometry": {"type": "Point", "coordinates": [round(lon, 3), round(lat, 3)]},
            }
        )
    features.sort(
        key=lambda item: (item["properties"]["kind"] != "country", item["properties"]["rank"])
    )
    return {"type": "FeatureCollection", "features": features}


def main(argv: list[str]) -> int:
    if len(argv) == 3 and argv[1] == "--natural-earth":
        folder = Path(argv[2])
        for path, data in (
            (BORDERS_OUTPUT, build_borders(folder)),
            (PLACES_OUTPUT, build_places(folder)),
        ):
            path.write_text(json.dumps(data, separators=(",", ":"), ensure_ascii=False) + "\n")
            print(f"wrote {path} ({path.stat().st_size // 1024} KiB)")
        return 0
    if len(argv) != 2:
        print(__doc__)
        return 2
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(build(Path(argv[1])), separators=(",", ":")) + "\n")
    print(f"wrote {OUTPUT} ({OUTPUT.stat().st_size // 1024} KiB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
