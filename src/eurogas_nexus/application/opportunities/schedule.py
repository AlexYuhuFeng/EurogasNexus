"""When evaluations run (design J.2): on demand now; the job runner and the outbox later.

- **On demand** (:func:`evaluate_on_demand`): a person asks for a fresh evaluation; it runs
  synchronously, firm-wide, and is recorded with who asked.
- **Job runner** (CP-13): a scheduled ingestion that changed rows (:func:`note_ingestion_changes`)
  or a write of a contract, book, mark, assumption set, limit or terminal terms
  (:func:`note_input_changed`, in the writer's own transaction) marks its input class pending
  (``opportunity_pending_inputs``). The data-operations scheduler calls :func:`run_due` on
  every tick: while classes are pending it runs one full evaluation, at most once per
  :data:`DEBOUNCE` (:func:`due`), and clears the classes noted before the run started. A
  failing evaluator produces no opportunity and one administrator alert (the monitoring
  scan reads the run's evaluator status); the desk sees nothing of it.
  :class:`StoreTrigger` is the :class:`EvaluationTrigger` over that table.
- **Outbox** (M4): :class:`OutboxSubscription` is the seam. Each record stores the input keys
  it read (``opportunity_dependencies``); an event carrying a key re-evaluates only the
  records that depend on it (:func:`affected_by`). The keys are stored from the first
  release so M4 needs no remodelling.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from eurogas_nexus.streaming.contracts import IngestionInvalidationV1, OpportunityInputClass

#: At most one scheduled full evaluation per five minutes.
DEBOUNCE = timedelta(minutes=5)

#: Input classes whose change makes a scheduled evaluation due.
INPUT_CLASSES = frozenset(item.value for item in OpportunityInputClass)

#: Source categories (connector manifests) and the input class an ingestion of them changes.
#: Weather, power and AI sources feed no evaluator directly: they make nothing due.
CATEGORY_INPUT_CLASS = {
    "price": "prices",
    "fx": "fx",
    "rates": "rates",
    "tariff": "tariffs",
}
#: Infrastructure sources: outage messages, else capacity and flows.
OUTAGE_SOURCES = frozenset({"src-remit-umm", "src-entsog-umm"})

#: Who a scheduled evaluation is recorded as.
SCHEDULE_PRINCIPAL = "dataops-worker"


def due(last_started_utc: datetime | None, now_utc: datetime) -> bool:
    """Whether a scheduled evaluation may start now (debounce)."""

    return last_started_utc is None or now_utc - last_started_utc >= DEBOUNCE


class EvaluationTrigger(Protocol):
    """What the job runner calls when an input class changes (:class:`StoreTrigger`)."""

    def input_changed(self, input_class: str, at_utc: datetime) -> None:
        """Note a change; run (or schedule) a debounced full evaluation."""


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def note_input_changed(
    session, input_class: str, *, reason: str, at_utc: datetime | None = None
) -> None:
    """Mark an input class pending, in the caller's transaction (it commits with the write).

    Raises:
        ValueError: an unknown input class.
    """

    from eurogas_nexus.db.models import OpportunityPendingInputRecord

    if input_class not in INPUT_CLASSES:
        raise ValueError(f"unknown input class {input_class!r}")
    now = _aware(at_utc) or datetime.now(UTC)
    row = session.get(OpportunityPendingInputRecord, input_class)
    if row is None:
        session.add(
            OpportunityPendingInputRecord(
                input_class=input_class,
                first_noted_at_utc=now,
                last_noted_at_utc=now,
                changes=1,
                last_reason=reason[:128],
            )
        )
    else:
        row.last_noted_at_utc = max(_aware(row.last_noted_at_utc), now)
        row.changes = (row.changes or 0) + 1
        row.last_reason = reason[:128]
    session.flush()


def input_class_for_source(source_id: str, category: str | None) -> str | None:
    """The input class an ingestion of this source changes, or None."""

    if category == "infrastructure":
        return "outages" if source_id in OUTAGE_SOURCES else "capacity"
    return CATEGORY_INPUT_CLASS.get(category or "")


def note_ingestion_changes(session, outcomes: Iterable[dict[str, Any]], *, now_utc: datetime):
    """Mark pending the input classes of the ingestion runs that wrote rows.

    A run that failed, or succeeded without inserting or updating a row, changes nothing.
    Returns the classes noted.
    """

    from eurogas_nexus.db.models import IngestionRunRecord
    from eurogas_nexus.domain.connectors.registry import builtin_manifests

    categories = {manifest.source_id: manifest.category for manifest in builtin_manifests()}
    noted: set[str] = set()
    for outcome in outcomes:
        if outcome.get("status") not in {"SUCCEEDED", "SUCCEEDED_WITH_WARNINGS"}:
            continue
        run = session.get(IngestionRunRecord, outcome.get("run_id"))
        if run is None or not ((run.rows_inserted or 0) + (run.rows_updated or 0)):
            continue
        input_class = input_class_for_source(run.source_id, categories.get(run.source_id))
        if input_class is None:
            continue
        event = IngestionInvalidationV1(
            event_type="opportunity.input.invalidated",
            schema_version=1,
            source_id=run.source_id,
            run_id=run.run_id,
            input_class=input_class,
            noticed_at_utc=_aware(now_utc),
        )
        note_input_changed(
            session,
            event.input_class.value,
            reason=f"ingestion {event.source_id}",
            at_utc=event.noticed_at_utc,
        )
        noted.add(event.input_class.value)
    return sorted(noted)


def last_scheduled_start(session) -> datetime | None:
    """The evaluation instant of the latest scheduled evaluation (its ``as_of_utc``: the
    runner's clock, which a scheduled run is started at)."""

    from eurogas_nexus.db.models import OpportunityEvaluationRecord

    row = (
        session.query(OpportunityEvaluationRecord)
        .filter(OpportunityEvaluationRecord.trigger == "schedule")
        .order_by(OpportunityEvaluationRecord.as_of_utc.desc())
        .first()
    )
    return _aware(row.as_of_utc) if row else None


def run_due(
    session,
    *,
    now_utc: datetime | None = None,
    runner: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Run the debounced scheduled evaluation if input classes are pending; commit is the
    caller's.

    Returns ``{"status": "idle"}`` (nothing pending), ``{"status": "debounced", "next_at_utc"}``
    or ``{"status": "ran", "classes": [...], "evaluation": <summary>}``.
    """

    from eurogas_nexus.db.models import OpportunityPendingInputRecord

    now = _aware(now_utc) or datetime.now(UTC)
    pending = session.query(OpportunityPendingInputRecord).all()
    if not pending:
        return {"status": "idle"}
    last = last_scheduled_start(session)
    if not due(last, now):
        return {
            "status": "debounced",
            "classes": sorted(row.input_class for row in pending),
            "next_at_utc": (last + DEBOUNCE).isoformat(),
        }
    if runner is None:
        from eurogas_nexus.application.opportunities.service import run_evaluation

        runner = run_evaluation
    summary = runner(session, trigger="schedule", triggered_by=SCHEDULE_PRINCIPAL, now_utc=now)
    covered = [row for row in pending if _aware(row.last_noted_at_utc) <= now]
    for row in covered:
        session.delete(row)
    session.flush()
    return {
        "status": "ran",
        "classes": sorted(row.input_class for row in covered),
        "evaluation": summary,
    }


class StoreTrigger:
    """The job runner's :class:`EvaluationTrigger`: notes the change in the store."""

    def __init__(self, session) -> None:
        self.session = session

    def input_changed(self, input_class: str, at_utc: datetime) -> None:
        note_input_changed(self.session, input_class, reason="job runner", at_utc=at_utc)


class OutboxSubscription(Protocol):
    """What the outbox delivers to (implementation: M4, PostgreSQL LISTEN/NOTIFY)."""

    def keys(self) -> Iterable[str]:
        """The input keys this subscriber depends on."""

    def deliver(self, event_keys: Iterable[str], at_utc: datetime) -> None:
        """Re-evaluate the records that depend on any of the keys."""


def affected_by(session, input_keys: Iterable[str]) -> list[str]:
    """Opportunity ids whose stored dependencies include any of the keys."""

    from eurogas_nexus.db.models import OpportunityDependencyRecord

    keys = sorted(set(input_keys))
    if not keys:
        return []
    return sorted(
        {
            row.opportunity_id
            for row in session.query(OpportunityDependencyRecord)
            .filter(OpportunityDependencyRecord.input_key.in_(keys))
            .all()
        }
    )


def evaluate_on_demand(
    session, *, principal_id: str, now_utc: datetime | None = None, **kw
) -> dict[str, Any]:
    """Run a full evaluation now for a person who asked; commit is the caller's."""

    from eurogas_nexus.application.opportunities.service import run_evaluation

    return run_evaluation(
        session, trigger="on_demand", triggered_by=principal_id, now_utc=now_utc, **kw
    )
