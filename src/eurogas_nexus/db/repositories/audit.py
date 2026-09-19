"""Shared audit-event recording helper (append-only, human-review aware)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy.orm import Session

from eurogas_nexus.db.models import AuditEventRecord


def list_audit_events_for_resource(
    session: Session, resource: str, *, limit: int = 50
) -> list[dict[str, object]]:
    """Return the audit trail recorded against one resource, oldest first.

    按资源读取审计轨迹（最早的在前），供决策包引用而不必猜测关联方式。

    Args:
        session: Open session.
        resource: The ``resource`` value the acts were recorded under, e.g.
            ``decision_case:<case_id>``.
        limit: Maximum rows to return; the newest ``limit`` are kept, then ordered oldest first.

    Returns:
        One dict per event with the fields a reviewer cites: action, principal, outcome, severity,
        timestamp and the detail text.
    """

    from sqlalchemy import desc

    rows = (
        session.query(AuditEventRecord)
        .filter(AuditEventRecord.resource == resource)
        .order_by(desc(AuditEventRecord.event_ts_utc))
        .limit(limit)
        .all()
    )
    ordered = list(reversed(rows))
    return [
        {
            "event_id": row.event_id,
            "action": row.action,
            "principal": row.principal,
            "outcome": row.outcome,
            "severity": row.severity,
            "event_ts_utc": (
                row.event_ts_utc.isoformat() if row.event_ts_utc is not None else None
            ),
            "detail": row.detail,
        }
        for row in ordered
    ]


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
    permission: str | None = None,
    correlation_id: str | None = None,
    client_type: str | None = None,
    before_summary: dict | None = None,
    after_summary: dict | None = None,
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
        permission=permission,
        correlation_id=correlation_id,
        client_type=client_type,
        before_summary=before_summary,
        after_summary=after_summary,
    )
    session.add(event)
    session.flush()
    return event
