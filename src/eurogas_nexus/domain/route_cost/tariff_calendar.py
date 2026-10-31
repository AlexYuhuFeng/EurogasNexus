"""When each TSO's tariffs for a gas year are due, and whether the firm holds them.

European transmission tariffs change every gas year (1 October). Under the tariff network
code (Regulation (EU) 2017/460, NC TAR) a TSO publishes the reserve prices for the coming
gas year no later than 30 days before the annual yearly capacity auction, which is held on
the first Monday of July. Many TSOs publish indicative prices first (consultations,
regulator approval pending) and final prices once approved; some revise during the year.
GB (National Gas, under UNC) and some non-EU points follow their own charging statements.

The register holds one row per TSO and gas year: its status (expected, indicative, final),
where it is published and when the firm last checked the page. This module turns that into
what the desk must act on:

``final``            the firm holds the final tariff                                  ok
``due_soon``         no final yet, and the publication deadline is within 45 days     watch
``overdue``          the deadline has passed and the firm holds no final tariff       breach
``in_force_without_final``  the gas year has started on indicative or no prices       breach
``changed``          the publication page changed since it was last reviewed          watch
``not_yet_due``      nothing to do yet                                                ok
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta

DUE_SOON = timedelta(days=45)


def gas_year_start(label: str) -> date:
    """``2027/28``, ``2027-2028`` or ``2027`` -> 1 October 2027."""

    digits = "".join(ch if ch.isdigit() else " " for ch in label).split()
    if not digits or len(digits[0]) != 4:
        raise ValueError(f"gas year {label!r} not understood")
    return date(int(digits[0]), 10, 1)


def annual_yearly_auction(year: int) -> date:
    """First Monday of July: the annual yearly capacity auction (CAM NC)."""

    day = date(year, 7, 1)
    return day + timedelta(days=(7 - day.weekday()) % 7)


def final_tariff_deadline(label: str) -> date:
    """Latest date the final reserve prices for the gas year are due (NC TAR Art. 32)."""

    return annual_yearly_auction(gas_year_start(label).year) - timedelta(days=30)


@dataclass(frozen=True)
class PublicationState:
    state: str
    severity: str  # ok, watch, breach
    deadline: date
    message: str


def publication_state(
    *,
    tso: str,
    gas_year: str,
    status: str,
    today: date,
    changed_at: datetime | None = None,
    reviewed_at: datetime | None = None,
) -> PublicationState:
    deadline = final_tariff_deadline(gas_year)
    start = gas_year_start(gas_year)
    status = (status or "expected").casefold()
    if changed_at is not None and (reviewed_at is None or changed_at > reviewed_at):
        return PublicationState(
            "changed",
            "watch",
            deadline,
            f"{tso} {gas_year}: the publication page changed; review the tariffs.",
        )
    if status == "final":
        return PublicationState("final", "ok", deadline, f"{tso} {gas_year}: final tariffs held.")
    if today >= start:
        return PublicationState(
            "in_force_without_final",
            "breach",
            deadline,
            f"{tso} {gas_year} is in force and the firm holds {status} tariffs only.",
        )
    if today > deadline:
        return PublicationState(
            "overdue",
            "breach",
            deadline,
            f"{tso} {gas_year}: final tariffs were due by {deadline:%d %b %Y}.",
        )
    if deadline - today <= DUE_SOON:
        return PublicationState(
            "due_soon",
            "watch",
            deadline,
            f"{tso} {gas_year}: final tariffs due by {deadline:%d %b %Y} ({status} held).",
        )
    return PublicationState(
        "not_yet_due",
        "ok",
        deadline,
        f"{tso} {gas_year}: final tariffs due by {deadline:%d %b %Y}.",
    )
