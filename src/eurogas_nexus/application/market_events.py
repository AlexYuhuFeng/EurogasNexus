"""The market event outbox: publish, deliver, retry, replay, stale and status (M4).

ADR Decision 28. A producer publishes a canonical :class:`MarketEvent` **in its own
transaction** (:func:`publish`); the event row and one pending delivery per subscribed consumer
commit with the producer's write or not at all (the transactional outbox). A worker drains each
consumer (:func:`process`) in priority, then log order; a consumer that raises leaves its batch
for a retry with exponential backoff, and after :data:`MAX_ATTEMPTS` the deliveries are ``dead``
and named in :func:`status`. :func:`replay` re-arms deliveries so a consumer can reproduce what
it did; :func:`staleness` says which subjects have gone quiet; :func:`timeline` gives an event's
five times as one consumer saw them.

On PostgreSQL, :func:`publish` issues ``pg_notify('market_events', <event_id>)``; the notice is
delivered at commit and only wakes a worker early. Polling the tables is what guarantees
delivery, so a lost notice costs latency, never an event.

Consumers
---------
``opportunities`` (:class:`OpportunityImpactConsumer`): the impact propagation of design J.2.
An event carrying dependency keys (``hub:TTF:2027-01``, ``contract:<id>``) re-evaluates only the
evaluators whose stored opportunities read one of those keys (``opportunity_dependencies``,
trigger ``outbox``). Discovery of *new* opportunities stays with CP-13's debounced full
evaluation, which every on-write path and every ingestion already marks due; an event without
dependency keys is therefore not delivered to this consumer.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from eurogas_nexus.domain.market_events import (
    EventTimeline,
    HeldRevision,
    MarketEvent,
    PublishKind,
    SubjectLatest,
    decide_publication,
    evaluate_staleness,
)

NOTIFY_CHANNEL = "market_events"
MAX_ATTEMPTS = 5
#: First retry after one minute, doubling, at most an hour apart.
BACKOFF_BASE = timedelta(minutes=1)
BACKOFF_CAP = timedelta(hours=1)
DEFAULT_BATCH = 100
#: How long one :func:`drain` may keep a consumer busy before it hands back to its loop (the
#: scheduler's next tick, the listen worker's next wake-up), which drains the rest. Until M7 a
#: drain stopped after ten batches (1,000 events) whatever the time; a backlog now drains in
#: one pass unless it takes longer than this.
DRAIN_BUDGET_SECONDS = 45.0

PENDING = "pending"
FAILED = "failed"
PROCESSED = "processed"
SUPERSEDED = "superseded"
DEAD = "dead"
STATUSES = (PENDING, FAILED, PROCESSED, SUPERSEDED, DEAD)
_DUE = (PENDING, FAILED)


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def backoff(attempts: int) -> timedelta:
    """The wait before attempt ``attempts + 1``."""

    return min(BACKOFF_CAP, BACKOFF_BASE * (2 ** max(0, attempts - 1)))


# --------------------------------------------------------------------------------- consumers


class Consumer(Protocol):
    """Something that reacts to market events."""

    name: str

    def accepts(self, record) -> bool:
        """Whether this consumer needs a delivery of the event (a ``MarketEventRecord``)."""

    def handle(self, session, records: Sequence[Any], *, now_utc: datetime) -> dict[str, Any]:
        """Process a batch in the caller's transaction; raise to have it retried."""


_CONSUMERS: dict[str, Consumer] = {}


def register_consumer(consumer: Consumer) -> Consumer:
    """Subscribe a consumer (idempotent by name).

    Raises:
        ValueError: another consumer already holds the name.
    """

    held = _CONSUMERS.get(consumer.name)
    if held is not None and held is not consumer:
        raise ValueError(f"consumer {consumer.name!r} is already registered")
    _CONSUMERS[consumer.name] = consumer
    return consumer


def unregister_consumer(name: str) -> None:
    """Remove a consumer (tests)."""

    _CONSUMERS.pop(name, None)


