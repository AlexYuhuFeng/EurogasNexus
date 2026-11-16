"""ENTSOG transmission UMMs: recorded API records reach the REMIT store through the importer.

The fixture is eight records recorded from
``https://transparency.entsog.eu/api/v1/urgentmarketmessages`` on 2026-11-16: an "Other"
market message (no capacity), a Fluxys VIP THE-ZTP outage in kWh/h with two versions, OGE's
Etzel ESE storage-connection entry in kWh/d, a dismissed Oberkappel message with its first
version, an inactive GRTgaz message and Elering's Värska entry (published 2023, running to
2029).
"""

from __future__ import annotations

import importlib.util
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from eurogas_nexus.application.remit_outages import load_outage_rows
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import RemitUmmRecord, SourceEntityMappingRecord
from eurogas_nexus.domain.observations.remit_platforms import platform_attribution
from eurogas_nexus.domain.observations.remit_umm import parse_umm_export
from eurogas_nexus.ingestion import entsog_transport as et
from eurogas_nexus.ingestion.entsog_umm import acer_fields, acer_messages, citation

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests" / "fixtures" / "remit" / "entsog_umm_page.json"
SCRIPT = ROOT / "scripts" / "ops" / "ingest_remit_entsog.py"
NOW = datetime(2026, 11, 16, 9, 0, tzinfo=UTC)


def _records():
    return json.loads(FIXTURE.read_text())["urgentmarketmessages"]


def _by_message_id(message_id):
    return next(r for r in _records() if r["messageId"] == message_id)


def _messages(since=NOW - timedelta(days=7)):
    return parse_umm_export(
        json.dumps(acer_messages(_records(), since=since)),
        source_reference="ENTSOG_TP:terms-published:api:20261116T0900Z",
    )


def test_thread_version_zone_and_asset_type_map_to_acer_fields():
    fields = acer_fields(_by_message_id("26030821X-BE-A-A0A0A-Y003_002"))
    assert fields["messageId"] == "26030821X-BE-A-A0A0A-Y003"
    assert fields["version"] == 2
    assert fields["balancingZone"] == "BE-LUX"  # ENTSOG pads keys with dashes
    assert fields["affectedAssetType"] == "transmission"
    assert fields["affectedAssetEic"] == "21Z102938475601E"
    assert fields["marketParticipant"] == "Fluxys Belgium SA/NV (BE-TSO-0001)"
    assert fields["unavailabilityReason"] == "Other unavailability - Maintenance CS Zelzate"
    # "Other" market information carries no capacity: not an outage.
    assert acer_fields(_by_message_id("0000000000000000000038576_001")) is None


def test_normalised_versions_units_and_utc():
    messages = {(m.message_id, m.version): m for m in _messages()}
    # 7 unavailability versions in the fixture, all still running after the window start.
    assert len(messages) == 7
    fluxys = messages[("26030821X-BE-A-A0A0A-Y003", 2)]
    assert fluxys.published_at_utc == datetime(2026, 11, 5, 10, 42, 19, tzinfo=UTC)
    assert fluxys.event_start_utc == datetime(2026, 11, 9, 5, tzinfo=UTC)  # 06:00 CET
    # 5,000,000 kWh/h through the unit authority, times the 24 h of the gas day of 9 Nov.
    assert fluxys.unit == "kWh/h" and fluxys.unavailable_gwh_d == pytest.approx(5.0 * 24)
    etzel = messages[("V0025782/11--------------", 1)]
    assert etzel.unavailable_gwh_d == pytest.approx(20.151768)
    assert etzel.asset_eic == "21Z000000000324T" and etzel.direction == "entry"
    assert messages[("V0025728/1---------------", 2)].event_status == "dismissed"


def test_inactive_is_not_read_as_active_and_ends_the_event():
    messages = {(m.message_id, m.version): m for m in _messages()}
    natran = messages[("25102721X-FR-A-A0A0A-S001", 5)]
    assert natran.event_status == "inactive"  # "Inactive" contains "active"
    from eurogas_nexus.domain.observations.remit_umm import current_messages

    assert "25102721X-FR-A-A0A0A-S001" not in {m.message_id for m in current_messages(
        messages.values())}


def test_a_message_without_a_version_flagged_latest_is_named():
    from eurogas_nexus.ingestion.entsog_umm import threads_without_latest

    assert threads_without_latest(_records()) == {"25102721X-FR-A-A0A0A-S001": 5}


def test_window_keeps_running_events_published_long_ago():
    late = acer_messages(_records(), since=datetime(2027, 1, 1, tzinfo=UTC))
    # Only Värska (published 2023) still runs after 1 Jan 2027.
    assert [item["messageId"] for item in late] == ["23120110X1001A1001A39W005"]


