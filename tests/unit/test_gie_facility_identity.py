"""GIE facility listing as identity, and outages at known facilities with no position.

The fixture is part of the AGSI+/ALSI listings recorded on 2026-11-16 (``/api/about?show=
listing``): the six facilities whose outages the map could not place, plus Eneco's
Enschede-Epe, whose EIC ENTSOG also publishes as a storage point's EIC.
"""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from eurogas_nexus.application.map_situation import build_map_situation
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import (
    CanonicalEntityRecord,
    ReferenceNode,
    RemitUmmRecord,
    SourceEntityMappingRecord,
)
from eurogas_nexus.db.repositories.gie_facilities import (
    load_gie_facilities,
    upsert_gie_facilities,
)
from eurogas_nexus.db.repositories.remit import store_umm_messages
from eurogas_nexus.domain.observations.remit_umm import parse_umm_export
from eurogas_nexus.ingestion.gie_facilities import one_per_eic, parse_listing

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "remit" / "gie_facility_listing.json"
NOW = datetime(2026, 11, 16, 9, 0, tzinfo=UTC)


def _facilities():
    listing = json.loads(FIXTURE.read_text())
    rows = parse_listing(listing["agsi"], "storage") + parse_listing(listing["alsi"], "lng")
    return one_per_eic(rows)[0]


def test_listing_gives_identity_without_a_position():
    facilities = {f.eic: f for f in _facilities()}
    epe = facilities["21W000000000066U"]
    assert (epe.name, epe.country, epe.operator_name, epe.kind) == (
        "UGS Epe Uniper H-Gas", "DE", "Uniper Energy Storage GmbH", "storage",
    )
    assert facilities["21W0000000001253"].kind == "lng"
    assert epe.metadata()["position"] is None


def test_one_row_per_eic_prefers_the_open_row():
    epe = next(f for f in _facilities() if f.eic == "21W000000000066U")
    closed = replace(epe, name="old row", operational_end_date="2022-10-07")
    chosen, repeated = one_per_eic([closed, epe])
    assert [item.name for item in chosen] == [epe.name] and repeated == [epe.eic]


def _engine():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine


def test_upsert_is_idempotent_retires_and_restores_never_deletes():
    engine = _engine()
    facilities = _facilities()
    with Session(engine) as session:
        first = upsert_gie_facilities(session, facilities, now=NOW)
        again = upsert_gie_facilities(session, facilities, now=NOW)
        assert first["inserted"] == len(facilities) == 7
        assert again == {"inserted": 0, "updated": 0, "unchanged": 7, "retired": 0,
                         "restored": 0}
        # Klaipeda no longer listed: retired, not deleted; back again: restored.
        without = [f for f in facilities if f.eic != "21W0000000001253"]
        assert upsert_gie_facilities(session, without, now=NOW)["retired"] == 1
        mapping = session.scalars(select(SourceEntityMappingRecord).where(
            SourceEntityMappingRecord.source_identifier == "21W0000000001253")).one()
        assert mapping.mapping_status == "RETIRED"
        assert session.get(CanonicalEntityRecord, "ent:gas_facility:21W0000000001253")
        assert len(load_gie_facilities(session)) == 6
        assert upsert_gie_facilities(session, facilities, now=NOW)["restored"] == 1
        # An empty listing changes nothing.
        assert upsert_gie_facilities(session, [], now=NOW)["retired"] == 0
        assert len(load_gie_facilities(session)) == 7


def _outage(message_id, name, eic):
    return {
        "messageId": message_id, "version": 1, "publicationDateTime": NOW.isoformat(),
        "eventStatus": "Active", "eventStart": (NOW - timedelta(days=1)).isoformat(),
        "eventStop": (NOW + timedelta(days=3)).isoformat(), "affectedAssetName": name,
        "affectedAssetEic": eic, "affectedAssetType": "storage", "unitMeasure": "GWh/d",
        "technicalCapacity": 100, "unavailableCapacity": 10,
    }


def test_map_places_by_gie_identity_or_lists_a_known_facility():
    engine = _engine()
    messages = parse_umm_export(json.dumps([
        _outage("m-epe", "EPE-H", "21W000000000066U"),
        _outage("m-epe-2", "EPE-H", "21W000000000066U"),
        # No EIC: GIE's name, accents and brackets aside, identifies the terminal.
        _outage("m-klaipeda", "Klaipeda LNG Terminal FSRU Independence", ""),
        # Named as GIE names it; GIE's EIC is an ENTSOG storage point's EIC: placed there.
        _outage("m-eneco", "UGS Enschede - Epe (Eneco)", ""),
        _outage("m-unknown", "CUGS Mogilno", "53ZPL0000602319I"),
    ]), source_reference="GIE_IIP:terms-published:test")
    with Session(engine) as session:
        session.add(ReferenceNode(
            id="entsog-ugs-00271", name="Epe (DE) (Eneco) / Enschede (NL)",
            node_type="storage", country="DE", lat=52.2516, lon=6.7978,
            source_system="ENTSOG", source_record_id="UGS-00271",
            data_quality="display_approximation",
            metadata_json={"point_eic_code": "21W000000000012G"},
        ))
        # As in the live reference: "Epe" names two places, so EPE-H has no unique site.
        session.add(ReferenceNode(
            id="entsog-ugs-00459", name="Epe (DE) (Trianel)", node_type="storage",
            country="DE", lat=52.71, lon=15.04, source_system="ENTSOG",
            source_record_id="UGS-00459", data_quality="display_approximation",
            metadata_json={},
        ))
        store_umm_messages(session, messages, now=NOW)
        session.commit()
        before = build_map_situation(session, now=NOW, entitled=list)
        assert before["outage_placement"]["unlocated"] == 5
        upsert_gie_facilities(session, _facilities(), now=NOW)
        session.commit()
        after = build_map_situation(session, now=NOW, entitled=list)
    placement = after["outage_placement"]
    assert (placement["placed"], placement["known_facility_no_position"],
            placement["unlocated"]) == (1, 3, 1)
    assert after["outages"][0]["location"]["match"] == "gie_facility_name"
    assert after["outages"][0]["location"]["ref_id"] == "entsog-ugs-00271"
    known = {item["facility_eic"]: item for item in after["known_facility_outages"]}
    assert known["21W000000000066U"]["outages"] == 2
    assert known["21W000000000066U"]["country"] == "DE"
    assert known["21W000000000066U"]["identified_by"] == "eic"
    assert known["21W0000000001253"]["identified_by"] == "name"
    assert [item["facility_name"] for item in after["unlocated_outages"]] == ["CUGS Mogilno"]
    assert RemitUmmRecord.__tablename__ == "remit_umm_messages"
