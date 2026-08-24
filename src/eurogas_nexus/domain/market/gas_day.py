"""Versioned, DST-aware gas-day calendar helpers.

The European gas day is defined by REMIT Implementing Regulation
(EU) 1348/2014 and the CAM Network Code (Regulation (EU) 2017/459) as the
period from 05:00 hours to 05:00 hours Central European Time / Central
European Summer Time. Great Britain aligned its NBP gas day to the same
definition in 2015-2016 (Ofgem licence modifications; UNC 0461), so the
modern rule for both EU hubs and NBP is:

- winter (CET, UTC+1):  05:00 CET  -> 04:00 UTC
- summer (CEST, UTC+2): 05:00 CEST -> 03:00 UTC

The ``UK-NBP-LEGACY`` calendar (05:00 UK local time -> 05:00/04:00 UTC)
exists only for historical backfill of pre-2016 UK data.

This module is the single implementation used by ingestion, simulation and
analysis so that no caller re-implements gas-day boundaries.

本模块是全仓气体日（gas day）边界的唯一实现：任何调用方（采集、仿真、
分析、Web）都不得自行推算 05:00 CET 边界，DST 切换由 zoneinfo 保证正确。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from enum import StrEnum
from zoneinfo import ZoneInfo

EU_CAM_CALENDAR = "EU-CAM-2025"
UK_LEGACY_CALENDAR = "UK-NBP-LEGACY"

# 时区对象复用：构造开销小但重复创建无意义，模块级缓存一次。
_BERLIN = ZoneInfo("Europe/Berlin")
_LONDON = ZoneInfo("Europe/London")


class GasDayCalendar(StrEnum):
    """Supported gas-day calendars with explicit versions.

    日历以版本字符串标识（如 ``EU-CAM-2025``），未来规则修订时新增版本
    而不是原地修改旧版本，保证历史数据回填可复现。
    """

    EU_CAM = EU_CAM_CALENDAR
    UK_LEGACY = UK_LEGACY_CALENDAR


@dataclass(frozen=True)
class GasDayCalendarRef:
    """Metadata for one gas-day calendar version.

    Attributes:
        calendar_id: Stable calendar version identifier.
        local_start_time: Local wall-clock time of the gas-day boundary.
        timezone_name: IANA timezone used to resolve DST transitions.
        description: Human-readable rule summary (shown in UI docs).
        effective_from: ISO date from which the calendar applies.
    """

    calendar_id: str
    local_start_time: time
    timezone_name: str
    description: str
    effective_from: str = "2015-10-01"


GAS_DAY_CALENDARS: dict[str, GasDayCalendarRef] = {
    EU_CAM_CALENDAR: GasDayCalendarRef(
        calendar_id=EU_CAM_CALENDAR,
        local_start_time=time(hour=5),
        timezone_name="Europe/Berlin",
        description=(
            "CAM/REMIT gas day: 05:00 CET/CEST (04:00 UTC winter, "
            "03:00 UTC during DST). Applies to EU hubs and NBP since 2016."
        ),
        effective_from="2015-10-01",
    ),
    UK_LEGACY_CALENDAR: GasDayCalendarRef(
        calendar_id=UK_LEGACY_CALENDAR,
        local_start_time=time(hour=5),
        timezone_name="Europe/London",
        description=(
            "Pre-2016 UK gas day: 05:00 UK local time (05:00 UTC winter, "
            "04:00 UTC during BST). Historical backfill only."
        ),
        effective_from="1990-01-01",
    ),
}


def _calendar_zone(calendar: str) -> ZoneInfo:
    """Resolve a calendar id to its IANA timezone.

    Args:
        calendar: Calendar version id (see :data:`GAS_DAY_CALENDARS`).

    Returns:
        The calendar's IANA ``ZoneInfo``.

    Raises:
        ValueError: When the calendar id is not registered.
    """

    try:
        ref = GAS_DAY_CALENDARS[calendar]
    except KeyError as exc:
        raise ValueError(f"Unsupported gas-day calendar: {calendar!r}") from exc
    return ZoneInfo(ref.timezone_name)


def gas_day_start_for_date(value: date, calendar: str = EU_CAM_CALENDAR) -> datetime:
    """Return the UTC start of the gas day whose calendar date is ``value``.

    返回"日历日 value 的当地 05:00"对应的 UTC 时刻（夏令时自动换算）。

    Args:
        value: Calendar date (the date of the local start, e.g. 2026-01-02
            for the gas day starting 2026-01-02 05:00 CET).
        calendar: Calendar version id; defaults to ``EU-CAM-2025``.

    Returns:
        Aware UTC datetime of the local start instant.

    Raises:
        ValueError: When ``calendar`` is not registered.
    """

    zone = _calendar_zone(calendar)
    ref = GAS_DAY_CALENDARS[calendar]
    local_start = datetime.combine(value, ref.local_start_time, tzinfo=zone)
    return local_start.astimezone(UTC)


def gas_day_start_utc(instant: datetime, calendar: str = EU_CAM_CALENDAR) -> datetime:
    """Return the UTC start of the gas day containing ``instant``.

    计算包含指定时刻的气体日的 UTC 起点（DST 安全）。

    Args:
        instant: Any timestamp; naive values are assumed UTC, aware values
            are converted through the calendar's timezone.
        calendar: Calendar version id; defaults to ``EU-CAM-2025``.

    Returns:
        Aware UTC datetime of the containing gas day's start. DST
        transitions are handled through the calendar's local timezone, so
        gas days are 23/25 hours long at spring-forward / fall-back rather
        than a wrong fixed 24-hour boundary.

    Raises:
        ValueError: When ``calendar`` is not registered.
    """

    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=UTC)
    zone = _calendar_zone(calendar)
    local_date = instant.astimezone(zone).date()
    start = gas_day_start_for_date(local_date, calendar)
    if instant < start:
        # 当地 00:00-05:00 区间仍属于"前一天"的气体日，需回退一个日历日。
        start = gas_day_start_for_date(local_date - timedelta(days=1), calendar)
    return start


def gas_day_interval_utc(
    instant: datetime,
    calendar: str = EU_CAM_CALENDAR,
) -> tuple[datetime, datetime]:
    """Return the (start, end) UTC interval of the gas day containing ``instant``.

    返回包含指定时刻的气体日 [起点, 终点) 的 UTC 区间；终点为次日边界，
    长度随 DST 为 23/24/25 小时。

    Args:
        instant: Any timestamp; naive values are assumed UTC.
        calendar: Calendar version id; defaults to ``EU-CAM-2025``.

    Returns:
        Tuple ``(start, end)`` of aware UTC datetimes, half-open interval.

    Raises:
        ValueError: When ``calendar`` is not registered.
    """

    start = gas_day_start_utc(instant, calendar)
    local_date = start.astimezone(_calendar_zone(calendar)).date()
    end = gas_day_start_for_date(local_date + timedelta(days=1), calendar)
    return start, end


def gas_day_label(instant: datetime, calendar: str = EU_CAM_CALENDAR) -> str:
    """Return a stable gas-day label (the calendar date of its start).

    返回稳定气体日标签：以当地起点的日历日（ISO 格式）作为跨时区一致的
    分组键，供报表与 UI 分组使用。

    Args:
        instant: Any timestamp; naive values are assumed UTC.
        calendar: Calendar version id; defaults to ``EU-CAM-2025``.

    Returns:
        ISO date string of the gas day's local start date (e.g. ``2026-01-02``).

    Raises:
        ValueError: When ``calendar`` is not registered.
    """

    start = gas_day_start_utc(instant, calendar)
    return start.astimezone(_calendar_zone(calendar)).date().isoformat()