def consumers() -> tuple[Consumer, ...]:
    """Every registered consumer, by name."""

    _ensure_builtin()
    return tuple(_CONSUMERS[name] for name in sorted(_CONSUMERS))


def consumer(name: str) -> Consumer:
    """One registered consumer.

    Raises:
        KeyError: no consumer has the name.
    """

    _ensure_builtin()
    return _CONSUMERS[name]


# ----------------------------------------------------------------------------------- publish


@dataclass(frozen=True)
class Published:
    """What :func:`publish` did."""

    kind: PublishKind
    event_id: str
    revision: int
    supersedes_event_id: str | None = None
    deliveries: tuple[str, ...] = ()
    reason: str = ""

    def to_json(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "event_id": self.event_id,
            "revision": self.revision,
            "supersedes_event_id": self.supersedes_event_id,
            "deliveries": list(self.deliveries),
            "reason": self.reason,
        }


def _held(session, event_key: str) -> list:
    from eurogas_nexus.db.models import MarketEventRecord

    return (
        session.query(MarketEventRecord)
        .filter(MarketEventRecord.event_key == event_key)
        .order_by(MarketEventRecord.revision)
        .all()
    )


def publish(session, event: MarketEvent) -> Published:
    """Record ``event`` and its deliveries in the caller's transaction (commit is the caller's).

    A duplicate or an out-of-order replay writes nothing. A revision supersedes the deliveries
    of the revision before it that have not been processed yet.
    """

    from sqlalchemy.exc import IntegrityError

    for attempt in (1, 2):
        try:
            with session.begin_nested():
                return _publish_once(session, event)
        except IntegrityError:
            # Another transaction wrote this revision first (the unique key refused ours):
            # decide again against what it wrote; the second decision is a duplicate or the
            # next revision.
            if attempt == 2:
                raise
    raise AssertionError("unreachable")


def _publish_once(session, event: MarketEvent) -> Published:
    from eurogas_nexus.db.models import MarketEventDeliveryRecord, MarketEventRecord

    held = _held(session, event.event_key)
    decision = decide_publication(
        event,
        [
            HeldRevision(row.revision, row.content_hash, _aware(row.published_at_utc))
            for row in held
        ],
    )
    if not decision.writes:
        return Published(
            decision.kind, event.event_id(decision.revision), decision.revision,
            reason=decision.reason,
        )
    previous = held[-1] if held else None
    row = MarketEventRecord(
        event_id=event.event_id(decision.revision),
        event_key=event.event_key,
        revision=decision.revision,
        supersedes_event_id=None if previous is None else previous.event_id,
        content_hash=event.content_hash,
        source_id=event.source_id,
        event_type=event.event_type,
        subject_key=event.subject_key,
        input_class=event.input_class,
        priority=event.priority,
        dependency_keys=list(event.dependency_keys),
        payload_json=dict(event.payload),
        market_time_utc=event.market_time_utc,
        published_at_utc=event.published_at_utc,
        ingested_at_utc=event.ingested_at_utc,
        correlation_id=(event.correlation_id or None) and event.correlation_id[:64],
    )
    session.add(row)
    session.flush()
    if previous is not None:
        (
            session.query(MarketEventDeliveryRecord)
            .filter(MarketEventDeliveryRecord.event_seq == previous.seq)
            .filter(MarketEventDeliveryRecord.status.in_(_DUE))
            .update(
                {"status": SUPERSEDED, "last_error": f"superseded by {row.event_id}"},
                synchronize_session=False,
            )
        )
    names = []
    for item in consumers():
        if not item.accepts(row):
            continue
        session.add(
            MarketEventDeliveryRecord(
                consumer=item.name,
                event_seq=row.seq,
                status=PENDING,
                attempts=0,
                available_at_utc=event.ingested_at_utc,
            )
        )
        names.append(item.name)
    session.flush()
    _notify(session, row.event_id)
    return Published(
        decision.kind,
        row.event_id,
        row.revision,
        supersedes_event_id=row.supersedes_event_id,
        deliveries=tuple(names),
    )


