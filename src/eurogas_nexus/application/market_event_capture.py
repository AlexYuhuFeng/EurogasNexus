"""Change capture for market events (M5): prices, FX fixings, REMIT outages and desk edits.

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
  arriving late is out of order;
- a contract (M5b): ``contract:<id>``, over its stored terms, book, lifecycle and hedge
  band; an approved assumption value (M5b): ``assumption:<key>``, one identity per set and
  key, including a key the newest approved version no longer sets. The desk's figures stay
  in their own tables: these payloads carry a digest, never a term or a value (as firm
  marks do). The store's current state is the truth here, so the capture instant is the
  publication time: any state that differs from the latest revision is news, including a
  return to an earlier one.

Nothing here reads a network source; capture works on what the store already holds.
"""

from __future__ import annotations

import hashlib
import json
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

#: What a capture can read.
KINDS = ("prices", "fx", "outages", "contracts", "assumptions")


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
    observed = _aware(getattr(row, "observed_at_utc", None))
    return MarketEvent(
        source_id=str(row.source_system),
        event_type="fx.updated",
        subject_key=key,
        ingested_at_utc=max(ingested_at_utc, market_time, observed or market_time),
        market_time_utc=market_time,
        # The observation instant orders fixings of one value date, as for settlements.
        published_at_utc=observed,
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


_CONTRACT_BOOKKEEPING = frozenset(
    {"created_at_utc", "updated_at_utc", "retired_at_utc", "retired_by", "retire_reason"}
)


def _digest(document: Any) -> str:
    text = json.dumps(document, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(text.encode()).hexdigest()[:24]


def _plain(value: Any) -> Any:
    if isinstance(value, float | Decimal):
        return str(_decimal(value).normalize())
    if isinstance(value, datetime | date):
        return value.isoformat()
    return value


def contract_event(row, *, hedge=None, now_utc: datetime) -> MarketEvent:
    """The ``contract.changed`` event for one stored contract and its hedge band.

    Everything that can change a valuation is digested (terms, book, retirement, the hedge
    band); who changed it and when are not, so re-saving the same terms is no news.
    """

    terms = {
        column: _plain(getattr(row, column))
        for column in row.__table__.columns.keys()
        if column not in _CONTRACT_BOOKKEEPING
    }
    terms["retired"] = row.retired_at_utc is not None
    if hedge is not None:
        terms["hedge_band"] = [
            _plain(hedge.min_hedge_ratio_pct),
            _plain(hedge.max_hedge_ratio_pct),
            _plain(hedge.valid_until),
        ]
    key = f"contract:{row.contract_id}"
    return MarketEvent(
        source_id="desk-contracts",
        event_type="contract.changed",
        subject_key=key,
        ingested_at_utc=now_utc,
        # A desk record has no market time; the edit instants are bookkeeping and stay out
        # of the content (they are in the contract's own revisions and audit).
        published_at_utc=now_utc,
        payload={
            "contract_id": row.contract_id,
            "retired": terms["retired"],
            "terms_digest": _digest(terms),
        },
        dependency_keys=(key,),
        identity=key,
    )


def assumption_events(
    set_id: str, approved, values: Iterable[Any], known_keys: Iterable[str], *, now_utc: datetime
) -> list[MarketEvent]:
    """``assumption.changed`` events for one set: each key the approved version sets, and
    each key an earlier version set that the approved version (or no version) no longer
    does, since a valuation then falls back to the catalogue default.

    A key's digest covers its value, unit, currency and range, not the version number or
    the effective dates: a new version that repeats a value is no news for that key. (A
    change of effective dates alone still makes the CP-13 full evaluation due.)"""

    by_key = {value.key: value for value in values}
    events = []
    for name in sorted(set(known_keys) | set(by_key)):
        value = by_key.get(name)
        if value is None or approved is None:
            state, digest = "unset", None
        else:
            state = "set"
            digest = _digest(
                [
                    _plain(value.value),
                    value.unit,
                    value.currency,
                    _plain(value.range_low),
                    _plain(value.range_high),
                ]
            )
        key = f"assumption:{name}"
        events.append(
            MarketEvent(
                source_id="desk-assumptions",
                event_type="assumption.changed",
                subject_key=key,
                ingested_at_utc=now_utc,
                published_at_utc=now_utc,
                payload={"set_id": set_id, "key": name, "state": state, "value_digest": digest},
                dependency_keys=(key,),
                identity=f"{set_id}|{key}",
            )
        )
    return events


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


def _known_content(session, events: Sequence[MarketEvent]) -> dict[str, str]:
    """The content hash of each key's latest revision, one query per 500 keys.

    Only the latest revision counts: content of an older one may be news again when it is
    published later (the outbox decides).
    """

    from eurogas_nexus.db.models import MarketEventRecord

    keys = sorted({event.event_key for event in events})
    latest: dict[str, tuple[int, str]] = {}
    for start in range(0, len(keys), 500):
        chunk = keys[start : start + 500]
        rows = (
            session.query(
                MarketEventRecord.event_key,
                MarketEventRecord.revision,
                MarketEventRecord.content_hash,
            )
            .filter(MarketEventRecord.event_key.in_(chunk))
            .all()
        )
        for key, revision, content in rows:
            if key not in latest or revision > latest[key][0]:
                latest[key] = (revision, content)
    return {key: content for key, (_, content) in latest.items()}


def publish_events(session, events: Iterable[MarketEvent | None]) -> CaptureResult:
    """Publish events whose content the outbox does not already hold; commit is the caller's.

    Content equal to an identity's latest revision is a duplicate and is counted as
    unchanged without a write; anything else goes to the outbox, which decides.
    """

    from eurogas_nexus.application import market_events as outbox

    result = CaptureResult(published={})
    ready = [event for event in events if event is not None]
    result.examined = len(ready)
    held = _known_content(session, ready)
    for event in sorted(ready, key=lambda item: (item.event_key, _order(item))):
        if held.get(event.event_key) == event.content_hash:
            result.unchanged += 1
            continue
        published = outbox.publish(session, event)
        if published.kind.value in {"new", "revision"}:  # PublishKind.NEW / REVISION
            result.published[event.event_type] = result.published.get(event.event_type, 0) + 1
            held[event.event_key] = event.content_hash
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


def contract_events(session, *, contract_ids: Iterable[str] | None = None, now_utc: datetime):
    """``contract.changed`` events for the stored contracts (or the ones named)."""

    from eurogas_nexus.db.models import HedgeApprovalRecord, UpstreamResourceContractRecord

    query = session.query(UpstreamResourceContractRecord)
    hedges = session.query(HedgeApprovalRecord)
    if contract_ids is not None:
        ids = sorted(set(contract_ids))
        if not ids:
            return []
        query = query.filter(UpstreamResourceContractRecord.contract_id.in_(ids))
        hedges = hedges.filter(HedgeApprovalRecord.contract_id.in_(ids))
    bands = {row.contract_id: row for row in hedges.all()}
    return [
        contract_event(row, hedge=bands.get(row.contract_id), now_utc=now_utc)
        for row in query.order_by(UpstreamResourceContractRecord.contract_id).all()
    ]


def assumption_set_events(session, *, set_ids: Iterable[str] | None = None, now_utc: datetime):
    """``assumption.changed`` events for the assumption sets (or the ones named)."""

    from eurogas_nexus.db.models import (
        AssumptionSetRecord,
        AssumptionSetVersionRecord,
        AssumptionValueRecord,
    )
    from eurogas_nexus.domain.valuation.assumptions import ReviewState

    sets = session.query(AssumptionSetRecord.set_id)
    if set_ids is not None:
        sets = sets.filter(AssumptionSetRecord.set_id.in_(sorted(set(set_ids))))
    events: list[MarketEvent] = []
    for (set_id,) in sets.order_by(AssumptionSetRecord.set_id).all():
        versions = (
            session.query(AssumptionSetVersionRecord)
            .filter(AssumptionSetVersionRecord.set_id == set_id)
            .all()
        )
        version_ids = [version.version_id for version in versions]
        rows = (
            session.query(AssumptionValueRecord)
            .filter(AssumptionValueRecord.version_id.in_(version_ids))
            .all()
            if version_ids
            else []
        )
        # Drafts are not read by a valuation; keys of approved and retired versions are.
        read = {
            version.version_id
            for version in versions
            if version.review_state != ReviewState.DRAFT.value
        }
        approved = next((v for v in versions if v.review_state == ReviewState.APPROVED.value), None)
        events.extend(
            assumption_events(
                set_id,
                approved,
                [row for row in rows if approved and row.version_id == approved.version_id],
                {row.key for row in rows if row.version_id in read},
                now_utc=now_utc,
            )
        )
    return events


def capture_desk(
    session,
    *,
    contract_ids: Iterable[str] | None = None,
    set_ids: Iterable[str] | None = None,
    now_utc: datetime | None = None,
) -> dict[str, Any]:
    """Publish the contract and assumption events a desk write has just stored, in the
    writer's transaction (commit is the caller's). Name what was written: ``contract_ids``,
    ``set_ids``; a kind not named is not read."""

    now = _aware(now_utc) or datetime.now(UTC)
    session.flush()
    events: list[MarketEvent] = []
    if contract_ids is not None:
        events.extend(contract_events(session, contract_ids=contract_ids, now_utc=now))
    if set_ids is not None:
        events.extend(assumption_set_events(session, set_ids=set_ids, now_utc=now))
    return publish_events(session, events).to_json()


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
    kinds: Sequence[str] = KINDS,
) -> dict[str, Any]:
    """Publish events for the settlements, fixings and REMIT messages in the window, and for
    every contract and assumption set (desk tables are small and have no window).

    ``since_utc`` defaults to ``now - DEFAULT_LOOKBACK``. Commit is the caller's.
    """

    now = _aware(now_utc) or datetime.now(UTC)
    since = _aware(since_utc) or now - DEFAULT_LOOKBACK
    session.flush()
    events, skipped = events_for_rows(
        settlements=settlement_rows(session, since_utc=since) if "prices" in kinds else (),
        fixings=fx_rows(session, since_utc=since) if "fx" in kinds else (),
        outages=outage_rows(session, since_utc=since) if "outages" in kinds else (),
        now_utc=now,
    )
    if "contracts" in kinds:
        events.extend(contract_events(session, now_utc=now))
    if "assumptions" in kinds:
        events.extend(assumption_set_events(session, now_utc=now))
    result = publish_events(session, events)
    result.skipped += skipped
    return result.to_json() | {"since_utc": since.isoformat()}


__all__ = [
    "DEFAULT_LOOKBACK",
    "KINDS",
    "CaptureResult",
    "assumption_events",
    "assumption_set_events",
    "capture",
    "capture_desk",
    "capture_rows",
    "contract_event",
    "contract_events",
    "events_for_rows",
    "fx_event",
    "outage_event",
    "period_of",
    "publish_events",
    "settlement_event",
]
