"""Best-effort audit event persistence for governed runtime actions.

Gate 1: policy decisions (entitlement denials, export denials, LLM
invocations, review decisions) are recorded as immutable ``audit_events`` rows
with request context when the runtime DB is available. Failures to record are
never raised: the API already reports runtime-DB state to operators.
"""

from __future__ import annotations

from datetime import UTC, datetime

AUDIT_APP_SOURCE = "eurogas-nexus"


def record_audit_event(
    *,
    event_type: str,
    action: str,
    resource: str,
    principal: str = "operator",
    outcome: str = "recorded",
    severity: str = "info",
    detail: str = "",
    source_system: str = AUDIT_APP_SOURCE,
    request_id: str | None = None,
) -> str | None:
    """Persist one audit event and return its id, or None when unavailable.

    Never raises: audit recording must not break governed requests.
    """

    try:
        from eurogas_nexus.db.repositories.audit import record_audit_event as _record
        from eurogas_nexus.db.session import get_session_factory, resolve_database_url

        if resolve_database_url() is None:
            return None
        with get_session_factory()() as session:
            full_detail = detail
            if request_id:
                prefix = f"request_id={request_id}"
                full_detail = f"{prefix}; {detail}" if detail else prefix
            event = _record(
                session,
                event_type=event_type,
                principal=principal,
                action=action,
                resource=resource,
                outcome=outcome,
                severity=severity,
                detail=full_detail,
                source_system=source_system,
                now_utc=datetime.now(UTC),
            )
            session.commit()
            return event.event_id
    except Exception:
        return None
