"""Scheduled reports: kept by administrators, run by the worker as the service principal,
delivered in-app to the distribution roles and by e-mail through the notification outbox."""

from __future__ import annotations

import importlib.util
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import eurogas_nexus.db.models  # noqa: F401
from eurogas_nexus.application.caller import Caller
from eurogas_nexus.application.reports import schedule as S
from eurogas_nexus.application.reports.store import list_reports
from eurogas_nexus.db.base import Base
from eurogas_nexus.security.identity import AuthenticatedPrincipal

SEED = Path(__file__).resolve().parents[2] / "scripts" / "demo" / "seed_demo_desk.py"
NOW = datetime(2026, 11, 9, 6, 45, tzinfo=UTC)  # a Monday, after 06:30 UTC


def _principal(pid: str, role: str, kind: str = "USER") -> AuthenticatedPrincipal:
    return AuthenticatedPrincipal(principal_id=pid, name=pid, principal_type=kind, role=role,
                                  status="ACTIVE", data_scopes=("DEMO",), roles=(role,))


@pytest.fixture(scope="module")
def store(tmp_path_factory):
    path = tmp_path_factory.mktemp("schedules") / "desk.sqlite"
    url = f"sqlite+pysqlite:///{path}"
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("RUNTIME_STORE_DATABASE_URL", url)
        mp.setenv("EUROGAS_NEXUS_DEMO_MARKS", "true")
        engine = create_engine(url)
        Base.metadata.create_all(engine)
        spec = importlib.util.spec_from_file_location("seed_demo_desk", SEED)
        seed = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(seed)
        with Session(engine) as session:
            seed.seed(session, NOW)
            session.commit()
        yield engine, url


@pytest.fixture
def env(store, monkeypatch):
    engine, url = store
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", url)
    monkeypatch.setenv("EUROGAS_NEXUS_DEMO_MARKS", "true")
    return engine


def test_a_schedule_is_validated_and_its_slot_is_the_latest_time_passed():
    daily = S.validate_schedule({"kind": "daily", "at_utc": "06:30", "roles": ["analyst"]},
                                now=NOW)
    assert daily["roles"] == ["ANALYST"] and daily["sections"] and daily["language"] == "en"
    assert S.latest_slot(daily, NOW) == datetime(2026, 11, 9, 6, 30, tzinfo=UTC)
    assert S.latest_slot(daily, NOW.replace(hour=6, minute=0)) == datetime(
        2026, 11, 8, 6, 30, tzinfo=UTC)
    weekly = S.validate_schedule({"kind": "weekly", "at_utc": "07:00", "weekday": 4,
                                  "roles": ["VIEWER"], "language": "zh-CN"}, now=NOW)
    assert S.latest_slot(weekly, NOW) == datetime(2026, 11, 6, 7, 0, tzinfo=UTC)  # Friday
    for bad in ({"kind": "monthly", "roles": ["ANALYST"]}, {"at_utc": "25:00", "roles": ["A"]},
                {"roles": []}, {"roles": ["TRADER"]}):
        with pytest.raises(S.ScheduleError):
            S.validate_schedule(bad, now=NOW)


def test_the_worker_generates_a_due_report_once_delivers_it_to_its_roles_and_queues_mail(env):
    from eurogas_nexus.db.models import NotificationOutboxRecord

    service = Caller(_principal("svc-reports", "ANALYST", "SERVICE"))
    with Session(env) as session:
        # Saved before the slot: the slot of the save itself is recorded as run.
        S.replace_schedules(session, [{"schedule_id": "morning", "kind": "daily",
                                       "at_utc": "06:30", "roles": ["ANALYST"],
                                       "email": True}],
                            actor="admin", now=NOW - timedelta(days=1, hours=1))
        session.commit()
        first = S.run_due(session, now=NOW, caller=service)
        again = S.run_due(session, now=NOW + timedelta(minutes=1), caller=service)
        outbox = session.query(NotificationOutboxRecord).filter_by(category="report").all()
        analyst = list_reports(session, Caller(_principal("a1", "ANALYST")))
        viewer = list_reports(session, Caller(_principal("v1", "VIEWER")))
    assert [o["status"] for o in first] == ["generated"] and again == []
    report_id = first[0]["report_id"]
    assert report_id in {r["report_id"] for r in analyst}
    assert report_id not in {r["report_id"] for r in viewer}  # not in its distribution
    assert len(outbox) == 1 and "Research → Reports" in outbox[0].body


def test_a_slot_missed_for_hours_is_skipped_and_no_service_principal_refuses(env):
    with Session(env) as session:
        S.replace_schedules(session, [{"schedule_id": "late", "kind": "daily",
                                       "at_utc": "06:30", "roles": ["ANALYST"]}],
                            actor="admin", now=NOW - timedelta(days=2))
        session.commit()
        late = S.run_due(session, now=NOW + timedelta(hours=8), caller=None)
    assert [o["status"] for o in late] == ["skipped_late"]
