"""Forward curve from one consistent snapshot (quant review 2026-11-26, section 3.2).

The curve kept the latest quote per window over ten days across sources and price types, so
today's January met a nine-day-old Q1 and Feb/Mar became the price move between the two; and
unquoted months were filled flat with the hub's latest close, which could be a day-ahead price.
"""

from datetime import UTC, date, datetime, timedelta

import pytest

from eurogas_nexus.application.position_inputs import curve_snapshot
from eurogas_nexus.domain.market.forward_curve import (
    CurveQuote,
    build_forward_curve,
    gas_day_hours,
)

TODAY = date(2026, 11, 26)


def _row(first, end, price, *, days_old=0, source="EEX", label="", **extra):
    observed = datetime.combine(TODAY - timedelta(days=days_old), datetime.min.time(), tzinfo=UTC)
    return {
        "hub": "TTF",
        "label": label,
        "first": first,
        "end": end,
        "price": price,
        "source_system": source,
        "observed_at": observed + timedelta(hours=17),
        "settlement": False,
        "price_type": None,
        **extra,
    }


JAN, FEB, APR = date(2027, 1, 1), date(2027, 2, 1), date(2027, 4, 1)


def test_a_stale_quarter_never_meets_todays_month():
    """The review's example: today's Jan at 32 and a nine-day-old Q1 at 30."""

    quotes, left_out = curve_snapshot(
        [_row(JAN, APR, 30.0, days_old=9, label="Q1-27"), _row(JAN, FEB, 32.0, label="Jan-27")]
    )
    assert [(q.first_day, q.price) for q in quotes] == [(JAN, 32.0)]
    assert left_out == [
        "TTF: 1 product(s) quoted only longer ago than their tenor allows against the curve's "
        "as-of 2026-11-26; left out of the curve"
    ]
    curve = build_forward_curve(quotes, first_month=JAN, last_month=date(2027, 3, 1))
    points = {p.month: p for p in curve.points}
    assert points["2027-01"].basis == "quoted" and points["2027-01"].age_days == 0
    # Before: Feb = Mar = 28.948 (the price move between the two timestamps).
    assert points["2027-02"].price is None and points["2027-02"].basis == "not available"
    assert ("TTF", "2027-02") not in curve.marks()


def test_one_sided_prices_and_day_ahead_windows_stay_out_of_the_curve():
    quotes, _ = curve_snapshot(
        [
            _row(JAN, FEB, 31.0, price_type="bid"),
            _row(JAN, FEB, 33.0, price_type="ask"),
            _row(TODAY + timedelta(days=1), TODAY + timedelta(days=2), 45.0, label="DA"),
        ]
    )
    assert quotes == []


def test_settlement_then_primary_source_then_newest():
    rows = [
        _row(JAN, FEB, 32.0, source="BROKER", days_old=0),
        _row(FEB, date(2027, 3, 1), 31.0, source="BROKER", days_old=0),
        _row(JAN, FEB, 31.5, source="EEX", days_old=1, settlement=True),
        _row(date(2027, 3, 1), APR, 29.0, source="ICE", days_old=0),
        _row(date(2027, 3, 1), APR, 29.5, source="BROKER", days_old=1),
    ]
    quotes, _ = curve_snapshot(rows)
    by_month = {q.first_day.month: q for q in quotes}
    assert by_month[1].price == 31.5 and by_month[1].reference == "EEX"  # the settlement
    assert by_month[2].reference == "BROKER"
    # March: the primary source (BROKER quotes the most windows on the as-of day) first.
    assert by_month[3].price == 29.5 and by_month[3].reference == "BROKER"
    assert by_month[3].as_of == TODAY - timedelta(days=1)


def test_a_day_ahead_price_never_prices_the_current_month():
    quotes = [
        CurveQuote("TTF", date(2026, 11, 27), date(2026, 11, 28), 45.0, label="DA"),
        CurveQuote("TTF", date(2026, 12, 1), date(2027, 1, 1), 34.0, label="Dec-26"),
    ]
    curve = build_forward_curve(quotes, first_month=date(2026, 11, 26),
                                last_month=date(2026, 12, 31))
    points = {p.month: p for p in curve.points}
    assert points["2026-11"].method == "not_available"
    bom = CurveQuote("TTF", date(2026, 11, 27), date(2026, 12, 1), 33.0, label="BOM")
    curve = build_forward_curve([*quotes, bom], first_month=date(2026, 11, 26))
    point = {p.month: p for p in curve.points}["2026-11"]
    assert (point.method, point.price, point.basis) == ("front", 33.0, "balance of month (BOM)")


def _hours(year, month):
    day, total = date(year, month, 1), 0
    while day.month == month:
        total += gas_day_hours(day)
        day += timedelta(days=1)
    return total


def test_a_season_beyond_the_quoted_quarters_takes_their_shape():
    quotes = [
        CurveQuote("TTF", date(2026, 10, 1), date(2027, 1, 1), 40.0, label="Q4-26"),
        CurveQuote("TTF", date(2027, 1, 1), date(2027, 4, 1), 44.0, label="Q1-27"),
        CurveQuote("TTF", date(2027, 10, 1), date(2028, 4, 1), 42.0, label="Win-27"),
    ]
    points = {p.month: p for p in build_forward_curve(quotes, first_month=date(2026, 10, 1)).points}
    oct27, jan28 = points["2027-10"], points["2028-01"]
    assert oct27.basis == "derived from Win-27"
    assert jan28.price / oct27.price == pytest.approx(44.0 / 40.0)
    months = [(2027, m) for m in (10, 11, 12)] + [(2028, m) for m in (1, 2, 3)]
    hours = {key: _hours(*key) for key in months}
    average = sum(points[f"{y}-{m:02d}"].price * h for (y, m), h in hours.items()) / sum(
        hours.values()
    )
    assert average == pytest.approx(42.0)
