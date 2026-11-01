"""The daily gas balance: supply plus purchases minus sales, and what a miss costs."""

from __future__ import annotations

from datetime import date, timedelta

from eurogas_nexus.domain.portfolio.daily_balance import BalanceLeg, daily_balance

D0 = date(2026, 11, 2)
DAYS = [D0, D0 + timedelta(days=1)]


def test_residual_counts_supply_exchange_and_bilateral_trades() -> None:
    legs = [
        BalanceLeg("C1", date(2026, 10, 1), date(2027, 9, 30), 24_000, "supply"),
        # A November month sold on the exchange: 15,000 MWh a day.
        BalanceLeg("M1", date(2026, 11, 1), date(2026, 11, 30), -15_000, "exchange"),
        # Day-ahead sold bilaterally for the first day only.
        BalanceLeg("DA", D0, D0, -8_000, "bilateral"),
        # Within-day bought back on the second day.
        BalanceLeg("WD", D0 + timedelta(days=1), D0 + timedelta(days=1), 2_000, "exchange"),
    ]
    first, second = daily_balance(
        DAYS, legs, delivery_ratio=0.98, short_premium_per_mwh=1.5, long_discount_per_mwh=0.6
    )
    # 24,000 x 0.98 = 23,520 expected; 23,520 - 15,000 - 8,000 = 520 still to sell.
    assert first["supply"] == 23_520 and first["residual_mwh"] == 520
    assert first["state"] == "long" and first["cash_out_cost"] == 312.0
    assert first["bilateral_sold"] == 8_000 and first["exchange_sold"] == 15_000
    # 23,520 + 2,000 - 15,000 = 10,520 open on the second day.
    assert second["residual_mwh"] == 10_520 and second["exchange_bought"] == 2_000


def test_short_day_costs_the_premium_and_a_small_residual_is_balanced() -> None:
    legs = [
        BalanceLeg("C1", D0, D0, 10_000, "supply"),
        BalanceLeg("S1", D0, D0, -10_500, "exchange"),
    ]
    (short,) = daily_balance([D0], legs, short_premium_per_mwh=2.0)
    assert short["state"] == "short" and short["cash_out_cost"] == 1_000.0
    (flat,) = daily_balance([D0], legs, flat_band_mwh=600)
    assert flat["state"] == "balanced" and flat["cash_out_cost"] == 0.0
    (unpriced,) = daily_balance([D0], legs)
    assert unpriced["cash_out_cost"] is None
