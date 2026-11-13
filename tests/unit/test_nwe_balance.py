"""NW Europe balance: measured call, component forecasts, outages and storage trajectory."""

from datetime import date, timedelta

from eurogas_nexus.domain.fundamentals.balance import (
    BalanceHistoryDay,
    Outage,
    fit_weather_model,
    forecast_balance,
)

START = date(2026, 11, 1)


def _history(days: int, call=lambda d: 3000.0):
    out = []
    for back in range(days, 0, -1):
        day = START - timedelta(days=back)
        total = call(day)
        out.append(BalanceHistoryDay(day, 1000.0, 400.0, total - 1400.0))
    return out


def test_call_is_measured_and_norway_outages_shift_supply_to_storage():
    result = forecast_balance(
        _history(40),
        start=START,
        days=5,
        norway_outages=[Outage(START + timedelta(days=1), START + timedelta(days=3), 150.0)],
        inventory_twh=100.0,
        working_capacity_twh=120.0,
    )
    first, second = result.days[0], result.days[1]
    assert first.call_gwh == 3000.0 and first.methods["call"] == "28_day_average"
    assert first.norway_gwh == 1000.0 and second.norway_gwh == 850.0
    assert second.storage_net_withdrawal_gwh == first.storage_net_withdrawal_gwh + 150.0
    assert result.days[0].inventory_twh == 100.0 - 1.6
    assert result.days[-1].fill_pct < first.fill_pct
    assert any("degree-day" in w for w in result.warnings)


def test_seasonal_normal_plus_recent_anomaly_uses_earlier_years():
    # Two years of history: the call follows the season; the last two weeks run 200 above.
    def call(day):
        seasonal = 3000.0 + 1000.0 * (1 if day.month in (12, 1, 2) else 0)
        return seasonal + (200.0 if day >= START - timedelta(days=14) else 0.0)

    result = forecast_balance(_history(800, call), start=START, days=3)
    assert result.days[0].methods["call"] == "seasonal_normal_plus_recent_anomaly"
    assert round(result.days[0].call_gwh) == 3200


def test_weather_regression_recovers_the_hdd_slope():
    hdd = {}
    history = []
    for back in range(60, 0, -1):
        day = START - timedelta(days=back)
        hdd[day] = 5 + back % 10
        call = 1500 + 120 * hdd[day] + (-200 if day.weekday() >= 5 else 0)
        history.append(BalanceHistoryDay(day, 1000.0, 400.0, call - 1400.0))
    model = fit_weather_model(history, hdd)
    assert round(model.slope_per_hdd) == 120 and round(model.weekend_effect) == -200
    assert model.r2 > 0.99
    hdd[START] = 12
    result = forecast_balance(history, start=START, days=1, hdd=hdd)
    assert result.days[0].methods["call"] == "weather_regression"
    assert round(result.days[0].call_gwh) == 1500 + 120 * 12 + (-200 if START.weekday() >= 5 else 0)


def test_existing_outage_is_not_subtracted_twice_and_ending_outage_restores_supply():
    history = [
        BalanceHistoryDay(START - timedelta(days=i), 800, 400, 1800) for i in range(40, 0, -1)
    ]
    result = forecast_balance(
        history,
        start=START,
        days=3,
        norway_outages=[Outage(START - timedelta(days=10), START + timedelta(days=2), 200)],
    )
    assert result.days[0].norway_gwh == 800
    assert result.days[1].norway_gwh == 800
    assert result.days[2].norway_gwh == 1000
    assert result.days[0].norway_recent_outage_baseline_gwh == 200


def test_inventory_projection_draws_only_on_the_facilities_in_the_inventory():
    # 1,600 GWh/d net withdrawal region-wide, of which 400 from storage outside the
    # inventory (GB publishes no working capacity, so its stock is not in inventory_twh).
    history = [
        BalanceHistoryDay(
            START - timedelta(days=back), 1000.0, 400.0, 1600.0,
            inventory_scope_net_withdrawal_gwh=1200.0,
        )
        for back in range(40, 0, -1)
    ]
    result = forecast_balance(
        history, start=START, days=2, inventory_twh=100.0, working_capacity_twh=120.0
    )
    first, second = result.days
    # The call still uses all storage: the regional draw is unchanged.
    assert first.call_gwh == 3000.0 and first.storage_net_withdrawal_gwh == 1600.0
    # The inventory falls by its own facilities' share only.
    assert first.inventory_draw_gwh == 1200.0
    assert first.inventory_twh == 100.0 - 1.2
    assert second.inventory_twh == 100.0 - 2.4
    assert first.methods["inventory_draw"] == "residual_less_14_day_average_outside_inventory"


def test_a_28_day_fallback_far_from_the_last_week_says_so():
    # Live, 13 Nov 2026: a 46-day history, so no seasonal normal; the 28-day average call
    # was 7.7 TWh/d against 9.9 TWh/d over the last week, and the storage draw fell to 0.5.
    rising = forecast_balance(
        _history(30, call=lambda d: 7000.0 if d < START - timedelta(days=7) else 10000.0),
        start=START,
        days=3,
    )
    assert rising.days[0].methods["call"] == "28_day_average"
    assert any("likely understated" in w and "28-day average" in w for w in rising.warnings)
    # A steady history gives no such warning.
    steady = forecast_balance(_history(30), start=START, days=3)
    assert not any("28-day average (" in w for w in steady.warnings)


def test_a_seasonal_normal_from_one_year_says_it_replays_that_year():
    # Live, 13 Nov 2026: 418 days of history, so the normal for mid-November is November
    # 2025 alone, cold spell included.
    one_year = forecast_balance(_history(400), start=START, days=3)
    assert one_year.days[0].methods["call"] == "seasonal_normal_plus_recent_anomaly"
    assert any("rests on one earlier year (2025)" in w for w in one_year.warnings)
    two_years = forecast_balance(_history(800), start=START, days=3)
    assert not any("rests on one earlier year" in w for w in two_years.warnings)
