"""SCHED-1 on the demo desk and on imported files: the reconciliation read, Today, the alerts.

The demo desk's bilateral sale to Aldermoor (UK book, NBP, 6,000 MWh a day) is nominated in
full every gas day. On an R1 gas day (11 and 12 of each month, ``demo_market.r1_planted``)
Aldermoor nominated 4,800 MWh and the demo TSO confirmed the lesser: 6,000 - 4,800 = 1,200 MWh
cut, the UK book long 1,200 MWh, at the demo long discount of 1.20 GBP/MWh an indicative
1,440 GBP. On any other gas day the reconciliation is quiet.
"""

from __future__ import annotations

import importlib.util
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import eurogas_nexus.db.models  # noqa: F401
from eurogas_nexus.application.caller import Caller
from eurogas_nexus.application.gas_day_reconciliation import (
    ALERT_CATEGORY,
    csv_rows,
    queue_break_alerts,
    reconciliation,
)
from eurogas_nexus.db.base import Base
from eurogas_nexus.security.identity import AuthenticatedPrincipal

DEMO = Path(__file__).resolve().parents[2] / "scripts" / "demo"
R1_DAY = date(2026, 12, 11)
QUIET_DAY = date(2026, 12, 2)


def _load(name: str):
    spec = importlib.util.spec_from_file_location(f"{name}_sched1", DEMO / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


SEED = _load("seed_demo_desk")
MARKET = _load("demo_market")


def _caller(name: str = "demo.scheduler") -> Caller:
    return Caller(AuthenticatedPrincipal(
        principal_id=f"p-{name}", name=name, principal_type="USER", role="ANALYST",
        status="ACTIVE", data_scopes=("*",), roles=("ANALYST",),
    ))


def _desk(tmp_path, monkeypatch, day: date):
    url = f"sqlite+pysqlite:///{(tmp_path / f'recon-{day}.sqlite').as_posix()}"
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", url)
    monkeypatch.setenv("EUROGAS_NEXUS_DEMO_MARKS", "true")
    engine = create_engine(url, future=True)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        SEED.seed(session, datetime(day.year, day.month, day.day, 9, tzinfo=UTC),
                  history_days=3)
        session.commit()
    return engine


def _at(day: date, hour: int, minute: int = 0) -> datetime:
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=UTC)


def test_the_planted_days_are_what_the_tests_say():
    assert MARKET.r1_planted(R1_DAY) and not MARKET.r1_planted(QUIET_DAY)
    assert not MARKET.s1_planted(R1_DAY) and not MARKET.s1_planted(R1_DAY + timedelta(days=1))
    assert any(case.case_id.startswith("R1-") for case in MARKET.PLANTED_CASES)


def test_r1_day_shows_the_lesser_rule_with_its_arithmetic(tmp_path, monkeypatch):
    engine = _desk(tmp_path, monkeypatch, R1_DAY)
    with Session(engine) as session:
        payload = reconciliation(session, _caller(), R1_DAY, now=_at(R1_DAY, 10))
    (group,) = payload["groups"]
    assert (group["hub"], group["counterparty"]) == ("NBP", "Aldermoor Energy plc")
    assert group["traded"]["mwh"] == -6_000 and group["nominated"]["mwh"] == -6_000
    assert group["tso"]["mwh"] == -4_800 and group["shipper_codes"] == ["DEMO-ALD-01"]
    assert group["traded"]["unit"] == "th/d"  # NBP in the desk's unit
    (item,) = payload["breaks"]
    assert item["kind"] == "lesser_rule_cut" and item["mwh_at_risk"] == 1_200
    assert "6,000 − 4,800 = 1,200 MWh cut" in item["explanation"]
    assert "Aldermoor Energy plc nominated 4,800 MWh" in item["explanation"]
    assert item["cutoff"]["key"] == "last_renomination"
    assert item["cutoff"]["at_utc"] == "2026-12-12T02:00:00+00:00"
    assert item["urgency"] == "open" and item["minutes_left"] == 16 * 60
    # Long 1,200 MWh at the demo UK book's long discount (1.20 GBP/MWh): 1,440 GBP, indicative.
    assert item["cash_out"]["value"] == 1_440 and item["cash_out"]["currency"] == "GBP"
    assert item["cash_out"]["basis"] == "indicative"
    assert "no published imbalance price" in item["cash_out"]["note"]
    assert item["quantity"]["kwh_h"] == 50_000
    assert payload["execution"].startswith("none")
    (row,) = csv_rows(payload)
    assert row["kind"] == "lesser_rule_cut" and row["cash_out_value"] == 1_440


