"""GIE IIP UMMs: recorded API records reach the REMIT store through the importer's normaliser.

The fixture is five records recorded from ``https://iip.gie.eu/api`` on 2026-11-14 (embedded
ACER XML dropped, ``prev`` cut to two versions): a storage message with earlier versions, an
LNG regasification outage, an "other market information" report, a dismissed event and a
message in kWh/h.
"""

from __future__ import annotations

import importlib.util
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from eurogas_nexus.application.remit_outages import load_outage_rows
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import RemitUmmRecord
from eurogas_nexus.db.repositories.remit import store_umm_messages
from eurogas_nexus.domain.observations.remit_umm import parse_umm_export
from eurogas_nexus.ingestion.gie_iip import (
    IipError,
    acer_fields,
    acer_messages,
    fetch_iip_messages,
)

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests" / "fixtures" / "remit" / "gie_iip_api_page.json"
SCRIPT = ROOT / "scripts" / "ops" / "ingest_remit_iip.py"
NOW = datetime(2026, 11, 14, 6, 30, tzinfo=UTC)


def _page():
    return json.loads(FIXTURE.read_text())


def _messages():
    return parse_umm_export(
        json.dumps(acer_messages(_page()["data"])),
        source_reference="GIE_IIP:terms-published:test",
    )


def test_message_id_version_times_and_capacity_map_to_acer_fields():
    record = _page()["data"][0]
    fields = acer_fields(record)
    assert fields["messageId"] == "25041521X000000001120V182"
    assert fields["version"] == 35
    assert fields["publicationDateTime"] == record["published"]
    assert fields["affectedAssetName"] == "UGS Bergermeer"
    assert fields["affectedAssetEic"] == "21W0000000000087"
    assert fields["affectedAssetType"] == "storage"
    assert fields["unitMeasure"] == "GWh/d"
    assert fields["balancingZone"] == "21YNL----TTF---1"
    # Other market information is not an outage.
    assert acer_fields(_page()["data"][2]) is None


def test_normalised_versions_keep_units_and_utc():
    messages = {(m.message_id, m.version): m for m in _messages()}
    # Message 1 with two earlier versions, LNG, dismissed (with its earlier version), kWh/h.
    assert len(messages) == 3 + 1 + 2 + 1
    storage = messages[("25041521X000000001120V182", 35)]
    assert storage.published_at_utc == datetime(2026, 11, 14, 6, 13, 20, tzinfo=UTC)
    assert storage.event_start_utc == datetime(2026, 12, 7, 5, tzinfo=UTC)
    assert storage.unavailable_gwh_d == 0.0 and storage.technical_capacity == 384.0
    lng = messages[("26111321X000000001360B007", 1)]
    assert lng.asset_type == "lng" and lng.unavailable_gwh_d == pytest.approx(67.162764)
    hourly = messages[("26111221X000000001138C011", 1)]
    # kWh/h keeps its unit; the daily figure is the hourly rate times the hours of the gas
    # day the event starts in (18 Nov 2026: 24 h), through the unit authority.
    assert hourly.unit == "kWh/h" and hourly.unavailable_gwh_d == pytest.approx(1.218 * 24)
    assert hourly.unavailable_capacity == 1_218_000.0
    assert messages[("26103021X000000001360B002", 2)].event_status == "dismissed"


def test_stored_once_and_read_by_the_outage_reader():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine, tables=[RemitUmmRecord.__table__])
    with Session(engine) as session:
        first = store_umm_messages(session, _messages(), now=NOW)
        session.commit()
        again = store_umm_messages(session, _messages(), now=NOW + timedelta(minutes=30))
        session.commit()
        assert first == {"inserted": 7, "updated": 0, "unchanged": 0}
        assert again == {"inserted": 0, "updated": 0, "unchanged": 7}
        stored = session.execute(select(RemitUmmRecord)).scalars().all()
        assert {row.source_system for row in stored} == {"REMIT"}
        rows = load_outage_rows(session, now=NOW, horizon_days=366)
    events = {row["event_id"]: row for row in rows}
    # Latest version per message; the dismissed event and the past one are gone.
    assert set(events) == {
        "25041521X000000001120V182",
        "26111321X000000001360B007",
        "26111221X000000001138C011",
    }
    assert events["25041521X000000001120V182"]["version"] == 35
    assert events["26111321X000000001360B007"]["unavailable_gwh_d"] == pytest.approx(67.162764)


def test_paging_stops_at_the_window_and_refuses_a_partial_read():
    page = _page()
    newest = max(datetime.fromisoformat(r["submitted"]) for r in page["data"]).replace(tzinfo=UTC)
    pages = []

    def get_page(number):
        pages.append(number)
        return page

    read = fetch_iip_messages(
        get_page, since=newest + timedelta(seconds=1), max_pages=5, sleep=lambda _s: None
    )
    assert read.stop == "window_exhausted" and pages == [1]
    with pytest.raises(IipError) as refused:
        fetch_iip_messages(
            get_page, since=newest - timedelta(days=30), max_pages=2, sleep=lambda _s: None
        )
    assert refused.value.code == "iip_read_bound_reached"


