"""Position ladder: physical and financial legs by hub and month, MtM and historical VaR."""

from datetime import date, timedelta

import pytest

from eurogas_nexus.domain.portfolio.position_ladder import (
    PositionLeg,
    build_ladder,
    historical_var,
    ladder_report,
)

NOV, DEC = date(2026, 11, 1), date(2026, 12, 1)


def _legs():
    return [
        # Upstream supply: long 10,000 MWh/d at TTF for Nov and Dec at 30.
        PositionLeg("physical", "TTF", NOV, date(2026, 12, 31), 10_000, price=30.0),
        # Hedge: sold 6,000 MWh/d TTF Nov-26 at 34.
        PositionLeg("financial", "TTF", NOV, date(2026, 11, 30), -6_000, price=34.0),
        # NBP hub sale for December.
        PositionLeg("physical", "NBP", DEC, date(2026, 12, 31), -2_000, price=33.0),
    ]


def test_ladder_by_hub_and_month_with_hedge_ratio():
    rows = build_ladder(_legs(), horizon_start=NOV, horizon_end=date(2027, 1, 31))
    by_key = {(r.hub, r.month): r for r in rows}
    nov = by_key[("TTF", "2026-11")]
    assert (nov.physical_mwh, nov.financial_mwh, nov.net_mwh) == (300_000, -180_000, 120_000)
    assert nov.hedge_ratio == pytest.approx(0.6)
    assert by_key[("TTF", "2026-12")].net_mwh == 310_000
    assert by_key[("NBP", "2026-12")].physical_mwh == -62_000
    assert [r.month for r in rows] == ["2026-11", "2026-12", "2026-12"]


def test_mark_to_market_and_unpriced_legs():
    marks = {("TTF", "2026-11"): 35.0, ("TTF", "2026-12"): 36.0}
    report = ladder_report(_legs(), horizon_start=NOV, horizon_end=date(2026, 12, 31), marks=marks)
    # TTF supply: (35-30)*300k + (36-30)*310k; hedge: (35-34)*(-180k). NBP has no mark.
    assert report.mark_to_market == pytest.approx(5 * 300_000 + 6 * 310_000 - 180_000)
    assert report.unpriced_rows == 1


def test_historical_var_needs_history_and_scales_with_position():
    closes = {date(2026, 9, 1) + timedelta(days=i): 30 + (i % 5) * 0.5 for i in range(41)}
    var, n = historical_var({"TTF": 100_000}, {"TTF": closes})
    assert n == 40
    assert var == pytest.approx(200_000)  # worst daily move is -2.0 EUR/MWh on 100,000 MWh
    assert historical_var({"TTF": 100_000}, {"TTF": dict(list(closes.items())[:5])})[0] is None
    flat, _ = historical_var({"TTF": 0.0}, {"TTF": closes})
    assert flat == 0.0


def test_nothing_valued_is_unknown_not_zero():
    report = ladder_report(_legs(), horizon_start=NOV, horizon_end=date(2026, 12, 31), marks={})
    assert report.mark_to_market is None
    assert report.unpriced_rows == 4
