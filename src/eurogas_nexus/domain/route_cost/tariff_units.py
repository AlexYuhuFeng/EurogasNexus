"""A published capacity tariff as a cost per MWh, for a stated product and load factor.

The tariff register stores what the operator published (``ingestion/entsog_tariffs.py``): a
reserve price per unit of capacity per period, in the operator's currency and capacity unit,
for one capacity product (the product's multiplier and any seasonal factor are already in the
published price). A route is priced per MWh, so the reading converts here, never at
ingestion, and says how:

- **Units understood.** ``<money>/(kWh/h)/<period>`` and ``<money>/(kWh/d)/<period>`` as
  ENTSOG publishes them (``EUR/(kWh/h)/y``, ``GBP/(kWh/d)/y``, ``Euro/(kWh/h)/d``,
  ``EUR/(kWh/h)/h``), the GB convention ``p/kWh/d`` (pence per kWh/d of capacity per day), and
  energy units already per MWh or kWh (``EUR/MWh``, ``GBP/MWh``, ``p/kWh``). Money is an ISO
  code, ``Euro``, or ``p``/``pence`` (GBP / 100) and ``ct`` (EUR / 100). Anything else is not
  converted (the caller states the leg missing; never a guessed unit).
- **Period.** ``y`` is the twelve months from the tariff's anniversary on or before the
  delivery day (365 or 366 days); ``q`` the calendar quarter of the delivery day; ``m`` its
  month; ``d`` one gas day; ``h`` one hour (24 per gas day).
- **Capacity to energy.** One kWh/h of capacity carries 24 kWh in a gas day at a 100 % load
  factor, one kWh/d carries 1 kWh. At a load factor *L* the capacity cost is spread over *L*
  of that energy, so the cost per MWh is divided by *L*.

Golden case (``tests/unit/test_tariff_units.py``): Gasunie Deutschland's 2026 yearly firm
reserve price at VIP TTF-THE-H, 7.06 EUR/(kWh/h)/y, is 7.06 / 365 / 24 x 1000 = 0.8059 EUR/MWh
at 100 % load factor.

本模块在读取时把运营商公布的容量费率（每单位容量每期间）换算为每 MWh 成本，
明确产品与负荷率；无法识别的单位不换算，由调用方标记为缺失。
"""

from __future__ import annotations

import calendar
import re
from dataclasses import dataclass
from datetime import date

from eurogas_nexus.domain.ontology.quantity import convert

#: kWh per MWh, from the unit authority.
KWH_PER_MWH = convert(1.0, "MWh", "kWh")

_MONEY = {
    "EUR": ("EUR", 1.0),
    "EURO": ("EUR", 1.0),
    "€": ("EUR", 1.0),
    "CT": ("EUR", 0.01),
    "GBP": ("GBP", 1.0),
    "£": ("GBP", 1.0),
    "P": ("GBP", 0.01),
    "PENCE": ("GBP", 0.01),
}
_CAPACITY = re.compile(
    r"^\s*(?P<money>[^/\s]+)\s*/\s*\(\s*kWh\s*/\s*(?P<basis>h|d)\s*\)\s*/\s*(?P<period>[yqmdh])\s*$",
    re.IGNORECASE,
)
_GB_CAPACITY = re.compile(r"^\s*(?P<money>p|pence)\s*/\s*kWh\s*/\s*(d|day)\s*$", re.IGNORECASE)
_ENERGY = re.compile(r"^\s*(?P<money>[^/\s]+)\s*/\s*(?P<energy>MWh|kWh)\s*$", re.IGNORECASE)
_PERIOD_WORD = {"y": "year", "q": "quarter", "m": "month", "d": "gas day", "h": "hour"}


@dataclass(frozen=True)
class TariffUnit:
    """A parsed tariff unit: money, and either a capacity basis and period or an energy unit."""

    currency: str
    money_scale: float
    capacity_basis: str | None = None  # "h" (kWh/h) or "d" (kWh/d); None for an energy unit
    period: str | None = None  # y | q | m | d | h
    energy: str | None = None  # "MWh" | "kWh" for an energy unit

    @property
    def is_capacity(self) -> bool:
        return self.capacity_basis is not None


