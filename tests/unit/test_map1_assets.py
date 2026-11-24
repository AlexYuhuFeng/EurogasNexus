"""MAP-1: the map's terminals, storage sites, stored flow window and cargo ETA basis.

Every figure on a site is one a publisher stated, with its source and gas day; a GIE figure
read by country is said to be the country's, never the site's; nothing is estimated here.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import eurogas_nexus.db.models  # noqa: F401  (registers every table)
from eurogas_nexus.application.map_situation import build_map_situation
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import (
    CapacityObservationRecord,
    FlowObservationRecord,
    LngCargoRecord,
    LngObservationRecord,
    ReferenceNode,
    StorageObservationRecord,
)

DAY = datetime(2026, 11, 8, 5, tzinfo=UTC)  # gas day 8 November
NOW = datetime(2026, 11, 12, 11, 56, tzinfo=UTC)  # gas day 12 November is open


def _node(node_id, name, node_type, country, lon, lat, eic=None):
    return ReferenceNode(
        id=node_id, name=name, node_type=node_type, country=country, lat=lat, lon=lon,
        source_system="ENTSOG", source_record_id=node_id.removeprefix("entsog-").upper(),
        data_quality="display_approximation",
        metadata_json={"point_eic_code": eic} if eic else {},
    )


def _flow(db, key, point, direction, kwh, day):
    db.add(
        FlowObservationRecord(
            observation_id=key, point_id=point, point_name=point, direction=direction,
            kind="actual", flow_mcm_d=None, original_value=kwh, original_unit="kWh/d",
            period_start_utc=day, period_end_utc=day + timedelta(days=1),
            observed_at_utc=day + timedelta(days=1, hours=4), source_system="ENTSOG",
            source_reference="t", freshness="daily", research_only=True,
            metadata_json={"operatorKey": "NL-TSO-0001"},
            normalizer_version="entsog-native-units-v1",
            native_rate_json={"value": str(kwh), "unit": "kWh/d"},
        )
    )


def _capacity(db, key, point, direction, kwh, day, source="ENTSOG"):
    db.add(
        CapacityObservationRecord(
            observation_id=key, point_id=point, point_name=point, direction=direction,
            capacity_type="firm_technical", capacity_mcm_d=None, original_value=kwh,
            original_unit="kWh/d", period_start_utc=day, period_end_utc=day + timedelta(days=1),
            observed_at_utc=day - timedelta(days=1), source_system=source, source_reference="t",
            freshness="daily", research_only=True, metadata_json={"operatorKey": "NL-TSO-0001"},
            normalizer_version="entsog-native-units-v1",
            native_rate_json={"value": str(kwh), "unit": "kWh/d"},
        )
    )


@pytest.fixture
def session():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(_node("entsog-lng-00027", "Gate Terminal (I)", "lng", "NL", 4.03, 51.95,
                     eic="21Z0000000002212"))
        db.add(_node("entsog-ugs-00149", "Bergermeer", "storage", "NL", 4.7, 52.6,
                     eic="21Z0000000001127"))
        db.add(_node("entsog-ugs-00002", "Loenhout Storage", "storage", "BE", 4.6, 51.4))
        db.add(_node("entsog-itp-00005", "Bacton (IUK)", "interconnection", "GB", 1.46, 52.85))
        for offset in range(4):  # closed days 8 to 11 November
            day = DAY + timedelta(days=offset)
            _flow(db, f"g{offset}", "LNG-00027", "entry", (300 + offset * 10) * 1e6, day)
            _flow(db, f"b{offset}", "ITP-00005", "exit", 40e6, day)
        # Capacity: an older and the current gas day, and one ENTSOG publishes days ahead.
        _capacity(db, "c-old", "LNG-00027", "entry", 400e6, DAY - timedelta(days=5))
        _capacity(db, "c-now", "LNG-00027", "entry", 450e6, DAY + timedelta(days=4))
        _capacity(db, "c-ahead", "LNG-00027", "entry", 999e6, DAY + timedelta(days=9))
        _capacity(db, "c-ugs", "UGS-00149", "exit", 200e6, DAY + timedelta(days=4))
        _capacity(db, "c-licensed", "UGS-00002", "entry", 77e6, DAY + timedelta(days=4),
                  source="LICENSED_FEED")
        db.add(
            StorageObservationRecord(
                observation_id="agsi-nl", source_dataset="AGSI", facility_id="NL",
                facility_name="Netherlands", country="NL", inventory_twh=110.0,
                working_capacity_twh=140.0, fill_pct=78.5, injection_twh_d=0.1,
                withdrawal_twh_d=0.4, period_start_utc=DAY + timedelta(days=3),
                period_end_utc=DAY + timedelta(days=4), observed_at_utc=NOW - timedelta(hours=3),
                source_system="GIE", source_reference="gie-agsi-api", freshness="live",
                research_only=True,
            )
        )
        db.add(
            LngObservationRecord(
                observation_id="alsi-nl", source_dataset="ALSI", terminal_id="NL",
                terminal_name="Netherlands", country="NL", inventory_twh=2.1,
                send_out_twh_d=0.32, dtmi_twh=3.4, period_start_utc=DAY + timedelta(days=3),
                period_end_utc=DAY + timedelta(days=4), observed_at_utc=NOW - timedelta(hours=3),
                source_system="GIE", source_reference="gie-alsi-api", freshness="live",
                research_only=True,
            )
        )
        db.add(
            LngCargoRecord(
                cargo_id="C1", vessel_name="Arctic Voyager", status="laden", load_port="Hammerfest",
                load_lat=70.68, load_lon=23.6, departed_at_utc=NOW - timedelta(days=2),
                destination_terminal="Gate Terminal (I)", eta_utc=NOW + timedelta(days=3),
                book_id=None, source_system="ETRM", source_reference="t", updated_at_utc=NOW,
                eta_basis="master_notice", eta_confidence="medium", eta_source="ETRM",
                eta_recorded_at_utc=NOW - timedelta(hours=1),
            )
        )
        db.commit()
        yield db


def _situation(db, entitled=lambda rows: list(rows)):
    return build_map_situation(db, now=NOW, entitled=entitled, include_positions=True)


def test_sites_carry_published_capacity_flow_and_inventory_with_their_source(session):
    situation = _situation(session)
    assets = {asset["asset_id"]: asset for asset in situation["assets"]}
    assert set(assets) == {"entsog-lng-00027", "entsog-ugs-00149", "entsog-ugs-00002"}
    assert "Bacton (IUK)" not in {asset["name"] for asset in assets.values()}
    assert situation["asset_rule"].startswith("Terminals and storage sites")

    gate = assets["entsog-lng-00027"]
    assert gate["kind"] == "lng_terminal" and gate["location"]["ref_id"] == "entsog-lng-00027"
    # The current gas day's capacity, not an older one or a day ENTSOG publishes ahead.
    (capacity,) = gate["capacity"]
    assert capacity == {
        "direction": "entry", "capacity_type": "firm_technical", "gwh_d": 450.0,
        "gas_day": "2026-11-12", "operator_key": "NL-TSO-0001", "source_system": "ENTSOG",
        "observed_at_utc": "2026-11-11T05:00:00+00:00", "basis": "published",
    }
    # Send-out is the point's newest closed day, as the map's flows show it.
    (flow,) = gate["flow"]
    assert flow["gwh_d"] == pytest.approx(330.0) and flow["gas_day"] == "2026-11-11"
    # GIE reads LNG by country: the figure is said to be the Netherlands', not Gate's.
    assert gate["stock"]["basis"] == "country_aggregate"
    assert gate["stock"]["scope"] == "NL" and gate["stock"]["dataset"] == "ALSI"
    assert gate["stock"]["dtmi_twh"] == 3.4 and gate["stock"]["gas_day"] == "2026-11-11"

    bergermeer = assets["entsog-ugs-00149"]
    assert [item["direction"] for item in bergermeer["capacity"]] == ["exit"]
    assert bergermeer["flow"] == []
    assert bergermeer["stock"]["fill_pct"] == 78.5
    assert bergermeer["stock"]["basis"] == "country_aggregate"
    # Belgium: no GIE row held, so no inventory figure at all (absent, not estimated).
    assert assets["entsog-ugs-00002"]["stock"] is None


def test_a_site_figure_the_caller_may_not_read_is_left_out(session):
    def no_licensed(rows):
        return [row for row in rows if row.get("source_system") != "LICENSED_FEED"]

    unfiltered = {a["asset_id"]: a for a in _situation(session)["assets"]}
    assert unfiltered["entsog-ugs-00002"]["capacity"][0]["gwh_d"] == 77.0
    filtered = {a["asset_id"]: a for a in _situation(session, no_licensed)["assets"]}
    assert filtered["entsog-ugs-00002"]["capacity"] == []

    def no_gie(rows):
        return [row for row in rows if row.get("source_system") != "GIE"]

    assert all(a["stock"] is None for a in _situation(session, no_gie)["assets"])


def test_the_stored_flow_window_is_every_closed_day_oldest_first(session):
    days = _situation(session)["flow_days"]
    assert [day["gas_day"] for day in days] == [
        "2026-11-08", "2026-11-09", "2026-11-10", "2026-11-11"
    ]
    first = {item["point_id"]: item for item in days[0]["flows"]}
    assert first["LNG-00027"]["gwh_d"] == pytest.approx(300.0)
    assert first["LNG-00027"]["ref_id"] == "entsog-lng-00027"
    assert first["ITP-00005"]["direction"] == "exit"

    def no_entsog(rows):
        return [row for row in rows if row.get("source_system") != "ENTSOG"]

    assert _situation(session, no_entsog)["flow_days"] == []


def test_a_cargo_says_what_its_eta_rests_on_and_that_no_position_was_reported(session):
    (cargo,) = _situation(session)["cargoes"]
    assert cargo["position"] is None and cargo["position_basis"] is None
    assert cargo["eta"]["basis"] == "master_notice"
    assert cargo["eta"]["confidence"] == "medium"
    assert cargo["eta"]["source"] == "ETRM"
    assert "the master's notice" in cargo["eta"]["text"]