def test_stored_once_read_by_the_outage_reader_with_the_citation():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine, tables=[RemitUmmRecord.__table__])
    from eurogas_nexus.db.repositories.remit import store_umm_messages

    with Session(engine) as session:
        first = store_umm_messages(session, _messages(), now=NOW, source_system="ENTSOG_UMM")
        again = store_umm_messages(session, _messages(), now=NOW, source_system="ENTSOG_UMM")
        session.commit()
        assert first == {"inserted": 7, "updated": 0, "unchanged": 0}
        assert again == {"inserted": 0, "updated": 0, "unchanged": 7}
        rows = load_outage_rows(session, now=NOW, horizon_days=90)
    events = {row["event_id"]: row for row in rows}
    assert "V0025728/1---------------" not in events  # dismissed
    fluxys = events["26030821X-BE-A-A0A0A-Y003"]
    assert fluxys["version"] == 2 and fluxys["asset_type"] == "transmission"
    assert fluxys["platform"] == "ENTSOG_TP"
    assert fluxys["attribution"] == "ENTSOG TP [16-11-2026] https://transparency.entsog.eu/"


def test_platform_attribution_and_citation():
    assert platform_attribution("GIE_IIP:terms-published:api:20261114T0600Z") == (
        "GIE_IIP", "Source: GIE Inside Information Platform",
    )
    assert platform_attribution("unknown") == ("", "")
    assert citation(NOW) == "ENTSOG TP [16-11-2026] https://transparency.entsog.eu/"


def _client(pages_seen):
    page = json.loads(FIXTURE.read_text())

    def handler(request):
        pages_seen.append(request.url.params["offset"])
        assert request.url.path.endswith("/urgentmarketmessages")
        if request.url.params["offset"] != "0":
            return httpx.Response(404, json={"message": "No result found"})
        page["meta"]["limit"] = int(request.url.params["limit"])
        return httpx.Response(200, json=page)

    return httpx.Client(transport=httpx.MockTransport(handler))


def _script():
    spec = importlib.util.spec_from_file_location("ingest_remit_entsog_script", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_transport_reads_the_dataset_with_its_paging_rules():
    seen = []
    with _client(seen) as client:
        result = et.fetch_entsog_dataset(client, "urgentmarketmessages", page_size=100)
    # 8 rows left of a limit of 100: exhausted on the first page.
    assert seen == ["0"] and result.complete and result.record_count == 8


def test_script_dry_run_commit_and_operator_quarantine(tmp_path, monkeypatch, capsys):
    url = f"sqlite+pysqlite:///{(tmp_path / 'remit.sqlite').as_posix()}"
    engine = create_engine(url)
    Base.metadata.create_all(engine, tables=[RemitUmmRecord.__table__])
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", url)
    module = _script()

    assert module.main(["--days", "7", "--json"], client=_client([])) == 0
    dry = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    # NaTran's message has no version flagged latest in the feed: held back, not stored.
    assert dry["sources"]["entsog_umm"]["records"] == 6
    assert dry["sources"]["entsog_umm"]["inserted"] == 0
    # No ENTSOG reference mappings in this store: operators are not judged.
    assert [(item["message_id"], item["reason"]) for item in dry["quarantined"]] == [
        ("25102721X-FR-A-A0A0A-S001", "latest_version_not_published")
    ]

    assert module.main(["--days", "7", "--commit", "--json"], client=_client([])) == 0
    report = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert report["ok"] is True and report["sources"]["entsog_umm"]["inserted"] == 6
    assert report["citation"].startswith("ENTSOG TP [")
    with Session(engine) as session:
        stored = session.execute(select(RemitUmmRecord)).scalars().all()
        assert {row.source_system for row in stored} == {"ENTSOG_UMM"}
        assert all(row.source_reference.startswith("ENTSOG_TP:terms-published:api:")
                   for row in stored)

    # Once the store holds ENTSOG operator mappings, an unmapped publisher is held back.
    Base.metadata.create_all(engine, tables=[SourceEntityMappingRecord.__table__])
    with Session(engine) as session:
        for key in ("DE-TSO-0009", "BE-TSO-0001"):
            session.add(SourceEntityMappingRecord(
                mapping_id=f"map:src-entsog:entsog_operator:{key}",
                canonical_entity_id=f"ent:entsog_operator:{key}",
                source_id="src-entsog", source_entity_type="entsog_operator",
                source_identifier=key, valid_from_utc=datetime(2000, 1, 1, tzinfo=UTC),
                mapping_status="ACTIVE", confidence="CONFIRMED", evidence="test",
                created_at_utc=NOW,
            ))
        session.commit()
    assert module.main(["--days", "7", "--json"], client=_client([])) == 0
    held = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert {
        item["detail"] for item in held["quarantined"] if item["reason"] == "unresolved_operator"
    } == {"FR-TSO-0003", "EE-TSO-0001"}
    assert {item["reason"] for item in held["quarantined"]} == {
        "unresolved_operator", "latest_version_not_published",
    }
    assert held["sources"]["entsog_umm"]["records"] == 5
    engine.dispose()
