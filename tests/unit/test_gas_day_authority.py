"""One gas-day calendar: every module that needs a boundary takes it from the calendar."""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from eurogas_nexus.domain.market.forward_curve import gas_day_hours
from eurogas_nexus.domain.market.gas_day import gas_day_label, gas_day_start_for_date
from eurogas_nexus.ingestion.national_gas_demand import gas_day_period_utc

DAYS = [date(2026, 1, 1) + timedelta(days=offset) for offset in range(730)]


def test_uk_and_continental_wall_clocks_are_the_calendars_instants_every_day():
    """05:00 London and 06:00 Brussels are the same instant, through both clock changes."""

    for day in DAYS:
        start = gas_day_start_for_date(day)
        assert start == datetime.combine(day, time(5), ZoneInfo("Europe/London")).astimezone(UTC)
        assert start == datetime.combine(day, time(6), ZoneInfo("Europe/Brussels")).astimezone(UTC)
        assert gas_day_period_utc(day) == (start, gas_day_start_for_date(day + timedelta(days=1)))


def test_gas_days_are_23_hours_in_march_and_25_in_october():
    lengths = {day: gas_day_hours(day) for day in DAYS}
    assert lengths[date(2026, 3, 28)] == 23  # the gas day that contains the spring change
    assert lengths[date(2026, 10, 24)] == 25
    assert lengths[date(2027, 3, 27)] == 23 and lengths[date(2027, 10, 30)] == 25
    assert sorted(set(lengths.values())) == [23, 24, 25]
    assert sum(1 for hours in lengths.values() if hours != 24) == 4


def test_an_instant_before_the_morning_boundary_belongs_to_the_previous_gas_day():
    assert gas_day_label(datetime(2026, 12, 1, 5, 0, tzinfo=UTC)) == "2026-12-01"
    assert gas_day_label(datetime(2026, 12, 1, 4, 59, tzinfo=UTC)) == "2026-11-30"
    assert gas_day_label(datetime(2026, 7, 1, 4, 0, tzinfo=UTC)) == "2026-07-01"  # summer
    assert gas_day_label(datetime(2026, 7, 1, 3, 59, tzinfo=UTC)) == "2026-06-30"
