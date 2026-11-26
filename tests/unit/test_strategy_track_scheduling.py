"""A newly created track evaluates only itself, not every user's tracks."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from eurogas_nexus.application import strategy_tracking
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import StrategyTrackRecord

ROOT = Path(__file__).resolve().parents[2]


def _track(track_id: str) -> StrategyTrackRecord:
    return StrategyTrackRecord(
        track_id=track_id, owner_principal_id="p", name=track_id, mode="daily",
        state="active", spec_json={}, rule_json={}, instruments=[], book_state={},
        created_at_utc=datetime(2026, 11, 1, tzinfo=UTC), evaluations=0,
    )


def test_run_due_can_be_limited_to_the_new_track(monkeypatch):
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine, tables=[StrategyTrackRecord.__table__])
    session = sessionmaker(engine)()
    session.add_all([_track("trk-mine"), _track("trk-someone-else")])
    session.flush()
    seen: list[str] = []
    monkeypatch.setattr(strategy_tracking, "evaluate_daily",
                        lambda session, record, now: seen.append(record.track_id))
    strategy_tracking.run_due(session, datetime(2026, 11, 25, tzinfo=UTC),
                              track_ids=["trk-mine"])
    assert seen == ["trk-mine"]
    # The scheduler's call (positional ``now``, no filter) still evaluates every due track.
    strategy_tracking.run_due(session, datetime(2026, 11, 25, tzinfo=UTC))
    assert sorted(seen) == ["trk-mine", "trk-mine", "trk-someone-else"]


def test_the_create_route_evaluates_only_the_track_it_created():
    route = (ROOT / "src/eurogas_nexus/api/routes/public/strategy_tracks.py").read_text()
    assert "run_due(session)" not in route
    assert 'run_due(session, track_ids=[data["track_id"]])' in route
