"""Typed shadow scheduling semantics.

Schedule calculations are pure and deterministic. The scheduler itself lives
in the application layer; this module owns the clock math only.
"""

from __future__ import annotations

from datetime import UTC, datetime, time, timedelta

from eurogas_nexus.domain.ontology.vocabulary import (
    ShadowMissedPolicy,
    ShadowScheduleType,
)


def parse_daily_time(value: str) -> time:
    hour, minute = value.split(":", maxsplit=1)
    return time(hour=int(hour), minute=int(minute))


def next_scheduled_instant(
    *,
    schedule: dict,
    activated_at: datetime,
    after: datetime,
) -> datetime:
    """Return the next schedule time strictly after ``after`` (no now cap)."""

    schedule_type = ShadowScheduleType(str(schedule.get("type", "INTERVAL")))
    if schedule_type == ShadowScheduleType.INTERVAL:
        interval_seconds = int(schedule.get("interval_seconds", 3600))
        if interval_seconds <= 0:
            raise ValueError("interval_seconds must be positive")
        anchor = _as_utc(activated_at)
        previous = _as_utc(after)
        elapsed = (previous - anchor).total_seconds()
        steps = int(elapsed // interval_seconds) + 1
        return anchor + timedelta(seconds=steps * interval_seconds)
    daily_time = parse_daily_time(str(schedule.get("daily_at_utc", "05:00")))
    current = _as_utc(after)
    candidate = datetime.combine(current.date(), daily_time, tzinfo=UTC)
    if candidate <= current:
        candidate = datetime.combine(
            current.date() + timedelta(days=1), daily_time, tzinfo=UTC
        )
    return candidate


def next_scheduled_time(
    *,
    schedule: dict,
    activated_at: datetime,
    after: datetime,
    now: datetime,
) -> datetime | None:
    """Return the next schedule time strictly after ``after``.

    ``INTERVAL`` advances in fixed seconds from activation. ``DAILY_AT`` uses
    explicit UTC wall-clock time. Both return ``None`` when the next event is
    in the future (not yet due).
    """

    candidate = next_scheduled_instant(
        schedule=schedule,
        activated_at=activated_at,
        after=after,
    )
    return candidate if candidate <= _as_utc(now) else None


def missed_schedule_note(
    *,
    previous: datetime,
    next_time: datetime,
    now: datetime,
    missed_policy: str,
) -> str | None:
    """Return a MISSED_SCHEDULE note when a gap existed."""

    policy = ShadowMissedPolicy(missed_policy)
    if policy == ShadowMissedPolicy.SKIP and next_time < _as_utc(now):
        return f"MISSED_SCHEDULE:{previous.isoformat()}:{next_time.isoformat()}"
    return None


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