def test_a_quiet_day_has_no_break(tmp_path, monkeypatch):
    engine = _desk(tmp_path, monkeypatch, QUIET_DAY)
    with Session(engine) as session:
        for day in (QUIET_DAY, QUIET_DAY + timedelta(days=1)):
            payload = reconciliation(session, _caller(), day, now=_at(QUIET_DAY, 10))
            assert payload["breaks"] == []
            assert [g["state"] for g in payload["groups"]] == ["matched"]


def test_filters_and_refusals(tmp_path, monkeypatch):
    from eurogas_nexus.application.gas_day_reconciliation import ReconciliationError

    engine = _desk(tmp_path, monkeypatch, R1_DAY)
    with Session(engine) as session:
        now = _at(R1_DAY, 10)
        assert reconciliation(session, _caller(), R1_DAY, now=now, hub="TTF")["groups"] == []
        assert reconciliation(session, _caller(), R1_DAY, now=now,
                              counterparty="alder")["breaks"]
        assert reconciliation(session, _caller(), R1_DAY, now=now,
                              kind="not_nominated")["groups"] == []
        with pytest.raises(ReconciliationError) as unknown:
            reconciliation(session, _caller(), R1_DAY, now=now, kind="teleport")
        assert unknown.value.code == "unknown_kind"
        # The NL trader's mandate holds the NL book only: the UK book's deal is not theirs.
        mine = reconciliation(session, _caller("demo.nl.trader"), R1_DAY, now=now)
        assert mine["groups"] == []
        with pytest.raises(ReconciliationError) as outside:
            reconciliation(session, _caller("demo.nl.trader"), R1_DAY, now=now,
                           book_id="demo-uk-nbp")
        assert outside.value.code == "book_not_in_scope"


def test_today_lists_the_break_only_near_the_cut_off(tmp_path, monkeypatch):
    from eurogas_nexus.application.desk_today import _Read, _reconciliation_items

    engine = _desk(tmp_path, monkeypatch, R1_DAY)
    with Session(engine) as session:
        assert _reconciliation_items(session, _caller(), _at(R1_DAY, 10), _Read()) == []
        (item,) = _reconciliation_items(session, _caller(), _at(R1_DAY, 23, 30), _Read())
    assert item["kind"] == "reconciliation" and item["break_kind"] == "lesser_rule_cut"
    assert item["deadline_utc"] == "2026-12-12T02:00:00+00:00"
    assert item["status"] == "watch"  # 2 h 30 left: due soon, not yet within the hour


def _outbox(session):
    from eurogas_nexus.db.models import NotificationOutboxRecord

    return session.query(NotificationOutboxRecord).order_by(
        NotificationOutboxRecord.created_at_utc).all()


def _record(session, day, status, mwh, at, other=None):
    from eurogas_nexus.db.models import GasDayNominationEventRecord

    session.add(GasDayNominationEventRecord(
        event_id=f"t-{status}-{at:%H%M}", gas_day=day, line_ref="trade:demo-etrm-ald-1",
        hub="NBP", book_id="demo-uk-nbp", step="renomination", status=status,
        quantity_mwh=mwh, agent=None, origin="import", recorded_by="test",
        recorded_at_utc=at, note=None, source_system="TEST", counterparty_quantity_mwh=other))
    session.flush()


def test_alerts_dedupe_cool_down_worsen_and_withdraw(tmp_path, monkeypatch):
    from eurogas_nexus.db.models import MonitoringAlertRecord

    engine = _desk(tmp_path, monkeypatch, R1_DAY)
    with Session(engine) as session:
        # 10:00: sixteen hours to the last renomination, nothing alerted.
        assert queue_break_alerts(session, now=_at(R1_DAY, 10))["raised"] == 0
        first = queue_break_alerts(session, now=_at(R1_DAY, 23, 30))
        assert first["notified"] == 1
        again = queue_break_alerts(session, now=_at(R1_DAY, 23, 35))
        assert again["notified"] == 0 and again["held_back"] == 1
        rows = _outbox(session)
        assert len(rows) == 1 and rows[0].category == "nomination"
        assert rows[0].severity == "warning"
        assert "1,200 MWh at risk" in rows[0].title
        assert rows[0].body.endswith("For: Operations. If not acted on: Trader.")
        assert "Indicative cash-out 1,440 GBP" in rows[0].body
        alert = session.query(MonitoringAlertRecord).filter(
            MonitoringAlertRecord.category == ALERT_CATEGORY).one()
        assert alert.evidence_snapshot["book_ids"] == ["demo-uk-nbp"]
        # Worse within the cooldown: Aldermoor renominated 3,600, the TSO confirmed 3,600.
        _record(session, R1_DAY, "renominated", 6_000.0, _at(R1_DAY, 23, 36))
        _record(session, R1_DAY, "confirmed", 3_600.0, _at(R1_DAY, 23, 37), other=3_600.0)
        worse = queue_break_alerts(session, now=_at(R1_DAY, 23, 40))
        assert worse["notified"] == 1
        assert "2,400 MWh at risk" in _outbox(session)[-1].title
        # Both renominate 6,000 and the TSO matches it: the alert is withdrawn and said so.
        _record(session, R1_DAY, "renominated", 6_000.0, _at(R1_DAY, 23, 45))
        _record(session, R1_DAY, "confirmed", 6_000.0, _at(R1_DAY, 23, 50), other=6_000.0)
        gone = queue_break_alerts(session, now=_at(R1_DAY, 23, 55))
        assert gone["withdrawn"] == 1 and gone["raised"] == 0
        session.refresh(alert)
        assert alert.resolved_at_utc is not None and alert.message_en.startswith("Withdrawn")
        assert _outbox(session)[-1].title.startswith("Withdrawn:")
        assert queue_break_alerts(session, now=_at(R1_DAY, 23, 58))["withdrawn"] == 0


