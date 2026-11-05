"""Forward curve: months from quoted months, quarters, seasons and years, day-weighted."""

from datetime import date

import pytest

from eurogas_nexus.domain.market.forward_curve import CurveQuote, build_forward_curve, gas_day_hours


def q(first, end, price, label):
    return CurveQuote("TTF", first, end, price, label=label)


def _by_month(curve):
    return {p.month: p for p in curve.points}


def _hours(year, month):
    day, total = date(year, month, 1), 0
    while day.month == month:
        total += gas_day_hours(day)
        day = date.fromordinal(day.toordinal() + 1)
    return total


def test_quarter_residual_respects_quoted_month_and_hour_weights():
    quotes = [
        q(date(2027, 1, 1), date(2027, 2, 1), 40.0, "Jan-27"),
        q(date(2027, 1, 1), date(2027, 4, 1), 38.0, "Q1-27"),
    ]
    curve = _by_month(build_forward_curve(quotes, first_month=date(2027, 1, 1)))
    assert curve["2027-01"].method == "quoted"
    feb, mar = curve["2027-02"], curve["2027-03"]
    assert feb.method == mar.method == "derived" and feb.source == "Q1-27"
    # Hour-weighted average of the three months equals the quarter (March loses an hour).
    jan_h, feb_h, mar_h = _hours(2027, 1), _hours(2027, 2), _hours(2027, 3)
    assert (40 * jan_h + feb.price * feb_h + mar.price * mar_h) / (jan_h + feb_h + mar_h) == (
        pytest.approx(38.0)
    )
    assert feb.price == pytest.approx(mar.price)


def test_seasonal_shape_and_longer_products_fill_only_open_months():
    quotes = [
        q(date(2027, 4, 1), date(2027, 10, 1), 30.0, "Sum-27"),
        q(date(2027, 1, 1), date(2028, 1, 1), 34.0, "Cal-27"),
        q(date(2027, 1, 1), date(2027, 4, 1), 38.0, "Q1-27"),
    ]
    shape = {10: 1.05, 11: 1.1, 12: 1.15}
    curve = build_forward_curve(quotes, first_month=date(2027, 1, 1), shape=shape)
    months = _by_month(curve)
    assert len(months) == 12
    assert months["2027-07"].source == "Sum-27"
    assert months["2027-11"].source == "Cal-27"
    assert months["2027-12"].price > months["2027-10"].price  # shape applied
    hours = [_hours(2027, m) for m in range(1, 13)]
    total = sum(months[f"2027-{m:02d}"].price * hours[m - 1] for m in range(1, 13))
    assert sum(hours) == 8760
    assert total / sum(hours) == pytest.approx(34.0)


def test_no_extrapolation_front_month_from_prompt_and_warnings():
    quotes = [
        q(date(2026, 10, 31), date(2026, 11, 1), 33.0, "DA"),
        q(date(2026, 11, 1), date(2026, 12, 1), 34.0, "Nov-26"),
    ]
    curve = _by_month(build_forward_curve(quotes, first_month=date(2026, 10, 1)))
    assert curve["2026-10"].method == "front"
    assert "2026-12" not in curve
    odd = build_forward_curve(
        [
            q(date(2027, 1, 1), date(2027, 2, 1), 90.0, "Jan-27"),
            q(date(2027, 1, 1), date(2027, 4, 1), 30.0, "Q1-27"),
        ],
        first_month=date(2027, 1, 1),
    )
    assert odd.warnings and _by_month(odd)["2027-02"].warning


def test_summer_time_gas_days_have_23_and_25_hours():
    # 2027: clocks go forward on Sunday 28 March and back on Sunday 31 October at 02:00/03:00
    # CET, inside the gas days that start at 06:00 on the Saturdays before.
    assert gas_day_hours(date(2027, 3, 27)) == 23
    assert gas_day_hours(date(2027, 10, 30)) == 25
    assert gas_day_hours(date(2027, 1, 15)) == 24


def test_a_quarter_weighs_its_months_by_delivery_hours():
    jan = CurveQuote("TTF", date(2027, 1, 1), date(2027, 2, 1), 40.0, label="Jan-27")
    feb = CurveQuote("TTF", date(2027, 2, 1), date(2027, 3, 1), 38.0, label="Feb-27")
    q1 = CurveQuote("TTF", date(2027, 1, 1), date(2027, 4, 1), 37.0, label="Q1-27")
    curve = build_forward_curve([jan, feb, q1], first_month=date(2027, 1, 1))
    march = curve.marks()[("TTF", "2027-03")]
    # March has 743 delivery hours (one lost to summer time), January 744, February 672.
    assert march == pytest.approx((37.0 * 2159 - 40.0 * 744 - 38.0 * 672) / 743)


def test_months_that_do_not_average_to_the_quoted_quarter_are_reported():
    months = [
        CurveQuote("TTF", date(2027, 1, 1), date(2027, 2, 1), 40.0, label="Jan-27"),
        CurveQuote("TTF", date(2027, 2, 1), date(2027, 3, 1), 40.0, label="Feb-27"),
        CurveQuote("TTF", date(2027, 3, 1), date(2027, 4, 1), 40.0, label="Mar-27"),
    ]
    q1 = CurveQuote("TTF", date(2027, 1, 1), date(2027, 4, 1), 37.0, label="Q1-27")
    curve = build_forward_curve([*months, q1], first_month=date(2027, 1, 1))
    assert curve.marks()[("TTF", "2027-01")] == 40.0  # the month quotes stand
    assert any("Q1-27 quoted 37.000 but its months average 40.000" in w for w in curve.warnings)
    consistent = build_forward_curve(
        [*months, CurveQuote("TTF", date(2027, 1, 1), date(2027, 4, 1), 40.0, label="Q1-27")],
        first_month=date(2027, 1, 1),
    )
    assert consistent.warnings == []
