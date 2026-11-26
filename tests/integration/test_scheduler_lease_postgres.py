"""Two schedulers against one PostgreSQL: only one is active; the standby takes over.

Runs when ``EUROGAS_NEXUS_TEST_POSTGRES_URL`` is set (the PostgreSQL CI job).
"""

from __future__ import annotations

import json
import os
import threading

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from eurogas_nexus.application.scheduler_lease import AdvisoryLease, lease_for, touch_heartbeat
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import DataOperationsHeartbeatRecord

_POSTGRES_URL = os.environ.get("EUROGAS_NEXUS_TEST_POSTGRES_URL", "")

pytestmark = pytest.mark.skipif(
    not _POSTGRES_URL.startswith("postgresql"),
    reason="needs EUROGAS_NEXUS_TEST_POSTGRES_URL (the PostgreSQL CI job)",
)


@pytest.fixture()
def engine():
    engine = create_engine(_POSTGRES_URL, future=True)
    Base.metadata.create_all(engine, tables=[DataOperationsHeartbeatRecord.__table__])
    yield engine
    engine.dispose()


def test_second_lease_is_refused_until_the_first_is_released(engine) -> None:
    first = AdvisoryLease(engine, "test-scheduler-a")
    second = AdvisoryLease(engine, "test-scheduler-a")
    try:
        assert first.acquire() is True
        assert first.check() is True
        assert second.acquire() is False
        first.release()
        assert second.acquire() is True
        assert second.check() is True
    finally:
        first.release()
        second.release()


def test_a_killed_lock_connection_is_noticed_and_frees_the_lock(engine) -> None:
    first = AdvisoryLease(engine, "test-scheduler-b")
    second = AdvisoryLease(engine, "test-scheduler-b")
    try:
        assert first.acquire()
        backend = first._connection.execute(text("SELECT pg_backend_pid()")).scalar()
        with engine.connect() as admin:
            admin.execute(text("SELECT pg_terminate_backend(:pid)"), {"pid": backend})
            admin.commit()
        assert first.check() is False
        assert first.lost.is_set()
        assert second.acquire() is True
    finally:
        first.release()
        second.release()


def test_lease_for_a_postgres_session_factory_is_the_advisory_lease(engine) -> None:
    assert isinstance(lease_for(sessionmaker(bind=engine)), AdvisoryLease)


def test_touch_heartbeat_writes_the_row(engine) -> None:
    factory = sessionmaker(bind=engine)
    touch_heartbeat(factory)
    with factory() as session:
        row = session.get(DataOperationsHeartbeatRecord, "primary")
        assert row is not None and row.last_heartbeat_at_utc is not None


def test_two_scheduler_loops_only_one_scans(engine, monkeypatch) -> None:
    """The real loop: a second process sharing the database stays a standby."""

    from scripts.ops import run_dataops_scheduler as scheduler

    factory = sessionmaker(bind=engine)
    monkeypatch.setattr(scheduler, "resolve_database_url", lambda: _POSTGRES_URL)
    monkeypatch.setattr(scheduler, "get_session_factory", lambda: factory)
    scans: list[str] = []
    gate = threading.Event()
    release = threading.Event()

    def fake_scan(session, **kwargs):
        scans.append(threading.current_thread().name)
        gate.set()
        release.wait(10)
        return {}

    monkeypatch.setattr(scheduler, "scan_scheduler", fake_scan)
    monkeypatch.setattr(scheduler, "activate_keyed_sources", lambda *a, **k: [])
    monkeypatch.setattr(
        scheduler, "execute_claimed_runs", lambda *a, **k: {"outcomes": []}
    )
    for name in ("evaluate_opportunities_if_due", "deliver_market_events"):
        monkeypatch.setattr(scheduler, name, lambda *a, **k: {})
    monkeypatch.setattr(scheduler, "track_strategies_if_due", lambda *a, **k: {})
    results: dict[str, int] = {}

    def active() -> None:
        results["active"] = scheduler.run_loop(
            interval_seconds=60,
            max_iterations=1,
            emit=lambda line: None,
            entsog_lookback_gas_days=7,
        )

    thread = threading.Thread(target=active, name="active")
    thread.start()
    assert gate.wait(10), "the first scheduler never scanned"
    reports: list[str] = []
    results["standby"] = scheduler.run_loop(
        interval_seconds=60, max_iterations=1, emit=reports.append, entsog_lookback_gas_days=7
    )
    release.set()
    thread.join(10)
    assert scans == ["active"]
    assert results == {"active": 0, "standby": 3}
    assert json.loads(reports[0])["status"] == "standby"
