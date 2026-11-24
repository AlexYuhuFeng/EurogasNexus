"""Change capture for market events (M5): prices, FX fixings and REMIT outages.

Every writer of settlements, FX fixings and REMIT messages (scheduled ingestion through
Core upserts, ORM importers, the demo seed) leaves rows behind; this module reads those rows
and publishes one canonical market event per row through the outbox. The outbox decides
what is new: the same figure again is a duplicate and writes nothing, a changed figure is a
revision that supersedes the last, an older figure after a correction is out of order. So a
capture can run as often as wanted and over any window, and a re-download of unchanged data
costs one read.

Dependency keys are the keys an opportunity stores for the input (see
``domain/valuation/snapshot.dependency_key``):

- a settlement: ``hub:<HUB>:<period label>`` (market time: the observation's trade instant);
- an FX fixing: ``fx:<BASE><QUOTE>`` (market time: the value date). EUR is the pivot of the
  fixings, so the opportunity consumer also reaches the cross pairs that share the fixing's
  other currency;
- a REMIT message: ``outage:<message id>``, with the message id as identity, so a new
  version (a moved start, a new volume) is a revision of one event and an older version
  arriving late is out of order.

Nothing here reads a network source; capture works on what the store already holds.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

from eurogas_nexus.domain.market_events import MarketEvent, MarketEventError
from eurogas_nexus.domain.valuation.periods import DeliveryPeriod, PeriodError

#: How far back a scheduled capture looks for settlements and fixings by market time, and
#: for REMIT messages by ingestion time. Corrections older than this are captured by an
#: explicit ``capture(..., since_utc=...)`` (the operations CLI).
DEFAULT_LOOKBACK = timedelta(days=4)

SIMULATED_SUFFIX = "_Sim"


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    return Decimal(repr(float(value))) if isinstance(value, float) else Decimal(str(value))


def _naive(session) -> bool:
    return session.get_bind().dialect.name == "sqlite"


def _bound(session, moment: datetime) -> datetime:
    return moment.replace(tzinfo=None) if _naive(session) else moment


# ---------------------------------------------------------------------------- periods


def period_of(start: date, end: date) -> DeliveryPeriod | None:
    """The canonical delivery period a ``[start, end)`` or ``[start, end]`` row covers.

    Settlement rows store the end either exclusive or as the last gas day; both resolve to
    the same period. A span that is no day, month, quarter or season gives None.
    """

    candidates: list[DeliveryPeriod] = [DeliveryPeriod.gas_day(start)]
    candidates.append(DeliveryPeriod.month(start.year, start.month))
    if start.month in (1, 4, 7, 10):
        candidates.append(DeliveryPeriod.quarter(start.year, (start.month - 1) // 3 + 1))
    if start.month in (4, 10):
        try:
            candidates.append(
                DeliveryPeriod.season("SUM" if start.month == 4 else "WIN", start.year % 100)
            )
        except PeriodError:  # pragma: no cover - season labels are always valid
            pass
    for period in candidates:
        if period.start == start and end in {period.end, period.end - timedelta(days=1)}:
            return period
    return None


# ---------------------------------------------------------------------------- builders


def settlement_event(row, *, ingested_at_utc: datetime) -> MarketEvent | None:
    """The ``price.updated`` event for one settlement row, or None when it names no hub or
    no canonical period (such a row is not an input any opportunity can store)."""

    from eurogas_nexus.domain.ontology.identity import resolve_hub

    metadata = row.metadata_json or {}
    hub = resolve_hub(metadata.get("hub") or row.product).hub
    start, end = _aware(row.period_start_utc), _aware(row.period_end_utc)
    if hub is None or start is None or end is None:
        return None
    period = period_of(start.date(), end.date())
    if period is None:
        return None
    key = f"hub:{hub.upper()}:{period.label}"
    observed = _aware(row.observed_at_utc)
    trade_day = observed.date().isoformat()
    return MarketEvent(
        source_id=str(row.source_system),
        event_type="price.updated",
        subject_key=key,
        ingested_at_utc=max(ingested_at_utc, observed),
        market_time_utc=observed,
        # The observation instant orders figures of one day: an earlier figure found after
        # a later one is out of order, never a revision on top of it.
        published_at_utc=observed,
        payload={
            "price": _decimal(row.price),
            "unit": row.unit,
            "currency": row.currency,
            "venue": row.market_venue,
            "basis": "settlement",
            "trade_day": trade_day,
            "simulated": bool(metadata.get("simulated"))
            or str(row.source_system).endswith(SIMULATED_SUFFIX),
        },
        dependency_keys=(key,),
        # One settlement per hub, period, venue and trade day: a figure stored again for
        # the same day (a correction, a re-observation) is a revision of that event.
        identity=f"{key}|{row.market_venue}|{trade_day}",
        correlation_id=str(row.observation_id)[:64],
    )


def fx_event(row, *, ingested_at_utc: datetime) -> MarketEvent | None:
    """The ``fx.updated`` event for one fixing row, or None when its value date is unusable."""

    try:
        value_day = date.fromisoformat(str(row.value_date)[:10])
    except ValueError:
        return None
    pair = f"{str(row.base_currency).upper()}{str(row.quote_currency).upper()}"
    key = f"fx:{pair}"
    market_time = datetime.combine(value_day, datetime.min.time(), tzinfo=UTC)
    return MarketEvent(
        source_id=str(row.source_system),
        event_type="fx.updated",
        subject_key=key,
        ingested_at_utc=max(ingested_at_utc, market_time),
        market_time_utc=market_time,
        payload={
            "rate": _decimal(row.rate),
            "rate_type": row.rate_type,
            "value_date": value_day.isoformat(),
        },
        dependency_keys=(key,),
        correlation_id=str(row.observation_id)[:64],
    )


def outage_event(row) -> MarketEvent:
    """The ``outage.published`` event for one REMIT message version."""

    published = _aware(row.published_at_utc)
    ingested = _aware(row.ingested_at_utc) or published
    key = f"outage:{row.message_id}"
    return MarketEvent(
        source_id=str(row.source_system),
        event_type="outage.published",
        subject_key=key,
        ingested_at_utc=max(ingested, published),
        market_time_utc=_aware(row.event_start_utc),
        published_at_utc=published,
        payload={
            "message_id": row.message_id,
            "version": int(row.version),
            "status": str(row.event_status),
            "unavailability_type": row.unavailability_type,
            "event_start_utc": _aware(row.event_start_utc),
            "event_stop_utc": _aware(row.event_stop_utc),
            "asset_eic": row.asset_eic,
            "balancing_zone": row.balancing_zone,
            "direction": row.direction,
            "unavailable_gwh_d": _decimal(row.unavailable_gwh_d),
            "unavailable_mcm_d": _decimal(row.unavailable_mcm_d),
        },
        dependency_keys=(key,),
        identity=str(row.message_id),
        correlation_id=str(row.record_id)[:64],
    )


# ---------------------------------------------------------------------------- capture


@dataclass
class CaptureResult:
    """What one capture did, by event type."""

    examined: int = 0
    published: dict[str, int] | None = None
    unchanged: int = 0
    skipped: int = 0

    def to_json(self) -> dict[str, Any]:
        return {
            "examined": self.examined,
            "published": dict(sorted((self.published or {}).items())),
            "unchanged": self.unchanged,
            "skipped": self.skipped,
        }


def _known_content(session, events: Sequence[MarketEvent]) -> set[tuple[str, str]]:
    """(event_key, content_hash) pairs already held, read in one query per 500 keys."""

    from eurogas_nexus.db.models import MarketEventRecord

    keys = sorted({event.event_key for event in events})
    held: set[tuple[str, str]] = set()
    for start in range(0, len(keys), 500):
        chunk = keys[start : start + 500]
        rows = (
            session.query(MarketEventRecord.event_key, MarketEventRecord.content_hash)
            .filter(MarketEventRecord.event_key.in_(chunk))
            .all()
        )
        held.update((row[0], row[1]) for row in rows)
    return held


def publish_events(session, events: Iterable[MarketEvent | None]) -> CaptureResult:
    """Publish events whose content the outbox does not already hold; commit is the caller's.

    Content already held under the same identity (the latest revision or an older one) can
    only be a duplicate or out of order, so it is counted as unchanged without a write.
    """

    from eurogas_nexus.application import market_events as outbox

    result = CaptureResult(published={})
    ready = [event for event in events if event is not None]
    result.examined = len(ready)
    held = _known_content(session, ready)
    for event in sorted(ready, key=lambda item: (item.event_key, _order(item))):
        if (event.event_key, event.content_hash) in held:
            result.unchanged += 1
            continue
        published = outbox.publish(session, event)
        if published.kind.value in {"new", "revision"}:  # PublishKind.NEW / REVISION
            result.published[event.event_type] = result.published.get(event.event_type, 0) + 1
            held.add((event.event_key, event.content_hash))
        else:
            result.unchanged += 1
    return result


def _order(event: MarketEvent) -> tuple:
    # Several figures of one event in one capture (versions of a REMIT message, prints of
    # one settlement day): oldest first, so each later one is a revision of the one before.
    published = event.published_at_utc or event.market_time_utc or event.ingested_at_utc
    return (published, event.payload.get("version") or 0)


def settlement_rows(session, *, since_utc: datetime):
    from eurogas_nexus.db.models import MarketObservationRecord

    return (
        session.query(MarketObservationRecord)
        .filter(MarketObservationRecord.observed_at_utc >= _bound(session, since_utc))
        .order_by(MarketObservationRecord.observed_at_utc)
        .all()
    )


def fx_rows(session, *, since_utc: datetime):
    from eurogas_nexus.db.models import FxObservationRecord

    return (
        session.query(FxObservationRecord)
        .filter(FxObservationRecord.value_date >= since_utc.date().isoformat())
        .order_by(FxObservationRecord.value_date)
        .all()
    )


def outage_rows(session, *, since_utc: datetime):
    from eurogas_nexus.db.models import RemitUmmRecord

    return (
        session.query(RemitUmmRecord)
        .filter(RemitUmmRecord.ingested_at_utc >= _bound(session, since_utc))
        .order_by(RemitUmmRecord.message_id, RemitUmmRecord.version)
        .all()
    )


def events_for_rows(
    *,
    settlements: Iterable[Any] = (),
    fixings: Iterable[Any] = (),
    outages: Iterable[Any] = (),
    now_utc: datetime,
) -> tuple[list[MarketEvent], int]:
    """Build events for rows; returns the events and how many rows could not be one."""

    events: list[MarketEvent] = []
    skipped = 0
    builders = (
        (settlements, lambda row: settlement_event(row, ingested_at_utc=now_utc)),
        (fixings, lambda row: fx_event(row, ingested_at_utc=now_utc)),
        (outages, outage_event),
    )
    for rows, build in builders:
        for row in rows:
            try:
                event = build(row)
            except MarketEventError:
                event = None
            if event is None:
                skipped += 1
            else:
                events.append(event)
    return events, skipped


def capture_rows(
    session,
    *,
    settlements: Iterable[Any] = (),
    fixings: Iterable[Any] = (),
    outages: Iterable[Any] = (),
    now_utc: datetime | None = None,
) -> dict[str, Any]:
    """Publish the events for rows a writer has just stored; commit is the caller's."""

    now = _aware(now_utc) or datetime.now(UTC)
    session.flush()
    events, skipped = events_for_rows(
        settlements=settlements, fixings=fixings, outages=outages, now_utc=now
    )
    result = publish_events(session, events)
    result.skipped += skipped
    return result.to_json()


def capture(
    session,
    *,
    now_utc: datetime | None = None,
    since_utc: datetime | None = None,
    kinds: Sequence[str] = ("prices", "fx", "outages"),
) -> dict[str, Any]:
    """Publish events for the settlements, fixings and REMIT messages in the window.

    ``since_utc`` defaults to ``now - DEFAULT_LOOKBACK``. Commit is the caller's.
    """

    now = _aware(now_utc) or datetime.now(UTC)
    since = _aware(since_utc) or now - DEFAULT_LOOKBACK
    return capture_rows(
        session,
        settlements=settlement_rows(session, since_utc=since) if "prices" in kinds else (),
        fixings=fx_rows(session, since_utc=since) if "fx" in kinds else (),
        outages=outage_rows(session, since_utc=since) if "outages" in kinds else (),
        now_utc=now,
    ) | {"since_utc": since.isoformat()}


__all__ = [
    "DEFAULT_LOOKBACK",
    "CaptureResult",
    "capture",
    "capture_rows",
    "events_for_rows",
    "fx_event",
    "outage_event",
    "period_of",
    "publish_events",
    "settlement_event",
]
