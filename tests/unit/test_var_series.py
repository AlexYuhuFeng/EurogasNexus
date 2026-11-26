"""VaR price series: one product per hub, moves within one contract, a stated minimum sample.

Quant review 2026-11-26 (section 3.1): day-ahead closes filled month-ahead gaps, the month-ahead
roll was booked as a one-day move, and 20-39 scenarios gave "the single worst day" as a 95 % VaR.
"""

from datetime import UTC, date, datetime, timedelta

import pytest

from eurogas_nexus.application.position_inputs import hub_close_series
from eurogas_nexus.domain.market.returns import contract_move, contract_returns
from eurogas_nexus.domain.portfolio.position_ladder import (
    VAR_MIN_OBSERVATIONS,
    PositionLeg,
    historical_var,
    ladder_report,
)

START = date(2025, 9, 1)


def _row(day, tenor, price, *, source="ICE_ENDEX", start=None, days=30, simulated=False):
    first = start or (day.replace(day=1) + timedelta(days=32)).replace(day=1)
    begin = datetime.combine(first, datetime.min.time(), tzinfo=UTC)
    return {
        "hub": "TTF",
        "hub_resolved": True,
        "tenor": tenor,
        "source_system": source,
        "day": day,
        "observed_at_utc": datetime.combine(day, datetime.min.time(), tzinfo=UTC)
        + timedelta(hours=17),
        "period_start_utc": begin,
        "period_end_utc": begin + timedelta(days=days),
        "price_mwh": price,
        "simulated": simulated,
    }


def _weekdays(count):
    day, out = START, []
    while len(out) < count:
        if day.weekday() < 5:
            out.append(day)
        day += timedelta(days=1)
    return out


def test_day_ahead_never_fills_a_month_ahead_gap():
    """The review's minimal example: MA flat at 30, DA 35 on the days MA is missing."""

    rows = []
    for index, day in enumerate(_weekdays(300)):
        if index % 10 == 5:
            rows.append(_row(day, "day-ahead", 35.0, start=day + timedelta(days=1), days=1))
        else:
            rows.append(_row(day, "month-ahead", 30.0))
    series = hub_close_series(rows)["TTF"]
    assert series.tenor == "month-ahead"
    assert set(series.closes.values()) == {30.0}
    var, _n = historical_var(
        {"TTF": 372_000}, {"TTF": series.closes}, contracts_by_hub={"TTF": series.contracts}
    )
    # Before: 1,860,000 (5 EUR/MWh x 372,000 MWh) with no true price move.
    assert var == 0.0


def test_one_source_per_hub_not_arrival_order():
    rows = []
    for day in _weekdays(40):
        rows.append(_row(day, "month-ahead", 30.0, source="EEX"))
        if day.day % 3 == 0:
            rows.append(_row(day, "month-ahead", 31.0, source="BROKER"))
    series = hub_close_series(rows)["TTF"]
    assert series.source_system == "EEX"
    assert set(series.closes.values()) == {30.0}


def test_a_hub_with_only_day_ahead_uses_that_one_product():
    rows = [
        _row(day, "day-ahead", 30.0 + (day.day % 2), start=day + timedelta(days=1), days=1)
        for day in _weekdays(30)
    ]
    series = hub_close_series(rows)["TTF"]
    assert series.tenor == "day-ahead"
    assert len(series.closes) == 30


def test_the_move_across_a_roll_is_not_a_price_move():
    assert contract_move(30.0, 34.0, ("2026-10-01", 31), ("2026-11-01", 30)) is None
    assert contract_move(30.0, 34.0, ("2026-10-01", 31), ("2026-10-01", 31)) == 4.0
    # A day-ahead series is a new delivery every close by nature: not a roll.
    assert contract_move(30.0, 34.0, ("2026-10-01", 1), ("2026-10-02", 1)) == 4.0
    days = [date(2026, 9, 28), date(2026, 9, 29), date(2026, 9, 30), date(2026, 10, 1)]
    closes = dict(zip(days, (30.0, 30.5, 30.0, 34.0), strict=True))
    contracts = {
        day: ("2026-10-01", 31) if day.month == 9 else ("2026-11-01", 30) for day in days
    }
    assert contract_returns(closes, contracts) == {days[1]: 0.5, days[2]: -0.5}


def test_var_ignores_roll_jumps():
    """A flat contract with a +-4 jump at each roll has no price risk."""

    closes, contracts = {}, {}
    for day in _weekdays(300):
        delivery = (day.replace(day=1) + timedelta(days=32)).replace(day=1)
        closes[day] = 30.0 + (4.0 if delivery.month % 2 else 0.0)
        contracts[day] = (delivery.isoformat(), 30)
    var, n = historical_var(
        {"TTF": 100_000}, {"TTF": closes}, contracts_by_hub={"TTF": contracts},
        confidence=0.99,
    )
    assert n >= VAR_MIN_OBSERVATIONS
    assert var == 0.0
    # Without the contracts, each roll was a 4 EUR/MWh "move" in the tail.
    unaware, _ = historical_var({"TTF": 100_000}, {"TTF": closes}, confidence=0.99)
    assert unaware == pytest.approx(400_000)


def test_var_below_the_minimum_sample_is_not_a_number():
    assert VAR_MIN_OBSERVATIONS == 250
    closes = {day: 30.0 + (index % 5) * 0.5 for index, day in enumerate(_weekdays(40))}
    var, n = historical_var({"TTF": 100_000}, {"TTF": closes})
    assert (var, n) == (None, 39)
    report = ladder_report(
        [PositionLeg("financial", "TTF", date(2026, 12, 1), date(2026, 12, 31), 100)],
        horizon_start=date(2026, 12, 1),
        horizon_end=date(2026, 12, 31),
        daily_closes_by_hub={"TTF": closes},
    )
    assert report.var_95_1d is None
    note = report.as_dict()["notes"][-1]
    assert note["code"] == "VAR_SHORT_HISTORY"
    assert note["params"] == {"count": 39, "minimum": 250}
    assert "not enough history" in report.warnings[-1]
