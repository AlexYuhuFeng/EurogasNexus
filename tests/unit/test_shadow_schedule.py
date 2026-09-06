"""Unit tests for shadow schedule and lifecycle semantics."""

from datetime import UTC, datetime, timedelta

import pytest

from eurogas_nexus.domain.shadow.schedule import (
    next_scheduled_instant,
    next_scheduled_time,
)


def test_interval_schedule_is_deterministic_from_activation() -> None:
    activated = datetime(2026, 7, 1, 0, 0, tzinfo=UTC)
    schedule = {"type": "INTERVAL", "interval_seconds": 300, "missed_policy": "SKIP"}

    first = next_scheduled_instant(
        schedule=schedule, activated_at=activated, after=activated
    )
    second = next_scheduled_instant(
        schedule=schedule, activated_at=activated, after=first
    )

    assert first == activated + timedelta(seconds=300)
    assert second == activated + timedelta(seconds=600)


def test_daily_at_schedule_is_utc_wall_clock() -> None:
    activated = datetime(2026, 3, 28, 0, 0, tzinfo=UTC)
    schedule = {"type": "DAILY_AT", "daily_at_utc": "15:00", "missed_policy": "SKIP"}

    first = next_scheduled_instant(
        schedule=schedule, activated_at=activated, after=activated
    )
    second = next_scheduled_instant(
        schedule=schedule, activated_at=activated, after=first
    )

    assert first == datetime(2026, 3, 28, 15, 0, tzinfo=UTC)
    assert second == datetime(2026, 3, 29, 15, 0, tzinfo=UTC)


def test_dst_transition_days_remain_explicit_utc() -> None:
    # Spring-forward and autumn-back are ordinary UTC clock days for DAILY_AT;
    # gas-day resolution is owned by the shared calendar elsewhere.
    schedule = {"type": "DAILY_AT", "daily_at_utc": "05:00", "missed_policy": "SKIP"}
    spring = datetime(2026, 3, 28, 5, 0, tzinfo=UTC)
    autumn = datetime(2026, 10, 25, 5, 0, tzinfo=UTC)

    assert next_scheduled_instant(
        schedule=schedule,
        activated_at=datetime(2026, 3, 1, tzinfo=UTC),
        after=spring - timedelta(seconds=1),
    ) == spring
    assert next_scheduled_instant(
        schedule=schedule,
        activated_at=datetime(2026, 10, 1, tzinfo=UTC),
        after=autumn - timedelta(seconds=1),
    ) == autumn


def test_due_filter_never_returns_future_events() -> None:
    activated = datetime(2026, 7, 1, 0, 0, tzinfo=UTC)
    now = datetime(2026, 7, 1, 0, 6, tzinfo=UTC)
    schedule = {"type": "INTERVAL", "interval_seconds": 3600, "missed_policy": "SKIP"}

    assert next_scheduled_time(
        schedule=schedule, activated_at=activated, after=activated, now=now
    ) is None


def test_invalid_schedule_values_fail_closed() -> None:
    with pytest.raises(ValueError):
        next_scheduled_instant(
            schedule={"type": "INTERVAL", "interval_seconds": 0},
            activated_at=datetime.now(UTC),
            after=datetime.now(UTC),
        )
    with pytest.raises(ValueError):
        next_scheduled_instant(
            schedule={"type": "DAILY_AT", "daily_at_utc": "25:99"},
            activated_at=datetime.now(UTC),
            after=datetime.now(UTC),
        )
