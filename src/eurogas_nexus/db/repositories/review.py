"""Trader-review decision repository (persisted + audited)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy.orm import Session

from eurogas_nexus.db.models import ReviewDecisionRecord
from eurogas_nexus.db.repositories.audit import record_audit_event
from eurogas_nexus.domain.identity.principal import normalize_principal


def record_review_decision(
    session: Session,
    *,
    entity_type: str,
    entity_id: str,
    actor: str,
    decision: str,
    note: str | None = None,
    now_utc: datetime | None = None,
) -> dict:
    """Persist one review decision together with its audit event."""

    now = _as_utc(now_utc or datetime.now(UTC))
    principal = normalize_principal(actor)
    row = ReviewDecisionRecord(
        decision_id=f"review-{uuid4().hex[:24]}",
        entity_type=entity_type,
        entity_id=entity_id,
        actor=principal,
        decision=decision,
        note=note,
        created_at_utc=now,
    )
    session.add(row)
    record_audit_event(
        session,
        event_type=f"review.{entity_type}",
        principal=principal,
        action=f"review_{decision}",
        resource=f"{entity_type}:{entity_id}",
        outcome=decision,
        severity="warning" if decision == "rejected" else "info",
        detail=note or "",
        source_system="review",
        now_utc=now,
    )
    session.flush()
    return review_payload(row)


def list_review_decisions(
    session: Session,
    *,
    entity_type: str | None = None,
    entity_id: str | None = None,
    limit: int = 100,
) -> list[dict]:
    """List review decisions, newest first."""

    query = session.query(ReviewDecisionRecord)
    if entity_type:
        query = query.filter(ReviewDecisionRecord.entity_type == entity_type)
    if entity_id:
        query = query.filter(ReviewDecisionRecord.entity_id == entity_id)
    rows = (
        query.order_by(ReviewDecisionRecord.created_at_utc.desc())
        .limit(max(1, min(limit, 500)))
        .all()
    )
    return [review_payload(row) for row in rows]


def review_payload(row: ReviewDecisionRecord) -> dict:
    return {
        "decision_id": row.decision_id,
        "entity_type": row.entity_type,
        "entity_id": row.entity_id,
        "actor": row.actor,
        "decision": row.decision,
        "note": row.note,
        "created_at_utc": _as_utc(row.created_at_utc).isoformat(),
    }


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
