"""Tariff years as each publisher defines them, and the NC TAR status rule (TAR-2).

A tariff is published for a **tariff year** (NC TAR's "tariff period"), and each publisher
defines its own: National Gas (GB) and Enagás use the gas year, 1 October to 30 September
(``GY 2027/28``); GTS, the German market-area TSOs, Fluxys Belgium and Fluxys LNG use the
calendar year (``CY 2027``); NaTran, Elengy and the French and German storage years run from
1 April (``TY 2027/28 Apr-Mar``); an exempt terminal or an auctioned slot has none. ENTSOG
carries each TSO's own tariff period on the row, so its rows take the year from the row. A
publisher whose convention could not be confirmed is ``unknown`` and the year is then read
from the period the publication states, never assumed.

Each tariff year can hold an indicative and a final publication (a version each, in
``tariff_versions``); :func:`split_by_tariff_year` cuts a delivery period that spans two
tariff years so each part is priced from its own year's tariff.

**The status of a row that carries no marker.** ENTSOG's ``tariffsfulls`` rows carry no
indicative/final field (measured on all 12,670 rows read 2026-11-19). For those rows the
platform applies a named rule of Regulation (EU) 2017/460 (NC TAR) Article 29: the reserve
prices applicable for the gas year beginning after the annual yearly capacity auction (first
Monday of July, CAM NC) are published no later than 30 days before that auction, and the
auction is run at them. So, as of an instant, a reserve price is the final price when its
tariff period is already in force (basis ``nc_tar_tariff_in_force``) or begins no later than
the first day of the gas year sold at the latest yearly auction already held (basis
``nc_tar_yearly_auction_held``); a period that begins later is indicative (basis
``nc_tar_before_yearly_auction``): a calendar-year tariff for January read in November is
still indicative, because the auction that ran at it sold capacity from October. The rule is
evaluated at the instant asked for, so a valuation as of June reads a GY 2027/28 row as
indicative that a valuation as of August reads as final. A status the operator states itself
(an ENTSOG remark, a reviewed entry, a terminal document) always wins over the rule.

TAR-2：按各发布方定义的费率年度（燃气年、日历年、四月年度）组织费率；无标记的 ENTSOG
行按 NC TAR 第 29 条规则判定指示性或最终，并在所问时点评估。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

GAS_YEAR = "gas_year"  # 1 October - 30 September
CALENDAR_YEAR = "calendar_year"  # 1 January - 31 December
APRIL_YEAR = "april_year"  # 1 April - 31 March
PER_ROW = "per_row"  # the publication states its own period (ENTSOG)
NO_TARIFF_YEAR = "none"  # exempt terminal, auctioned slot: priced per offer
UNKNOWN = "unknown"  # not confirmed: the period stated on the publication is used
CONVENTIONS = (GAS_YEAR, CALENDAR_YEAR, APRIL_YEAR, PER_ROW, NO_TARIFF_YEAR, UNKNOWN)

_START_MONTH = {GAS_YEAR: 10, CALENDAR_YEAR: 1, APRIL_YEAR: 4}

#: Status bases of the NC TAR rule (``model.STATUS_BASES`` lists them with the others).
BASIS_IN_FORCE = "nc_tar_tariff_in_force"
BASIS_AUCTION_HELD = "nc_tar_yearly_auction_held"
BASIS_BEFORE_AUCTION = "nc_tar_before_yearly_auction"
RULE_BASES = frozenset({BASIS_IN_FORCE, BASIS_AUCTION_HELD, BASIS_BEFORE_AUCTION})

RULE_TEXT = {
    BASIS_IN_FORCE: "NC TAR Art. 29: the tariff period is in force, so its price is final",
    BASIS_AUCTION_HELD: (
        "NC TAR Art. 29: the period begins by the start of the gas year sold at the latest "
        "yearly auction held, which ran at this reserve price (final)"
    ),
    BASIS_BEFORE_AUCTION: (
        "NC TAR Art. 29: the period begins after the gas year sold at the latest yearly "
        "auction held; its published reserve price is indicative until it is in force or "
        "that auction is held"
    ),
}


def annual_yearly_auction(year: int) -> date:
    """First Monday of July of ``year``: the annual yearly capacity auction (CAM NC Art. 11)."""

    day = date(year, 7, 1)
    return day + timedelta(days=(7 - day.weekday()) % 7)


def auctioned_gas_year_start(as_of: date) -> date:
    """The first gas day of the gas year sold at the latest yearly auction held by ``as_of``."""

    year = as_of.year if as_of >= annual_yearly_auction(as_of.year) else as_of.year - 1
    return date(year, 10, 1)


def nc_tar_status(period_from: date, as_of: date) -> tuple[str, str]:
    """``(status, basis)`` of a reserve price that carries no marker, as of ``as_of``."""

    if period_from <= as_of:
        return "FINAL", BASIS_IN_FORCE
    if period_from <= auctioned_gas_year_start(as_of):
        return "FINAL", BASIS_AUCTION_HELD
    return "INDICATIVE", BASIS_BEFORE_AUCTION


@dataclass(frozen=True)
class TariffYear:
    """One tariff year: its label, convention and gas days (inclusive)."""

    label: str
    convention: str
    first: date
    last: date

    def as_dict(self) -> dict[str, str]:
        return {
            "label": self.label,
            "convention": self.convention,
            "first_gas_day": self.first.isoformat(),
            "last_gas_day": self.last.isoformat(),
        }


def _label(convention: str, start: date) -> str:
    if convention == GAS_YEAR:
        return f"GY {start.year}/{(start.year + 1) % 100:02d}"
    if convention == CALENDAR_YEAR:
        return f"CY {start.year}"
    return f"TY {start.year}/{(start.year + 1) % 100:02d} Apr-Mar"


def year_containing(day: date, convention: str) -> TariffYear | None:
    """The tariff year of ``convention`` that contains ``day`` (``None``: no fixed year)."""

    month = _START_MONTH.get(convention)
    if month is None:
        return None
    year = day.year if day.month >= month else day.year - 1
    start = date(year, month, 1)
    end = date(year + 1, month, 1) - timedelta(days=1) if month != 1 else date(year, 12, 31)
    return TariffYear(_label(convention, start), convention, start, end)


def convention_of_period(period_from: date, period_to: date | None) -> str:
    """The convention a stated period follows (``unknown`` when it is none of the three)."""

    for convention, month in _START_MONTH.items():
        if period_from.month == month and period_from.day == 1:
            year = year_containing(period_from, convention)
            if period_to is None or (year is not None and period_to <= year.last):
                return convention
    return UNKNOWN


def tariff_year_for(
    period_from: date, period_to: date | None = None, convention: str = PER_ROW
) -> TariffYear:
    """The tariff year a published row belongs to.

    A fixed convention gives the year containing the period's first day. ``per_row`` and
    ``unknown`` read the convention from the period itself; a period that follows none (a
    one-off product period) is labelled by its own dates.
    """

    used = convention
    if convention in (PER_ROW, UNKNOWN, NO_TARIFF_YEAR):
        used = convention_of_period(period_from, period_to)
    year = year_containing(period_from, used)
    if year is not None:
        return year
    last = period_to or period_from
    return TariffYear(
        f"period {period_from.isoformat()}..{last.isoformat()}", UNKNOWN, period_from, last
    )


def parse_tariff_year(label: str) -> TariffYear | None:
    """A label this module wrote (``GY 2027/28``, ``CY 2027``, ``TY 2027/28 Apr-Mar``,
    ``period 2026-11-01..2026-11-30``), or a register gas-year column as ENTSOG's ingestion
    writes it (``2026/27``, ``2026``, ``2026-04..27-03``), back to its year; ``None`` otherwise."""

    text = (label or "").strip()
    try:
        if text.startswith("period "):
            first, last = text[7:].split("..", 1)
            return TariffYear(text, UNKNOWN, date.fromisoformat(first), date.fromisoformat(last))
        if text.startswith(("GY ", "CY ", "TY ")):
            kind = {"GY": GAS_YEAR, "CY": CALENDAR_YEAR, "TY": APRIL_YEAR}[text[:2]]
            year = int(text[3:7])
            return year_containing(date(year, _START_MONTH[kind], 1), kind)
        if len(text) == 4 and text.isdigit():
            return year_containing(date(int(text), 1, 1), CALENDAR_YEAR)
        if len(text) == 7 and text[4] == "/" and text[:4].isdigit():
            return year_containing(date(int(text[:4]), 10, 1), GAS_YEAR)
        if ".." in text:  # ENTSOG's other periods: 2026-04..27-03
            first, last = text.split("..", 1)
            start = date(int(first[:4]), int(first[5:7]), 1)
            end_month = date(2000 + int(last[:2]), int(last[3:5]), 1)
            following = date(end_month.year + end_month.month // 12, end_month.month % 12 + 1, 1)
            end = following - timedelta(days=1)
            convention = convention_of_period(start, end)
            year = year_containing(start, convention)
            if year is not None and year.last == end:
                return year
            return TariffYear(f"period {start.isoformat()}..{end.isoformat()}", UNKNOWN,
                              start, end)
    except (ValueError, KeyError, IndexError):
        return None
    return None


def split_by_tariff_year(first: date, last: date, convention: str) -> list[TariffYear]:
    """The parts of ``first..last`` in each tariff year (clipped to the period).

    ``per_row`` and ``unknown`` have no fixed boundary, so the whole period is one part: each
    day is then priced from the row in force on it, which splits it at the publisher's own
    period boundary.
    """

    if last < first:
        raise ValueError("last is before first")
    parts: list[TariffYear] = []
    day = first
    while day <= last:
        year = year_containing(day, convention)
        if year is None:
            return [TariffYear(f"{first.isoformat()}..{last.isoformat()}", convention, first, last)]
        end = min(year.last, last)
        parts.append(TariffYear(year.label, convention, day, end))
        day = end + timedelta(days=1)
    return parts


__all__ = [
    "APRIL_YEAR",
    "BASIS_AUCTION_HELD",
    "BASIS_BEFORE_AUCTION",
    "BASIS_IN_FORCE",
    "CALENDAR_YEAR",
    "CONVENTIONS",
    "GAS_YEAR",
    "NO_TARIFF_YEAR",
    "PER_ROW",
    "RULE_BASES",
    "RULE_TEXT",
    "UNKNOWN",
    "TariffYear",
    "annual_yearly_auction",
    "auctioned_gas_year_start",
    "convention_of_period",
    "nc_tar_status",
    "parse_tariff_year",
    "split_by_tariff_year",
    "tariff_year_for",
    "year_containing",
]
