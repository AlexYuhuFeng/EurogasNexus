"""Resolve declared nomination windows onto one gas day.

Why this module exists: ``nomination_window_masters`` declares a *clock*, not instants.
``opens_at`` and ``closes_at`` are times of day, and the nomination engine matches them against
the UTC clock time of a submitted instruction (``optimization/nomination.py::_find_window``). A
surface that shows a deadline therefore has to resolve the same clock the engine matches. Resolving
it in the client would put a calendar decision in the presentation layer, where the DST rules live
twice and disagree sooner or later.

The rule here is deliberately the engine's rule rather than a new one:

* the opening instant is the first occurrence of ``opens_at`` (read as a UTC clock time) at or
  after the gas day's start. That occurrence is the one inside the gas day, and it is the
  occurrence an instruction submitted during the window will be matched against;
* the closing instant is ``closes_at`` on the opening instant's UTC date, moved to the next UTC
  day when that would precede the opening instant. That mirrors ``_find_window``, which accepts a
  wrapping window (``opens_at > closes_at``) as "at or after the open, or at or before the close".

Known limit: a 25-hour gas day (autumn DST fall-back) can contain two occurrences of the same clock
time. The first is returned and a second is not, because one row per declared window per gas day is
what a board can act on without inventing a second identity for the same window.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta

from eurogas_nexus.domain.market.gas_day import (
    DEFAULT_GAS_DAY_CALENDAR,
    gas_day_start_for_date,
)

__all__ = [
    "NominationWindowOccurrence",
    "gas_day_bounds_utc",
    "resolve_window_occurrence",
]


@dataclass(frozen=True)
class NominationWindowOccurrence:
    """One declared nomination window resolved onto one gas day.

    Attributes:
        opens_at_utc: Aware UTC instant the window opens.
        closes_at_utc: Aware UTC instant the window closes.
        closes_after_utc_midnight: Whether the close falls on a later UTC date than the open,
            i.e. the declared window wraps UTC midnight (``opens_at > closes_at``).
    """

    opens_at_utc: datetime
    closes_at_utc: datetime
    closes_after_utc_midnight: bool


def gas_day_bounds_utc(
    gas_day: date,
    calendar: str = DEFAULT_GAS_DAY_CALENDAR,
) -> tuple[datetime, datetime]:
    """Return the half-open UTC interval of the gas day labelled ``gas_day``.

    返回气体日标签对应的 UTC 半开区间 [起点, 终点)，长度随夏令时为 23/24/25 小时。

    Args:
        gas_day: Calendar date of the gas day's local start (its stable label).
        calendar: Calendar version id; defaults to ``EU-CAM-UTC-2025``.

    Returns:
        Tuple ``(start, end)`` of aware UTC datetimes; ``end`` is the next boundary.

    Raises:
        ValueError: When ``calendar`` is not registered.
    """

    start = gas_day_start_for_date(gas_day, calendar)
    end = gas_day_start_for_date(gas_day + timedelta(days=1), calendar)
    return start, end


def resolve_window_occurrence(
    *,
    gas_day: date,
    opens_at: time,
    closes_at: time,
    calendar: str = DEFAULT_GAS_DAY_CALENDAR,
) -> NominationWindowOccurrence:
    """Resolve one declared window's clock times onto ``gas_day``.

    把窗口主数据的时钟时刻解析为该气体日内的 UTC 起止时刻（与提名引擎的匹配规则一致）。

    Args:
        gas_day: Calendar date of the gas day whose occurrence is wanted.
        opens_at: Declared opening time of day, read as a UTC clock time.
        closes_at: Declared closing time of day, read as a UTC clock time.
        calendar: Calendar version id; defaults to ``EU-CAM-UTC-2025``.

    Returns:
        The resolved :class:`NominationWindowOccurrence`.

    Raises:
        ValueError: When ``calendar`` is not registered, or when a declared time carries a
            timezone offset - these masters declare a clock, not an instant, and reading an
            offset-bearing value as a clock time would silently drop the offset.
    """

    if opens_at.tzinfo is not None or closes_at.tzinfo is not None:
        raise ValueError(
            "Nomination window masters declare clock times, not instants; "
            "opens_at/closes_at must be timezone-naive."
        )
    start, _ = gas_day_bounds_utc(gas_day, calendar)
    opens_at_utc = datetime.combine(start.date(), opens_at, tzinfo=UTC)
    if opens_at_utc < start:
        opens_at_utc += timedelta(days=1)
    closes_at_utc = datetime.combine(opens_at_utc.date(), closes_at, tzinfo=UTC)
    closes_after_utc_midnight = False
    if closes_at_utc < opens_at_utc:
        closes_at_utc += timedelta(days=1)
        closes_after_utc_midnight = True
    return NominationWindowOccurrence(
        opens_at_utc=opens_at_utc,
        closes_at_utc=closes_at_utc,
        closes_after_utc_midnight=closes_after_utc_midnight,
    )
