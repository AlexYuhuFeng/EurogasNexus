"""Maker-checker on limits and reference data (P-17): propose, approve, reject, withdraw.

A change to a credit line, a trader mandate, a deal hedge band, the firm's marks, LNG
terminal terms or a freight route is, by default, proposed by one person and takes effect
only when a different authorised person approves it (``governance/four_eyes.py`` lists the
writes, who approves each, and the organisation setting that can switch one off).

The rules, as in an ETRM's or a bank's market-risk controls:

* the proposer never approves their own change, under any of their names;
* the approver holds the authority to make the change themselves (the risk function for
  limits, hedge bands and marks; the desk for terminal terms and freight routes), and a
  mandate is never approved by the trader it governs;
* one open proposal per record: a second waits until the first is decided or withdrawn;
* a proposal records each changed field before and after, why, who and since when; it is
  applied exactly as proposed, and refused (``change_stale``) when the stored figures moved
  since, so nobody approves a diff that is no longer true;
* proposing, approving, rejecting and withdrawing are governed writes: each audit row is
  written in the same transaction as the change (``record_governed_audit``), and the
  approved write keeps its own audit row naming both people;
* an applied row keeps the proposal's ``change_id``: its provenance (who proposed, who
  approved, when, why) is read back with the figure.

Approved assumption sets keep their own four-eyes flow (a draft version, approved by a
different person in the risk function; ``db/repositories/commercial_assumptions.py``).

限额与参考数据的四眼复核：一人提议，另一名有权限者批准后才生效；提议、批准、驳回、撤回
均在同一事务中审计；生效的数值保留提议人与批准人。
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

from eurogas_nexus.governance.four_eyes import (
    DESK,
    FOUR_EYES_BY_ACTION,
    FOUR_EYES_BY_KIND,
    FOUR_EYES_SETTING,
    FOUR_EYES_WRITES,
    RISK_FUNCTION,
    four_eyes_in_force,
)

PENDING = "pending"
APPROVED = "approved"
REJECTED = "rejected"
WITHDRAWN = "withdrawn"

SINGLE_PERSON_HINT = (
    "On an installation with one person, an administrator can switch four eyes off for this "
    "write in the organisation settings (four_eyes); that switch is itself audited."
)


class ChangeRequestError(Exception):
    """A proposal, approval, rejection or withdrawal that is refused, with its HTTP status."""

    def __init__(self, code: str, message: str, *, status: int = 409, **extra: Any) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.extra = extra

    def detail(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, **self.extra}


# ------------------------------------------------------------------------- the setting


def four_eyes_settings(session: Any) -> dict[str, bool]:
    """Each maker-checker write and whether it needs a second person now."""

    from eurogas_nexus.db.models import OrganisationSettingRecord

    row = session.get(OrganisationSettingRecord, FOUR_EYES_SETTING)
    return four_eyes_in_force(row.value_json if row is not None else None)


def four_eyes_required(session: Any, action: str) -> bool:
    """Whether ``action`` waits for a second person (default on for every listed write)."""

    if action not in FOUR_EYES_BY_ACTION:
        return False
    return four_eyes_settings(session)[action]


def four_eyes_summary(session: Any) -> list[dict[str, Any]]:
    """The listed writes, who approves each and whether a second person is required now."""

    settings = four_eyes_settings(session)
    return [
        {
            "action": write.action,
            "kind": write.kind,
            "label": write.label,
            "label_zh": write.label_zh,
            "approver": write.approver,
            "default_on": write.default_on,
            "required": settings[write.action],
        }
        for write in FOUR_EYES_WRITES
    ]


# ------------------------------------------------------------------------ authority


def _is_person(identity: Any) -> bool:
    principal_id = getattr(identity, "principal_id", None)
    return bool(principal_id) and getattr(identity, "auth_method", "") != "legacy_public_token"


def _is_own(identity: Any, change: Any) -> bool:
    from eurogas_nexus.security.segregation import names_of

    return str(change.proposed_by).strip().casefold() in names_of(identity)


def authority_refusal(identity: Any, kind: str) -> dict[str, str] | None:
    """Why ``identity`` may not approve a change of ``kind``, or ``None`` when it may."""

    from eurogas_nexus.security.authorization import Permission, authorize
    from eurogas_nexus.security.segregation import risk_function_refusal

    write = FOUR_EYES_BY_KIND[kind]
    if not _is_person(identity):
        return {
            "code": "named_principal_required",
            "message": "A change is approved by a named person, not a shared token.",
        }
    if write.approver == RISK_FUNCTION:
        return risk_function_refusal(identity, what=f"{write.label} changes")
    if write.approver == DESK and not authorize(identity, Permission.PORTFOLIO_WRITE).allowed:
        return {
            "code": "permission_denied",
            "message": f"{write.label} changes are approved by the desk (portfolio write).",
        }
    return None


def _approval_refusal(
    identity: Any, change: Any, session: Any = None
) -> ChangeRequestError | None:
    from eurogas_nexus.security.segregation import names_of

    if session is not None and not _is_own(identity, change):
        # An approver the proposer provisioned is not a second person (H7).
        from eurogas_nexus.application.sock_puppet import sock_puppet_refusal

        reason = sock_puppet_refusal(
            session,
            {str(v) for v in (getattr(identity, "principal_id", None),
                              getattr(identity, "name", None)) if v},
            {str(change.proposed_by)},
            getattr(identity, "principal_id", None),
        )
        if reason is not None:
            return ChangeRequestError("four_eyes_same_person", reason, status=403)
    if _is_own(identity, change):
        return ChangeRequestError(
            "four_eyes_required",
            "You proposed this change; a different person must approve it (four eyes). "
            + SINGLE_PERSON_HINT,
            status=403,
        )
    refusal = authority_refusal(identity, change.kind)
    if refusal is not None:
        return ChangeRequestError(refusal["code"], refusal["message"], status=403)
    if change.kind == "trader_mandate":
        traders = {
            str(value).strip().casefold()
            for value in (
                (change.payload or {}).get("values", {}).get("trader"),
                (change.before_json or {}).get("trader"),
            )
            if value
        }
        if traders & names_of(identity):
            return ChangeRequestError(
                "own_mandate",
                "A trader's mandate is approved by someone else (four eyes).",
                status=403,
            )
    return None


def may_see(identity: Any, change: Any) -> bool:
    """A proposal is shown to its proposer and to whoever may approve its kind."""

    return _is_own(identity, change) or authority_refusal(identity, change.kind) is None


# ------------------------------------------------------------------- kinds of change


@dataclass(frozen=True, slots=True)
class _Kind:
    """How one kind of record is read for a proposal and written on approval."""

    snapshot: Callable[[Any, str, list[str]], dict | None]
    apply: Callable[[Any, Any, str, datetime], None]


_ROW_RECORDS = {
    "credit_line": ("CreditLineRecord", "risk.limits"),
    "trader_mandate": ("TraderMandateRecord", "risk.limits"),
    "hedge_approval": ("HedgeApprovalRecord", "risk.limits"),
    "lng_terminal_terms": ("LngTerminalTermsRecord", "desk.reference"),
}


def _record_type(kind: str) -> Any:
    import eurogas_nexus.db.models as models

    return getattr(models, _ROW_RECORDS[kind][0])


def _row_kind(kind: str) -> _Kind:
    from eurogas_nexus.application.reference_rows import current_fields, from_json, write_row

    def snapshot(session: Any, key: str, names: list[str]) -> dict | None:
        return current_fields(session, _record_type(kind), key, names)

    def apply(session: Any, change: Any, approved_by: str, now: datetime) -> None:
        record_type = _record_type(kind)
        write_row(
            session,
            record_type=record_type,
            key=change.target_key,
            values=from_json(record_type, dict(change.payload["values"])),
            defaults=None,
            action=change.action,
            resource=change.resource,
            actor=change.proposed_by,
            event_type=_ROW_RECORDS[kind][1],
            approved_by=approved_by,
            change_id=change.change_id,
            now_utc=now,
        )

    return _Kind(snapshot, apply)


def mark_text(value: Any) -> str | None:
    """A mark's value as text that compares equal however the database returns it."""

    if value is None:
        return None
    text = format(Decimal(str(value)).normalize(), "f")
    return "0" if text in {"-0", ""} else text


