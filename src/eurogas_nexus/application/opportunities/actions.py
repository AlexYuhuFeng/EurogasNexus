"""The only things a person can do with an opportunity: follow it, dismiss it (with a reason),
restore it, or open it as a decision case. No order, no nomination, no instruction.

- **Dismiss** hides the key for that person until the record materially changes (a new
  version); the reason is counted per type for the monthly threshold review.
- **Open as a case** creates a decision case through the existing case flow, carrying the
  frozen object of the current version as evidence (``opportunity:<id>@v<n>``) with the
  valuation snapshot it was computed on, the assumptions as the case's assumptions and the
  claim as its alternative. The record becomes ``converted``; nothing else happens.
- **Statistics**: dismissals by type and reason; cases opened and accepted per type
  (precision = accepted / opened, design B.6), for the administrator view.
"""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
from typing import Any

from eurogas_nexus.domain.opportunities.model import DismissReason, OpportunityState

USER_ACTIONS = ("dismiss", "restore", "watch", "unwatch")


class ActionError(ValueError):
    """A refused action; ``code`` names why and ``status`` the HTTP answer."""

    def __init__(self, code: str, status: int = 409, **detail: Any) -> None:
        super().__init__(code)
        self.code = code
        self.status = status
        self.detail = detail


def set_user_state(
    session, row, *, principal_id: str, action: str, reason: str | None, note: str
) -> dict[str, Any]:
    """Apply one of :data:`USER_ACTIONS` for one person.

    Raises:
        ActionError: unknown action, or a dismissal without a known reason.
    """

    from eurogas_nexus.db.models import OpportunityUserStateRecord

    if action not in USER_ACTIONS:
        raise ActionError("unknown_action", 422)
    now = datetime.now(UTC)
    held = session.get(OpportunityUserStateRecord, (principal_id, row.opp_key))
    if action in {"restore", "unwatch"}:
        if held is not None and held.state == ("dismissed" if action == "restore" else "watching"):
            session.delete(held)
        session.flush()
        return {"state": None}
    if action == "dismiss":
        try:
            reason = DismissReason(reason or "").value
        except ValueError as exc:
            raise ActionError(
                "dismiss_reason_required", 422, allowed=[item.value for item in DismissReason]
            ) from exc
    state = "dismissed" if action == "dismiss" else "watching"
    if held is None:
        held = OpportunityUserStateRecord(
            principal_id=principal_id,
            opp_key=row.opp_key,
            created_at_utc=now,
            opportunity_type=row.type,
        )
        session.add(held)
    held.state = state
    held.reason_code = reason if action == "dismiss" else None
    held.note = (note or "")[:400]
    held.at_version = row.version
    held.opportunity_type = row.type
    held.updated_at_utc = now
    session.flush()
    return {"state": state, "reason": held.reason_code, "at_version": row.version}


