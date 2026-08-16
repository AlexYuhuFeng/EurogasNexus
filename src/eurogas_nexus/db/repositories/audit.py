"""Shared audit-event recording helper (append-only, human-review aware)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy.orm import Session

from eurogas_nexus.db.models import AuditEventRecord


def record_audit_event(
    session: Session,
    *,
    event_type: str,
    principal: str,
    action: str,
    resource: str,
    outcome: str = "recorded",
    severity: str = "info",
    detail: str = "",
    source_system: str = "eurogas-nexus",
    now_utc: datetime | None = None,
) -> AuditEventRecord:
    """Append one audit event to the append-only audit trail."""

    event = AuditEventRecord(
        event_id=f"audit-{uuid4().hex[:24]}",
        event_type=event_type,
        severity=severity,
        principal=principal,
        action=action,
        resource=resource,
        outcome=outcome,
        detail=detail,
        event_ts_utc=now_utc or datetime.now(UTC),
        source_system=source_system,
        human_review_required=True,
    )
    session.add(event)
    session.flush()
    return event