def firm_mark_cells(session: Any, cells: Iterable[str]) -> dict[str, str | None]:
    """Each ``HUB:PERIOD`` cell's current mark as text, ``None`` where there is none."""

    from eurogas_nexus.db.models import FirmMarkRecord

    current: dict[str, str | None] = {}
    for cell in cells:
        hub, _, period = cell.partition(":")
        row = (
            session.query(FirmMarkRecord)
            .filter(FirmMarkRecord.hub == hub)
            .filter(FirmMarkRecord.period_label == period)
            .filter(FirmMarkRecord.superseded_at_utc.is_(None))
            .order_by(FirmMarkRecord.entered_at_utc.desc())
            .first()
        )
        current[cell] = None if row is None else mark_text(row.value)
    return current


def store_firm_marks(
    session: Any,
    entries: list[Any],
    *,
    actor: str,
    approved_by: str | None = None,
    change_id: str | None = None,
    now_utc: datetime | None = None,
) -> list[Any]:
    """Store marks, make an evaluation due and publish one market event per cell.

    The caller commits. Shared by the direct write and the approval of a proposal.
    """

    from eurogas_nexus.application.market_events import publish_firm_marks
    from eurogas_nexus.application.opportunities.schedule import note_input_changed
    from eurogas_nexus.db.repositories.commercial_assumptions import put_firm_marks

    now = now_utc or datetime.now(UTC)
    stored = put_firm_marks(
        session, entries, actor=actor, now_utc=now, approved_by=approved_by, change_id=change_id
    )
    note_input_changed(session, "marks", reason="firm marks")
    # M4: one market event per hub and period, so the opportunities that read the mark are
    # re-evaluated without waiting for the debounced full evaluation.
    publish_firm_marks(session, entries, actor=approved_by or actor, now_utc=now)
    return stored


