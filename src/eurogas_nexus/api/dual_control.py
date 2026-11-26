"""Dual control on security-relevant changes (security review H7).

One administrator could switch four eyes off, grant roles and scopes, create a second
account and approve their own proposals from it. Now each security-relevant change needs a
second administrator who is not the requester:

1. The requesting call is answered 409 ``dual_control_required`` with a ``change_id``; the
   exact call (method, path, SHA-256 of the body) is stored as a pending privileged change.
2. A different administrator approves it (``POST /api/access/privileged-changes/{id}/approve``).
   Refused when the approver is the requester under any of their names, or when the requester
   created the approver's account or changed its grants within the cooling period
   (``EUROGAS_NEXUS_DUAL_CONTROL_COOLING_DAYS``, default 7): a sock puppet cannot approve.
3. The requester or the approver repeats the call with ``X-Eurogas-Dual-Control: <change_id>``;
   the stored hash must match, and the change is applied once.

Break-glass: ``X-Eurogas-Break-Glass: <reason of at least 20 characters>`` applies the change
at once when ``EUROGAS_NEXUS_BREAK_GLASS`` is not ``off``; it is audited at ``critical``
severity (``security.break_glass.used``), forwarded to the SIEM like every audit row, and
listed on the privileged-change page for review.

``EUROGAS_NEXUS_DUAL_CONTROL``: ``on`` (default in trial and release) or ``off`` (default in
development and test, where one developer works alone); ``off`` is refused in trial and
release.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from fastapi import HTTPException, Request

DUAL_CONTROL_ENV = "EUROGAS_NEXUS_DUAL_CONTROL"
COOLING_DAYS_ENV = "EUROGAS_NEXUS_DUAL_CONTROL_COOLING_DAYS"
BREAK_GLASS_ENV = "EUROGAS_NEXUS_BREAK_GLASS"
APPROVAL_HEADER = "X-Eurogas-Dual-Control"
BREAK_GLASS_HEADER = "X-Eurogas-Break-Glass"
PRODUCTION = frozenset({"trial", "release"})
MIN_BREAK_GLASS_REASON = 20

from eurogas_nexus.application.sock_puppet import (  # noqa: E402
    sock_puppet_refusal,
)

PENDING, APPROVED, REJECTED, WITHDRAWN, APPLIED = (
    "pending", "approved", "rejected", "withdrawn", "applied"
)


def _environment(environ=None) -> str:
    from eurogas_nexus.core.config import runtime_environment

    return runtime_environment(environ)


def dual_control_enabled() -> bool:
    raw = (os.environ.get(DUAL_CONTROL_ENV) or "").strip().lower()
    if raw in {"on", "true", "1", "yes"}:
        return True
    if raw in {"off", "false", "0", "no"}:
        return _environment() not in PRODUCTION
    return _environment() in PRODUCTION


from eurogas_nexus.security.dual_control_policy import (  # noqa: E402, F401 - re-exported
    assert_dual_control_setting_allowed,
)


def break_glass_allowed() -> bool:
    return (os.environ.get(BREAK_GLASS_ENV) or "on").strip().lower() not in {"off", "false", "0"}


def body_digest(body: Any) -> str:
    text = json.dumps(body, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _ids(principal: Any) -> set[str]:
    return {str(v) for v in (getattr(principal, "principal_id", None),
                             getattr(principal, "name", None)) if v}


def _session():
    from eurogas_nexus.db.session import get_session_factory

    return get_session_factory()()


def _audit(session, *, principal: str, action: str, resource: str, outcome: str,
           detail: str, severity: str = "warning") -> None:
    from eurogas_nexus.db.repositories.audit import record_governed_audit

    record_governed_audit(
        session,
        event_type="governance.security",
        principal=principal[:64],
        action=action,
        resource=resource[:128],
        outcome=outcome,
        severity=severity,
        detail=detail[:2000],
        source_system="dual-control",
    )


def require_dual_control(
    request: Request, *, kind: str, body: Any, summary: str
) -> None:
    """Let a security-relevant call through only with a second administrator's approval.

    Returns when the call may proceed (dual control off, an approved matching change, or an
    allowed break-glass). Otherwise stores a pending change and raises 409
    ``dual_control_required`` naming it.
    """

    from eurogas_nexus.db.models import PrivilegedChangeRecord

    principal = getattr(request.state, "identity", None)
    actor = str(getattr(principal, "principal_id", None) or "unknown")
    digest = body_digest(body)
    method, path = request.method.upper(), request.url.path
    if not dual_control_enabled():
        return
    approval = (request.headers.get(APPROVAL_HEADER) or "").strip()
    reason = (request.headers.get(BREAK_GLASS_HEADER) or "").strip()
    with _session() as session:
        if approval:
            change = session.get(PrivilegedChangeRecord, approval)
            ok = (
                change is not None
                and change.state == APPROVED
                and change.method == method
                and change.path == path
                and change.body_sha256 == digest
                and actor in {change.requested_by, change.decided_by}
            )
            if not ok:
                _audit(session, principal=actor, action="security.dual_control.refused",
                       resource=f"privileged_change:{approval}", outcome="denied",
                       detail=f"{method} {path}: approval does not match this call")
                session.commit()
                raise HTTPException(status_code=403, detail={
                    "code": "dual_control_approval_invalid",
                    "message": "The approval does not match this change, or was used already.",
                })
            change.state = APPLIED
            change.applied_at_utc = datetime.now(UTC)
            _audit(session, principal=actor, action="security.dual_control.applied",
                   resource=f"privileged_change:{change.change_id}", outcome="applied",
                   detail=f"{kind}: {change.summary}; requested_by={change.requested_by}; "
                          f"approved_by={change.decided_by}", severity="info")
            session.commit()
            return
        if reason:
            if not break_glass_allowed() or len(reason) < MIN_BREAK_GLASS_REASON:
                raise HTTPException(status_code=403, detail={
                    "code": "break_glass_refused",
                    "message": (
                        f"Break-glass needs a reason of at least {MIN_BREAK_GLASS_REASON} "
                        f"characters and {BREAK_GLASS_ENV} not set to off."
                    ),
                })
            _audit(session, principal=actor, action="security.break_glass.used",
                   resource=f"{kind}:{path}", outcome="applied", severity="critical",
                   detail=f"{method} {path}: {summary}; reason={reason[:500]}")
            session.commit()
            return
        change = PrivilegedChangeRecord(
            change_id=f"pc-{uuid4().hex[:24]}",
            kind=kind,
            method=method,
            path=path[:200],
            body_sha256=digest,
            body_json=body if isinstance(body, dict) else {"value": body},
            summary=summary[:300],
            state=PENDING,
            requested_by=actor[:80],
            requested_by_name=str(getattr(principal, "name", actor))[:80],
            requested_at_utc=datetime.now(UTC),
        )
        session.add(change)
        _audit(session, principal=actor, action="security.dual_control.requested",
               resource=f"privileged_change:{change.change_id}", outcome="pending",
               detail=f"{kind}: {summary}", severity="info")
        session.commit()
        change_id = change.change_id
    raise HTTPException(status_code=409, detail={
        "code": "dual_control_required",
        "message": (
            "This change needs a second administrator. It is waiting for approval under "
            "Admin, Access, Pending approvals; once approved, repeat it with the approval."
        ),
        "change_id": change_id,
        "approval_header": APPROVAL_HEADER,
    })


def decide(change_id: str, approver: Any, *, approve: bool, note: str | None) -> dict:
    """Approve or reject a pending change as a second administrator."""

    from eurogas_nexus.db.models import PrivilegedChangeRecord

    actor = str(getattr(approver, "principal_id", None) or "unknown")
    with _session() as session:
        change = session.get(PrivilegedChangeRecord, change_id)
        if change is None:
            raise HTTPException(status_code=404, detail={"code": "privileged_change_not_found"})
        if change.state != PENDING:
            raise HTTPException(status_code=409, detail={
                "code": "privileged_change_not_pending", "state": change.state})
        if approve:
            refusal = sock_puppet_refusal(
                session, _ids(approver), {change.requested_by, change.requested_by_name},
                getattr(approver, "principal_id", None),
            )
            if refusal is not None:
                _audit(session, principal=actor, action="security.dual_control.refused",
                       resource=f"privileged_change:{change_id}", outcome="denied",
                       detail=refusal)
                session.commit()
                raise HTTPException(status_code=403, detail={
                    "code": "dual_control_same_person", "message": refusal})
        change.state = APPROVED if approve else REJECTED
        change.decided_by = actor[:80]
        change.decided_at_utc = datetime.now(UTC)
        change.decision_note = (note or "")[:500] or None
        _audit(session, principal=actor,
               action="security.dual_control.approved" if approve
               else "security.dual_control.rejected",
               resource=f"privileged_change:{change_id}",
               outcome=change.state, severity="info",
               detail=f"{change.kind}: {change.summary}; requested_by={change.requested_by}")
        session.commit()
        return change_payload(change)


def withdraw(change_id: str, requester: Any) -> dict:
    from eurogas_nexus.db.models import PrivilegedChangeRecord

    with _session() as session:
        change = session.get(PrivilegedChangeRecord, change_id)
        if change is None:
            raise HTTPException(status_code=404, detail={"code": "privileged_change_not_found"})
        if change.requested_by not in _ids(requester) or change.state not in {PENDING, APPROVED}:
            raise HTTPException(status_code=403, detail={"code": "privileged_change_not_yours"})
        change.state = WITHDRAWN
        change.decided_at_utc = datetime.now(UTC)
        _audit(session, principal=change.requested_by, action="security.dual_control.withdrawn",
               resource=f"privileged_change:{change_id}", outcome="withdrawn",
               detail=change.summary, severity="info")
        session.commit()
        return change_payload(change)


def list_changes(limit: int = 100) -> list[dict]:
    from eurogas_nexus.db.models import PrivilegedChangeRecord

    with _session() as session:
        rows = (
            session.query(PrivilegedChangeRecord)
            .order_by(PrivilegedChangeRecord.requested_at_utc.desc())
            .limit(limit)
            .all()
        )
        return [change_payload(row) for row in rows]


def change_payload(row: Any) -> dict:
    def iso(value):
        return value.isoformat() if value is not None else None

    return {
        "change_id": row.change_id,
        "kind": row.kind,
        "method": row.method,
        "path": row.path,
        "summary": row.summary,
        "state": row.state,
        "requested_by": row.requested_by,
        "requested_at_utc": iso(row.requested_at_utc),
        "decided_by": row.decided_by,
        "decided_at_utc": iso(row.decided_at_utc),
        "decision_note": row.decision_note,
        "applied_at_utc": iso(row.applied_at_utc),
        "body": row.body_json,
    }
