"""The reference network's topology: every European market area joined to its neighbours.

The owner's complaint (2026-11-26): many markets on Desk -> Network had no connections. The
bundle covered north-west Europe only; Austria, Italy, Spain, Poland, Czechia, the Balkans,
the Baltics and Ukraine had no node, so ENTSOG's interconnection points to them resolved to
"outside" and nothing was drawn. These tests hold the all-Europe topology to its sources.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import eurogas_nexus.db.models  # noqa: F401  (registers every table)
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import ReferenceNode
from eurogas_nexus.domain.route_cost.market_area_graph import MarketAreaGraph
from eurogas_nexus.reference_data.network_adjacency import (
    BZ_HUB,
    EXTERNAL_OPERATOR_ZONES,
    MARKET_AREAS,
    REPLACED_ZONES,
    canonical_zone,
    derive_adjacency,
    two_point_systems,
)
from eurogas_nexus.reference_data.network_bundle import load_bundle, seed_reference_bundle

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures/entsog/topology_sample_2026-11-26.json"
NOW = datetime(2026, 11, 26, 12, tzinfo=UTC)


@pytest.fixture(scope="module")
def bundle():
    return load_bundle()


@pytest.fixture(scope="module")
def graph(bundle):
    return MarketAreaGraph.from_bundle(bundle)


@pytest.fixture(scope="module")
def sample():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _code(graph: MarketAreaGraph, code: str) -> str:
    key = graph.hub_for(code)
    assert key, f"{code} is not a market area of the bundle"
    return key


# -- every supported market area is on the network ------------------------------------------


@pytest.mark.parametrize("area", MARKET_AREAS, ids=lambda area: area.code)
def test_every_market_area_has_a_located_node(bundle, area):
    nodes = {node["point_key"]: node for node in bundle["nodes"]}
    node = nodes.get(area.point_key)
    assert node is not None, f"{area.code}: no node {area.point_key}"
    assert node["type"] == "hub"
    assert node["located"], f"{area.code}: no position to draw from"
    assert node["hub_code"] == area.code
    assert node["balancing_zone_key"] == area.bz_key


@pytest.mark.parametrize("area", MARKET_AREAS, ids=lambda area: area.code)
def test_every_market_area_is_joined_to_at_least_one_neighbour(graph, area):
    assert graph.neighbours(area.point_key), f"{area.code} has no edge to any neighbour"


def test_the_market_area_list_covers_europe():
    codes = {area.code for area in MARKET_AREAS}
    assert {
        "TTF", "THE", "NBP", "PEG", "ZTP", "PSV", "CEGH", "PVB", "OTE", "PL-VTP", "MGP", "SK",
        "SI", "HR", "RO", "BG", "HTP", "GTF", "EE-LV", "LT", "FI", "IBP", "CH", "PT", "UA",
    } <= codes
    assert len(codes) == len(MARKET_AREAS)
    assert len({area.bz_key for area in MARKET_AREAS}) == len(MARKET_AREAS)
    # A replaced zone is never a market area of its own, and every replacement ends in one.
    assert not set(REPLACED_ZONES) & set(BZ_HUB)
    assert all(canonical_zone(key) in BZ_HUB for key in REPLACED_ZONES)
    assert set(EXTERNAL_OPERATOR_ZONES.values()) <= set(BZ_HUB)


@pytest.mark.parametrize(
    ("a", "b", "point"),
    [
        ("THE", "CEGH", None),  # Oberkappel, Überackern ...
        ("CEGH", "PSV", "ITP-00040"),  # Tarvisio / Arnoldstein
        ("CEGH", "SK", "ITP-00168"),  # Baumgarten
        ("CEGH", "MGP", "ITP-00043"),  # Mosonmagyaróvár
        ("CEGH", "SI", "ITP-00079"),  # Murfeld / Ceršak
        ("CH", "PSV", "ITP-00136"),  # Passo Gries
        ("CH", "THE", None),
        ("CH", "PEG", None),
        ("PEG", "PVB", "ITP-00304"),  # VIP Pirineos
        ("PVB", "PT", "ITP-00286"),  # VIP Ibérico
        ("THE", "OTE", None),
        ("OTE", "SK", "ITP-00051"),  # Lanžhot
        ("THE", "PL-VTP", "ITP-00497"),
        ("THE", "TGPS", "ITP-00096"),  # Mallnow
        ("GTF", "PL-VTP", "ITP-10009"),  # Baltic Pipe
        ("PL-VTP", "LT", "ITP-00556"),  # GIPL
        ("LT", "EE-LV", "ITP-00054"),  # Kiemenai
        ("EE-LV", "FI", "ITP-00550"),  # Balticconnector
        ("SK", "UA", None),  # Velké Kapušany, Budince
        ("MGP", "UA", "ITP-10006"),  # VIP Bereg
        ("PL-VTP", "UA", "ITP-10008"),  # Hermanowice
        ("MGP", "HR", "ITP-00011"),  # Drávaszerdahely
        ("MGP", "RO", "ITP-00032"),  # Csanádpalota
        ("MGP", "RS", "ITP-00055"),  # Kiskundorozsma
        ("RO", "BG", None),  # Ruse / Giurgiu
        ("BG", "HTP", None),  # Kulata / Sidirokastro, IGB
        ("BG", "TR", "ITP-00041"),  # Strandzha / Malkoclar
        ("HTP", "TR", "ITP-00046"),  # Kipi
        ("RO", "MD", "ITP-00154"),  # Ungheni
        ("TTF", "ZTP-L", None),  # the Belgian L-gas zone
        ("NBP", "IBP", "ITP-00090"),  # Moffat
        ("NBP", "TTF", None),  # BBL
        ("NBP", "ZTP", None),  # IUK
    ],
)
def test_physical_neighbours_are_joined_at_entsog_points(graph, a, b, point):
    crossings = graph.crossings(_code(graph, a), _code(graph, b))
    assert crossings, f"{a} and {b} are neighbours on ENTSOG and must be joined"
    if point:
        assert any(point in crossing.points for crossing in crossings)


@pytest.mark.parametrize(
    ("a", "b"),
    [("TTF", "PSV"), ("NBP", "PEG"), ("THE", "MGP"), ("PVB", "PSV"), ("CEGH", "PL-VTP")],
)
def test_market_areas_that_share_no_border_are_not_joined_directly(graph, a, b):
    assert graph.crossings(_code(graph, a), _code(graph, b)) == []


# -- every edge names known places and its source -------------------------------------------


def test_every_adjacency_edge_references_known_market_areas_and_nodes(bundle):
    node_ids = {node["id"] for node in bundle["nodes"]}
    area_keys = set(BZ_HUB.values())
    pipelines = {
        f"pipeline:{item['operator_key']}"
        for item in bundle["adjacency"]["pipelines"]
        if item["in_network"]
    }
    adjacency = [e for e in bundle["edges"] if e["type"] in {"market_area_link", "interconnector"}]
    assert adjacency
    for edge in adjacency:
        assert edge["from"] in node_ids and edge["to"] in node_ids, edge["id"]
        if edge["type"] == "market_area_link":
            assert edge["hub_point_key"] in area_keys, edge["id"]
            assert set(edge["joins"]) <= area_keys | pipelines, edge["id"]
            assert edge["to"] == f"entsog-{edge['hub_point_key'].lower()}"


def test_every_zone_link_points_at_a_market_area(bundle):
    by_id = {node["id"]: node for node in bundle["nodes"]}
    for edge in bundle["edges"]:
        if edge["type"] == "virtual":
            assert by_id[edge["to"]]["type"] == "hub", edge["id"]


def test_every_interconnection_edge_carries_its_entsog_source(bundle):
    adjacency = bundle["adjacency"]
    assert "transparency.entsog.eu" in adjacency["attribution"]
    assert adjacency["downloaded"]
    for edge in bundle["edges"]:
        if edge["type"] not in {"market_area_link", "interconnector"}:
            continue
        assert edge.get("basis") in {"entsog_interconnection", "entsog_two_point_system"}
        assert edge.get("downloaded"), edge["id"]
        if edge["type"] == "market_area_link":
            assert edge["point_key"].startswith(("ITP-", "LNG-", "UGS-")), edge["id"]
            assert edge["evidence"] and all(edge["evidence"]), edge["id"]
            assert edge["side_basis"] in {"entsog_balancing_zone", "entsog_operator_country"}
            assert set(edge["hub_directions"]) <= {"entry", "exit"}
        else:
            assert len(edge["point_keys"]) == 2 and edge["operator_key"], edge["id"]


def test_a_side_named_by_operator_country_is_only_a_listed_non_eu_grid(bundle):
    external = {BZ_HUB[zone] for zone in EXTERNAL_OPERATOR_ZONES.values()}
    for edge in bundle["edges"]:
        if edge.get("side_basis") == "entsog_operator_country":
            assert edge["hub_point_key"] in external, edge["id"]


# -- positions -------------------------------------------------------------------------------


def test_zone_nodes_sit_at_entsogs_balancing_zone_position(bundle):
    zone_nodes = [node for node in bundle["nodes"] if node.get("zone_only")]
    assert {node["point_key"] for node in zone_nodes} == {
        area.zone_point_key for area in MARKET_AREAS if not area.hub_point_key
    }
    for node in zone_nodes:
        assert node["source_dataset"] == "balancingzones"
        assert node["entsog_map_x"] or node["entsog_map_y"]
        assert node["coordinate_quality"] == "display_approximation"
        assert node["verified"] is False


def test_no_point_is_placed_at_entsogs_unplaced_position(bundle):
    # ENTSOG writes 0/0 for a point it has not placed; transformed, that is 52.71 N 15.04 E,
    # where the first bundle put Rough, Holford and Stublach storage.
    for node in bundle["nodes"]:
        assert not (node["entsog_map_x"] == 0 and node["entsog_map_y"] == 0 and node["located"])


# -- the rule on recorded ENTSOG rows --------------------------------------------------------


def _nodes_for(sample) -> list[dict]:
    keys = {row["pointKey"] for row in sample["interconnections"]}
    return [
        {"point_key": key, "id": f"entsog-{key.lower()}", "type": "interconnection",
         "located": True, "name": key}
        for key in sorted(keys)
    ] + [
        {"point_key": area.point_key, "id": f"entsog-{area.point_key.lower()}", "type": "hub",
         "located": True, "name": area.code}
        for area in MARKET_AREAS
    ]


def _joins(result) -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for edge in result["edges"]:
        if edge["type"] == "market_area_link":
            out.setdefault(edge["point_key"], set()).add(edge["hub_point_key"])
    return out


def test_a_blank_non_eu_side_resolves_to_its_operators_zone(sample):
    result = derive_adjacency(
        sample["interconnections"], _nodes_for(sample),
        connection_points=sample["connectionpoints"], downloaded="2026-11-26",
    )
    joins = _joins(result)
    assert joins["ITP-00117"] == {"BZ-SK", "BZ-UA"}  # Velké Kapušany
    assert joins["ITP-00154"] == {"BZ-RO", "BZ-MD"}  # Ungheni (Vestmoldtransgaz, MD)
    ua = [e for e in result["edges"] if e["id"] == "adj-itp-00117-bz-ua"]
    assert ua and ua[0]["side_basis"] == "entsog_operator_country"
    sk = [e for e in result["edges"] if e["id"] == "adj-itp-00117-bz-sk"]
    assert sk[0]["side_basis"] == "entsog_balancing_zone"


def test_a_national_grid_at_two_borders_is_not_a_pipeline(sample):
    # Botas runs Turkey's grid; ENTSOG lists it at Strandzha and Kipi only. That is not a
    # pipeline from Bulgaria to Greece: each point joins its EU zone to Turkey.
    rows = sample["interconnections"]
    assert ("Transmission", "TR-TSO-0001") not in two_point_systems(rows)
    assert ("IUK", "UK-TSO-0003") in two_point_systems(rows)
    joins = _joins(
        derive_adjacency(rows, _nodes_for(sample), connection_points=[], downloaded="2026-11-26")
    )
    assert joins["ITP-00041"] == {"BZ-BG", "BZ-TR"}
    assert joins["ITP-00046"] == {"VTP-00042", "BZ-TR"}


def test_a_zone_without_a_trading_point_is_joined_through_its_zone_node(sample):
    joins = _joins(
        derive_adjacency(
            sample["interconnections"], _nodes_for(sample),
            connection_points=sample["connectionpoints"], downloaded="2026-11-26",
        )
    )
    assert joins["ITP-00136"] == {"BZ-CH", "VTP-00013"}  # Passo Gries: CH - PSV
    assert joins["ITP-00168"] == {"VTP-00014", "BZ-SK"}  # Baumgarten: CEGH - SK
    assert joins["ITP-00059"] == {"BZ-RO-DTS", "BZ-BG"}  # Negru Voda: transit - BG


def test_a_row_filed_under_a_replaced_zone_reads_as_its_successor(sample):
    # Synthetic: a row as ENTSOG filed it before the THE merger (GASPOOL), on a real point.
    row = dict(next(r for r in sample["interconnections"] if r["pointKey"] == "ITP-00544"))
    side = "from" if row["fromBzKey"] == "DE-THE-----" else "to"
    row[f"{side}BzKey"] = "DE-GASPOOL-"
    joins = _joins(
        derive_adjacency([row], _nodes_for(sample), connection_points=[], downloaded="2026-11-26")
    )
    assert joins["ITP-00544"] == {"VTP-00045", "BZ-CH"}


def test_every_active_entsog_zone_is_a_market_area_or_left_out_with_a_reason(sample):
    active = {
        row["bzKey"]
        for row in sample["balancingzones"]
        if not row.get("replacedBy") and str(row.get("isDeactivated") or "0") == "0"
    }
    # The Interconnector's zone is its pipeline; Poland's L-gas zone has no interconnection.
    assert active - set(BZ_HUB) == {"UK-IUK-----", "PL-L-gas---"}
    replaced = {
        row["bzKey"]: row["replacedBy"] for row in sample["balancingzones"] if row.get("replacedBy")
    }
    assert replaced == REPLACED_ZONES


# -- the read: a live store draws the zones too ----------------------------------------------


def test_a_live_store_serves_the_zone_nodes_and_their_edges(bundle):
    from eurogas_nexus.db.repositories.reference_network import (
        SqlAlchemyEdgeRepository,
        SqlAlchemyNodeRepository,
    )

    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        seed_reference_bundle(session, bundle=bundle, now=NOW)
        session.commit()
        # As a live ENTSOG read leaves the store: connection points only, no zone nodes.
        session.query(ReferenceNode).filter(ReferenceNode.id.like("entsog-bz-%")).delete(
            synchronize_session=False
        )
        for node in session.query(ReferenceNode).all():
            node.metadata_json = {
                **(node.metadata_json or {}),
                "data_status": "live_source_metadata",
            }
        session.commit()
        nodes = {node.id: node for node in SqlAlchemyNodeRepository(session).list_all()}
        assert "entsog-bz-sk" in nodes and nodes["entsog-bz-sk"].node_type == "hub"
        assert nodes["entsog-bz-sk"].metadata_json["zone_only"] is True
        assert SqlAlchemyNodeRepository(session).get_by_id("entsog-bz-ch") is not None
        assert [n.id for n in SqlAlchemyNodeRepository(session).list_all(country="SK")].count(
            "entsog-bz-sk"
        ) == 1
        edges = SqlAlchemyEdgeRepository(session).list_all()
        assert any(
            edge.to_node_id == "entsog-bz-sk" and edge.edge_type == "market_area_link"
            for edge in edges
        )


def test_an_empty_store_serves_no_zone_nodes():
    from eurogas_nexus.db.repositories.reference_network import SqlAlchemyNodeRepository

    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        assert SqlAlchemyNodeRepository(session).list_all() == []


# -- obsolete and misplaced trading points ---------------------------------------------------


def test_retired_trading_points_are_neither_read_nor_served():
    from eurogas_nexus.db.repositories.reference_network import SqlAlchemyNodeRepository
    from eurogas_nexus.ingestion.public_sources import (
        entsog_reference_nodes_from_connectionpoints,
    )
    from eurogas_nexus.reference_data.network_adjacency import RETIRED_TRADING_POINTS

    assert set(RETIRED_TRADING_POINTS) == {"VTP-00009", "VTP-00010"}  # PEG SUD, PEG TIGF
    assert all(successor == "VTP-00039" for successor, _, _ in RETIRED_TRADING_POINTS.values())
    # ENTSOG still publishes PEG SUD (with a real map position here, to test the retirement
    # rather than the 0/0 rule).
    payload = {
        "connectionpoints": [
            {"pointKey": "VTP-00009", "pointLabel": "PEG SUD", "tpMapX": -60, "tpMapY": -50,
             "pointType": "Trading Point"},
            {"pointKey": "VTP-00003", "pointLabel": "OTE", "tpMapX": -8.09, "tpMapY": -21.7,
             "pointType": "Trading Point"},
            {"pointKey": "VTP-00028", "pointLabel": "VTP - GAZ-SYSTEM", "tpMapX": 19.47,
             "tpMapY": -10.53, "pointType": "Trading Point"},
            {"pointKey": "UGS-00235", "pointLabel": "Rough", "tpMapX": 0, "tpMapY": 0,
             "pointType": "Storage"},
        ]
    }
    rows = {
        row["source_record_id"]: row
        for row in entsog_reference_nodes_from_connectionpoints(payload)
    }
    assert "VTP-00009" not in rows  # retired zone
    assert "UGS-00235" not in rows  # ENTSOG has not placed it
    assert rows["VTP-00003"]["country"] == "CZ"
    assert rows["VTP-00028"]["country"] == "PL"

    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        # A store read before the fix: PEG SUD placed in Poland, OTE with country EU.
        for key, name, lat, lon in (
            ("VTP-00009", "PEG SUD", 52.71, 15.04),
            ("VTP-00003", "OTE", 50.1, 13.58),
        ):
            session.add(
                ReferenceNode(
                    id=f"entsog-{key.lower()}", name=name, node_type="hub", country="EU",
                    lat=lat, lon=lon, source_system="ENTSOG", source_record_id=key,
                    data_quality="display_approximation",
                    metadata_json={"data_status": "live_source_metadata", "point_key": key},
                )
            )
        session.commit()
        repository = SqlAlchemyNodeRepository(session)
        served = {node.id: node for node in repository.list_all()}
        assert "entsog-vtp-00009" not in served
        assert repository.get_by_id("entsog-vtp-00009") is None
        assert served["entsog-vtp-00003"].country == "CZ"


def test_every_trading_point_in_the_bundle_has_its_zones_country(bundle):
    from eurogas_nexus.reference_data.network_adjacency import trading_point_country

    for node in bundle["nodes"]:
        if node["type"] == "hub" and node["point_key"].startswith("VTP-"):
            assert node["country"] == trading_point_country(node["point_key"]), node["point_key"]
    keys = {node["point_key"] for node in bundle["nodes"]}
    assert not keys & {"VTP-00009", "VTP-00010"}
