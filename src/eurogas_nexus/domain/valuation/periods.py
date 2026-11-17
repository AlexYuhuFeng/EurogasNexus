"""Delivery periods as the desk names them: a gas day, a month, a quarter, a season.

A period is the half-open range of gas days ``[start, end)`` with its desk label. The label
is the canonical text form (``2027-01``, ``2026-11-18``, ``2027-Q1``, ``SUM-27``,
``WIN-27``), so a stored key and a screen label never disagree.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta

_MONTH = re.compile(r"^(\d{4})-(\d{2})$")
_DAY = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
_QUARTER = re.compile(r"^(\d{4})-Q([1-4])$")
_SEASON = re.compile(r"^(SUM|WIN)-(\d{2})$")


class PeriodError(ValueError):
    """A delivery period label that does not parse."""


@dataclass(frozen=True, order=True)
class DeliveryPeriod:
    """Gas days ``[start, end)`` and the label the desk uses for them."""

    start: date
    end: date
    label: str

    def __post_init__(self) -> None:
        if self.end <= self.start:
            raise PeriodError(f"empty delivery period {self.label!r}")

    @property
    def days(self) -> int:
        """Number of gas days in the period."""

        return (self.end - self.start).days

    @property
    def kind(self) -> str:
        """``day``, ``month``, ``quarter`` or ``season``."""

        if _DAY.match(self.label):
            return "day"
        if _MONTH.match(self.label):
            return "month"
        if _QUARTER.match(self.label):
            return "quarter"
        return "season"

    def contains(self, day: date) -> bool:
        """Whether a gas day falls inside the period."""

        return self.start <= day < self.end

    @classmethod
    def gas_day(cls, day: date) -> DeliveryPeriod:
        """One gas day."""

        return cls(day, day + timedelta(days=1), day.isoformat())

    @classmethod
    def month(cls, year: int, month: int) -> DeliveryPeriod:
        """One calendar month of gas days."""

        start = date(year, month, 1)
        end = date(year + (month == 12), month % 12 + 1, 1)
        return cls(start, end, f"{year:04d}-{month:02d}")

    @classmethod
    def quarter(cls, year: int, quarter: int) -> DeliveryPeriod:
        """One calendar quarter."""

        first = 3 * (quarter - 1) + 1
        start = date(year, first, 1)
        end = date(year + (quarter == 4), (first + 2) % 12 + 1, 1)
        return cls(start, end, f"{year:04d}-Q{quarter}")

    @classmethod
    def season(cls, name: str, year_2d: int) -> DeliveryPeriod:
        """Summer (April-September) or winter (October-March) of the gas year."""

        year = 2000 + year_2d
        if name == "SUM":
            return cls(date(year, 4, 1), date(year, 10, 1), f"SUM-{year_2d:02d}")
        return cls(date(year, 10, 1), date(year + 1, 4, 1), f"WIN-{year_2d:02d}")

    @classmethod
    def parse(cls, label: str) -> DeliveryPeriod:
        """Parse a canonical label.

        Raises:
            PeriodError: The label is none of the supported forms.
        """

        text = (label or "").strip().upper()
        try:
            if match := _DAY.match(text):
                return cls.gas_day(date(*(int(part) for part in match.groups())))
            if match := _MONTH.match(text):
                return cls.month(int(match.group(1)), int(match.group(2)))
            if match := _QUARTER.match(text):
                return cls.quarter(int(match.group(1)), int(match.group(2)))
            if match := _SEASON.match(text):
                return cls.season(match.group(1), int(match.group(2)))
        except ValueError as exc:
            raise PeriodError(f"not a delivery period: {label!r}") from exc
        raise PeriodError(f"not a delivery period: {label!r}")


def month_of(day: date) -> DeliveryPeriod:
    """The month containing a gas day."""

    return DeliveryPeriod.month(day.year, day.month)
