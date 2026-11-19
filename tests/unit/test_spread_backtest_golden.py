"""A golden series for the daily spread backtest, worked by hand (strategy audit 2026-11-19).

The arithmetic pinned here is the one the independent recomputation used: the signal at a
close is traded at the next close; a month contract's move across its roll is not P&L; the
currency P&L is the size per gas day times the gas days the held contract delivers; a cost per
MWh is charged on entry and exit.
"""

from datetime import date, timedelta

import pytest

from eurogas_nexus.domain.research.spread_analysis import SpreadLeg, SpreadRule, analyse_spread

START = date(2026, 11, 1)
VALUES = [0.0, 0.0, 0.0, 0.0, 0.0, 1.5, 1.2, 0.8, 0.5, 0.3, 2.0, 1.0, -0.2, -0.1, 0.0]
RULE = SpreadRule(kind="threshold", lookback=5, low=-1.0, high=1.0, volume_mwh_per_day=10,
                  cost_per_mwh=0.05)


def _days():
    return [START + timedelta(days=index) for index in range(len(VALUES))]


def _leg(*, deliveries=True):
    days = _days()
    contracts = {
        day: (("2026-12-01", 31) if index < 10 else ("2027-01-01", 31))
        for index, day in enumerate(days)
    }
    return SpreadLeg("TTF M+1", 1.0, dict(zip(days, VALUES, strict=True)),
                     contracts if deliveries else None)


def test_golden_roll_sizing_cost_and_next_close():
    result = analyse_spread([_leg()], RULE)
    by_day = {point.day: point for point in result.points}
    day = _days()
    assert by_day[day[5]].signal == -1 and by_day[day[5]].position == 0
    assert by_day[day[6]].position == -1
    # Short from the close of day 6 (1.2): 31 gas days × 10 MWh/d per EUR/MWh.
    assert by_day[day[6]].pnl == pytest.approx(-15.5)  # entry cost 0.05 × 10 × 31
    assert by_day[day[7]].pnl == pytest.approx(124.0)
    assert by_day[day[8]].pnl == pytest.approx(93.0)
    assert by_day[day[9]].pnl == pytest.approx(62.0)
    assert by_day[day[10]].roll is True and by_day[day[10]].pnl == 0.0  # the +1.7 roll jump
    assert by_day[day[11]].pnl == pytest.approx(310.0)
    assert by_day[day[12]].pnl == pytest.approx(372.0)
    assert by_day[day[13]].pnl == pytest.approx(-31.0 - 15.5)
    assert result.metrics["total_pnl"] == pytest.approx(899.0)
    assert result.metrics["roll_days_excluded"] == 1
    assert result.metrics["pnl_per_mwh"] == pytest.approx(2.9)
    [trade] = result.trades
    assert (trade.opened, trade.closed, trade.direction) == (day[6], day[13], "short")
    assert (trade.entry_spread, trade.exit_spread) == (1.2, -0.1)
    assert trade.pnl == pytest.approx(899.0)
    assert trade.pnl_per_mwh == pytest.approx(2.9)
    assert trade.holding_days == 7
    assert result.metrics["worst_trade"] == pytest.approx(899.0)
    assert result.metrics["too_few_trades"] is True
    assert "too few" in result.limitations[0]
    assert result.metrics["max_drawdown"] == pytest.approx(-46.5)  # day 13 from the peak
    assert "roll is not counted" in result.assumptions


def test_without_contracts_the_roll_jump_would_be_counted():
    result = analyse_spread([_leg(deliveries=False)], RULE)
    # One gas day per close and the +1.7 jump charged to the short: what the audit found.
    assert result.metrics["roll_days_excluded"] == 0
    assert result.metrics["total_pnl"] == pytest.approx(10 * (0.4 + 0.3 + 0.2 - 1.7 + 1.0 + 1.2
                                                              - 0.1) - 2 * 0.5)


def test_same_close_execution_is_optional_and_named():
    same = analyse_spread([_leg()], SpreadRule(**{**RULE.identity(), "execution": "same_close"}))
    assert same.trades[0].opened == _days()[5]
    assert "same close" in same.assumptions


def test_a_spread_that_does_not_move_has_no_zscore():
    days = _days() + [START + timedelta(days=15 + i) for i in range(20)]
    # 2.9871 held to float noise (what the demo's Win-27 − Sum-27 is): no z, no trade.
    values = {day: 3.1 - 0.1129 + (1e-12 if i % 2 else 0.0) for i, day in enumerate(days)}
    result = analyse_spread([SpreadLeg("W-S", 1.0, values)], SpreadRule(lookback=10))
    assert result.statistics["zscore_last"] is None
    assert result.metrics["trades"] == 0


def test_the_rule_reads_the_net_spread_and_pnl_the_gross():
    days = _days()
    tariff = {day: 1.88 for day in days}
    leg = SpreadLeg("NBP-TTF", 1.0, {day: 1.88 + value for day, value in zip(days, VALUES,
                                                                              strict=True)})
    net = analyse_spread([leg], RULE, signal_offsets=tariff)
    gross = analyse_spread([_leg(deliveries=False)], RULE)
    assert [point.signal for point in net.points] == [point.signal for point in gross.points]
    assert net.points[5].signal_level == pytest.approx(1.5)
    assert net.points[5].spread == pytest.approx(3.38)
    assert net.metrics["total_pnl"] == pytest.approx(gross.metrics["total_pnl"])
    assert "net of the route tariff" in net.assumptions


def test_out_of_sample_period_is_the_later_share():
    result = analyse_spread([_leg()], RULE)
    assert result.periods["out_of_sample"]["from"] == _days()[10].isoformat()
    total = result.periods["in_sample"]["pnl"] + result.periods["out_of_sample"]["pnl"]
    assert total == pytest.approx(result.metrics["total_pnl"])
