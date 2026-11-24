"""The gas day checklist: statuses as recorded, mismatch, LNG steps, scope, writes, outbox."""

from __future__ import annotations

import importlib.util
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import eurogas_nexus.db.models  # noqa: F401
from eurogas_nexus.application.caller import Caller
from eurogas_nexus.application.gas_day import balance_band, state_within
from eurogas_nexus.application.gas_day_checklist import (
    ChecklistError,
    checklist,
    needs_me_items,
    queue_deadline_notifications,
    record_status,
)
from eurogas_nexus.db.base import Base
from eurogas_nexus.security.identity import AuthenticatedPrincipal

SEED = Path(__file__).resolve().parents[2] / "scripts" / "demo" / "seed_demo_desk.py"
NOW = datetime(2026, 11, 19, 9, tzinfo=UTC)
TODAY, TOMORROW = date(2026, 11, 19), date(2026, 11, 20)


def _caller(name: str) -> Caller:
    return Caller(AuthenticatedPrincipal(
        principal_id=f"p-{name}", name=name, principal_type="USER", role="ANALYST",
        status="ACTIVE", data_scopes=("*",), roles=("ANALYST",),
    ))


@pytest.fixture
def desk(tmp_path, monkeypatch):
    url = f"sqlite+pysqlite:///{tmp_path / 'checklist.sqlite'}"
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", url)
    monkeypatch.setenv("EUROGAS_NEXUS_DEMO_MARKS", "true")
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    spec = importlib.util.spec_from_file_location("seed_demo_desk", SEED)
    seed = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(seed)
    with Session(engine) as session:
        seed.seed(session, NOW, history_days=3)
        session.commit()
    return engine


def _items(engine, name, which="today", now=NOW):
    with Session(engine) as session:
        row = checklist(session, _caller(name), now=now)
    day = next(d for d in row["days"] if d["which"] == which)
    return row, {(item["ref"], item["step"]): item for item in day["items"]}


def test_the_balancing_band_reads_rounding_as_balanced():
    band = balance_band(None, 4_044, 4_000)
    assert band["basis"] == "default" and band["pct"] == 2.0 and band["mwh"] == 80.9
    assert state_within(44, band) == "balanced"
    assert state_within(-120, band) == "short"
    held = balance_band({"flat_band_pct": 0.5, "band_set": "Desk v2"}, 4_044, 4_000)
    assert held["basis"] == "assumption" and state_within(44, held) == "long"


def test_statuses_as_recorded_agent_and_mismatch(desk):
    _, items = _items(desk, "demo.trader")
    haldor = items[("contract:demo-haldor-24", "nomination")]
    assert haldor["status"]["status"] == "confirmed" and haldor["status"]["origin"] == "import"
    assert haldor["agent"] == "Demo nominations agent (fictional)"
    assert haldor["expected"]["mwh"] == 24_000 and haldor["nominated"]["mwh"] == 21_120
    assert haldor["mismatch"]["over_tolerance"] is True and haldor["mismatch"]["pct"] == -12.0
    brae = items[("contract:demo-brae-10", "nomination")]
    assert brae["status"] == {**brae["status"], "status": "sent", "origin": "delivery_record"}
    assert brae["mismatch"]["over_tolerance"] is False
    # The customer's offtake is the customer's to nominate: not on the firm's checklist.
    assert not any("offtake" in ref for ref, _ in items)
    # Only the books the mandate covers: the NL book's own contract is not here.
    assert ("contract:demo-kestrel-18", "nomination") not in items


def test_tomorrows_unsent_nomination_is_due_then_overdue(desk):
    _, items = _items(desk, "demo.trader", "tomorrow", now=TODAY_AT(11))
    brae = items[("contract:demo-brae-10", "nomination")]
    assert brae["status"]["status"] == "to_send" and brae["urgency"] == "due_soon"
    assert brae["deadline"]["at_utc"] == "2026-11-19T13:00:00+00:00"
    assert brae["deadline"]["basis"] == "assumption"
    _, items = _items(desk, "demo.trader", "tomorrow", now=TODAY_AT(14))
    assert items[("contract:demo-brae-10", "nomination")]["urgency"] == "overdue"


def TODAY_AT(hour: int) -> datetime:  # noqa: N802
    return datetime(2026, 11, 19, hour, tzinfo=UTC)


def test_lng_steps_of_the_send_out_day(desk):
    _, items = _items(desk, "demo.nl.trader", "tomorrow")
    steps = {step for ref, step in items if ref.startswith("lng:")}
    assert steps == {"lng_unloading", "lng_send_out", "lng_inventory"}
    send_out = next(item for (ref, step), item in items.items() if step == "lng_send_out")
    assert send_out["expected"]["mwh"] == 4_800 and send_out["status"]["status"] == "to_send"
    inventory = next(item for (ref, step), item in items.items() if step == "lng_inventory")
    assert inventory["status"]["status"] == "not_held"  # never invented