def _firm_marks_kind() -> _Kind:
    def snapshot(session: Any, _key: str, names: list[str]) -> dict | None:
        return firm_mark_cells(session, names)

    def apply(session: Any, change: Any, approved_by: str, now: datetime) -> None:
        from eurogas_nexus.domain.valuation.firm_marks import validate_firm_mark

        entries = [
            validate_firm_mark(
                cell["hub"], cell["period"], cell["value"], cell["unit"], cell.get("note", "")
            )
            for cell in change.payload["marks"]
        ]
        store_firm_marks(
            session,
            entries,
            actor=change.proposed_by,
            approved_by=approved_by,
            change_id=change.change_id,
            now_utc=now,
        )

    return _Kind(snapshot, apply)


def route_snapshot(session: Any, route_id: str, names: list[str]) -> dict | None:
    """The current version of a freight route, the named fields, or ``None``."""

    from eurogas_nexus.application.lng_cargo_economics import current_route

    held = current_route(session, route_id)
    if held is None:
        return None
    return {name: getattr(held, name, None) for name in names}


def _freight_kind() -> _Kind:
    def apply(session: Any, change: Any, approved_by: str, _now: datetime) -> None:
        from eurogas_nexus.application.lng_cargo_economics import record_route

        record_route(
            session,
            change.target_key,
            dict(change.payload["values"]),
            actor=change.proposed_by,
            approved_by=approved_by,
            change_id=change.change_id,
        )

    return _Kind(route_snapshot, apply)


def _kind(kind: str) -> _Kind:
    if kind in _ROW_RECORDS:
        return _row_kind(kind)
    if kind == "firm_marks":
        return _firm_marks_kind()
    if kind == "freight_route":
        return _freight_kind()
    raise KeyError(kind)


# ------------------------------------------------------------------------ the flow


