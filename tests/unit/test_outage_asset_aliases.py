"""The reviewed outage-asset alias table and the placement it adds to the map.

The cases are the ones the GIE IIP feed left unplaced on 2026-11-18 (Polish site EICs of
virtual storage groups, Adriatic LNG named by its operator's EIC, Brunsbüttel's FSRU named
without an EIC). Nothing here is placed by a guessed position: a site maps to a GIE facility,
and a facility is placed only at the ENTSOG reference point the table ties it to.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.application.map_situation import build_map_situation
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import ReferenceNode
from eurogas_nexus.db.repositories.gie_facilities import upsert_gie_facilities
from eurogas_nexus.db.repositories.remit import store_umm_messages
from eurogas_nexus.domain.observations.remit_umm import parse_umm_export
from eurogas_nexus.ingestion.gie_facilities import one_per_eic, parse_listing
from eurogas_nexus.reference_data.outage_aliases import (
    alias_path,
    name_key,
    shipped_aliases,
    validate_aliases,
)

NOW = datetime(2026, 11, 18, 21, 40, tzinfo=UTC)

# As GIE's AGSI+/ALSI listings publish these operators and facilities (2026-11-18).
LISTING = {
    "agsi": [
        {"name": "Gas Storage Poland sp. z o.o.", "eic": "53XPL000000OSMP5", "country": "PL",
         "facilities": [
             {"name": "VGS GIM Kawerna (Kosakowo, Mogilno)", "type": "ASF",
              "eic": "21Z000000000383D", "country": "PL", "company": "53XPL000000OSMP5",
              "operational_end_date": None},
             {"name": "VGS GIM Sanok (Brzeznica, Husow, Strachocina, Swarzow)", "type": "DSR",
              "eic": "21Z000000000382F", "country": "PL", "company": "53XPL000000OSMP5",
              "operational_end_date": None},
         ]},
    ],
    "alsi": [
        {"name": "Terminale GNL Adriatico S.r.l.", "eic": "21X000000001360B", "country": "IT",
         "facilities": [
             {"name": "Rovigo LNG Terminal", "type": "LAND", "eic": "21W000000000082W",
              "country": "IT", "company": "21X000000001360B", "operational_end_date": None},
         ]},
        {"name": "Deutsche Energy Terminal GmbH", "eic": "21X000000001403J", "country": "DE",
         "facilities": [
             {"name": "Brunsbuettel LNG Terminal 1 (FSRU Hoegh Gannet)", "type": "FSRU",
              "eic": "37W000000000107A", "country": "DE", "company": "21X000000001403J",
              "operational_end_date": None},
             {"name": "Stade LNG Terminal 1 (FSRU Energos Force)", "type": "FSRU",
              "eic": "37W000000000110L", "country": "DE", "company": "21X000000001403J",
              "operational_end_date": None},
         ]},
    ],
}


def _facilities():
    rows = parse_listing(LISTING["agsi"], "storage") + parse_listing(LISTING["alsi"], "lng")
    return one_per_eic(rows)[0]


def _outage(message_id, name, eic, asset_type="storage"):
    return {
        "messageId": message_id, "version": 1, "publicationDateTime": NOW.isoformat(),
        "eventStatus": "Active", "eventStart": (NOW - timedelta(days=1)).isoformat(),
        "eventStop": (NOW + timedelta(days=3)).isoformat(), "affectedAssetName": name,
        "affectedAssetEic": eic, "affectedAssetType": asset_type, "unitMeasure": "GWh/d",
        "technicalCapacity": 100, "unavailableCapacity": 10,
    }


def _situation(messages, *, with_brunsbuettel_point=True, facilities=True):
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(ReferenceNode(
            id="entsog-ugs-00002", name="Loenhout Storage", node_type="storage", country="BE",
            lat=51.40, lon=4.65, source_system="ENTSOG", source_record_id="UGS-00002",
            data_quality="display_approximation", metadata_json={},
        ))
        session.add(ReferenceNode(
            id="entsog-ugs-00271", name="Epe (DE) (Eneco) / Enschede (NL)", node_type="storage",
            country="DE", lat=52.2516, lon=6.7978, source_system="ENTSOG",
            source_record_id="UGS-00271", data_quality="display_approximation",
            metadata_json={},
        ))
        if with_brunsbuettel_point:
            session.add(ReferenceNode(
                id="entsog-lng-00060", name="BRUNSBUETTEL HAFEN (FSRU) (DE)", node_type="lng",
                country="DE", lat=53.9076, lon=8.5852, source_system="ENTSOG",
                source_record_id="LNG-00060", data_quality="display_approximation",
                metadata_json={"point_eic_code": "37Z000000008198A"},
            ))
        parsed = parse_umm_export(
            json.dumps(messages), source_reference="GIE_IIP:terms-published:test"
        )
        store_umm_messages(session, parsed, now=NOW)
        if facilities:
            upsert_gie_facilities(session, _facilities(), now=NOW)
        session.commit()
        return build_map_situation(session, now=NOW, entitled=list)


def test_the_shipped_table_is_sound_and_carries_no_position():
    table = json.loads(alias_path().read_text(encoding="utf-8"))
    assert validate_aliases(table) == []
    assert all("lat" not in entry and "lon" not in entry for entry in table["entries"])
    assert all(entry["evidence"] and entry["reviewed"] for entry in table["entries"])
    aliases = shipped_aliases()
    assert aliases.facility_for(eic="53zpl0000602319i", name=None)["gie_facility_eic"] == (
        "21Z000000000383D"
    )
    assert aliases.facility_for(eic=None, name="BRUNSBUETTEL LNG Terminal 1 (FSRU)")
    assert aliases.point_for("37W000000000107A")["reference_point_key"] == "LNG-00060"
    assert aliases.facility_for(eic="53ZPL9999999999X", name="UGS Somewhere") is None


@pytest.mark.parametrize(
    ("entry", "problem"),
    [
        ({"match": {"asset_eic": "A", "asset_name": "B"}, "gie_facility_eic": "F",
          "evidence": "e", "reviewed": "2026-11-19"}, "match must name one"),
        ({"match": {"asset_eic": "A"}, "reference_point_key": "P", "evidence": "e",
          "reviewed": "2026-11-19"}, "maps to a GIE facility only"),
        ({"match": {"asset_eic": "A"}, "gie_facility_eic": "F", "evidence": "",
          "reviewed": "2026-11-19"}, "evidence is required"),
        ({"match": {"asset_eic": "A"}, "gie_facility_eic": "F", "evidence": "e",
          "reviewed": "2026-11-19", "lat": 52.0, "lon": 18.0}, "never carries a position"),
    ],
)
def test_an_unsound_entry_is_refused(entry, problem):
    table = {"schema": "eurogas-nexus/outage-asset-aliases/1", "entries": [entry]}
    assert any(problem in item for item in validate_aliases(table))


def test_names_compare_without_case_accents_or_punctuation():
    assert name_key("UGS Brzeźnica") == name_key("ugs  brzeznica")


def test_aliases_identify_sites_and_place_only_at_a_reference_point():
    situation = _situation([
        _outage("m-mogilno", "CUGS Mogilno", "53ZPL0000602319I"),
        _outage("m-kosakowo", "CUGS Kosakowo", "53ZPL0000602320X"),
        _outage("m-husow", "UGS Husów", "53ZPL00004023145"),
        # The operator's EIC as the asset: it runs one current LNG facility.
        _outage("m-adriatic", "Terminale GNL Adriatico S.r.l.", "21X000000001360B", "lng"),
        # No EIC, a name GIE does not use; the reviewed alias names the facility, and the
        # facility's ENTSOG entry point is in the reference.
        _outage("m-bruns", "Brunsbuettel LNG Terminal 1 (FSRU)", "", "lng"),
        # Nothing ties this one to anything: it stays unlocated, with the reason.
        _outage("m-unknown", "UGS Nowhere", "53ZPL0000000000Z"),
    ])
    placement = situation["outage_placement"]
    assert (placement["placed"], placement["known_facility_no_position"],
            placement["unlocated"]) == (1, 4, 1)
    placed = situation["outages"][0]
    assert placed["facility_name"] == "Brunsbuettel LNG Terminal 1 (FSRU)"
    assert placed["location"]["ref_id"] == "entsog-lng-00060"
    assert placed["location"]["match"] == "gie_facility_alias_alias_point"
    assert placed["location"]["coordinate_quality"] == "display_approximation"
    known = {item["facility_eic"]: item for item in situation["known_facility_outages"]}
    kawerna = known["21Z000000000383D"]
    assert kawerna["outages"] == 2 and kawerna["identified_by"] == "alias"
    assert sorted(kawerna["sites"]) == ["Kosakowo", "Mogilno"]
    # No reference point in PL or IT: said so, not passed off as "no position published".
    assert kawerna["reason"] == "outside_reference_network"
    assert known["21W000000000082W"]["identified_by"] == "operator_eic"
    assert known["21Z000000000382F"]["sites"] == ["Husów"]
    assert len(situation["unlocated_outages"]) == 1
    unlocated = situation["unlocated_outages"][0]
    assert {key: unlocated[key] for key in
            ("facility_name", "facility_id", "market_participant", "reason")} == {
        "facility_name": "UGS Nowhere", "facility_id": "53ZPL0000000000Z",
        "market_participant": "", "reason": "no_reference_match",
    }
    # The window and size travel with it, so the map can still say what is out and until when.
    assert unlocated["unavailable_gwh_d"] == 10.0 and unlocated["end_utc"]


def test_without_the_reference_point_or_the_listing_nothing_is_guessed():
    messages = [_outage("m-bruns", "Brunsbuettel LNG Terminal 1 (FSRU)", "", "lng"),
                _outage("m-mogilno", "CUGS Mogilno", "53ZPL0000602319I")]
    no_point = _situation(messages, with_brunsbuettel_point=False)
    assert no_point["outage_placement"]["placed"] == 0
    bruns = next(item for item in no_point["known_facility_outages"]
                 if item["facility_eic"] == "37W000000000107A")
    # DE has reference points, so this is a known facility with no published position.
    assert bruns["reason"] == "no_published_position"
    # Without GIE's listing an alias has no facility to resolve to: both stay unlocated.
    no_listing = _situation(messages, facilities=False)
    assert no_listing["outage_placement"]["unlocated"] == 2


def test_the_operator_rule_needs_exactly_one_facility_of_that_kind():
    # Deutsche Energy Terminal runs two LNG facilities here: its EIC identifies neither.
    situation = _situation([_outage("m-det", "DET", "21X000000001403J", "lng")])
    assert situation["outage_placement"]["unlocated"] == 1