def _notify(session, event_id: str) -> None:
    """Wake listening workers at commit (PostgreSQL only; delivery never depends on it)."""

    bind = session.get_bind()
    if bind.dialect.name != "postgresql":
        return
    from sqlalchemy import text

    session.execute(
        text("SELECT pg_notify(:channel, :payload)"),
        {"channel": NOTIFY_CHANNEL, "payload": event_id},
    )


# ----------------------------------------------------------------------------------- process


def _due(session, name: str, now: datetime, limit: int):
    from eurogas_nexus.db.models import MarketEventDeliveryRecord, MarketEventRecord

    query = (
        session.query(MarketEventDeliveryRecord, MarketEventRecord)
        .join(MarketEventRecord, MarketEventRecord.seq == MarketEventDeliveryRecord.event_seq)
        .filter(MarketEventDeliveryRecord.consumer == name)
        .filter(MarketEventDeliveryRecord.status.in_(_DUE))
        .filter(MarketEventDeliveryRecord.available_at_utc <= now)
        .order_by(MarketEventRecord.priority, MarketEventRecord.seq)
        .limit(limit)
    )
    if session.get_bind().dialect.name == "postgresql":
        # Two workers never take the same deliveries; a locked one is left for the other.
        query = query.with_for_update(skip_locked=True, of=MarketEventDeliveryRecord)
    return query.all()


def process(
    session,
    name: str,
    *,
    now_utc: datetime | None = None,
    limit: int = DEFAULT_BATCH,
    clock=None,
) -> dict[str, Any]:
    """Deliver one batch of due events to consumer ``name``; commit is the caller's.

    The consumer's writes run in a savepoint: a consumer that raises leaves nothing behind, its
    deliveries are retried after :func:`backoff`, and are ``dead`` after :data:`MAX_ATTEMPTS`.

    Args:
        now_utc: The instant deliveries must be due by (default now).
        clock: When processing completed (default the wall clock; tests fix it).

    Returns:
        ``{"consumer", "claimed", "processed", "failed", "dead", "result"}``.
    """

    now = _aware(now_utc) or datetime.now(UTC)
    target = consumer(name)
    rows = _due(session, name, now, limit)
    summary: dict[str, Any] = {
        "consumer": name,
        "claimed": len(rows),
        "processed": 0,
        "failed": 0,
        "dead": 0,
        "result": None,
    }
    if not rows:
        return summary
    deliveries = [delivery for delivery, _event in rows]
    events = [event for _delivery, event in rows]
    try:
        with session.begin_nested():
            result = target.handle(session, events, now_utc=now) or {}
    except Exception as exc:  # noqa: BLE001 - a consumer failure is retried, never raised
        message = f"{type(exc).__name__}: {exc}"[:300]
        for delivery in deliveries:
            delivery.attempts = (delivery.attempts or 0) + 1
            delivery.last_error = message
            if delivery.attempts >= MAX_ATTEMPTS:
                delivery.status = DEAD
                summary["dead"] += 1
            else:
                delivery.status = FAILED
                delivery.available_at_utc = now + backoff(delivery.attempts)
                summary["failed"] += 1
        session.flush()
        summary["result"] = {"error": message}
        return summary
    finished = _aware((clock or (lambda: datetime.now(UTC)))())
    finished = max(finished, now)
    notified = result.pop("notified", False)
    for delivery in deliveries:
        delivery.attempts = (delivery.attempts or 0) + 1
        delivery.status = PROCESSED
        delivery.processed_at_utc = finished
        delivery.notified_at_utc = finished if notified else None
        delivery.last_error = None
        delivery.result_json = result
    session.flush()
    summary["processed"] = len(deliveries)
    summary["result"] = result
    return summary


