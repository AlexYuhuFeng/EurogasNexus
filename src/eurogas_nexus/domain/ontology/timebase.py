"""Time: instants in UTC, business dates per market calendar, and offices in their zones.

Three rules, the same in every office:

1. An **instant** (an observation, a publication, an audit event) is stored as an aware UTC
   datetime. A naive datetime is refused at the boundary, never assumed.
2. A **business date** (gas day, power delivery date, settlement date) belongs to a market
   calendar: the EU gas day runs 06:00-06:00 Europe/Berlin, the NAESB gas day
   09:00-09:00 America/Chicago, power days run midnight to midnight in the bidding zone.
   It is derived from the market, not from the reader's clock.
3. A **person** reads instants in their office's zone; dates of business stay as they are.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

from eurogas_nexus.domain.ontology.markets import market


class NaiveDatetimeError(ValueError):
    """A datetime without a time zone reached a boundary that requires one."""


def require_utc(moment: datetime) -> datetime:
    """The same instant in UTC; refuses naive datetimes."""

    if moment.tzinfo is None or moment.utcoffset() is None:
        raise NaiveDatetimeError(f"{moment.isoformat()} has no time zone")
    return moment.astimezone(UTC)


@dataclass(frozen=True)
class Office:
    """An office: its time zone, home currency and the data region it belongs to."""

    code: str
    name: str
    timezone: str
    currency: str
    data_region: str  # installation that holds its data (GLOBAL_DEPLOYMENT.md)


OFFICES: dict[str, Office] = {
    o.code: o
    for o in (
        Office("UK", "London", "Europe/London", "GBP", "primary"),
        Office("NL", "Amsterdam", "Europe/Amsterdam", "EUR", "primary"),
        Office("DE", "Germany", "Europe/Berlin", "EUR", "primary"),
        Office("CH", "Switzerland", "Europe/Zurich", "CHF", "primary"),
        Office("CA", "Calgary", "America/Edmonton", "CAD", "primary"),
        Office("US", "Houston", "America/Chicago", "USD", "primary"),
        Office("SG", "Singapore", "Asia/Singapore", "SGD", "primary"),
        Office("CN", "Shanghai", "Asia/Shanghai", "CNY", "china"),
    )
}


def office_local(moment: datetime, office_code: str) -> datetime:
    """An instant as read in an office."""

    office = OFFICES.get((office_code or "").upper())
    zone = ZoneInfo(office.timezone) if office else UTC
    return require_utc(moment).astimezone(zone)


def business_date(moment: datetime, market_code: str) -> date:
    """The business date an instant falls in for a market (gas day or power day)."""

    from eurogas_nexus.domain.market.gas_day import (
        GAS_DAY_CALENDARS,
        gas_day_start_for_date,
    )

    found = market(market_code)
    instant = require_utc(moment)
    if found.calendar in GAS_DAY_CALENDARS:
        local = instant.astimezone(ZoneInfo(GAS_DAY_CALENDARS[found.calendar].timezone_name))
        candidate = local.date()
        if instant < gas_day_start_for_date(candidate, found.calendar):
            candidate = date.fromordinal(candidate.toordinal() - 1)
        return candidate
    return instant.astimezone(ZoneInfo(found.timezone)).date()