def open_case(session, row, *, principal) -> dict[str, Any]:
    """Open a decision case carrying the frozen arithmetic; returns the case payload.

    Raises:
        ActionError: already converted (with the case id), blocked, ended or not yet shown.
    """

    from eurogas_nexus.db.models import DecisionCaseRecord, OpportunityVersionRecord
    from eurogas_nexus.db.repositories.audit import record_audit_event
    from eurogas_nexus.db.repositories.decision import (
        attach_evidence,
        create_decision_case,
        get_decision_case,
    )

    state = OpportunityState(row.state)
    if state is OpportunityState.CONVERTED:
        raise ActionError("already_converted", 409, case_id=row.case_id)
    if state in {OpportunityState.EXPIRED, OpportunityState.BLOCKED, OpportunityState.NEW}:
        raise ActionError(f"not_openable_{state.value}", 409)
    version = session.get(OpportunityVersionRecord, (row.opportunity_id, row.version))
    payload = version.payload_json if version else {}
    ref = f"opportunity:{row.opportunity_id}@v{row.version}"
    evaluated = row.last_evaluated_utc
    if evaluated.tzinfo is None:
        evaluated = evaluated.replace(tzinfo=UTC)
    now = datetime.now(UTC)
    deadline = row.deadline_utc
    if deadline is not None and deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=UTC)
    created = create_decision_case(
        session,
        objective=row.claim_text[:500],
        created_by=principal.name,
        delivery_product=row.period_label,
        portfolio_ref=",".join(row.book_ids or [])[:128],
        snapshot_id=row.snapshot_id,
        decision_due_at_utc=deadline if deadline and deadline > now else None,
        now_utc=now,
    )
    case_id = created["case_id"]
    case_row = session.get(DecisionCaseRecord, case_id)
    case_row.assumptions_json = [
        {
            "key": item["key"],
            "value": f"{item['value']['value']} {item['value']['unit']}",
            "source": "BACKEND",
            "note": f"{item['origin']}, set by {item['set_by']} {item['set_at_utc']}",
        }
        for item in payload.get("assumptions", [])
    ] + [
        {
            "key": f"input:{item['key']}",
            "value": f"{item.get('value')} {item.get('unit') or ''}".strip(),
            "source": "BACKEND" if item["kind"] == "book" else "MARKET_DATA",
            "note": (
                f"{item['class']}, {item.get('source_family') or ''}, "
                f"as of {item.get('as_of_utc')}"
            ),
        }
        for item in payload.get("quality", {}).get("inputs", [])
    ]
    case_row.alternatives_json = [
        {
            "alternative_id": "opportunity",
            "label": row.claim_text[:200],
            "description": (
                f"{payload.get('headline', {}).get('value')} "
                f"{payload.get('headline', {}).get('unit')}; class {row.quality_class}"
            ),
            "economics_ref": ref,
            "warnings": ["simulated inputs (demo)"] if row.simulated else [],
        }
    ]
    session.flush()
    attach_evidence(
        session,
        case_id=case_id,
        kind="SCENARIO",
        ref=ref,
        label="Opportunity arithmetic, frozen at this version",
        as_of_utc=evaluated.isoformat(),
        snapshot_id=row.snapshot_id,
        now_utc=now,
    )
    row.state = OpportunityState.CONVERTED.value
    row.case_id = case_id
    row.converted_by = principal.principal_id
    row.converted_at_utc = now
    row.last_changed_utc = now
    if version is not None:
        version.state = row.state
    record_audit_event(
        session,
        event_type="decision.case",
        principal=principal.principal_id,
        action="opportunity.open_case",
        resource=f"opportunity:{row.opportunity_id}",
        outcome="created",
        detail=f"case={case_id} version={row.version} snapshot={row.snapshot_id}",
        source_system="opportunities-api",
        now_utc=now,
    )
    session.flush()
    return {"case": get_decision_case(session, case_id), "evidence_ref": ref}


def statistics(session) -> dict[str, Any]:
    """Dismissal reasons by type, and cases opened and accepted by type."""

    from eurogas_nexus.db.models import (
        DecisionCaseDecisionRecord,
        OpportunityRecord,
        OpportunityUserStateRecord,
    )

    dismissals: Counter[tuple[str, str]] = Counter(
        (row.opportunity_type, row.reason_code or "")
        for row in session.query(OpportunityUserStateRecord)
        .filter(OpportunityUserStateRecord.state == "dismissed")
        .all()
    )
    converted = (
        session.query(OpportunityRecord.type, OpportunityRecord.case_id)
        .filter(OpportunityRecord.case_id.is_not(None))
        .all()
    )
    latest: dict[str, str] = {}
    case_ids = [case_id for _type, case_id in converted]
    if case_ids:
        for record in (
            session.query(DecisionCaseDecisionRecord)
            .filter(DecisionCaseDecisionRecord.case_id.in_(case_ids))
            .order_by(DecisionCaseDecisionRecord.recorded_at_utc)
            .all()
        ):
            latest[record.case_id] = record.outcome
    by_type: dict[str, dict[str, Any]] = {}
    for kind, case_id in converted:
        entry = by_type.setdefault(kind, {"opened": 0, "accepted": 0, "decided": 0})
        entry["opened"] += 1
        if case_id in latest:
            entry["decided"] += 1
            entry["accepted"] += latest[case_id] == "accepted"
    for entry in by_type.values():
        entry["precision"] = (
            None if not entry["opened"] else round(entry["accepted"] / entry["opened"], 3)
        )
    return {
        "dismissals": [
            {"type": kind, "reason": reason, "count": count}
            for (kind, reason), count in sorted(dismissals.items())
        ],
        "cases": by_type,
    }
