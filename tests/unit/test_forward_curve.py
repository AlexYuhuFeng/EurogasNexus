"""Forward curve: months from quoted months, quarters, seasons and years, day-weighted."""

from datetime import date

import pytest

from eurogas_nexus.domain.market.forward_curve import CurveQuote, build_forward_curve


def q(first, end, price, label):
    return CurveQuote("TTF", first, end, price, label=label)


def _by_month(curve):
    return {p.month: p for p in curve.points}


def test_quarter_residual_respects_quoted_month_and_day_weights():
    quotes = [
        q(date(2027, 1, 1), date(2027, 2, 1), 40.0, "Jan-27"),
        q(date(2027, 1, 1), date(2027, 4, 1), 38.0, "Q1-27"),
    ]
    curve = _by_month(build_forward_curve(quotes, first_month=date(2027, 1, 1)))
    assert curve["2027-01"].method == "quoted"
    feb, mar = curve["2027-02"], curve["2027-03"]
    assert feb.method == mar.method == "derived" and feb.source == "Q1-27"
    # Day-weighted average of the three months equals the quarter.
    assert (40 * 31 + feb.price * 28 + mar.price * 31) / 90 == pytest.approx(38.0)
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
    total = sum(
        p.price * d
        for p, d in zip(
            [months[f"2027-{m:02d}"] for m in range(1, 13)],
            [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31],
            strict=True,
        )
    )
    assert total / 365 == pytest.approx(34.0)


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
