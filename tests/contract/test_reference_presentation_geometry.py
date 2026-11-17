"""Open reference pipeline geometry is drawn, never priced.

SciGRID_gas IGGIELGN (CC BY 4.0) gives the map the general direction pipes run: a faint
context layer of trunk lines and, for a drawn connection leg, a ``presentation_path`` along
them. Route pricing walks the ENTSOG market-area adjacency only. These checks hold that line:
the provenance and licence travel with the geometry, the pricing graph is identical with or
without it, no pricing or application module reads it, and the drawn lines stay schematic.
"""

from __future__ import annotations

import copy
import json
from datetime import UTC, datetime
from pathlib import Path

from eurogas_nexus.domain.route_cost.market_area_graph import MarketAreaGraph
from eurogas_nexus.reference_data.network_bundle import (
    load_bundle,
    reference_rows,
    validate_bundle,
)
from eurogas_nexus.reference_data.reference_geometry import (
    BBOX,
    PipeGraph,
    presentation_path,
    simplify,
)

ROOT = Path(__file__).resolve().parents[2]
CONTEXT = ROOT / "clients/web/public/map/context-pipelines.geojson"


def _graph_facts(graph: MarketAreaGraph) -> tuple:
    hubs = sorted(graph.hub_codes)
    return (
        sorted(graph.hub_codes.items()),
        sorted((key, json.dumps(value, sort_keys=True)) for key, value in graph.points.items()),
        [
            (a, b, json.dumps(graph.hub_paths(a, b), sort_keys=True, default=str))
            for a in hubs
            for b in hubs
            if a != b
        ],
    )


def test_the_shipped_geometry_carries_its_source_and_licence() -> None:
    bundle = load_bundle()
    assert validate_bundle(bundle) == []
    provenance = bundle["presentation_geometry"]
    assert provenance["name"] == "SciGRID_gas IGGIELGN"
    assert provenance["licence"] == "CC-BY-4.0"
    assert provenance["doi"] == "10.5281/zenodo.4767098"
    assert len(provenance["sha256"]) == 64
    assert "never priced" in provenance["use"]
    routed = [edge for edge in bundle["edges"] if edge.get("presentation_path")]
    assert routed and provenance["routed_edges"] == len(routed)
    assert all(edge["type"] != "virtual" and edge["schematic"] is True for edge in routed)


def test_the_context_layer_is_small_attributed_and_regional() -> None:
    raw = CONTEXT.read_bytes()
    assert len(raw) < 600_000
    layer = json.loads(raw)
    assert layer["properties"]["licence"] == "CC-BY-4.0"
    assert "SciGRID_gas" in layer["properties"]["attribution"]
    assert layer["features"]
    for feature in layer["features"]:
        assert feature["geometry"]["type"] == "LineString"
        ends = feature["geometry"]["coordinates"][0], feature["geometry"]["coordinates"][-1]
        assert any(BBOX[0] <= lon <= BBOX[2] and BBOX[1] <= lat <= BBOX[3] for lon, lat in ends)
        # Geometry only: nothing a reader could take for a capacity, flow or tariff.
        assert set(feature["properties"]) == {"id", "diameter_mm"}


def test_route_pricing_is_the_same_with_or_without_the_geometry() -> None:
    bundle = load_bundle()
    stripped = copy.deepcopy(bundle)
    stripped.pop("presentation_geometry", None)
    for edge in stripped["edges"]:
        edge.pop("presentation_path", None)
    assert _graph_facts(MarketAreaGraph.from_bundle(bundle)) == _graph_facts(
        MarketAreaGraph.from_bundle(stripped)
    )


def test_no_pricing_or_application_module_reads_the_geometry() -> None:
    src = ROOT / "src/eurogas_nexus"
    readers = [
        path.relative_to(ROOT).as_posix()
        for folder in ("domain", "application", "api", "db", "ingestion")
        for path in (src / folder).rglob("*.py")
        if "reference_geometry" in path.read_text(encoding="utf-8")
        or "presentation_path" in path.read_text(encoding="utf-8")
    ]
    assert readers == []


def test_a_drawn_leg_along_the_trunk_lines_stays_schematic() -> None:
    bundle = load_bundle()
    rows = {
        row["id"]: row
        for row in reference_rows(bundle, now=datetime(2026, 11, 17, tzinfo=UTC))["edges"]
    }
    for edge in bundle["edges"]:
        row = rows[edge["id"]]
        if edge.get("presentation_path"):
            meta = row["metadata_json"]
            assert meta["geometry_basis"] == "reference_pipeline_direction"
            assert meta["verification_status"] == "schematic"
            assert meta["presentation_licence"] == "CC-BY-4.0"
            assert row["data_quality"] == "schematic"
            assert meta["presentation_path"] == edge["presentation_path"]
        else:
            assert "presentation_path" not in row["metadata_json"]


def test_a_path_is_kept_only_close_to_both_ends_and_without_a_long_detour() -> None:
    # A trunk line from (0, 50) to (2, 50) through (1, 50.2).
    graph = PipeGraph(
        [
            {"id": "a", "coordinates": [(0.0, 50.0), (1.0, 50.2)]},
            {"id": "b", "coordinates": [(1.0, 50.2), (2.0, 50.0)]},
        ]
    )
    path = presentation_path(graph, (0.0, 50.01), (2.0, 50.01))
    assert path is not None
    assert path[0] == [0.0, 50.01] and path[-1] == [2.0, 50.01]
    assert [1.0, 50.2] in path
    # An end far from any trunk line keeps the straight connection.
    assert presentation_path(graph, (0.0, 52.0), (2.0, 50.01)) is None
    # Douglas-Peucker drops a point within the tolerance.
    assert simplify([(0.0, 0.0), (0.5, 0.001), (1.0, 0.0)]) == [(0.0, 0.0), (1.0, 0.0)]
