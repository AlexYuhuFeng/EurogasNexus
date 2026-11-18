"""Storage fill against its own history: the gas-year axis, the years held and the band.

Pure functions over daily values (no database), so every figure the storage read returns is
reproducible by hand. The rules are the in-app chart standard's (design basis 2, F.2) and the
client's ``seasonModel.ts`` applies the same ones:

* The gas year runs 1 October to 30 September. Its axis has 365 days keyed ``MM-DD``; a leap
  year's 29 February has no slot (its value is left out), so every year draws on the same days.
* A prior gas year is **held** when it has a value on at least 95 % of its 365 days.
* With no prior year held there is no band; with one to four, each is a line ("N prior years
  held"); with five or more, the band is the min-max and the mean of the **last five** held
  ("5-yr range 2021/22-2025/26"). A day where any of those years has no value is a gap in the
  band, so no point of it rests on fewer years than its label states.
* "vs N-yr average" uses the years held (N = 1..5), stated with N.
* "Same gas day last year" is the same calendar day one year earlier (29 February: 28 February).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta

GAS_YEAR_START_MONTH = 10
BAND_YEARS = 5
COMPLETE_SHARE = 0.95
SEASON_DAYS = 365
_DAYS_IN_MONTH = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)


def gas_year_of(day: date) -> int:
    """The gas year a day belongs to, by its first calendar year (2026-11-17 -> 2026)."""

    return day.year if day.month >= GAS_YEAR_START_MONTH else day.year - 1


def gas_year_label(first_year: int) -> str:
    """2025 -> "2025/26"."""

    return f"{first_year}/{(first_year + 1) % 100:02d}"


def season_index(day: date) -> int:
    """Position of a day on the 365-day gas-year axis; -1 for 29 February."""

    if day.month == 2 and day.day == 29:
        return -1
    index = 0
    for step in range(12):
        month = (GAS_YEAR_START_MONTH - 1 + step) % 12 + 1
        if month == day.month:
            return index + day.day - 1
        index += _DAYS_IN_MONTH[month - 1]
    return -1  # pragma: no cover - every month is reached


def season_keys() -> list[str]:
    """The axis keys "10-01" ... "09-30"."""

    keys = []
    for step in range(12):
        month = (GAS_YEAR_START_MONTH - 1 + step) % 12 + 1
        keys.extend(f"{month:02d}-{d:02d}" for d in range(1, _DAYS_IN_MONTH[month - 1] + 1))
    return keys


def same_day_last_year(day: date) -> date:
    try:
        return day.replace(year=day.year - 1)
    except ValueError:  # 29 February
        return day.replace(year=day.year - 1, day=28)


def by_gas_year(values: Mapping[date, float]) -> dict[int, list[float | None]]:
    """Daily values laid on the gas-year axis, one list of 365 per gas year."""

    seasons: dict[int, list[float | None]] = {}
    for day, value in values.items():
        at = season_index(day)
        if at < 0 or value is None:
            continue
        seasons.setdefault(gas_year_of(day), [None] * SEASON_DAYS)[at] = float(value)
    return seasons


def is_complete(values: Sequence[float | None]) -> bool:
    held = sum(1 for value in values if value is not None)
    return held >= int(-(-COMPLETE_SHARE * SEASON_DAYS // 1))


@dataclass(frozen=True)
class HistoryPlan:
    """What the history shows: ``none``, ``lines`` or ``band``, from which years, and the label."""

    mode: str
    years: tuple[int, ...]
    label: str


def history_plan(complete_years: Iterable[int], history_from: date | None) -> HistoryPlan:
    """The F.2 rule applied to the complete prior gas years held."""

    years = sorted(set(complete_years))
    if not years:
        # A date as the desk writes it ("20 Oct 2025"), never an ISO string (display rule G8).
        since = f"{history_from.day} {history_from:%b %Y}" if history_from else "n/a"
        return HistoryPlan("none", (), f"History from {since}: no complete prior year held")
    if len(years) < BAND_YEARS:
        noun = "prior year" if len(years) == 1 else "prior years"
        return HistoryPlan("lines", tuple(years), f"{len(years)} {noun} held")
    used = tuple(years[-BAND_YEARS:])
    return HistoryPlan(
        "band",
        used,
        f"{len(used)}-yr range {gas_year_label(used[0])}–{gas_year_label(used[-1])}",
    )


@dataclass(frozen=True)
class Band:
    low: list[float | None]
    high: list[float | None]
    mean: list[float | None]
    years: int


def band_from_years(series: Sequence[Sequence[float | None]], digits: int = 2) -> Band:
    """Min, max and mean across the years per day; a day any year lacks is a gap in all three."""

    low: list[float | None] = []
    high: list[float | None] = []
    mean: list[float | None] = []
    for index in range(SEASON_DAYS):
        values = [s[index] if index < len(s) else None for s in series]
        if not series or any(v is None for v in values):
            low.append(None)
            high.append(None)
            mean.append(None)
            continue
        known = [float(v) for v in values if v is not None]
        low.append(round(min(known), digits))
        high.append(round(max(known), digits))
        mean.append(round(sum(known) / len(known), digits))
    return Band(low, high, mean, len(series))


def average_on_day(seasons: Mapping[int, Sequence[float | None]], years: Sequence[int],
                   index: int) -> tuple[float | None, float | None, float | None]:
    """(mean, low, high) of the years' values on one day of the axis; None when any is missing."""

    if index < 0 or not years:
        return None, None, None
    values = [seasons.get(year, [None] * SEASON_DAYS)[index] for year in years]
    if any(v is None for v in values):
        return None, None, None
    known = [float(v) for v in values if v is not None]
    return sum(known) / len(known), min(known), max(known)


def range_position(value: float, low: float, high: float) -> tuple[float, str | None]:
    """Where a value sits in a range, 0-100, clamped; the side it is outside, if any."""

    if high <= low:
        return 50.0, None
    raw = (value - low) / (high - low) * 100
    if raw < 0:
        return 0.0, "below"
    if raw > 100:
        return 100.0, "above"
    return raw, None


def change_over(values: Mapping[date, float], day: date, days: int) -> float | None:
    """Value on ``day`` minus the value ``days`` earlier; None when either is not held."""

    now = values.get(day)
    then = values.get(day - timedelta(days=days))
    if now is None or then is None:
        return None
    return now - then