def _audit(
    session: Any,
    change: Any,
    *,
    action: str,
    principal: str,
    outcome: str,
    now: datetime,
    note: str | None = None,
) -> None:
    from eurogas_nexus.application.audit_service import record_governed_audit

    detail = {
        "change_id": change.change_id,
        "write": change.action,
        "proposed_by": change.proposed_by,
        "reason": change.reason,
    }
    if note:
        detail["note"] = note
    before, after = change.before_json, change.after_json
    if change.kind == "firm_marks":
        # The firm's marks are audited without their values (CP-07): the cells only.
        before, after = None, {"cells": sorted(change.after_json or {})}
    record_governed_audit(
        session,
        event_type="governance.change_request",
        principal=principal,
        action=action,
        resource=change.resource,
        outcome=outcome,
        detail=json.dumps(detail, sort_keys=True, default=str)[:2000],
        source_system="maker-checker",
        now_utc=now,
        correlation_id=change.change_id,
        before_summary=before,
        after_summary=after,
    )


def pending_for(session: Any, resource: str) -> Any | None:
    """The open proposal for a record, if there is one."""

    from eurogas_nexus.db.models import ChangeRequestRecord

    return (
        session.query(ChangeRequestRecord)
        .filter(ChangeRequestRecord.resource == resource)
        .filter(ChangeRequestRecord.state == PENDING)
        .first()
    )


def propose_change(
    session: Any,
    *,
    action: str,
    target_key: str,
    resource: str,
    subject: str,
    payload: dict[str, Any],
    before: dict[str, Any] | None,
    after: dict[str, Any],
    reason: str,
    actor: str,
    now_utc: datetime | None = None,
) -> Any:
    """Record a proposal and its audit row in the caller's transaction (the caller commits).

    Raises:
        ChangeRequestError: ``change_pending`` (409) while the record has an open proposal.
    """

    from eurogas_nexus.db.models import ChangeRequestRecord

    write = FOUR_EYES_BY_ACTION[action]
    open_change = pending_for(session, resource)
    if open_change is not None:
        raise ChangeRequestError(
            "change_pending",
            "A change to this record is already waiting for approval; it is approved, rejected "
            "or withdrawn first.",
            change_id=open_change.change_id,
            proposed_by=open_change.proposed_by,
        )
    now = now_utc or datetime.now(UTC)
    change = ChangeRequestRecord(
        change_id=f"chg-{uuid4().hex[:20]}",
        action=action,
        kind=write.kind,
        resource=resource[:160],
        target_key=target_key[:160],
        subject=(subject or target_key)[:200],
        payload=payload,
        before_json=before,
        after_json=after,
        reason=(reason or "").strip()[:500],
        state=PENDING,
        proposed_by=actor[:128],
        proposed_at_utc=now,
    )
    session.add(change)
    _audit(
        session,
        change,
        action="change_request.propose",
        principal=actor,
        outcome="pending",
        now=now,
    )
    return change


def _load_for_decision(session: Any, change_id: str) -> Any:
    from eurogas_nexus.db.models import ChangeRequestRecord

    change = (
        session.query(ChangeRequestRecord)
        .filter(ChangeRequestRecord.change_id == change_id)
        .with_for_update()
        .one_or_none()
    )
    if change is None:
        raise ChangeRequestError("change_not_found", "No such change.", status=404)
    return change


def _require_pending(change: Any) -> None:
    if change.state != PENDING:
        raise ChangeRequestError(
            "change_not_pending",
            f"This change was {change.state} already.",
            state=change.state,
        )


def approve_change(
    session: Any, change_id: str, *, identity: Any, now_utc: datetime | None = None
) -> Any:
    """Apply a proposal on a different authorised person's approval (the caller commits).

    Raises:
        ChangeRequestError: 404 ``change_not_found``; 409 ``change_not_pending``; 403
            ``four_eyes_required`` (the proposer), ``own_mandate``, or the approver's lack of
            authority; 409 ``change_stale`` when the stored figures moved since the proposal.
    """

    now = now_utc or datetime.now(UTC)
    change = _load_for_decision(session, change_id)
    _require_pending(change)
    refusal = _approval_refusal(identity, change, session)
    if refusal is not None:
        raise refusal
    kind = _kind(change.kind)
    current = kind.snapshot(session, change.target_key, sorted(change.after_json))
    if _jsonable(current) != _jsonable(change.before_json):
        raise ChangeRequestError(
            "change_stale",
            "The stored figures changed after this was proposed; reject it and propose again.",
            proposed_before=change.before_json,
            stored_now=_jsonable(current),
        )
    approver = str(identity.principal_id)
    kind.apply(session, change, approver, now)
    change.state = APPROVED
    change.decided_by = approver[:128]
    change.decided_at_utc = now
    _audit(
        session,
        change,
        action="change_request.approve",
        principal=approver,
        outcome="approved",
        now=now,
    )
    return change