def test_a_status_entered_by_hand_is_labelled_audited_and_scoped(desk):
    from eurogas_nexus.db.models import AuditEventRecord

    with Session(desk) as session:
        result = record_status(
            session, _caller("demo.trader"), gas_day=TOMORROW,
            line_ref="contract:demo-brae-10", step="nomination", status="sent",
            quantity_mwh=10_000, note="sent to the agent by phone", now=NOW)
        session.commit()
        assert result["origin"] == "manual"
        audit = session.query(AuditEventRecord).filter(
            AuditEventRecord.action == "gas_day.status.record").one()
        assert "contract:demo-brae-10" in audit.resource
        with pytest.raises(ChecklistError) as refused:
            record_status(session, _caller("demo.trader"), gas_day=TODAY,
                          line_ref="contract:demo-kestrel-18", step="nomination",
                          status="sent", quantity_mwh=None, note=None, now=NOW)
        assert refused.value.code == "line_not_in_scope"
        with pytest.raises(ChecklistError) as unknown:
            record_status(session, _caller("demo.trader"), gas_day=TODAY,
                          line_ref="contract:demo-brae-10", step="nominate",
                          status="sent", quantity_mwh=None, note=None, now=NOW)
        assert unknown.value.code == "unknown_step"
    _, items = _items(desk, "demo.trader", "tomorrow")
    brae = items[("contract:demo-brae-10", "nomination")]
    assert brae["status"]["origin"] == "manual" and brae["status"]["by"] == "demo.trader"
    assert brae["nominated"]["mwh"] == 10_000


def test_deadlines_feed_what_needs_me_and_the_outbox_once(desk):
    from eurogas_nexus.db.models import NotificationOutboxRecord

    with Session(desk) as session:
        row = checklist(session, _caller("demo.trader"), now=TODAY_AT(11))
    needs = needs_me_items(row)
    assert any(item["step"] == "nomination" and item["urgency"] == "due_soon" for item in needs)
    assert any(item["mismatch"] for item in needs)  # Haldor's 12 % under
    with Session(desk) as session:
        first = queue_deadline_notifications(session, now=TODAY_AT(11))
        again = queue_deadline_notifications(session, now=TODAY_AT(11) + timedelta(minutes=5))
        session.commit()
        assert first >= 1 and again == 0
        rows = session.query(NotificationOutboxRecord).all()
        titles = [row.title for row in rows]
        # Routed to scheduling (M7); an ``alert`` subscription still receives it.
        assert {row.category for row in rows} == {"nomination"}
        assert all(row.body.endswith("If not acted on: Trader.") for row in rows)
    assert any("Brae North" in title for title in titles)


def test_today_carries_the_checklist_as_row_seven(desk):
    from eurogas_nexus.application.desk_today import build_today

    with Session(desk) as session:
        today = build_today(session, _caller("demo.operations"), now=TODAY_AT(11),
                            balance_reader=lambda: None)
    keys = [row["key"] for row in today["rows"]]
    assert keys[5:] == ["gas_day", "checklist"]
    assert today["rows"][6]["populated"] is True
    assert any(item["kind"] == "nomination" for item in today["rows"][4]["items"])


def test_an_unsent_lng_send_out_is_due_at_the_nomination_cut_off_not_the_last_renomination(
        desk):
    # QA-T-08. Tomorrow's send-out is still to send; its deadline is the nomination cut-off
    # (D-1 13:00 UTC, the network-code default), passed or not, as for a contract's
    # nomination: due soon at 11:00, overdue at 14:00, never "36 h left" on the renomination.
    _, items = _items(desk, "demo.nl.trader", "tomorrow", now=TODAY_AT(11))
    send_out = next(item for (ref, step), item in items.items() if step == "lng_send_out")
    assert send_out["status"]["status"] == "to_send"
    assert send_out["deadline"]["key"] == "nomination"
    assert send_out["deadline"]["at_utc"] == "2026-11-19T13:00:00+00:00"
    assert send_out["urgency"] == "due_soon"
    _, items = _items(desk, "demo.nl.trader", "tomorrow", now=TODAY_AT(14))
    send_out = next(item for (ref, step), item in items.items() if step == "lng_send_out")
    assert send_out["deadline"]["at_utc"] == "2026-11-19T13:00:00+00:00"
    assert send_out["deadline"]["passed"] is True and send_out["urgency"] == "overdue"
    # Once recorded as sent, the next deadline is the last renomination still ahead.
    with Session(desk) as session:
        record_status(session, _caller("demo.nl.trader"), gas_day=TOMORROW,
                      line_ref=send_out["ref"], step="lng_send_out", status="sent",
                      quantity_mwh=4_800, note=None, now=TODAY_AT(14))
        session.commit()
    _, items = _items(desk, "demo.nl.trader", "tomorrow", now=TODAY_AT(14))
    send_out = next(item for (ref, step), item in items.items() if step == "lng_send_out")
    assert send_out["deadline"]["key"] == "last_renomination"
    assert send_out["urgency"] == "open"


def test_a_nomination_row_names_the_outage_at_its_source(desk):
    _, items = _items(desk, "demo.trader")
    haldor = items[("contract:demo-haldor-24", "nomination")]
    assert [(item["source"], item["id"]) for item in haldor["outages"]] == [
        ("REMIT", "demo-umm-1")]
    assert items[("contract:demo-brae-10", "nomination")]["outages"] == []