def drain(
    session_factory,
    *,
    now_utc: datetime | None = None,
    limit: int = DEFAULT_BATCH,
    max_batches: int | None = None,
    max_seconds: float | None = DRAIN_BUDGET_SECONDS,
    clock=None,
) -> list[dict[str, Any]]:
    """Process every consumer, each batch in its own transaction, until nothing is due.

    Args:
        max_batches: Batches per consumer at most (``None``: no count limit).
        max_seconds: Time one consumer may take at most (``None``: no time limit); what is
            left stays due for the caller's next pass.
        clock: Monotonic seconds (tests fix it).

    A failure of the store (not of a consumer) is reported in the batch summary and stops that
    consumer for this tick; the caller's loop keeps running.
    """

    import time

    tick = clock or time.monotonic
    summaries = []
    for item in consumers():
        started = tick()
        batches = 0
        while max_batches is None or batches < max_batches:
            if batches and max_seconds is not None and tick() - started >= max_seconds:
                summaries.append({"consumer": item.name, "status": "budget_spent"})
                break
            batches += 1
            try:
                with session_factory() as session:
                    summary = process(session, item.name, now_utc=now_utc, limit=limit)
                    session.commit()
            except Exception as exc:  # noqa: BLE001 - never stops the worker loop
                summaries.append(
                    {"consumer": item.name, "status": "error", "error_type": type(exc).__name__}
                )
                break
            if summary["claimed"]:
                summaries.append(summary)
            if summary["claimed"] < limit or summary["failed"] or summary["dead"]:
                break
    return summaries


# ------------------------------------------------------------------------------------ replay


