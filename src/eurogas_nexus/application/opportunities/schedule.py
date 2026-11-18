"""When evaluations run (design J.2): on demand now; the job runner and the outbox later.

- **On demand** (:func:`evaluate_on_demand`): a person asks for a fresh evaluation; it runs
  synchronously, firm-wide, and is recorded with who asked.
- **Job runner** (CP-13): :class:`EvaluationTrigger` is the seam. After a scheduled ingestion
  that changes an input class (prices, tariffs, outages, book import) or a write of a
  contract, mark, assumption set or limit, the runner calls ``input_changed``; the trigger
  runs a full evaluation at most once per :data:`DEBOUNCE` (:func:`due`).
- **Outbox** (M4): :class:`OutboxSubscription` is the seam. Each record stores the input keys
  it read (``opportunity_dependencies``); an event carrying a key re-evaluates only the
  records that depend on it (:func:`affected_by`). The keys are stored from the first
  release so M4 needs no remodelling.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, timedelta
from typing import Any, Protocol

#: At most one scheduled full evaluation per five minutes.
DEBOUNCE = timedelta(minutes=5)

#: Input classes whose change makes a scheduled evaluation due.
INPUT_CLASSES = frozenset(
    {"prices", "tariffs", "outages", "book", "marks", "assumptions", "limits", "fx", "rates"}
)


def due(last_started_utc: datetime | None, now_utc: datetime) -> bool:
    """Whether a scheduled evaluation may start now (debounce)."""

    return last_started_utc is None or now_utc - last_started_utc >= DEBOUNCE


class EvaluationTrigger(Protocol):
    """What the job runner calls when an input class changes (implementation: CP-13)."""

    def input_changed(self, input_class: str, at_utc: datetime) -> None:
        """Note a change; run (or schedule) a debounced full evaluation."""


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
