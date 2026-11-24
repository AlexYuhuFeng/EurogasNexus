"""Tracked strategies are evaluated by the DataOps scheduler, not only when they are created."""

from __future__ import annotations

import importlib.util
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from eurogas_nexus.application import strategy_tracking
from eurogas_nexus.db.base import Base

ROOT = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 11, 24, 9, tzinfo=UTC)


def _script():
    spec = importlib.util.spec_from_file_location(
        "run_dataops_scheduler_tracks", ROOT / "scripts" / "ops" / "run_dataops_scheduler.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _factory(tmp_path):
    engine = create_engine(f"sqlite+pysqlite:///{(tmp_path / 't.sqlite').as_posix()}")
    Base.metadata.create_all(engine)
    return sessionmaker(engine)


def test_each_scheduler_cycle_runs_the_due_tracks(tmp_path, monkeypatch):
    seen = []

    def fake_run_due(session, now=None):
        seen.append(now)
        return {"evaluated": 2}

    monkeypatch.setattr(strategy_tracking, "run_due", fake_run_due)
    result = _script().track_strategies_if_due(_factory(tmp_path), now_utc=NOW)

    assert result == {"status": "ok", "evaluated": 2}
    assert seen == [NOW]


def test_an_empty_store_evaluates_nothing(tmp_path):
    assert _script().track_strategies_if_due(_factory(tmp_path), now_utc=NOW) == {
        "status": "ok",
        "evaluated": 0,
    }


def test_a_failing_track_is_reported_and_never_stops_the_loop(tmp_path, monkeypatch):
    def broken(session, now=None):
        raise RuntimeError("boom")

    monkeypatch.setattr(strategy_tracking, "run_due", broken)
    result = _script().track_strategies_if_due(_factory(tmp_path), now_utc=NOW)
    assert result == {"status": "failed", "error_type": "RuntimeError"}


def test_the_loop_calls_the_hook():
    source = (ROOT / "scripts" / "ops" / "run_dataops_scheduler.py").read_text(encoding="utf-8")
    loop = source[source.index("def run_loop(") :]
    assert "track_strategies_if_due(" in loop
