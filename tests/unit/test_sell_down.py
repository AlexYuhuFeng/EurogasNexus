"""Day-ahead versus within-day sell-down (newsvendor)."""

from __future__ import annotations

import pytest

from eurogas_nexus.domain.portfolio.sell_down import SellDownInputs, _expected_cost, plan_sell_down


def test_a_costly_shortfall_keeps_a_buffer_back():
    plan = plan_sell_down(
        SellDownInputs(
            240_000,
            6_000,
            da_price=34.0,
            wd_expected_price=33.8,
            short_penalty_per_mwh=2.0,
            long_discount_per_mwh=0.3,
        )
    )
    assert plan.critical_ratio == pytest.approx(0.5 / (1.8 + 0.5))
    assert plan.sell_day_ahead_mwh < 240_000 and plan.keep_within_day_mwh > 0
    assert plan.sell_day_ahead_mwh % 24 == 0
    assert plan.expected_cost_vs_perfect < plan.sell_all_cost_vs_perfect
    assert plan.probability_short < 0.5


def test_a_weak_within_day_market_sells_more_now():
    plan = plan_sell_down(
        SellDownInputs(
            240_000,
            6_000,
            da_price=34.0,
            wd_expected_price=32.0,
            short_penalty_per_mwh=0.2,
            long_discount_per_mwh=0.5,
        )
    )
    assert plan.critical_ratio > 0.5 and plan.sell_day_ahead_mwh > 240_000 - 24


def test_certain_supply_sells_everything_and_the_optimum_is_a_minimum():
    sure = plan_sell_down(SellDownInputs(100_000, 0, 34.0, 33.5, 1.0, 0.2))
    assert sure.sell_day_ahead_mwh == 99_984  # lots of 24 MWh
    best = plan_sell_down(SellDownInputs(240_000, 6_000, 34.0, 33.8, 2.0, 0.3))
    q = best.sell_day_ahead_mwh
    around = [
        _expected_cost(q + d, 240_000, 6_000, best.cost_over_per_mwh, best.cost_under_per_mwh)
        for d in (-2_400, 2_400)
    ]
    assert all(cost >= best.expected_cost_vs_perfect - 1 for cost in around)
