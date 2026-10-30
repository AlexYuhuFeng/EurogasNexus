"""Spread analysis: construction, statistics and a look-ahead-free rule backtest."""

from datetime import date, timedelta

import pytest

from eurogas_nexus.domain.research.spread_analysis import (
    SpreadAnalysisError,
    SpreadLeg,
    SpreadRule,
    analyse_spread,
)

START = date(2026, 9, 1)


def _series(values):
    return {START + timedelta(days=index): value for index, value in enumerate(values)}


def test_weighted_spread_and_statistics_on_common_days():
    nbp = _series([32.0 + 0.1 * i for i in range(40)])
    ttf = _series([31.0 + 0.1 * i for i in range(40)])
    del ttf[START + timedelta(days=3)]  # a missing close drops that day for both legs
    result = analyse_spread(
        [SpreadLeg("NBP DA", 1.0, nbp), SpreadLeg("TTF DA", -1.0, ttf)],
        SpreadRule(lookback=10),
    )
    assert result.statistics["days"] == 39
    assert result.statistics["last"] == pytest.approx(1.0)
    assert result.statistics["std"] == pytest.approx(0.0, abs=1e-9)
    assert result.points[0].legs == (32.0, 31.0)
    assert len(result.analysis_hash) == 64


def test_zscore_rule_trades_without_look_ahead():
    # Flat around 1.0, a spike to 3.0 on day 30, back to 1.0 after.
    values = [1.0 + (0.05 if i % 2 else -0.05) for i in range(40)]
    values[30] = 3.0
    leg = SpreadLeg("A-B", 1.0, _series(values))
    rule = SpreadRule(lookback=20, entry_z=2.0, exit_z=0.5, volume_mwh_per_day=100, cost_per_mwh=0)
    result = analyse_spread([leg], rule)
    by_day = {point.day: point for point in result.points}
    spike = START + timedelta(days=30)
    assert by_day[spike].position == -1  # short decided at the spike close
    assert by_day[spike].pnl == 0  # nothing earned on the day the position opens
    after = START + timedelta(days=31)
    # The short earns the fall from 3.0 to ~1.0 on the next day: 100 MWh * ~2.0.
    assert by_day[after].pnl == pytest.approx(100 * (3.0 - values[31]))
    assert result.trades[0].direction == "short"
    assert result.metrics["total_pnl"] > 0


def test_threshold_rule_and_costs():
    values = [0.0, -1.0, -1.5, -0.5, 0.2, 0.0, 1.2, 0.8, -0.1] * 4
    rule = SpreadRule(kind="threshold", lookback=5, low=-1.0, high=1.0,
                      volume_mwh_per_day=10, cost_per_mwh=0.1)
    result = analyse_spread([SpreadLeg("S", 1.0, _series(values))], rule)
    assert result.metrics["trades"] >= 2
    assert {trade.direction for trade in result.trades} == {"long", "short"}
    # Each position change costs 0.1 * 10 = 1.0 versus the same rule without costs.
    free = analyse_spread(
        [SpreadLeg("S", 1.0, _series(values))],
        SpreadRule(kind="threshold", lookback=5, low=-1.0, high=1.0,
                   volume_mwh_per_day=10, cost_per_mwh=0.0),
    )
    positions = [0] + [point.position for point in result.points]
    changes = sum(abs(b - a) for a, b in zip(positions, positions[1:], strict=False))
    assert result.metrics["total_pnl"] == pytest.approx(free.metrics["total_pnl"] - changes * 1.0)


@pytest.mark.parametrize(
    "rule",
    [
        SpreadRule(kind="magic"),
        SpreadRule(lookback=2),
        SpreadRule(entry_z=1.0, exit_z=1.5),
        SpreadRule(kind="threshold", low=2, high=1),
        SpreadRule(volume_mwh_per_day=0),
    ],
)
def test_bad_rules_are_refused(rule):
    with pytest.raises(SpreadAnalysisError):
        analyse_spread([SpreadLeg("S", 1.0, _series([1.0] * 40))], rule)


def test_too_little_overlap_and_bad_legs_are_refused():
    with pytest.raises(SpreadAnalysisError, match="common days"):
        analyse_spread([SpreadLeg("S", 1.0, _series([1.0] * 10))], SpreadRule(lookback=20))
    with pytest.raises(SpreadAnalysisError):
        analyse_spread([SpreadLeg("S", 0.0, _series([1.0] * 40))], SpreadRule())
    with pytest.raises(SpreadAnalysisError):
        analyse_spread([], SpreadRule())


def test_simulated_sources_are_named_in_limitations():
    result = analyse_spread(
        [SpreadLeg("S", 1.0, _series([1.0, 2.0] * 20))], SpreadRule(lookback=5),
        simulated_sources=True,
    )
    assert result.limitations[0].startswith("Includes simulated")
