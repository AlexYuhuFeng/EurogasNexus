"""CAM gas-day calendar tests (versioned, DST-aware, compatibility).

The default corrected calendar is ``EU-CAM-UTC-2025`` (CAM Article 3(16)):
05:00 UTC winter / 04:00 UTC during DST. The legacy ``EU-CAM-2025`` rule is
frozen and tested separately so historical reproducibility is preserved.
"""

from datetime import UTC, datetime

import pytest

from eurogas_nexus.domain.market.gas_day import (
    DEFAULT_GAS_DAY_CALENDAR,
    EU_CAM_CALENDAR,
    EU_CAM_UTC_CALENDAR,
    GAS_DAY_CALENDARS,
    UK_LEGACY_CALENDAR,
    gas_day_interval_utc,
    gas_day_label,
    gas_day_start_for_date,
    gas_day_start_utc,
)


def test_corrected_winter_gas_day_starts_0500_utc() -> None:
    instant = datetime(2025, 1, 15, 12, 0, tzinfo=UTC)
    assert gas_day_start_utc(instant) == datetime(2025, 1, 15, 5, 0, tzinfo=UTC)


def test_corrected_summer_gas_day_starts_0400_utc() -> None:
    instant = datetime(2025, 7, 15, 12, 0, tzinfo=UTC)
    assert gas_day_start_utc(instant) == datetime(2025, 7, 15, 4, 0, tzinfo=UTC)


def test_corrected_instant_before_gas_day_start_belongs_to_previous_gas_day() -> None:
    instant = datetime(2025, 1, 15, 4, 59, tzinfo=UTC)
    assert gas_day_start_utc(instant) == datetime(2025, 1, 14, 5, 0, tzinfo=UTC)


def test_corrected_naive_instant_is_treated_as_utc() -> None:
    assert gas_day_start_utc(datetime(2025, 1, 15, 12, 0)) == datetime(
        2025, 1, 15, 5, 0, tzinfo=UTC
    )


def test_corrected_spring_forward_gas_day_is_23_hours() -> None:
    # EU DST 2025 starts 2025-03-30 01:00 UTC (02:00 CET -> 03:00 CEST).
    instant = datetime(2025, 3, 30, 3, 30, tzinfo=UTC)
    start, end = gas_day_interval_utc(instant)
    assert start == datetime(2025, 3, 29, 5, 0, tzinfo=UTC)
    assert end == datetime(2025, 3, 30, 4, 0, tzinfo=UTC)
    assert (end - start).total_seconds() == 23 * 3600


def test_corrected_fall_back_gas_day_is_25_hours() -> None:
    # EU DST 2025 ends 2025-10-26 01:00 UTC (03:00 CEST -> 02:00 CET).
    instant = datetime(2025, 10, 26, 0, 30, tzinfo=UTC)
    start, end = gas_day_interval_utc(instant)
    assert start == datetime(2025, 10, 25, 4, 0, tzinfo=UTC)
    assert end == datetime(2025, 10, 26, 5, 0, tzinfo=UTC)
    assert (end - start).total_seconds() == 25 * 3600


def test_legacy_eu_cam_2025_rule_is_frozen_unchanged() -> None:
    winter = gas_day_start_utc(
        datetime(2025, 1, 15, 12, 0, tzinfo=UTC), calendar=EU_CAM_CALENDAR
    )
    summer = gas_day_start_utc(
        datetime(2025, 7, 15, 12, 0, tzinfo=UTC), calendar=EU_CAM_CALENDAR
    )
    assert winter == datetime(2025, 1, 15, 4, 0, tzinfo=UTC)
    assert summer == datetime(2025, 7, 15, 3, 0, tzinfo=UTC)


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
    assert gas_day_label(datetime(2025, 1, 15, 4, 30, tzinfo=UTC)) == "2025-01-14"
    assert gas_day_label(datetime(2025, 1, 15, 5, 0, tzinfo=UTC)) == "2025-01-15"


def test_unsupported_calendar_raises() -> None:
    with pytest.raises(ValueError, match="Unsupported gas-day calendar"):
        gas_day_start_utc(datetime(2025, 1, 15, 12, 0, tzinfo=UTC), calendar="NOPE")


def test_corrected_calendar_is_default_and_legacy_is_retained() -> None:
    assert DEFAULT_GAS_DAY_CALENDAR == EU_CAM_UTC_CALENDAR
    ref = GAS_DAY_CALENDARS[EU_CAM_UTC_CALENDAR]
    assert ref.local_start_time.hour == 6
    assert ref.timezone_name == "Europe/Berlin"
    assert "05:00 UTC winter" in ref.description
    legacy_ref = GAS_DAY_CALENDARS[EU_CAM_CALENDAR]
    assert legacy_ref.local_start_time.hour == 5
    assert "frozen" in legacy_ref.description.lower()
