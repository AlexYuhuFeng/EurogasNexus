"""MAP-01: the shipped NWE reference network bundle, its seed and the offline map."""

from __future__ import annotations

import copy
from collections import Counter
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import eurogas_nexus.db.models  # noqa: F401  (registers every table)
from eurogas_nexus.application.map_situation import build_map_situation
from eurogas_nexus.application.pipeline_supply import LANDING_POINTS
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import (
    ReferenceEdge,
    ReferenceMarketHub,
    ReferenceNode,
    ReferenceTsoAccessPoint,
)
from eurogas_nexus.reference_data.network_bundle import (
    BUNDLE_SCHEMA,
    bundle_path,
    load_bundle,
    seed_reference_bundle,
    validate_bundle,
)

NOW = datetime(2026, 11, 14, 12, tzinfo=UTC)


@pytest.fixture(scope="module")
def bundle():
    return load_bundle()


@pytest.fixture
def session():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        yield db


def test_shipped_bundle_passes_its_integrity_checks(bundle):
    assert bundle["schema"] == BUNDLE_SCHEMA
    assert validate_bundle(bundle) == []
    assert bundle_path().stat().st_size < 600_000  # small enough to ship as package data
    assert "transparency.entsog.eu" in bundle["source"]["attribution"]


def test_ids_are_unique_and_edges_join_located_points(bundle):
    ids = Counter(node["id"] for node in bundle["nodes"])
    assert max(ids.values()) == 1
    located = {node["id"] for node in bundle["nodes"] if node["located"]}
    assert bundle["edges"]
    for edge in bundle["edges"]:
        assert edge["from"] in located and edge["to"] in located
        assert edge["schematic"] is True
        assert edge["type"] in {"virtual", "market_area_link", "interconnector"}


def test_no_point_is_verified_and_unlocated_points_carry_no_coordinate(bundle):
    assert all(node["verified"] is False for node in bundle["nodes"])
    unlocated = [node for node in bundle["nodes"] if not node["located"]]
    assert unlocated, "ENTSOG publishes some NWE points without a map position"
    assert all(node["lat"] is None and node["lon"] is None for node in unlocated)
    countries = {node["country"] for node in bundle["nodes"]}
    assert {"NL", "DE", "BE", "FR", "GB"} <= countries
    assert "UK" not in countries  # ISO 3166, not ENTSOG's UK


def test_every_balance_landing_point_is_in_the_bundle(bundle):
    keys = {node["point_key"] for node in bundle["nodes"]}
    assert {point.point_id for point in LANDING_POINTS} <= keys


@pytest.mark.parametrize(
    ("mutate", "problem"),
    [
        (lambda b: b["nodes"].append(copy.deepcopy(b["nodes"][0])), "duplicate node id"),
        (lambda b: b["edges"][0].update({"to": "entsog-nowhere"}), "unknown node"),
        (lambda b: b["edges"][0].update({"schematic": False}), "schematic flag"),
        (lambda b: b["nodes"][0].update({"verified": True}), "verified flag"),
        (
            lambda b: next(n for n in b["nodes"] if not n["located"]).update({"lat": 52.0}),
            "unlocated node carries a coordinate",
        ),
        (lambda b: b["access"][0].update({"point_key": "ITP-99999"}), "unknown point"),
    ],
)
def test_integrity_check_names_each_defect(bundle, mutate, problem):
    broken = copy.deepcopy(bundle)
    mutate(broken)
    assert any(problem in item for item in validate_bundle(broken))


def test_seed_loads_an_empty_store_and_is_idempotent(session, bundle):
    first = seed_reference_bundle(session, bundle=bundle, now=NOW)
    session.commit()
    assert first["status"] == "seeded"
    located = sum(1 for node in bundle["nodes"] if node["located"])
    counts = {
        model: session.query(model).count()
        for model in (ReferenceNode, ReferenceEdge, ReferenceTsoAccessPoint, ReferenceMarketHub)
    }
    assert counts[ReferenceNode] == located
    assert counts[ReferenceEdge] == len(bundle["edges"])
    assert counts[ReferenceTsoAccessPoint] == len(bundle["access"])
    assert counts[ReferenceMarketHub] >= 7
    created = session.get(ReferenceNode, bundle["edges"][0]["from"]).created_at_utc

    again = seed_reference_bundle(session, bundle=bundle, now=datetime(2026, 11, 15, tzinfo=UTC))
    session.commit()
    assert again["status"] == "seeded"
    assert all(again[name]["retired"] == 0 for name in ("nodes", "access", "edges"))
    assert {model: session.query(model).count() for model in counts} == counts
    session.expire_all()
    assert session.get(ReferenceNode, bundle["edges"][0]["from"]).created_at_utc == created
    edge = session.query(ReferenceEdge).first()
    assert edge.metadata_json["schematic"] is True
    assert edge.data_quality == "schematic"


def test_seed_leaves_a_live_entsog_read_alone(session, bundle):
    session.add(
        ReferenceNode(
            id="entsog-itp-00001",
            name="Live point",
            node_type="interconnection",
            country="DE",
            lat=50.0,
            lon=8.0,
            source_system="ENTSOG",
            data_quality="display_approximation",
            metadata_json={"data_status": "live_source_metadata"},
        )
    )
    session.commit()
    outcome = seed_reference_bundle(session, bundle=bundle, now=NOW)
    assert outcome["status"] == "skipped_live_reference_present"
    assert session.query(ReferenceNode).count() == 1


def test_map_reads_the_seeded_bundle_offline_and_counts_unlocated_points(session, bundle):
    seed_reference_bundle(session, bundle=bundle, now=NOW)
    session.commit()
    payload = build_map_situation(
        session, now=NOW, entitled=lambda rows: list(rows), include_positions=False
    )
    unlocated = [node for node in bundle["nodes"] if not node["located"]]
    assert payload["unlocated"]["network_points"] == len(unlocated)
    assert {item["point_key"] for item in payload["unlocated_network_points"]} == {
        node["point_key"] for node in unlocated
    }
    assert all(
        item["reason"] == "no_position_published" for item in payload["unlocated_network_points"]
    )
    located = sum(1 for node in bundle["nodes"] if node["located"])
    assert payload["totals"]["network_points"] == located + len(unlocated)
    dornum = next(i for i in payload["unlocated_network_points"] if i["point_key"] == "ITP-00126")
    assert dornum["operators"]