def test_script_dry_run_and_commit_report(tmp_path, monkeypatch, capsys):
    url = f"sqlite+pysqlite:///{(tmp_path / 'remit.sqlite').as_posix()}"
    engine = create_engine(url)
    Base.metadata.create_all(engine, tables=[RemitUmmRecord.__table__])
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", url)
    spec = importlib.util.spec_from_file_location("ingest_remit_iip_script", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    page = _page()
    page["meta"]["last_page"] = 1

    assert module.main(["--days", "2", "--json"], get_page=lambda _n: page) == 0
    dry = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert dry["sources"]["gie_iip"]["records"] == 7 and dry["sources"]["gie_iip"]["inserted"] == 0

    assert module.main(["--days", "2", "--commit", "--json"], get_page=lambda _n: page) == 0
    report = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert report["ok"] is True
    assert report["sources"]["gie_iip"] == {
        "records": 7, "inserted": 7, "updated": 0, "unchanged": 0, "revised": 0,
    }
    with Session(engine) as session:
        assert len(session.execute(select(RemitUmmRecord)).scalars().all()) == 7
    engine.dispose()


def _mock_getter(monkeypatch, responses, **kwargs):
    """``http_page_getter`` against canned responses; returns the getter and the waits."""

    import httpx

    from eurogas_nexus.ingestion import gie_iip

    queue = list(responses)
    real_client = httpx.Client

    def handler(_request):
        status, body = queue.pop(0)
        return httpx.Response(status, json=body)

    monkeypatch.setattr(
        httpx, "Client",
        lambda **kw: real_client(transport=httpx.MockTransport(handler), timeout=kw["timeout"]),
    )
    waits: list[float] = []
    return gie_iip.http_page_getter("test-key", sleep=waits.append, **kwargs), waits, queue


RELAYED_429 = {"statusCode": 503, "content": "HTTP/2 429 returned for upstream"}


def test_a_relayed_rate_limit_is_waited_out_with_a_capped_backoff(monkeypatch):
    page = _page()
    get_page, waits, queue = _mock_getter(
        monkeypatch, [(200, RELAYED_429)] * 5 + [(200, page)]
    )
    assert get_page(1)["data"] == page["data"]
    assert waits == [60.0, 120.0, 180.0, 240.0, 300.0] and not queue


def test_a_rate_limit_that_does_not_clear_is_refused_with_a_stable_code(monkeypatch):
    get_page, waits, _queue = _mock_getter(
        monkeypatch, [(200, RELAYED_429)] * 2 + [(429, {})] * 2, refusal_attempts=4
    )
    with pytest.raises(IipError) as refused:
        get_page(1)
    assert refused.value.code == "iip_rate_limited" and len(waits) == 3


def test_a_refusal_after_the_first_page_keeps_the_newest_pages():
    page = _page()
    newest = max(datetime.fromisoformat(r["submitted"]) for r in page["data"]).replace(tzinfo=UTC)

    def get_page(number):
        if number == 3:
            raise IipError("iip_upstream_refused", "upstream 503")
        return page

    read = fetch_iip_messages(
        get_page, since=newest - timedelta(days=30), max_pages=10, sleep=lambda _s: None
    )
    assert read.stop == "interrupted" and read.error == "iip_upstream_refused"
    assert read.pages == 2 and len(read.records) == 2 * len(page["data"])

    def refuse_first(_number):
        raise IipError("iip_upstream_refused", "upstream 503")

    with pytest.raises(IipError):
        fetch_iip_messages(refuse_first, since=newest, max_pages=10, sleep=lambda _s: None)


def test_script_stores_a_partial_read_and_reports_it_incomplete(tmp_path, monkeypatch, capsys):
    url = f"sqlite+pysqlite:///{(tmp_path / 'remit.sqlite').as_posix()}"
    engine = create_engine(url)
    Base.metadata.create_all(engine, tables=[RemitUmmRecord.__table__])
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", url)
    spec = importlib.util.spec_from_file_location("ingest_remit_iip_partial", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    page = _page()
    for record in page["data"]:
        record["submitted"] = datetime.now(UTC).replace(tzinfo=None).isoformat()

    def get_page(number):
        if number == 2:
            raise IipError("iip_upstream_refused", "upstream 503")
        return page

    assert module.main(["--days", "2", "--commit", "--json"], get_page=get_page) == 1
    report = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert report["ok"] is False
    assert report["failures"] == [{"code": "iip_upstream_refused", "partial": True}]
    assert report["sources"]["gie_iip"]["inserted"] == 7
    with Session(engine) as session:
        assert len(session.execute(select(RemitUmmRecord)).scalars().all()) == 7
    engine.dispose()
