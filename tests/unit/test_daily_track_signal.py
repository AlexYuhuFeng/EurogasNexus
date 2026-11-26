"""A daily track advises the signal of the latest close, not the position it already holds."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from eurogas_nexus.application import spread_history, spreads_workbench, strategy_tracking
from eurogas_nexus.db.models import StrategyTrackRecord

SPEC = {"version": 1, "kind": "history", "unit": "EUR/MWh",
        "legs": [{"hub": "TTF", "tenor": "day-ahead", "weight": 1},
                 {"hub": "NBP", "tenor": "day-ahead", "weight": -1}],
        "rule": {"kind": "zscore", "lookback": 20, "entry_z": 2.0, "exit_z": 0.5}}


class _Session:
    def __init__(self):
        self.added = []

    def add(self, row):
        self.added.append(row)


def _record() -> StrategyTrackRecord:
    return StrategyTrackRecord(
        track_id="trk-test", owner_principal_id="p", name="t", mode="daily", state="active",
        spec_json=SPEC, rule_json=SPEC["rule"], instruments=[], book_state={}, snapshot=None,
        created_at_utc=datetime(2026, 11, 1, tzinfo=UTC), evaluations=0,
    )


def test_the_entry_signal_is_advised_at_the_close_that_decided_it(monkeypatch):
    # The latest close (z = -2.4) decided "long"; under next-close execution the rule holds
    # nothing yet (position 0) and buys at the next close.
    points = [
        {"date": "2026-11-23", "spread": -1.2, "zscore": -0.4, "signal": 0, "position": 0,
         "pnl": 0.0},
        {"date": "2026-11-24", "spread": -3.1, "zscore": -2.4, "signal": 1, "position": 0,
         "pnl": 0.0},
    ]
    monkeypatch.setattr(strategy_tracking, "_owner_caller", lambda session, owner: object())
    monkeypatch.setattr(spreads_workbench, "load_holdings", lambda caller, today: None)
    monkeypatch.setattr(spreads_workbench, "stored_tenor", lambda holdings, hub, tenor: tenor)
    monkeypatch.setattr(spread_history, "spread_history", lambda body, caller: {
        "data": {"points": points, "unit": "EUR/MWh", "limitations": []}})
    record = _record()
    record.snapshot = {"signal": "flat"}
    strategy_tracking.evaluate_daily(_Session(), record, datetime(2026, 11, 25, 6, tzinfo=UTC))
    assert record.snapshot["signal"] == "long"
    assert record.snapshot["position"] == 0
    assert record.snapshot["advice"]["signal"] == "long"
    assert record.snapshot["trade_at"] == "next close"


def test_a_daily_rule_the_engine_would_refuse_is_refused_when_saved():
    spec = {**SPEC, "rule": {"kind": "zscore", "entry_z": 0.5, "exit_z": 1.0}}

    class _Principal:
        principal_id = "p"

    class _Query:
        def filter(self, *args):
            return self

        def scalar(self):
            return 0

    class _CountingSession:
        def query(self, *args):
            return _Query()

    with pytest.raises(strategy_tracking.TrackError) as caught:
        strategy_tracking.create_track(_CountingSession(), _Principal(), name="bad", spec=spec,
                                       mode="daily")
    assert caught.value.code == "spec.rule"
    assert "exit_z" in str(caught.value)
