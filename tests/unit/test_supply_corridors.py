"""Europe's main import supply corridors: shipped data, its sources, and the read."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import eurogas_nexus.db.models  # noqa: F401  (registers every table)
from eurogas_nexus.application.supply_corridors_read import corridors_read
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import FlowObservationRecord
from eurogas_nexus.reference_data.network_adjacency import MARKET_AREAS
from eurogas_nexus.reference_data.supply_corridors import (
    CORRIDORS,
    classify_status,
    load_corridors,
    validate_corridors,
)

NOW = datetime(2026, 11, 26, 12, tzinfo=UTC)


@pytest.fixture(scope="module")
def data():
    return load_corridors()


@pytest.fixture(scope="module")
def by_id(data):
    return {item["id"]: item for item in data["corridors"]}


def test_the_shipped_corridors_pass_their_checks(data):
    assert validate_corridors(data) == []
    assert "transparency.entsog.eu" in data["source"]["attribution"]
    assert data["geometry_source"]["licence"] == "CC-BY-4.0"
    assert [item["id"] for item in data["corridors"]] == [c.id for c in CORRIDORS]


def test_the_owners_corridors_are_all_there(by_id):
    assert {
        "langeled", "europipe-1", "europipe-2", "norpipe", "zeepipe", "franpipe", "vesterled",
        "baltic-pipe-north-sea", "medgaz", "transmed", "greenstream", "maghreb-europe", "tap",
        "turkstream", "nord-stream-1", "nord-stream-2", "ukraine-transit", "yamal",
    } == set(by_id)


def test_a_shared_entry_point_is_marked_so_its_flow_is_not_the_corridors(data, by_id):
    # Langeled lands at Easington and Vesterled at St Fergus; both points also carry UK shelf
    # gas, so the point's whole flow must not be presented as the corridor's.
    marked = {corridor.id for corridor in CORRIDORS if corridor.shared_entry_point}
    assert marked == {"langeled", "vesterled"}
    for corridor in CORRIDORS:
        if not corridor.shared_entry_point:
            continue
        assert corridor.notes and "also receives" in corridor.notes, corridor.id
    for cid, item in by_id.items():
        assert item.get("shared_entry_point", False) == (cid in marked), cid


@pytest.mark.parametrize(
    ("corridor", "point"),
    [
        ("langeled", "ITP-00091"),  # Easington
        ("vesterled", "ITP-00022"),  # St Fergus
        ("europipe-2", "ITP-00208"),  # Dornum
        ("zeepipe", "ITP-00106"),  # Zeebrugge ZPT
        ("franpipe", "ITP-00045"),  # Dunkerque
        ("medgaz", "ITP-00048"),  # Almería
        ("transmed", "ITP-00093"),  # Mazara del Vallo
        ("greenstream", "ITP-00074"),  # Gela
        ("maghreb-europe", "ITP-00082"),  # Tarifa
        ("tap", "ITP-00008"),  # Melendugno
        ("tap", "ITP-00274"),  # Kipoi
        ("turkstream", "ITP-00549"),  # Strandzha 2
        ("nord-stream-1", "ITP-00120"),  # Greifswald
        ("nord-stream-2", "ITP-00501"),  # Lubmin II
        ("ukraine-transit", "ITP-00117"),  # Velké Kapušany
        ("ukraine-transit", "ITP-00184"),  # Sudzha
        ("yamal", "ITP-00096"),  # Mallnow
    ],
)
def test_each_corridor_lands_at_its_entsog_point(by_id, corridor, point):
    landing = {item["point_key"]: item for item in by_id[corridor]["landing_points"]}
    assert point in landing
    assert landing[point]["name"]  # ENTSOG's label, read from connectionpoints


def test_every_corridor_names_its_flow_series_and_where_the_gas_enters(data):
    codes = {area.code for area in MARKET_AREAS}
    for item in data["corridors"]:
        assert item["flow_series"], item["id"]
        for series in item["flow_series"]:
            assert series["point_key"].startswith("ITP-")
            assert "-TSO-" in series["operator_key"]
            assert series["direction"] == "entry" and series["indicator"] == "Physical Flow"
            assert series["node_id"] == f"entsog-{series['point_key'].lower()}"
        assert set(item["into_market_areas"]) <= codes, item["id"]
        assert item["into_market_areas"], item["id"]


def test_statuses_are_entsogs_with_their_dates(by_id):
    for item in by_id.values():
        assert "operationaldatas, Physical Flow" in item["status_source"]["citation"]
        assert item["status_source"]["window"]
    # As ENTSOG published them when the file was built (gas day 2026-11-25).
    for corridor in ("langeled", "europipe-2", "zeepipe", "franpipe", "medgaz", "transmed",
                     "tap", "turkstream"):
        assert by_id[corridor]["status"] == "in_service", corridor
    out = {
        "nord-stream-1": "2022-09-01",
        "ukraine-transit": "2025-01-01",
        "yamal": "2022-05-03",
        "maghreb-europe": "2021-11-01",
    }
    for corridor, since in out.items():
        assert by_id[corridor]["status"] == "out_of_service", corridor
        assert by_id[corridor]["since"] == since, corridor
        assert by_id[corridor]["since_basis"] == "last_flow_day"
    # Nord Stream 2 carried no flow in the window ENTSOG was read for: a bound, said so.
    assert by_id["nord-stream-2"]["status"] == "out_of_service"
    assert by_id["nord-stream-2"]["since_basis"] == "no_flow_in_window"
    # ENTSOG publishes no flow figure at Emden (NPT): unknown, never read as zero.
    assert by_id["norpipe"]["status"] == "not_published"


def test_an_out_of_service_corridor_is_never_shown_as_carrying_gas(by_id):
    for item in by_id.values():
        if item["status"] != "in_service":
            assert all(series["flow_days_last_30"] == 0 for series in item["flow_series"])


def test_capacity_and_pipeline_facts_carry_their_source(data):
    for item in data["corridors"]:
        capacity = item["capacity"]
        if capacity["firm_technical_kwh_d"] is not None:
            assert "Firm Technical" in capacity["citation"] and capacity["gas_day"]
        facts = item["facts"]
        if facts:
            assert facts["source"].startswith("Gassco") and facts["read"]


def test_geometry_is_scigrid_or_a_marked_schematic_line(data):
    for item in data["corridors"]:
        geometry = item["geometry"]
        coords = geometry["coordinates"]
        assert coords and len(coords) >= 2, item["id"]
        landing = [p for p in item["landing_points"] if p["lon"] is not None][-1]
        assert abs(coords[-1][0] - landing["lon"]) < 1e-3
        assert abs(coords[-1][1] - landing["lat"]) < 1e-3
        if geometry["basis"] == "schematic":
            assert len(coords) == 2 and "not where the pipe runs" in geometry["note"]
        else:
            assert geometry["licence"] == "CC-BY-4.0" and "SciGRID" in geometry["source"]
        source = item["source"]
        assert source["position_quality"] in {
            "scigrid_node", "approximate_place", "display_approximation",
        }


@pytest.mark.parametrize(
    ("args", "expected"),
    [
        ((3, "2026-11-25"), ("in_service", None)),
        ((0, "2022-08-31"), ("out_of_service", "2022-09-01")),
        ((0, None), ("out_of_service", "2021-09-01")),
    ],
)
def test_the_status_rule(args, expected):
    status = classify_status(*args, probe_from="2021-09-01", recent_from="2026-10-27")
    assert (status["status"], status["since"]) == expected


def test_no_published_flow_is_unknown_not_zero():
    status = classify_status(
        0, None, probe_from=None, recent_from="2026-10-27", recent_published_days=0
    )
    assert status["status"] == "not_published" and status["since"] is None


def _flow(point: str, operator: str, value_kwh: float, day: int) -> FlowObservationRecord:
    start = datetime(2026, 11, day, 5, tzinfo=UTC)
    end = datetime(2026, 11, day + 1, 5, tzinfo=UTC)
    return FlowObservationRecord(
        observation_id=f"f-{point}-{operator}-{day}", point_id=point, point_name=point,
        direction="entry", kind="actual", original_value=value_kwh, original_unit="kWh/d",
        flow_mcm_d=None, period_start_utc=start, period_end_utc=end, observed_at_utc=end,
        source_system="ENTSOG", source_reference="entsog-operationaldatas",
        source_record_id=f"r-{day}", freshness="live", research_only=True,
        normalizer_version="entsog-native-units-v1",
        native_rate_json={"energy_kwh_per_day": value_kwh},
        metadata_json={"operatorKey": operator, "pointKey": point},
    )


def test_the_read_adds_the_latest_stored_flow_per_entry_series():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add_all(
            [
                _flow("ITP-00091", "UK-TSO-0001", 700_000_000.0, 24),
                _flow("ITP-00091", "UK-TSO-0001", 800_000_000.0, 25),
                # Another operator's copy of the point is not the corridor's series.
                _flow("ITP-00091", "NO-TSO-0001", 999_000_000.0, 25),
            ]
        )
        session.commit()
        data = corridors_read(session, now=NOW)
    langeled = next(item for item in data["corridors"] if item["id"] == "langeled")
    assert langeled["latest_flow_gwh_d"] == 800.0
    assert langeled["flow_series"][0]["latest_flow"]["gas_day_start_utc"].startswith(
        "2026-11-25"
    )
    zeepipe = next(item for item in data["corridors"] if item["id"] == "zeepipe")
    assert zeepipe["latest_flow_gwh_d"] is None  # missing, never zero
    assert zeepipe["status"] == "in_service"


def test_the_route_serves_the_corridors_without_a_store(monkeypatch):
    from eurogas_nexus.api.app import create_app

    monkeypatch.delenv("RUNTIME_STORE_DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    client = TestClient(create_app())
    response = client.get("/api/reference-network/supply-corridors")
    assert response.status_code == 200
    body = response.json()
    assert len(body["data"]["corridors"]) == len(CORRIDORS)
    assert "transparency.entsog.eu" in body["meta"]["attribution"]
    assert all(
        series["latest_flow"] is None
        for item in body["data"]["corridors"]
        for series in item["flow_series"]
    )
