"""Credit and mandate breaches become monitoring alerts, from the risk pages' own figures."""

from __future__ import annotations

import importlib.util
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import eurogas_nexus.db.models  # noqa: F401  (registers every table)
from eurogas_nexus.application.alert_scope import alert_visibility
from eurogas_nexus.application.caller import firm_caller
from eurogas_nexus.application.limits_service import credit_exposure_rows
from eurogas_nexus.application.monitoring_service import scan_monitoring_conditions
from eurogas_nexus.application.notifications import mirror_monitoring_alerts
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import (
    CreditLineRecord,
    MonitoringAlertRecord,
    NotificationOutboxRecord,
)
from eurogas_nexus.security import portfolio_scope

SEED = Path(__file__).resolve().parents[2] / "scripts" / "demo" / "seed_demo_desk.py"
NOW = datetime(2026, 11, 7, 9, tzinfo=UTC)


@pytest.fixture
def desk(tmp_path, monkeypatch):
    url = f"sqlite+pysqlite:///{tmp_path / 'desk.sqlite'}"
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", url)
    monkeypatch.setenv("EUROGAS_NEXUS_DEMO_MARKS", "true")
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    spec = importlib.util.spec_from_file_location("seed_demo_desk", SEED)
    seed = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(seed)
    with Session(engine) as session:
        seed.seed(session, NOW)
        session.commit()
    return engine


def _scan(engine):
    with Session(engine) as session:
        scan_monitoring_conditions(session, now_utc=NOW, enrich_with_llm=False)
        return {
            row.fingerprint: row
            for row in session.query(MonitoringAlertRecord)
            .filter(MonitoringAlertRecord.category == "limits")
            .all()
        }


def test_the_worker_computes_credit_without_a_request(desk):
    rows = credit_exposure_rows(firm_caller(), NOW.date())
    status = {row["counterparty"]: row["status"] for row in rows.rows}
    assert "breach" in status.values() and "watch" in status.values()
    assert all(books for books in rows.books)  # every line has legs in a book


def test_breach_and_watch_raise_limits_alerts_that_reach_the_limits_channel(desk):
    alerts = _scan(desk)
    with Session(desk) as session:
        lines = {line.counterparty_id: line.name for line in session.query(CreditLineRecord)}
    breach = next(row for row in alerts.values() if row.severity == "critical")
    assert breach.alert_type == "credit"
    assert "credit breach" in breach.title_en and "limit" in breach.title_en
    assert breach.message_en.startswith("Net ")  # figures first, no preamble
    assert any(row.severity == "warning" for row in alerts.values())
    assert {key.split(":", 1)[1] for key in alerts if key.startswith("credit:")} <= set(lines)

    with Session(desk) as session:
        mirror_monitoring_alerts(session, now=NOW)
        session.commit()
        categories = {row.category for row in session.query(NotificationOutboxRecord)}
    assert "limits" in categories


def test_a_failed_calculation_keeps_standing_alerts(desk, monkeypatch):
    first = _scan(desk)
    assert first
    import eurogas_nexus.application.limits_service as service

    def broken(*_args, **_kwargs):
        raise RuntimeError("store down")

    monkeypatch.setattr(service, "credit_exposure_rows", broken)
    again = _scan(desk)
    assert {key for key, row in again.items() if row.resolved_at_utc is None} == set(first)


def test_a_regional_caller_sees_only_limits_alerts_for_its_books(desk, monkeypatch):
    alerts = _scan(desk)
    monkeypatch.setenv(portfolio_scope.ISOLATION_ENV, "true")
    portfolio_scope.set_request_scope(("BOOKS:BOOK:no-such-book",))
    try:
        with Session(desk) as session:
            visible = alert_visibility(session)
            assert not any(visible(row) for row in alerts.values())
            assert visible({"category": "physical"})  # market alerts are for everyone
        portfolio_scope.set_request_scope(("BOOKS:*",))
        with Session(desk) as session:
            assert all(alert_visibility(session)(row) for row in alerts.values())
    finally:
        portfolio_scope._current.set(None)


def test_alerts_on_demo_marks_say_they_are_simulated(desk):
    alerts = _scan(desk)
    assert alerts and all(row.simulated for row in alerts.values())
