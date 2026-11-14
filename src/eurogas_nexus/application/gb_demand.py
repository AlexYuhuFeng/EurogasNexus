"""The one rule for "GB NTS demand for gas day X, as known at time T".

National Gas publishes the D+1 actual-demand item (``PUBOB637``) in stages and the
D+6 item (``PUBOB652``) once.  Measured over the provider's own history (gas days
1 Nov 2025 to 12 Nov 2026, 2,215 D+1 and 372 D+6 publications):

- before 12:00 provider wall clock on the day after the gas day, the D+1 item is a
  build-up of the day's meter reads (published at 09:20, 10:20 and 11:20; 0 to 31 %
  of the settled figure).  It is never the day's demand;
- from 12:20 the figure is normally the full day (median 0.13 % from D+6), but the
  provider has published wrong or partial values at 12:20 too: 999,150 mscm on
  29 Aug 2026, 38 to 40 mscm (21 to 31 %) on 2, 3 and 8 May 2026, 196.27 against a
  settled 111.17 on 28 Sep 2026.  Each was corrected by the next publication;
- D+6 is published at 10:20 (winter) or 11:20 (summer) on day X+6 and is the settled
  figure.

The rule (``GB_DEMAND_DAY_RULE``), applied by every reader of
``national_gas_actual_demand`` values:

1. Only publications received by this store by ``T`` count (``available_at_utc``,
   the local receipt; a provider clock never makes a row available earlier).
2. Publications are ordered by the provider's own clocks (generated, then
   applicable wall clock), not by receipt: one download receives every stage at
   once, and its receipt time cannot order them.
3. A D+6 publication, when one is known, is the day's figure (``settled``).
4. Otherwise the latest complete D+1 publication (published at or after 12:00 on
   X+1) is returned only when it is *confirmed*: the complete publication before it
   agrees within 2 % and was received no later.  That figure is ``provisional``.
5. Otherwise nothing is returned, with the reason: ``not_published``, ``building``
   (only build-up stages known), ``awaiting_confirmation`` (one complete
   publication) or ``revision_unconfirmed`` (the newest publication moved more than
   2 % from the one before it).

Over that year the rule returned a figure for every gas day before its D+6
publication except 6, never a build-up stage nor any of the outliers above; the
largest gap to D+6 among returned figures (10.2 %, 28 Aug 2026) is a genuine
provider revision made three days later.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation
from enum import StrEnum

GB_DEMAND_DAY_RULE = (
    "GB demand for gas day X as of T: publications received by T, ordered by the "
    "provider's clocks; the D+6 figure when known (settled); else the latest D+1 "
    "publication made at or after 12:00 on X+1 when the complete publication before "
    "it agrees within 2% (provisional); else no value. D+1 publications before "
    "12:00 on X+1 are build-up stages, never the day's demand."
)
D1_ITEM = "PUBOB637"
D6_ITEM = "PUBOB652"
D1_COMPLETE_FROM_WALL_CLOCK = time(12, 0)
CONFIRMATION_TOLERANCE = Decimal("0.02")


class D1Stage(StrEnum):
    """What one D+1 publication is, given the publications known with it."""

    BUILD_UP = "build_up"
    UNCONFIRMED = "unconfirmed"
    CONFIRMED = "confirmed"


class DemandStatus(StrEnum):
    SETTLED = "settled"
    PROVISIONAL = "provisional"
    NOT_PUBLISHED = "not_published"
    BUILDING = "building"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    REVISION_UNCONFIRMED = "revision_unconfirmed"


@dataclass(frozen=True)
class GasDayDemand:
    """The figure a reader may show for one gas day, or why there is none."""

    gas_day: date
    status: DemandStatus
    value_text: str | None = None
    value: Decimal | None = None
    record_id: str | None = None
    provider_item_id: str | None = None
    provider_published_wall_clock: datetime | None = None
    available_at_utc: datetime | None = None

    @property
    def has_value(self) -> bool:
        return self.value is not None


def provider_publication_key(record: object) -> tuple[datetime, datetime, str]:
    """Order publications of one item by the provider's clocks, not by receipt.

    ``generated`` first: an amendment keeps its ``applicable`` time and carries a
    later ``generated`` time (31 Mar 2026: applicable 5 Apr 12:20, generated
    10 Apr 13:34).  Wall clocks are compared as published (the provider's local
    clock); publications never fall in the repeated autumn hour (01:00-02:00).
    """

    generated = getattr(record, "generated_at_naive", None)
    applicable = getattr(record, "applicable_at_naive", None)
    if not isinstance(generated, datetime) or not isinstance(applicable, datetime):
        raise ValueError("a demand publication needs its provider generated/applicable clocks")
    return (
        generated.replace(tzinfo=None),
        applicable.replace(tzinfo=None),
        str(getattr(record, "record_id", "")),
    )


def d1_complete_from(gas_day: date) -> datetime:
    """Provider wall clock from which a D+1 publication holds the whole day."""

    return datetime.combine(gas_day + timedelta(days=1), D1_COMPLETE_FROM_WALL_CLOCK)


def is_d1_build_up_stage(record: object) -> bool:
    """A D+1 publication made before 12:00 on X+1: a partial build-up of the day."""

    if getattr(record, "term", None) != "D+1":
        return False
    applicable = getattr(record, "applicable_at_naive", None)
    gas_day = getattr(record, "gas_day", None)
    if not isinstance(applicable, datetime) or not isinstance(gas_day, date):
        return True
    return applicable.replace(tzinfo=None) < d1_complete_from(gas_day)


def _value(record: object) -> Decimal | None:
    text = getattr(record, "value_text", None)
    if getattr(record, "value_is_blank", False) or not isinstance(text, str) or not text:
        return None
    try:
        value = Decimal(text)
    except InvalidOperation:
        return None
    return value if value.is_finite() else None


def _available(record: object) -> datetime | None:
    value = getattr(record, "available_at_utc", None)
    if not isinstance(value, datetime) or value.tzinfo is None:
        return None
    return value.astimezone(UTC)


def _agree(a: Decimal, b: Decimal) -> bool:
    scale = max(abs(a), abs(b))
    return abs(a - b) <= CONFIRMATION_TOLERANCE * scale


def classify_d1_publications(records: Iterable[object]) -> dict[str, D1Stage]:
    """Classify the D+1 publications of one gas day (by ``record_id``).

    The caller passes the publications it knows (as of its cutoff).  A complete
    publication is confirmed when the complete publication before it in provider
    order has a value within 2 % and was received no later than it, so wherever the
    confirmed row is visible its confirmation is visible too.
    """

    rows = [
        record
        for record in records
        if getattr(record, "term", None) == "D+1" and _value(record) is not None
    ]
    stages: dict[str, D1Stage] = {}
    previous = None
    for record in sorted(rows, key=provider_publication_key):
        record_id = str(getattr(record, "record_id", ""))
        if is_d1_build_up_stage(record):
            stages[record_id] = D1Stage.BUILD_UP
            continue
        confirmed = False
        if previous is not None:
            prior_at, own_at = _available(previous), _available(record)
            confirmed = (
                prior_at is not None
                and own_at is not None
                and prior_at <= own_at
                and _agree(_value(previous), _value(record))
            )
        stages[record_id] = D1Stage.CONFIRMED if confirmed else D1Stage.UNCONFIRMED
        previous = record
    return stages


def demand_for_gas_day(
    records: Iterable[object], *, gas_day: date, as_of: datetime
) -> GasDayDemand:
    """Apply ``GB_DEMAND_DAY_RULE`` to the stored publications of one gas day."""

    if as_of.tzinfo is None:
        raise ValueError("as_of must be timezone-aware")
    cutoff = as_of.astimezone(UTC)
    known = [
        record
        for record in records
        if getattr(record, "gas_day", None) == gas_day
        and getattr(record, "region", "GB_NTS") == "GB_NTS"
        and str(getattr(record, "unit", "mscm")).lower() == "mscm"
        and (_available(record) is not None and _available(record) <= cutoff)
        and _value(record) is not None
    ]
    if not known:
        return GasDayDemand(gas_day, DemandStatus.NOT_PUBLISHED)

    settled = [record for record in known if getattr(record, "term", None) == "D+6"]
    if settled:
        return _figure(gas_day, DemandStatus.SETTLED, max(settled, key=provider_publication_key))

    d1 = [record for record in known if getattr(record, "term", None) == "D+1"]
    stages = classify_d1_publications(d1)
    complete = [r for r in d1 if stages.get(str(r.record_id)) is not D1Stage.BUILD_UP]
    if not complete:
        return GasDayDemand(gas_day, DemandStatus.BUILDING)
    latest = max(complete, key=provider_publication_key)
    if stages[str(latest.record_id)] is D1Stage.CONFIRMED:
        return _figure(gas_day, DemandStatus.PROVISIONAL, latest)
    status = (
        DemandStatus.AWAITING_CONFIRMATION
        if len(complete) == 1
        else DemandStatus.REVISION_UNCONFIRMED
    )
    return GasDayDemand(gas_day, status)


def demand_by_gas_day(
    records: Iterable[object], *, as_of: datetime, gas_days: Iterable[date] | None = None
) -> dict[date, GasDayDemand]:
    """``demand_for_gas_day`` for every gas day in ``records`` (or the given days)."""

    rows = list(records)
    days = sorted(set(gas_days) if gas_days is not None else {r.gas_day for r in rows})
    by_day: dict[date, list[object]] = {}
    for row in rows:
        by_day.setdefault(row.gas_day, []).append(row)
    return {
        day: demand_for_gas_day(by_day.get(day, ()), gas_day=day, as_of=as_of)
        for day in days
    }


def _figure(gas_day: date, status: DemandStatus, record: object) -> GasDayDemand:
    return GasDayDemand(
        gas_day=gas_day,
        status=status,
        value_text=record.value_text,
        value=_value(record),
        record_id=record.record_id,
        provider_item_id=getattr(record, "provider_item_id", None),
        provider_published_wall_clock=provider_publication_key(record)[1],
        available_at_utc=_available(record),
    )
