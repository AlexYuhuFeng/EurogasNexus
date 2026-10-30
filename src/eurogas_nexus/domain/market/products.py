"""European gas traded-product (tenor) calendar.

Resolves the product codes a European gas desk quotes every day - ``WD``, ``DA``,
``WE``, ``BOM``, ``M+n``, ``Q+n``, seasons (``Sum-27`` / ``Win-27``), gas years
(``GY-27``) and calendar years (``Cal-27``) - into an exact delivery period on
the gas-day calendar of :mod:`eurogas_nexus.domain.market.gas_day`.

Conventions (TTF/THE/PEG/ZTP/PSV/NBP OTC and exchange practice):

- a gas day ``d`` runs from 06:00 CET/CEST on ``d`` to 06:00 on ``d + 1``;
- ``WD`` (within-day) is the gas day of the trade date;
- ``DA`` (day-ahead) is the next *working* day after the trade date, so a Friday
  DA delivers Monday; Saturday and Sunday trade as ``WE`` (weekend);
- ``BOM`` (balance-of-month) runs from the gas day after the trade date to the
  end of the month and does not exist on the last day of the month;
- summer runs April-September, winter October-March; ``Win-27`` starts on
  1 October 2027; the gas year ``GY-27`` runs 1 October 2027 to 30 September 2028.

Delivery hours are measured on UTC instants of the gas-day boundaries, so a
season containing a DST change carries the real 23/25 hour days and a 1 MW flat
position delivers exactly ``hours`` MWh. Exchange holiday calendars are not
modelled; the caller may pass explicit non-working days for ``DA``.

本模块把交易员每天使用的产品代码（DA/WE/BOM/M+1/Q+1/季节/燃气年/日历年）
解析为精确的气体日交割区间，并按 UTC 计算 DST 下真实交割小时数。
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from eurogas_nexus.domain.market.gas_day import (
    DEFAULT_GAS_DAY_CALENDAR,
    gas_day_start_for_date,
)

PRODUCT_KINDS = (
    "within_day",
    "day_ahead",
    "weekend",
    "balance_of_month",
    "month",
    "quarter",
    "season",
    "gas_year",
    "calendar_year",
)

#: The strip a European gas desk keeps on screen, nearest first.
STANDARD_STRIP: tuple[str, ...] = (
    "WD",
    "DA",
    "WE",
    "BOM",
    "M+1",
    "M+2",
    "M+3",
    "Q+1",
    "Q+2",
    "S+1",
    "S+2",
    "GY+1",
    "Cal+1",
)

_MONTHS = ("JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC")
_RELATIVE = re.compile(r"^(M|Q|S|GY|CAL)\+(\d{1,2})$")
_MONTH_CODE = re.compile(r"^(" + "|".join(_MONTHS) + r")-?(\d{2}|\d{4})$")
_QUARTER_CODE = re.compile(r"^Q([1-4])-?(\d{2}|\d{4})$")
_SEASON_CODE = re.compile(r"^(SUM|WIN)-?(\d{2}|\d{4})$")
_YEAR_CODE = re.compile(r"^(GY|CAL)-?(\d{2}|\d{4})$")
_MAX_RELATIVE = 36


class ProductCodeError(ValueError):
    """The product code is unknown or has no delivery period on the trade date."""


@dataclass(frozen=True)
class DeliveryPeriod:
    """One resolved traded product.

    Attributes:
        code: Canonical relative or absolute code as requested (normalised).
        label: Absolute desk label (``Nov-26``, ``Q1-27``, ``Win-26``, ...).
        kind: One of :data:`PRODUCT_KINDS`.
        first_gas_day: First delivered gas day (inclusive).
        last_gas_day: Last delivered gas day (inclusive).
        gas_days: Number of delivered gas days.
        delivery_start_utc: UTC start of the first gas day.
        delivery_end_utc: UTC end (exclusive) of the last gas day.
        hours: Delivery hours; MWh delivered by a 1 MW flat position.
        calendar: Gas-day calendar version used.
    """

    code: str
    label: str
    kind: str
    first_gas_day: date
    last_gas_day: date
    gas_days: int
    delivery_start_utc: datetime
    delivery_end_utc: datetime
    hours: float
    calendar: str

    def as_dict(self) -> dict[str, object]:
        """JSON-ready representation."""

        return {
            "code": self.code,
            "label": self.label,
            "kind": self.kind,
            "first_gas_day": self.first_gas_day.isoformat(),
            "last_gas_day": self.last_gas_day.isoformat(),
            "gas_days": self.gas_days,
            "delivery_start_utc": self.delivery_start_utc.isoformat(),
            "delivery_end_utc": self.delivery_end_utc.isoformat(),
            "hours": self.hours,
            "calendar": self.calendar,
        }


def _yy(year: int) -> str:
    return f"{year % 100:02d}"


def _year(text: str) -> int:
    value = int(text)
    return value + 2000 if len(text) == 2 else value


def _add_months(year: int, month: int, offset: int) -> tuple[int, int]:
    index = year * 12 + (month - 1) + offset
    return index // 12, index % 12 + 1


def _month_end(year: int, month: int) -> date:
    next_year, next_month = _add_months(year, month, 1)
    return date(next_year, next_month, 1) - timedelta(days=1)


def _period(
    code: str,
    label: str,
    kind: str,
    first: date,
    last: date,
    calendar: str,
) -> DeliveryPeriod:
    start = gas_day_start_for_date(first, calendar)
    end = gas_day_start_for_date(last + timedelta(days=1), calendar)
    return DeliveryPeriod(
        code=code,
        label=label,
        kind=kind,
        first_gas_day=first,
        last_gas_day=last,
        gas_days=(last - first).days + 1,
        delivery_start_utc=start,
        delivery_end_utc=end,
        hours=(end - start).total_seconds() / 3600.0,
        calendar=calendar,
    )


def _month(code: str, year: int, month: int, calendar: str) -> DeliveryPeriod:
    return _period(
        code,
        f"{_MONTHS[month - 1].title()}-{_yy(year)}",
        "month",
        date(year, month, 1),
        _month_end(year, month),
        calendar,
    )


def _quarter(code: str, year: int, quarter: int, calendar: str) -> DeliveryPeriod:
    first_month = 3 * (quarter - 1) + 1
    return _period(
        code,
        f"Q{quarter}-{_yy(year)}",
        "quarter",
        date(year, first_month, 1),
        _month_end(year, first_month + 2),
        calendar,
    )


def _season(code: str, year: int, summer: bool, calendar: str) -> DeliveryPeriod:
    if summer:
        return _period(
            code, f"Sum-{_yy(year)}", "season", date(year, 4, 1), date(year, 9, 30), calendar
        )
    return _period(
        code, f"Win-{_yy(year)}", "season", date(year, 10, 1), date(year + 1, 3, 31), calendar
    )


def _gas_year(code: str, year: int, calendar: str) -> DeliveryPeriod:
    return _period(
        code, f"GY-{_yy(year)}", "gas_year", date(year, 10, 1), date(year + 1, 9, 30), calendar
    )


def _cal(code: str, year: int, calendar: str) -> DeliveryPeriod:
    return _period(
        code, f"Cal-{_yy(year)}", "calendar_year", date(year, 1, 1), date(year, 12, 31), calendar
    )


def _next_working_day(trade_date: date, holidays: frozenset[date]) -> date:
    candidate = trade_date + timedelta(days=1)
    while candidate.weekday() >= 5 or candidate in holidays:
        candidate += timedelta(days=1)
    return candidate


def _relative(
    code: str, family: str, n: int, trade_date: date, calendar: str
) -> DeliveryPeriod:
    if not 1 <= n <= _MAX_RELATIVE:
        raise ProductCodeError(f"relative offset must be 1..{_MAX_RELATIVE}: {code}")
    if family == "M":
        year, month = _add_months(trade_date.year, trade_date.month, n)
        return _month(code, year, month, calendar)
    if family == "Q":
        current = (trade_date.month - 1) // 3
        index = trade_date.year * 4 + current + n
        return _quarter(code, index // 4, index % 4 + 1, calendar)
    if family == "S":
        # Seasons are indexed in half-years: summer of Y = 2Y, winter of Y = 2Y + 1.
        if trade_date.month >= 10:
            current = 2 * trade_date.year + 1
        elif trade_date.month >= 4:
            current = 2 * trade_date.year
        else:
            current = 2 * (trade_date.year - 1) + 1
        index = current + n
        return _season(code, index // 2, index % 2 == 0, calendar)
    if family == "GY":
        current = trade_date.year if trade_date.month >= 10 else trade_date.year - 1
        return _gas_year(code, current + n, calendar)
    return _cal(code, trade_date.year + n, calendar)


def resolve_product(
    code: str,
    trade_date: date,
    *,
    holidays: Iterable[date] = (),
    calendar: str = DEFAULT_GAS_DAY_CALENDAR,
) -> DeliveryPeriod:
    """Resolve one product code against a trade date.

    Args:
        code: Relative (``DA``, ``M+1``, ``S+1``) or absolute (``Nov-26``,
            ``Q1-27``, ``Win-26``, ``GY-27``, ``Cal-27``) product code.
        trade_date: Trading date the relative code is anchored to.
        holidays: Extra non-working days skipped by ``DA``.
        calendar: Gas-day calendar version.

    Returns:
        The resolved :class:`DeliveryPeriod`.

    Raises:
        ProductCodeError: Unknown code, or no such product on ``trade_date``.
    """

    raw = (code or "").strip()
    key = raw.upper().replace(" ", "")
    aliases = {
        "WITHIN-DAY": "WD",
        "WITHINDAY": "WD",
        "DAY-AHEAD": "DA",
        "DAYAHEAD": "DA",
        "WEEKEND": "WE",
        "MA": "M+1",
        "MONTH-AHEAD": "M+1",
        "QA": "Q+1",
        "SA": "S+1",
        "SEASON-AHEAD": "S+1",
        "YA": "CAL+1",
    }
    key = aliases.get(key, key)
    canonical = key.replace("CAL", "Cal") if key.startswith("CAL+") else key
    if key == "WD":
        return _period("WD", trade_date.isoformat(), "within_day", trade_date, trade_date, calendar)
    if key == "DA":
        day = _next_working_day(trade_date, frozenset(holidays))
        return _period("DA", day.isoformat(), "day_ahead", day, day, calendar)
    if key == "WE":
        saturday = trade_date + timedelta(days=(5 - trade_date.weekday()) % 7 or 7)
        sunday = saturday + timedelta(days=1)
        return _period("WE", f"WE {saturday.isoformat()}", "weekend", saturday, sunday, calendar)
    if key == "BOM":
        last = _month_end(trade_date.year, trade_date.month)
        if trade_date >= last:
            raise ProductCodeError("BOM has no delivery on the last day of the month")
        return _period(
            "BOM",
            f"BOM {_MONTHS[trade_date.month - 1].title()}-{_yy(trade_date.year)}",
            "balance_of_month",
            trade_date + timedelta(days=1),
            last,
            calendar,
        )
    match = _RELATIVE.match(key)
    if match:
        return _relative(canonical, match.group(1), int(match.group(2)), trade_date, calendar)
    match = _MONTH_CODE.match(key)
    if match:
        year = _year(match.group(2))
        period = _month(key, year, _MONTHS.index(match.group(1)) + 1, calendar)
        return _refuse_expired(period, trade_date)
    match = _QUARTER_CODE.match(key)
    if match:
        period = _quarter(key, _year(match.group(2)), int(match.group(1)), calendar)
        return _refuse_expired(period, trade_date)
    match = _SEASON_CODE.match(key)
    if match:
        period = _season(key, _year(match.group(2)), match.group(1) == "SUM", calendar)
        return _refuse_expired(period, trade_date)
    match = _YEAR_CODE.match(key)
    if match:
        year = _year(match.group(2))
        builder = _gas_year if match.group(1) == "GY" else _cal
        return _refuse_expired(builder(key, year, calendar), trade_date)
    raise ProductCodeError(f"unknown gas product code: {raw!r}")


def _refuse_expired(period: DeliveryPeriod, trade_date: date) -> DeliveryPeriod:
    """Absolute codes stay valid while any delivery remains after the trade date."""

    if period.last_gas_day <= trade_date:
        raise ProductCodeError(f"{period.label} has fully delivered by {trade_date.isoformat()}")
    return period


def standard_strip(
    trade_date: date,
    *,
    holidays: Iterable[date] = (),
    calendar: str = DEFAULT_GAS_DAY_CALENDAR,
) -> list[DeliveryPeriod]:
    """Resolve :data:`STANDARD_STRIP` for one trade date, skipping absent products.

    ``BOM`` is absent on the last day of a month; every other product always exists.
    """

    holiday_set = frozenset(holidays)
    periods: list[DeliveryPeriod] = []
    for code in STANDARD_STRIP:
        try:
            periods.append(
                resolve_product(code, trade_date, holidays=holiday_set, calendar=calendar)
            )
        except ProductCodeError:
            continue
    return periods