def reject_change(
    session: Any, change_id: str, *, identity: Any, note: str, now_utc: datetime | None = None
) -> Any:
    """Close a proposal without applying it; the approver says why (the caller commits).

    Raises:
        ChangeRequestError: as :func:`approve_change`; 422 ``note_required`` without a reason;
            409 ``withdraw_own_change`` when the proposer tries to reject their own.
    """

    now = now_utc or datetime.now(UTC)
    change = _load_for_decision(session, change_id)
    _require_pending(change)
    if _is_own(identity, change):
        raise ChangeRequestError(
            "withdraw_own_change", "You proposed this change; withdraw it instead."
        )
    refusal = authority_refusal(identity, change.kind)
    if refusal is not None:
        raise ChangeRequestError(refusal["code"], refusal["message"], status=403)
    text = (note or "").strip()
    if not text:
        raise ChangeRequestError("note_required", "Say why the change is rejected.", status=422)
    who = str(identity.principal_id)
    change.state = REJECTED
    change.decided_by = who[:128]
    change.decided_at_utc = now
    change.decision_note = text[:500]
    _audit(
        session,
        change,
        action="change_request.reject",
        principal=who,
        outcome="rejected",
        now=now,
        note=text,
    )
    return change


def withdraw_change(
    session: Any, change_id: str, *, identity: Any, note: str = "", now_utc: datetime | None = None
) -> Any:
    """The proposer takes back an open proposal (the caller commits).

    Raises:
        ChangeRequestError: 404, 409 ``change_not_pending``, or 403 ``not_the_proposer``.
    """

    now = now_utc or datetime.now(UTC)
    change = _load_for_decision(session, change_id)
    _require_pending(change)
    if not _is_own(identity, change):
        raise ChangeRequestError(
            "not_the_proposer", "Only the person who proposed a change withdraws it.", status=403
        )
    who = str(identity.principal_id)
    text = (note or "").strip()
    change.state = WITHDRAWN
    change.decided_by = who[:128]
    change.decided_at_utc = now
    change.decision_note = text[:500] or None
    _audit(
        session,
        change,
        action="change_request.withdraw",
        principal=who,
        outcome="withdrawn",
        now=now,
        note=text or None,
    )
    return change


def _jsonable(value: Any) -> Any:
    """A snapshot as JSON would return it, so stored and current compare like for like."""

    if value is None:
        return None
    return json.loads(json.dumps(value, default=_json_default, sort_keys=True))