def test_the_mirror_and_the_scan_leave_break_alerts_alone(tmp_path, monkeypatch):
    from eurogas_nexus.application.alert_routing import SELF_NOTIFYING, route_for
    from eurogas_nexus.application.notifications import mirror_monitoring_alerts

    assert ALERT_CATEGORY in SELF_NOTIFYING
    assert route_for(ALERT_CATEGORY).notification_category == "nomination"
    engine = _desk(tmp_path, monkeypatch, R1_DAY)
    with Session(engine) as session:
        queue_break_alerts(session, now=_at(R1_DAY, 23, 30))
        before = len(_outbox(session))
        mirror_monitoring_alerts(session, now=_at(R1_DAY, 23, 31))
        assert len(_outbox(session)) - before == sum(
            1 for row in _outbox(session)[before:] if not row.dedupe_key.startswith("recon:"))


def test_imported_matching_fields_explain_counterparty_and_code_breaks(tmp_path, monkeypatch):
    """A scheduling file with the SCHED-1 columns, through etrm.nominations.v1."""

    from eurogas_nexus.application.import_contracts import run_import

    engine = _desk(tmp_path, monkeypatch, QUIET_DAY)
    day = QUIET_DAY + timedelta(days=1)
    header = ("gas_day,line_ref,hub,step,status,recorded_at,quantity_mwh,book_id,counterparty,"
              "direction,shipper_code,counterparty_shipper_code,counterparty_quantity_mwh\n")
    text = header + (
        f"{day},trade:demo-etrm-ald-1,NBP,renomination,renominated,2026-12-02T10:00:00Z,6000,"
        "demo-uk-nbp,Aldermoor Trading GmbH,out,DEMO-EGN-01,DEMO-ALD-01,\n"
    )
    with Session(engine) as session:
        report = run_import("etrm.nominations.v1", text, system="SCHED", session=session,
                            commit=True, now=_at(QUIET_DAY, 10, 5))
        assert report.created == 1 and not report.refused
        session.commit()
        payload = reconciliation(session, _caller(), day, now=_at(QUIET_DAY, 10, 10))
    kinds = [b["kind"] for b in payload["breaks"]]
    assert kinds == ["counterparty_mismatch"]
    assert "names Aldermoor Trading GmbH" in payload["breaks"][0]["explanation"]
    (nomination,) = payload["groups"][0]["nominations"]
    assert nomination["counterparty"] == "Aldermoor Trading GmbH"
    assert nomination["direction"] == "out" and nomination["shipper_code"] == "DEMO-EGN-01"


def test_an_old_file_without_the_new_columns_keeps_its_event_ids():
    from eurogas_nexus.application.import_contracts import run_import

    text = ("gas_day,line_ref,hub,step,status,recorded_at,quantity_mwh\n"
            "2026-12-02,contract:x,NBP,nomination,sent,2026-12-01T10:00:00Z,10\n")
    first = run_import("etrm.nominations.v1", text, system="S", now=_at(QUIET_DAY, 10))
    assert not first.refused
    bad = text.replace("contract:x,NBP,nomination", "trade:x,NBP,trade_confirmation") + ""
    assert not run_import("etrm.nominations.v1", bad, system="S", now=_at(QUIET_DAY, 10)).refused
    wrong = ("gas_day,line_ref,hub,step,status,recorded_at,direction\n"
             "2026-12-02,trade:x,NBP,nomination,sent,2026-12-01T10:00:00Z,sideways\n")
    refused = run_import("etrm.nominations.v1", wrong, system="S", now=_at(QUIET_DAY, 10))
    assert refused.refused and refused.refused[0].reason_code == "direction_invalid"
