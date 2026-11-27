"""The cut-offs of one gas day at a hub: one calendar for Today's gas day and the prompt signals.

Two instants matter to a desk that has to leave every gas day balanced:

* the **nomination deadline** for gas day D: after it the shipper's day-ahead position at the
  hub is fixed except by renomination;
* the **last renomination** of gas day D: the last moment a trade done within-day can still be
  renominated, so the practical end of within-day trading to clear D.

Where the firm holds no declared window for the hub's market area these are the network-code
defaults of the EU balancing code (Regulation (EU) 312/2014): nominations by 13:00 UTC on D-1 in
winter and 12:00 UTC in summer, which is sixteen hours before the gas day starts in both seasons,
and renominations until three hours before the end of the gas day. A default is always returned
as an **assumption** with its basis in words, never as a market fact; a declared window from
``nomination_window_masters`` replaces it and names its source.

燃气日截止时间：日前提名截止与最后一次再提名（网络规范默认值，明确标注为假设）。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from eurogas_nexus.domain.market.gas_day import gas_day_start_for_date

#: Regulation (EU) 312/2014: nomination deadline 13:00 UTC (winter) / 12:00 UTC (summer) on D-1.
NOMINATION_LEAD = timedelta(hours=16)
#: Regulation (EU) 312/2014: the renomination period ends no earlier than 3 h before D ends.
LAST_RENOMINATION_BEFORE_END = timedelta(hours=3)
DEFAULT_BASIS = (
    "Network-code default (EU balancing code, Regulation 312/2014): nominations 16 hours "
    "before the gas day starts, renominations until 3 hours before it ends"
)


@dataclass(frozen=True)
class Cutoff:
    """One cut-off of one gas day: what it is, when, and whether it is held or assumed."""

    key: str  # "nomination" | "last_renomination" | "gas_day_end"
    gas_day: date
    at_utc: datetime
    #: ``held``: from a declared window the firm keeps; ``assumption``: the default above;
    #: ``calendar``: the gas-day calendar itself (the end of the day is a fact).
    basis: str
    source: str


def gas_day_end(gas_day: date) -> datetime:
    return gas_day_start_for_date(gas_day + timedelta(days=1))


def nomination_deadline(gas_day: date) -> datetime:
    """The default day-ahead nomination deadline for ``gas_day`` (an assumption)."""

    return gas_day_start_for_date(gas_day) - NOMINATION_LEAD


def last_renomination(gas_day: date) -> datetime:
    """The default last renomination of ``gas_day`` (an assumption)."""

    return gas_day_end(gas_day) - LAST_RENOMINATION_BEFORE_END


def default_cutoffs(gas_day: date) -> list[Cutoff]:
    """The network-code defaults and the end of the gas day, in time order."""

    return [
        Cutoff("nomination", gas_day, nomination_deadline(gas_day), "assumption", DEFAULT_BASIS),
        Cutoff("last_renomination", gas_day, last_renomination(gas_day), "assumption",
               DEFAULT_BASIS),
        Cutoff("gas_day_end", gas_day, gas_day_end(gas_day), "calendar", "Gas-day calendar"),
    ]


def product_cutoff(product: str, now: datetime) -> datetime:
    """The latest instant a prompt product traded at ``now`` still clears its gas day.

    Within-day: the last renomination of today's gas day; day-ahead: the nomination deadline
    for tomorrow while it is ahead, else the end of today's gas day; any other product: the
    end of today's gas day. Used by Today's gas day and the prompt desk, so both read one
    calendar.
    """

    from eurogas_nexus.domain.market.gas_day import gas_day_label

    today = date.fromisoformat(gas_day_label(now))
    end_of_today = gas_day_end(today)
    if product == "within-day":
        return last_renomination(today)
    if product == "day-ahead":
        deadline = nomination_deadline(today + timedelta(days=1))
        return deadline if deadline > now else end_of_today
    return end_of_today
