"""Audit recording: governed writes are audited in their own transaction; the rest best-effort.

Two ways to record an audit event, and which one a caller uses is a rule, not a choice:

* **Governed writes** (GOV-1, lesson P5) call :func:`record_governed_audit` with the session
  that makes the change. The audit row is written in the same transaction, and if it cannot
  be written the helper raises :class:`GovernedAuditError`: the caller's transaction is not
  committed and the change does not happen. The API answers 503 ``audit_unavailable``. The
  governed writes are listed in :data:`GOVERNED_WRITES`; tests hold each one to the rule.
* **Everything else** (entitlement and export denials, LLM invocations, review and shadow
  decisions recorded after the fact, list and read events, sign-in events, refusals of a
  governed write that changed nothing) calls :func:`record_audit_event`, which opens its own
  session and never raises: a missing audit row for a read must not break the read, and the
  API already reports runtime-DB state to operators.

``record_audit_event`` 为尽力而为（读取与事件）；``record_governed_audit`` 用于受治理的写入：
审计行与变更在同一事务中写入，写不进审计行则变更失败。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from eurogas_nexus.governance.audit import GovernedAuditError

__all__ = [
    "AUDIT_APP_SOURCE",
    "GOVERNED_WRITES",
    "GovernedAuditError",
    "GovernedWrite",
    "governed_actions",
    "record_audit_event",
    "record_governed_audit",
]

AUDIT_APP_SOURCE = "eurogas-nexus"


@dataclass(frozen=True, slots=True)
class GovernedWrite:
    """One governed write: what it changes, the audit actions it records and where."""

    area: str
    actions: tuple[str, ...]
    where: str


#: Every governed write and the audit actions it records in its own transaction. A write in
#: this list fails when its audit row cannot be written.
GOVERNED_WRITES: tuple[GovernedWrite, ...] = (
    GovernedWrite(
        "limits and credit lines",
        ("risk.credit_line.update",),
        "api/routes/public/risk.py (PUT /api/portfolio/credit-lines/{counterparty_id})",
    ),
    GovernedWrite(
        "trader mandates",
        ("risk.mandate.update",),
        "api/routes/public/risk.py (PUT /api/portfolio/trader-mandates/{mandate_id})",
    ),
    GovernedWrite(
        "hedge bands",
        ("risk.hedge_approval.update",),
        "api/routes/public/risk.py (PUT /api/portfolio/hedge-approvals/{contract_id})",
    ),
    GovernedWrite(
        "LNG terminal terms",
        ("lng.terminal_terms.update",),
        "api/routes/public/risk.py (PUT /api/portfolio/lng-terminal-terms/{terminal_id})",
    ),
    GovernedWrite(
        "opportunity thresholds",
        ("opportunities.thresholds.update",),
        "application/opportunities/settings.py (PUT /api/opportunities/settings)",
    ),
    GovernedWrite(
        "assumption sets, approvals and firm marks",
        (
            "assumption_set.create",
            "assumption_set.version.create",
            "assumption_set.version.approve",
            "market.firm_marks.update",
        ),
        "db/repositories/commercial_assumptions.py",
    ),
    GovernedWrite(
        "users, roles, groups and data licences",
        (
            "access.user.create",
            "access.user.invite",
            "access.user.update",
            "access.user.delete",
            "access.user.password_reset",
            "access.group.create",
            "access.group.update",
            "access.group.member.add",
            "access.group.member.remove",
            "access.licence.update",
            "identity.create",
            "identity.disable",
        ),
        "api/routes/public/access.py, application/local_accounts.py, "
        "api/routes/internal/identity_admin.py",
    ),
    GovernedWrite(
        "API keys and provider credentials",
        (
            "me.api_key.create",
            "me.api_key.revoke",
            "access.api_key.create",
            "access.api_key.revoke",
            "identity.key.issue",
            "identity.key.rotate",
            "identity.key.revoke",
            "upsert_credential",
            "delete_credential",
        ),
        "api/routes/public/access.py, api/routes/internal/identity_admin.py, "
        "api/routes/public/credentials.py",
    ),
    GovernedWrite(
        "organisation settings and AI feature switches",
        ("settings.organisation.update",),
        "api/routes/public/preferences.py (PUT /api/settings/organisation)",
    ),
    GovernedWrite(
        "hedges on cargoes",
        ("lng.cargo_hedges",),
        "application/lng_in_transit.py (PUT /api/lng/cargoes/{cargo_id}/hedges)",
    ),
    GovernedWrite(
        "freight routes",
        ("lng.freight_route",),
        "application/lng_cargo_economics.py (PUT /api/lng/freight-routes/{route_id})",
    ),
    GovernedWrite(
        "disruption options chosen (a record; nothing is booked)",
        ("lng.disruption_choice",),
        "application/lng_disruption.py "
        "(POST /api/lng/cargoes/{cargo_id}/disruption-options/{option_id}/choose)",
    ),
    GovernedWrite(
        "maker-checker: proposals and their approval, rejection and withdrawal (P-17)",
        (
            "change_request.propose",
            "change_request.approve",
            "change_request.reject",
            "change_request.withdraw",
        ),
        "application/maker_checker.py (/api/portfolio/change-requests)",
    ),
)


def governed_actions() -> frozenset[str]:
    """Every audit action a governed write records."""

    return frozenset(action for write in GOVERNED_WRITES for action in write.actions)


def record_governed_audit(session: Any, **fields: Any) -> Any:
    """Write a governed write's audit row in the caller's transaction, or refuse the write.

    See ``db.repositories.audit.record_governed_audit``; imported lazily so this module stays
    import-safe.

    Raises:
        GovernedAuditError: the audit row could not be written.
    """

    from eurogas_nexus.db.repositories.audit import record_governed_audit as _record

    return _record(session, **fields)


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
    after_summary: dict | None = None,
) -> str | None:
    """Persist one best-effort audit event and return its id, or None when unavailable.

    For reads and events only (see the module docstring); a governed write uses
    :func:`record_governed_audit`. Never raises: audit recording must not break a read.
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
                after_summary=after_summary,
            )
            session.commit()
            return event.event_id
    except Exception:
        return None
