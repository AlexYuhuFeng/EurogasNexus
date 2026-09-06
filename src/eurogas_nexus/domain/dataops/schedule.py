"""Pure, deterministic data-operations scheduling.

The scheduler math is intentionally shared with the CR-06 shadow scheduler
shape, but source schedules carry provider timezones and market-relative
gas-day offsets, so this module is the single owner of that math for ingestion.
"""

from __future__ import annotations

from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from eurogas_nexus.domain.dataops.contracts import (
    ScheduleType,
    SourceCalendar,
    SourceDefinition,
    as_utc,
)
from eurogas_nexus.domain.market.gas_day import (
    EU_CAM_UTC_CALENDAR,
    gas_day_start_utc,
)

MISSED_POLICIES = frozenset({"SKIP", "CATCH_UP_LIMITED", "RUN_LATEST_ONLY"})


def validate_schedule(definition: SourceDefinition) -> None:
    """Validate a typed schedule and raise ValueError when malformed."""

    spec = definition.schedule
    if spec.schedule_type == ScheduleType.INTERVAL:
        if not spec.interval_seconds or int(spec.interval_seconds) <= 0:
            raise ValueError("INTERVAL schedule requires positive interval_seconds")
    elif spec.schedule_type in {ScheduleType.DAILY, ScheduleType.MARKET_RELATIVE}:
        if not spec.daily_at and spec.schedule_type == ScheduleType.DAILY:
            raise ValueError("DAILY schedule requires daily_at HH:MM")
        if spec.daily_at:
            parse_daily_time(spec.daily_at)
    if spec.missed_policy not in MISSED_POLICIES:
        raise ValueError(f"Unsupported missed policy: {spec.missed_policy}")


def parse_daily_time(value: str) -> time:
    """Parse ``HH:MM`` in the source timezone."""

    hour_text, minute_text = value.split(":", maxsplit=1)
    hour = int(hour_text)
    minute = int(minute_text)
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError(f"Invalid daily time: {value}")
    return time(hour=hour, minute=minute)


def next_scheduled_instant(
    definition: SourceDefinition,
    *,
    activated_at: datetime,
    after: datetime,
) -> datetime | None:
    """Return the next schedule time strictly after ``after``.

    ``EXTERNAL`` schedules have no automatic next instant (the scheduler only
    monitors expected latency). ``INTERVAL`` advances in fixed seconds from
    activation. ``DAILY`` uses source-timezone wall-clock time.
    ``MARKET_RELATIVE`` is anchored to the corrected CAM gas day.
    """

    spec = definition.schedule
    if spec.schedule_type == ScheduleType.EXTERNAL:
        return None

    anchor = as_utc(activated_at)
    previous = as_utc(after)

    if spec.schedule_type == ScheduleType.INTERVAL:
        interval_seconds = int(spec.interval_seconds or 3600)
        elapsed = (previous - anchor).total_seconds()
        steps = int(elapsed // interval_seconds) + 1
        return anchor + timedelta(seconds=steps * interval_seconds)

    if spec.schedule_type == ScheduleType.MARKET_RELATIVE:
        offset = int(spec.market_relative_offset_seconds or 0)
        gas_day_start = gas_day_start_utc(previous, calendar=EU_CAM_UTC_CALENDAR)
        candidate = gas_day_start + timedelta(seconds=offset)
        if candidate <= previous:
            candidate = gas_day_start_utc(
                candidate + timedelta(seconds=1), calendar=EU_CAM_UTC_CALENDAR
            ) + timedelta(seconds=offset)
        return candidate

    daily_at = parse_daily_time(str(spec.daily_at or "00:00"))
    zone = ZoneInfo(spec.timezone or "UTC")
    current = previous.astimezone(zone)
    candidate = datetime.combine(current.date(), daily_at, tzinfo=zone)
    if candidate <= current:
        candidate = datetime.combine(current.date() + timedelta(days=1), daily_at, tzinfo=zone)
    return candidate.astimezone(UTC)


def update_expected(
    definition: SourceDefinition,
    *,
    now_utc: datetime,
) -> bool:
    """Return whether a source update is expected at ``now``.

    This is calendar awareness only. ``GAS_MARKET`` sources trade and publish
    every day; ``WEEKDAYS_ONLY`` sources (ECB) are not expected Saturday or
    Sunday in their declared timezone.
    """

    current = as_utc(now_utc)
    if definition.calendar == SourceCalendar.WEEKDAYS_ONLY:
        zone = ZoneInfo(definition.schedule.timezone or "UTC")
        return current.astimezone(zone).weekday() < 5
    return True


def next_expected_after(
    definition: SourceDefinition,
    *,
    now_utc: datetime,
) -> datetime | None:
    """Return the next time an update is expected (used for NOT_EXPECTED)."""

    if update_expected(definition, now_utc=now_utc):
        return next_scheduled_instant(
            definition,
            activated_at=as_utc(now_utc),
            after=as_utc(now_utc),
        )
    if definition.calendar == SourceCalendar.WEEKDAYS_ONLY:
        zone = ZoneInfo(definition.schedule.timezone or "UTC")
        current = as_utc(now_utc).astimezone(zone)
        days_until_monday = (7 - current.weekday()) % 7 or 7
        monday = current.date() + timedelta(days=days_until_monday)
        daily_at = (
            parse_daily_time(str(definition.schedule.daily_at))
            if definition.schedule.daily_at
            else time(hour=0)
        )
        return datetime.combine(monday, daily_at, tzinfo=zone).astimezone(UTC)
    return None


def missed_schedule_note(
    *,
    previous: datetime | None,
    next_time: datetime | None,
    now_utc: datetime,
    missed_policy: str,
) -> str | None:
    """Return a MISSED_SCHEDULE note when a gap existed and policy tracks it."""

    if previous is None or next_time is None:
        return None
    if missed_policy == "SKIP":
        return None
    previous_utc = as_utc(previous)
    next_utc = as_utc(next_time)
    now = as_utc(now_utc)
    if next_utc <= now:
        return f"MISSED_SCHEDULE:{previous_utc.isoformat()}:{next_utc.isoformat()}"
    return None