def _json_default(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return str(value)


# ---------------------------------------------------------------------- reading back


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.isoformat()


def _names(session: Any, ids: Iterable[str | None]) -> dict[str, str]:
    from eurogas_nexus.db.repositories.identity import display_names

    try:
        return display_names(session, [value for value in ids if value])
    except Exception:  # noqa: BLE001 - a name is a courtesy; the id still says who
        return {}


def change_payload(change: Any, *, identity: Any, names: dict[str, str]) -> dict[str, Any]:
    """One proposal as the API returns it: who, what (before and after), why, since when."""

    write = FOUR_EYES_BY_KIND[change.kind]
    before = change.before_json or {}
    after = change.after_json or {}
    own = _is_own(identity, change)
    pending = change.state == PENDING
    return {
        "change_id": change.change_id,
        "action": change.action,
        "kind": change.kind,
        "label": write.label,
        "label_zh": write.label_zh,
        "resource": change.resource,
        "target_key": change.target_key,
        "subject": change.subject,
        "new_record": change.before_json is None and change.kind != "firm_marks",
        "fields": [
            {"name": name, "before": before.get(name), "after": after.get(name)}
            for name in sorted(after)
        ],
        "reason": change.reason,
        "state": change.state,
        "proposed_by": change.proposed_by,
        "proposed_by_name": names.get(change.proposed_by, change.proposed_by),
        "proposed_at_utc": _iso(change.proposed_at_utc),
        "decided_by": change.decided_by,
        "decided_by_name": names.get(change.decided_by or "", change.decided_by),
        "decided_at_utc": _iso(change.decided_at_utc),
        "decision_note": change.decision_note,
        "own": own,
        "may_approve": pending and _approval_refusal(identity, change) is None,
        "may_reject": pending and not own and authority_refusal(identity, change.kind) is None,
        "may_withdraw": pending and own,
        "approver": write.approver,
    }


def describe(session: Any, change: Any, *, identity: Any) -> dict[str, Any]:
    """One proposal with people's names, for a route's answer."""

    names = _names(session, [change.proposed_by, change.decided_by])
    return change_payload(change, identity=identity, names=names)


def list_changes(
    session: Any,
    *,
    identity: Any,
    state: str = PENDING,
    resource: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """The proposals the caller proposed or may decide, newest first.

    ``state``: ``pending``, ``decided`` (approved, rejected or withdrawn) or ``all``.
    """

    from eurogas_nexus.db.models import ChangeRequestRecord

    query = session.query(ChangeRequestRecord)
    if state == PENDING:
        query = query.filter(ChangeRequestRecord.state == PENDING)
    elif state == "decided":
        query = query.filter(ChangeRequestRecord.state != PENDING)
    if resource:
        query = query.filter(ChangeRequestRecord.resource == resource)
    rows = [
        row
        for row in query.order_by(ChangeRequestRecord.proposed_at_utc.desc()).limit(limit * 4)
        if may_see(identity, row)
    ][:limit]
    names = _names(session, [value for row in rows for value in (row.proposed_by, row.decided_by)])
    return [change_payload(row, identity=identity, names=names) for row in rows]


def provenance_for(
    session: Any, rows: Iterable[tuple[str, str | None, datetime | None, str | None]]
) -> dict[str, dict[str, Any]]:
    """Each figure's provenance: who set it, and who approved it when a second person did.

    ``rows`` holds ``(key, set_by, set_at, change_id)`` per record. A row without a change id
    was set by one person (before P-17, or with four eyes switched off for that write) and
    says so: ``second_approval`` is false.
    """

    from eurogas_nexus.db.models import ChangeRequestRecord

    items = list(rows)
    ids = {change_id for _key, _by, _at, change_id in items if change_id}
    changes = {}
    if ids:
        changes = {
            row.change_id: row
            for row in session.query(ChangeRequestRecord).filter(
                ChangeRequestRecord.change_id.in_(ids)
            )
        }
    names = _names(
        session,
        [by for _key, by, _at, _id in items] + [change.decided_by for change in changes.values()],
    )
    result: dict[str, dict[str, Any]] = {}
    for key, set_by, set_at, change_id in items:
        change = changes.get(change_id) if change_id else None
        approved = change is not None and change.state == APPROVED
        result[key] = {
            "second_approval": approved,
            "set_by": set_by,
            "set_by_name": names.get(set_by or "", set_by),
            "set_at_utc": _iso(set_at),
            "approved_by": change.decided_by if approved else None,
            "approved_by_name": names.get(change.decided_by or "", change.decided_by)
            if approved
            else None,
            "approved_at_utc": _iso(change.decided_at_utc) if approved else None,
            "change_id": change_id if approved else None,
            "reason": change.reason if approved else None,
        }
    return result


__all__ = [
    "APPROVED",
    "PENDING",
    "REJECTED",
    "SINGLE_PERSON_HINT",
    "WITHDRAWN",
    "ChangeRequestError",
    "approve_change",
    "authority_refusal",
    "change_payload",
    "describe",
    "firm_mark_cells",
    "four_eyes_required",
    "four_eyes_settings",
    "four_eyes_summary",
    "list_changes",
    "mark_text",
    "may_see",
    "pending_for",
    "propose_change",
    "provenance_for",
    "reject_change",
    "route_snapshot",
    "store_firm_marks",
    "withdraw_change",
]