def _money(token: str) -> tuple[str, float] | None:
    text = token.strip()
    known = _MONEY.get(text.upper())
    if known:
        return known
    if re.fullmatch(r"[A-Z]{3}", text):
        return text, 1.0
    return None


def parse_unit(unit: str | None) -> TariffUnit | None:
    """The unit as money, capacity basis and period, or None when it is not understood."""

    text = (unit or "").strip()
    if not text:
        return None
    match = _CAPACITY.match(text)
    if match:
        money = _money(match["money"])
        if money is None:
            return None
        return TariffUnit(money[0], money[1], match["basis"].lower(), match["period"].lower())
    match = _GB_CAPACITY.match(text)
    if match:
        return TariffUnit("GBP", 0.01, "d", "d")
    match = _ENERGY.match(text)
    if match:
        money = _money(match["money"])
        if money is None:
            return None
        energy = "MWh" if match["energy"].lower() == "mwh" else "kWh"
        return TariffUnit(money[0], money[1], energy=energy)
    return None


def period_days(period: str, on: date, *, anniversary: date | None = None) -> float:
    """Gas days in the tariff period ``period`` that contains the delivery day ``on``."""

    if period == "d":
        return 1.0
    if period == "h":
        return 1.0 / 24.0
    if period == "m":
        return float(calendar.monthrange(on.year, on.month)[1])
    if period == "q":
        first = (on.month - 1) // 3 * 3 + 1
        months = range(first, first + 3)
        return float(sum(calendar.monthrange(on.year, month)[1] for month in months))
    if period == "y":
        anchor = anniversary or date(on.year, 1, 1)
        start = _anniversary_on_or_before(anchor, on)
        end = _shift_year(start, 1)
        return float((end - start).days)
    raise ValueError(f"unknown tariff period {period!r}")


def _shift_year(day: date, years: int) -> date:
    try:
        return day.replace(year=day.year + years)
    except ValueError:  # 29 February
        return day.replace(year=day.year + years, day=28)


def _anniversary_on_or_before(anchor: date, on: date) -> date:
    start = _shift_year(anchor, on.year - anchor.year)
    if start > on:
        start = _shift_year(anchor, on.year - anchor.year - 1)
    return start


@dataclass(frozen=True)
class PerMwh:
    """A tariff read as a cost per MWh, with how it was read."""

    value: float
    currency: str
    unit: str
    basis: str


def per_mwh(
    value: float,
    unit: str | None,
    *,
    on: date,
    load_factor: float = 1.0,
    anniversary: date | None = None,
    currency: str | None = None,
) -> PerMwh | None:
    """``value`` in ``unit`` as a cost per MWh on delivery day ``on``, or None if not readable.

    ``anniversary`` is the first day of the tariff's validity (a yearly price runs a year from
    it). ``load_factor`` is the share of the booked capacity used (0 < L <= 1); it applies to
    capacity units only (an energy unit is already per MWh flowed).
    """

    if not 0 < load_factor <= 1:
        raise ValueError("load_factor must be within (0, 1].")
    parsed = parse_unit(unit)
    if parsed is None:
        return None
    if currency and parsed.currency != (_money(currency) or (currency.upper(), 1.0))[0]:
        return None  # the row's currency and its unit's money disagree: not read
    money = value * parsed.money_scale
    if not parsed.is_capacity:
        per_mwh_value = money * (KWH_PER_MWH if parsed.energy == "kWh" else 1.0)
        return PerMwh(
            per_mwh_value,
            parsed.currency,
            f"{parsed.currency}/MWh",
            f"published per {parsed.energy}",
        )
    days = period_days(parsed.period or "d", on, anniversary=anniversary)
    per_capacity_day = money / days
    kwh_per_day = 24.0 if parsed.capacity_basis == "h" else 1.0
    per_mwh_value = per_capacity_day / kwh_per_day * KWH_PER_MWH / load_factor
    period_word = _PERIOD_WORD[parsed.period or "d"]
    return PerMwh(
        per_mwh_value,
        parsed.currency,
        f"{parsed.currency}/MWh",
        (
            f"{value:g} {unit} over {days:g} days a {period_word}"
            if parsed.period in {"y", "q", "m"}
            else f"{value:g} {unit}"
        )
        + f", kWh/{parsed.capacity_basis} capacity at {load_factor:.0%} load factor",
    )
