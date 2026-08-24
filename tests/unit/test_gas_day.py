"""CAM gas-day calendar tests (DST-aware, versioned)."""

from datetime import UTC, datetime

import pytest

from eurogas_nexus.domain.market.gas_day import (
    EU_CAM_CALENDAR,
    UK_LEGACY_CALENDAR,
    gas_day_interval_utc,
    gas_day_label,
    gas_day_start_for_date,
    gas_day_start_utc,
)


def test_winter_gas_day_starts_0400_utc() -> None:
    instant = datetime(2025, 1, 15, 12, 0, tzinfo=UTC)
    assert gas_day_start_utc(instant) == datetime(2025, 1, 15, 4, 0, tzinfo=UTC)


def test_summer_gas_day_starts_0300_utc() -> None:
    instant = datetime(2025, 7, 15, 12, 0, tzinfo=UTC)
    assert gas_day_start_utc(instant) == datetime(2025, 7, 15, 3, 0, tzinfo=UTC)


def test_instant_before_gas_day_start_belongs_to_previous_gas_day() -> None:
    instant = datetime(2025, 1, 15, 3, 59, tzinfo=UTC)
    assert gas_day_start_utc(instant) == datetime(2025, 1, 14, 4, 0, tzinfo=UTC)


def test_naive_instant_is_treated_as_utc() -> None:
    assert gas_day_start_utc(datetime(2025, 1, 15, 12, 0)) == datetime(
        2025, 1, 15, 4, 0, tzinfo=UTC
    )


def test_spring_forward_gas_day_is_23_hours() -> None:
    # EU DST 2025 starts 2025-03-30 01:00 UTC (02:00 CET -> 03:00 CEST).
    instant = datetime(2025, 3, 30, 1, 30, tzinfo=UTC)
    start, end = gas_day_interval_utc(instant)
    assert start == datetime(2025, 3, 29, 4, 0, tzinfo=UTC)
    assert end == datetime(2025, 3, 30, 3, 0, tzinfo=UTC)
    assert (end - start).total_seconds() == 23 * 3600


def test_fall_back_gas_day_is_25_hours() -> None:
    # EU DST 2025 ends 2025-10-26 01:00 UTC (03:00 CEST -> 02:00 CET).
    instant = datetime(2025, 10, 26, 0, 30, tzinfo=UTC)
    start, end = gas_day_interval_utc(instant)
    assert start == datetime(2025, 10, 25, 3, 0, tzinfo=UTC)
    assert end == datetime(2025, 10, 26, 4, 0, tzinfo=UTC)
    assert (end - start).total_seconds() == 25 * 3600


def test_uk_legacy_calendar_uses_uk_local_time() -> None:
    assert gas_day_start_utc(
        datetime(2025, 1, 15, 12, 0, tzinfo=UTC), calendar=UK_LEGACY_CALENDAR
    ) == datetime(2025, 1, 15, 5, 0, tzinfo=UTC)
    assert gas_day_start_utc(
        datetime(2025, 7, 15, 12, 0, tzinfo=UTC), calendar=UK_LEGACY_CALENDAR
    ) == datetime(2025, 7, 15, 4, 0, tzinfo=UTC)


def test_gas_day_start_for_date_matches_containing_instant() -> None:
    assert gas_day_start_for_date(datetime(2025, 6, 1).date()) == gas_day_start_utc(
        datetime(2025, 6, 1, 12, 0, tzinfo=UTC)
    )


def test_gas_day_label_is_stable_calendar_date() -> None:
    assert gas_day_label(datetime(2025, 7, 15, 12, 0, tzinfo=UTC)) == "2025-07-15"
    assert gas_day_label(datetime(2025, 1, 15, 2, 0, tzinfo=UTC)) == "2025-01-14"


def test_unsupported_calendar_raises() -> None:
    with pytest.raises(ValueError, match="Unsupported gas-day calendar"):
        gas_day_start_utc(datetime(2025, 1, 15, 12, 0, tzinfo=UTC), calendar="NOPE")


def test_calendar_version_is_explicit() -> None:
    from eurogas_nexus.domain.market.gas_day import GAS_DAY_CALENDARS

    ref = GAS_DAY_CALENDARS[EU_CAM_CALENDAR]
    assert ref.local_start_time.hour == 5
    assert "CET" in ref.description