def replay(
    session,
    name: str,
    *,
    now_utc: datetime | None = None,
    from_seq: int | None = None,
    since_utc: datetime | None = None,
    event_ids: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Re-arm consumer ``name`` for the latest revision of each matching event.

    Selects events by log position, ingestion time or id (all given filters apply). A consumer
    registered after an event was published gets a delivery it never had. Superseded revisions
    are not replayed: a replay reproduces the current state, not the history of corrections.
    Commit is the caller's.
    """

    from sqlalchemy import func

    from eurogas_nexus.db.models import MarketEventDeliveryRecord, MarketEventRecord

    now = _aware(now_utc) or datetime.now(UTC)
    target = consumer(name)
    latest = (
        session.query(
            MarketEventRecord.event_key, func.max(MarketEventRecord.revision).label("revision")
        )
        .group_by(MarketEventRecord.event_key)
        .subquery()
    )
    query = session.query(MarketEventRecord).join(
        latest,
        (MarketEventRecord.event_key == latest.c.event_key)
        & (MarketEventRecord.revision == latest.c.revision),
    )
    if from_seq is not None:
        query = query.filter(MarketEventRecord.seq >= from_seq)
    if since_utc is not None:
        query = query.filter(MarketEventRecord.ingested_at_utc >= _aware(since_utc))
    ids = None if event_ids is None else sorted(set(event_ids))
    if ids is not None:
        query = query.filter(MarketEventRecord.event_id.in_(ids))
    rearmed = 0
    created = 0
    for event in query.order_by(MarketEventRecord.seq).all():
        if not target.accepts(event):
            continue
        delivery = session.get(MarketEventDeliveryRecord, (name, event.seq))
        if delivery is None:
            session.add(
                MarketEventDeliveryRecord(
                    consumer=name,
                    event_seq=event.seq,
                    status=PENDING,
                    attempts=0,
                    available_at_utc=now,
                )
            )
            created += 1
            continue
        delivery.status = PENDING
        delivery.attempts = 0
        delivery.available_at_utc = now
        delivery.processed_at_utc = None
        delivery.notified_at_utc = None
        delivery.last_error = None
        delivery.result_json = None
        rearmed += 1
    session.flush()
    return {"consumer": name, "rearmed": rearmed, "created": created}


# ------------------------------------------------------------------------- status and reading


def status(session, *, now_utc: datetime | None = None, dead_limit: int = 20) -> dict[str, Any]:
    """Per consumer: deliveries by status, the oldest due event's lag, and the dead letters."""

    from sqlalchemy import func

    from eurogas_nexus.db.models import MarketEventDeliveryRecord, MarketEventRecord

    now = _aware(now_utc) or datetime.now(UTC)
    report: dict[str, Any] = {
        "as_of_utc": now.isoformat(),
        "events": session.query(func.count(MarketEventRecord.seq)).scalar() or 0,
        "last_seq": session.query(func.max(MarketEventRecord.seq)).scalar(),
        "consumers": {},
    }
    for item in consumers():
        counts = dict.fromkeys(STATUSES, 0)
        for state, count in (
            session.query(MarketEventDeliveryRecord.status, func.count())
            .filter(MarketEventDeliveryRecord.consumer == item.name)
            .group_by(MarketEventDeliveryRecord.status)
            .all()
        ):
            counts[state] = count
        # How long the oldest delivery that is due now has been waiting: a failed delivery
        # in its backoff is not waiting on the worker.
        oldest = (
            session.query(func.min(MarketEventDeliveryRecord.available_at_utc))
            .filter(MarketEventDeliveryRecord.consumer == item.name)
            .filter(MarketEventDeliveryRecord.status.in_(_DUE))
            .filter(MarketEventDeliveryRecord.available_at_utc <= now)
            .scalar()
        )
        dead = (
            session.query(MarketEventDeliveryRecord, MarketEventRecord)
            .join(MarketEventRecord, MarketEventRecord.seq == MarketEventDeliveryRecord.event_seq)
            .filter(MarketEventDeliveryRecord.consumer == item.name)
            .filter(MarketEventDeliveryRecord.status == DEAD)
            .order_by(MarketEventRecord.seq)
            .limit(dead_limit)
            .all()
        )
        report["consumers"][item.name] = {
            "counts": counts,
            "oldest_due_lag_seconds": (
                None if oldest is None else (now - _aware(oldest)).total_seconds()
            ),
            "dead_letters": [
                {
                    "event_id": event.event_id,
                    "subject_key": event.subject_key,
                    "attempts": delivery.attempts,
                    "last_error": delivery.last_error,
                }
                for delivery, event in dead
            ],
        }
    return report


def staleness(
    session, *, now_utc: datetime | None = None, expectations: dict[str, int] | None = None
) -> list[dict[str, Any]]:
    """Each event subject's freshness from its newest ingestion, stale first."""

    from sqlalchemy import func

    from eurogas_nexus.db.models import MarketEventRecord

    now = _aware(now_utc) or datetime.now(UTC)
    rows = (
        session.query(
            MarketEventRecord.subject_key,
            MarketEventRecord.source_id,
            MarketEventRecord.input_class,
            func.max(MarketEventRecord.ingested_at_utc),
        )
        .group_by(
            MarketEventRecord.subject_key,
            MarketEventRecord.source_id,
            MarketEventRecord.input_class,
        )
        .all()
    )
    latest = [
        SubjectLatest(subject, source, input_class, _aware(last))
        for subject, source, input_class, last in rows
    ]
    return [
        item.to_json()
        for item in evaluate_staleness(latest, now_utc=now, expectations=expectations)
    ]


def timeline(session, event_id: str, name: str) -> dict[str, Any] | None:
    """An event's five times and latencies as consumer ``name`` saw them (None: not held)."""

    from eurogas_nexus.db.models import MarketEventDeliveryRecord, MarketEventRecord

    event = (
        session.query(MarketEventRecord).filter(MarketEventRecord.event_id == event_id).first()
    )
    if event is None:
        return None
    delivery = session.get(MarketEventDeliveryRecord, (name, event.seq))
    line = EventTimeline(
        market_time_utc=_aware(event.market_time_utc),
        published_at_utc=_aware(event.published_at_utc),
        ingested_at_utc=_aware(event.ingested_at_utc),
        processed_at_utc=None if delivery is None else _aware(delivery.processed_at_utc),
        notified_at_utc=None if delivery is None else _aware(delivery.notified_at_utc),
    )

    def iso(value: datetime | None) -> str | None:
        return None if value is None else value.isoformat()

    return {
        "event_id": event.event_id,
        "consumer": name,
        "status": None if delivery is None else delivery.status,
        "market_time_utc": iso(line.market_time_utc),
        "published_at_utc": iso(line.published_at_utc),
        "ingested_at_utc": iso(line.ingested_at_utc),
        "processed_at_utc": iso(line.processed_at_utc),
        "notified_at_utc": iso(line.notified_at_utc),
        "latencies_seconds": line.latencies_seconds(),
        "issues": line.issues(),
    }


# ------------------------------------------------------------- producers on existing paths


def ingestion_events(session, outcomes: Iterable[dict[str, Any]], *, now_utc: datetime):
    """``source.ingested`` events for the ingestion runs that wrote rows (one per run).

    Class-level: they carry no dependency keys (a run does not say which hub periods it
    changed), so they are recorded for lineage, staleness and replay and are not delivered to
    the opportunity consumer; CP-13 already marks the class due.
    """

    from eurogas_nexus.application.opportunities.schedule import input_class_for_source
    from eurogas_nexus.db.models import IngestionRunRecord
    from eurogas_nexus.domain.connectors.registry import builtin_manifests

    categories = {manifest.source_id: manifest.category for manifest in builtin_manifests()}
    events = []
    for outcome in outcomes:
        if outcome.get("status") not in {"SUCCEEDED", "SUCCEEDED_WITH_WARNINGS"}:
            continue
        run = session.get(IngestionRunRecord, outcome.get("run_id"))
        if run is None or not ((run.rows_inserted or 0) + (run.rows_updated or 0)):
            continue
        events.append(
            MarketEvent(
                source_id=run.source_id[:64],
                event_type="source.ingested",
                subject_key=f"ingestion:{run.source_id}"[:160],
                identity=f"run:{run.run_id}",
                ingested_at_utc=_aware(run.finished_at_utc) or now_utc,
                market_time_utc=_aware(getattr(run, "window_end_utc", None)),
                input_class=input_class_for_source(run.source_id, categories.get(run.source_id)),
                payload={
                    "run_id": run.run_id,
                    "rows_inserted": run.rows_inserted or 0,
                    "rows_updated": run.rows_updated or 0,
                    "status": run.status,
                },
                correlation_id=run.run_id,
            )
        )
    return events


def publish_firm_marks(session, entries: Iterable[Any], *, actor: str, now_utc: datetime):
    """``mark.changed`` events for stored firm marks (one per hub and delivery period).

    The payload holds a digest of the mark, not its value: the firm's marks stay in their own
    table (the outbox is read by operators, the audit log carries no values either).
    """

    import hashlib

    published = []
    for entry in entries:
        digest = hashlib.sha256(
            f"{entry.value}|{entry.unit}|{entry.note or ''}".encode()
        ).hexdigest()[:24]
        label = entry.period.label
        published.append(
            publish(
                session,
                MarketEvent(
                    source_id="firm-marks",
                    event_type="mark.changed",
                    subject_key=f"hub:{entry.hub}:{label}",
                    dependency_keys=(f"hub:{entry.hub}:{label}",),
                    ingested_at_utc=now_utc,
                    payload={"hub": entry.hub, "period": label, "mark_digest": digest},
                    correlation_id=actor[:64],
                ),
            )
        )
    return published


# ------------------------------------------------------------------ the opportunity consumer


class OpportunityImpactConsumer:
    """Re-evaluates only the evaluators whose opportunities read a changed input key."""

    name = "opportunities"
    principal = "market-event-outbox"

    def __init__(self, runner=None) -> None:
        self._runner = runner

    def accepts(self, record) -> bool:
        return bool(record.dependency_keys)

    def handle(self, session, records, *, now_utc: datetime) -> dict[str, Any]:
        from eurogas_nexus.application.opportunities.schedule import affected_by
        from eurogas_nexus.db.models import OpportunityRecord
        from eurogas_nexus.domain.opportunities.evaluator import registered

        keys = sorted({key for record in records for key in (record.dependency_keys or [])})
        affected = affected_by(session, sorted(set(keys) | _fx_crosses(session, keys)))
        names: list[str] = []
        if affected:
            names = sorted(
                {
                    row.evaluator
                    for row in session.query(OpportunityRecord.evaluator)
                    .filter(OpportunityRecord.opportunity_id.in_(affected))
                    .all()
                }
            )
        result: dict[str, Any] = {
            "dependency_keys": keys,
            "affected_opportunities": len(affected),
            "evaluators": names,
            "evaluation_id": None,
            "evaluation_status": None,
        }
        if not names:
            return result
        registry = {item.name: item for item in registered()}
        chosen = [registry[name] for name in names if name in registry]
        result["unregistered_evaluators"] = sorted(set(names) - set(registry))
        if not chosen:
            return result
        from eurogas_nexus.application.opportunities.schedule import evaluation_lock

        # Wait for a full sweep that is merging (seconds); the two never merge at once.
        evaluation_lock(session, wait=True)
        if self._runner is None:
            from eurogas_nexus.application.opportunities.service import run_evaluation

            runner = run_evaluation
        else:
            runner = self._runner
        summary = runner(
            session,
            trigger="outbox",
            triggered_by=self.principal,
            now_utc=now_utc,
            evaluators=chosen,
        )
        result["evaluation_id"] = summary.get("evaluation_id")
        result["evaluation_status"] = summary.get("status")
        return result


def _fx_crosses(session, keys: Sequence[str]) -> set[str]:
    """Stored ``fx:`` keys a fixing also moves.

    Fixings are quoted against EUR, the pivot every conversion goes through, so a change to
    ``fx:EURUSD`` moves every stored pair that contains USD (``fx:GBPUSD``, ``fx:USDGBP``).
    A non-EUR fixing moves pairs that contain either of its currencies.
    """

    from eurogas_nexus.db.models import OpportunityDependencyRecord

    currencies: set[str] = set()
    for key in keys:
        pair = key[3:] if key.startswith("fx:") else ""
        if len(pair) == 6 and pair.isalpha():
            currencies.update(code for code in (pair[:3], pair[3:]) if code != "EUR")
    if not currencies:
        return set()
    stored = {
        row[0]
        for row in session.query(OpportunityDependencyRecord.input_key)
        .filter(OpportunityDependencyRecord.input_key.like("fx:%"))
        .distinct()
        .all()
    }
    return {
        key
        for key in stored
        if len(key) >= 9 and {key[3:6], key[6:9]} & currencies
    }


_BUILTIN_REGISTERED = False


def _ensure_builtin() -> None:
    global _BUILTIN_REGISTERED
    if _BUILTIN_REGISTERED:
        return
    _BUILTIN_REGISTERED = True
    if OpportunityImpactConsumer.name not in _CONSUMERS:
        _CONSUMERS[OpportunityImpactConsumer.name] = OpportunityImpactConsumer()


__all__ = [
    "BACKOFF_BASE",
    "BACKOFF_CAP",
    "DEAD",
    "DRAIN_BUDGET_SECONDS",
    "FAILED",
    "MAX_ATTEMPTS",
    "NOTIFY_CHANNEL",
    "PENDING",
    "PROCESSED",
    "SUPERSEDED",
    "Consumer",
    "OpportunityImpactConsumer",
    "Published",
    "backoff",
    "consumer",
    "consumers",
    "drain",
    "ingestion_events",
    "process",
    "publish",
    "publish_firm_marks",
    "register_consumer",
    "replay",
    "staleness",
    "status",
    "timeline",
    "unregister_consumer",
]
