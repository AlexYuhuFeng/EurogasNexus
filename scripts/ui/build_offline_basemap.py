"""Build the bundled offline basemap: Natural Earth land, clipped to the trading region.

    npm pack world-atlas@2.0.2 && tar xzf world-atlas-2.0.2.tgz
    python scripts/ui/build_offline_basemap.py package/land-50m.json

The output lands in ``clients/web/public/basemaps/``; its label glyphs are built from the
bundled Inter by ``scripts/ui/build_map_glyphs.mjs``.

Natural Earth is public domain (commercial use allowed, no attribution required; credited
anyway); world-atlas packages it as TopoJSON under ISC. The output is land polygons only,
with no country borders and no place names, clipped to Europe, North Africa and the Middle
East (``BBOX``). It therefore draws no Chinese territory and no disputed boundary, which
keeps it usable in a mainland China installation, where published maps of China need
approval (审图号), and in air-gapped networks, where no tile service is reachable.
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


def _unwrap(ring: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Longitudes made continuous across the antimeridian.

    Natural Earth draws Russia's polygon across 180 degrees: a ring that jumps from +180 to
    -180 in Chukotka (65 to 71 degrees north) would close across the whole map at those
    latitudes, and clipped to Europe that edge ran through Norway, Sweden and Finland. Each
    jump of more than half the globe is undone, so the ring runs on past 180 instead.
    """

    out: list[tuple[float, float]] = []
    shift = 0.0
    previous = None
    for lon, lat in ring:
        if previous is not None:
            step = lon + shift - previous
            if step > 180:
                shift -= 360
            elif step < -180:
                shift += 360
        out.append((lon + shift, lat))
        previous = lon + shift
    # A ring that starts in Chukotka would carry the rest of Eurasia a whole turn away: centre
    # the ring on its own middle longitude.
    middle = sorted(lon for lon, _ in out)[len(out) // 2] if out else 0.0
    turn = 360.0 * round(middle / 360.0)
    return [(lon - turn, lat) for lon, lat in out] if turn else out


def build(source: Path) -> dict:
    """Land polygons clipped to ``BBOX`` with a real polygon intersection.

    The ring-by-ring Sutherland-Hodgman clip (``_clip``) is only correct for convex shapes: on a
    concave coastline that leaves the box (the Russian Arctic coast at the east and north
    edges) it joined the pieces with thin "land" bridges along the box edge, drawn as a band
    across the Norwegian and Barents seas. Shapely intersects each polygon with the box instead
    (build time only; nothing here ships with the client): ``pip install shapely``.
    """

    try:
        from shapely.geometry import MultiPolygon, Polygon, box, mapping
        from shapely.validation import make_valid
    except ImportError as exc:  # pragma: no cover - a build-time tool
        raise SystemExit("building the land layer needs shapely: pip install shapely") from exc

    topology = json.loads(source.read_text(encoding="utf-8"))
    arcs = _decode_arcs(topology)
    frame = box(*BBOX)
    pieces: list[Polygon] = []
    for geometry in topology["objects"]["land"]["geometries"]:
        shapes = geometry["arcs"] if geometry["type"] == "MultiPolygon" else [geometry["arcs"]]
        for shape in shapes:
            rings = [_unwrap(_ring(indexes, arcs)) for indexes in shape]
            if not rings or len(rings[0]) < 4:
                continue
            polygon = make_valid(Polygon(rings[0], [ring for ring in rings[1:] if len(ring) >= 4]))
            clipped = polygon.intersection(frame)
            if clipped.is_empty:
                continue
            simplified = clipped.simplify(TOLERANCE, preserve_topology=True)
            for part in getattr(simplified, "geoms", [simplified]):
                if isinstance(part, Polygon) and not part.is_empty and part.area > 0:
                    pieces.append(part)
    land = MultiPolygon(pieces)
    coordinates = [
        [[(round(x, 3), round(y, 3)) for x, y in ring] for ring in polygon]
        for polygon in mapping(land)["coordinates"]
    ]
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"source": "Natural Earth 1:50m land (public domain)"},
                "geometry": {"type": "MultiPolygon", "coordinates": coordinates},
            }
        ],
    }


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(build(Path(argv[1])), separators=(",", ":")) + "\n")
    print(f"wrote {OUTPUT} ({OUTPUT.stat().st_size // 1024} KiB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
