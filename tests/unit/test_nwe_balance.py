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
