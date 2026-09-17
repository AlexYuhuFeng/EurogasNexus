"""Decision Case repository (Architecture V2 Wave 6).

Persists the container and its records and maps them back to the pure domain
objects in ``eurogas_nexus.domain.decision``. The domain module owns the rules
(what makes a case decidable, what a record means); this module owns storage,
ordering and audit.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy.orm import Session

from eurogas_nexus.db.models.decision import DecisionCaseDecisionRecord, DecisionCaseRecord
from eurogas_nexus.db.repositories.audit import record_audit_event
from eurogas_nexus.domain.decision import (
    DecisionAlternative,
    DecisionAssumption,
    DecisionAssumptionSource,
    DecisionCase,
    DecisionCaseStatus,
    DecisionEvidence,
    DecisionEvidenceKind,
    DecisionRecord,
    case_is_decidable,
    case_summary,
    decision_blockers,
    record_decision,
    reopen_case,
)
from eurogas_nexus.domain.identity.principal import normalize_principal
from eurogas_nexus.domain.ontology.vocabulary import ReviewDecisionValue


def create_decision_case(
    session: Session,
    *,
    objective: str,
    created_by: str,
    gas_day: str = "",
    delivery_product: str = "",
    hub_id: str = "",
    portfolio_ref: str = "",
    snapshot_id: str = "",
    now_utc: datetime | None = None,
) -> dict:
    """Create a case in DRAFT state and return its payload.

    Raises:
        ValueError: when the objective or creator is missing.
    """

    if not objective.strip():
        raise ValueError("objective_required")
    principal = normalize_principal(created_by)
    now = _as_utc(now_utc or datetime.now(UTC))
    case_id = f"case-{uuid4().hex[:24]}"
    row = DecisionCaseRecord(
        case_id=case_id,
        objective=objective.strip(),
        status=DecisionCaseStatus.DRAFT.value,
        created_by=principal,
        created_at_utc=now,
        updated_at_utc=now,
        gas_day=gas_day,
        delivery_product=delivery_product,
        hub_id=hub_id,
        portfolio_ref=portfolio_ref,
        snapshot_id=snapshot_id,
        assumptions_json=[],
        alternatives_json=[],
        evidence_json=[],
        ai_findings_json=[],
        warnings_json=[],
    )
    session.add(row)
    record_audit_event(
        session,
        event_type="decision.case",
        principal=principal,
        action="decision_case_create",
        resource=f"decision_case:{case_id}",
        outcome="created",
        severity="info",
        detail=f"gas_day={gas_day}",
        source_system="decision",
        now_utc=now,
    )
    session.flush()
    return decision_case_payload(session, row)


def list_decision_cases(
    session: Session,
    *,
    status: str | None = None,
    limit: int = 50,
) -> list[dict]:
    """List cases newest first, as compact summaries."""

    query = session.query(DecisionCaseRecord)
    if status:
        query = query.filter(DecisionCaseRecord.status == status)
    rows = (
        query.order_by(DecisionCaseRecord.updated_at_utc.desc())
        .limit(max(1, min(limit, 200)))
        .all()
    )
    return [case_summary(_to_domain(session, row)) for row in rows]


def get_decision_case(session: Session, case_id: str) -> dict | None:
    """Return one case payload, or ``None`` when it does not exist."""

    row = session.get(DecisionCaseRecord, case_id)
    if row is None:
        return None
    return decision_case_payload(session, row)


def attach_evidence(
    session: Session,
    *,
    case_id: str,
    kind: str,
    ref: str,
    label: str = "",
    as_of_utc: str = "",
    snapshot_id: str = "",
    now_utc: datetime | None = None,
) -> dict:
    """Attach one evidence reference, ignoring an exact duplicate.

    Raises:
        ValueError: unknown case or unknown evidence kind.
    """

    row = _require_case(session, case_id)
    try:
        resolved_kind = DecisionEvidenceKind(kind)
    except ValueError as exc:
        raise ValueError("unknown_evidence_kind") from exc
    if not ref.strip():
        raise ValueError("evidence_ref_required")

    domain = _to_domain(session, row)
    existing = {(item["kind"], item["ref"]) for item in row.evidence_json or []}
    if (resolved_kind.value, ref) not in existing:
        evidence = list(row.evidence_json or [])
        evidence.append(
            {
                "kind": resolved_kind.value,
                "ref": ref.strip(),
                "label": label,
                "as_of_utc": as_of_utc,
                "snapshot_id": snapshot_id,
            }
        )
        row.evidence_json = evidence
        if snapshot_id and not row.snapshot_id:
            row.snapshot_id = snapshot_id
        row.status = (
            DecisionCaseStatus.OPEN.value
            if domain.status is DecisionCaseStatus.DRAFT
            else row.status
        )
        row.updated_at_utc = _as_utc(now_utc or datetime.now(UTC))
        session.flush()
    return decision_case_payload(session, row)


def record_case_decision(
    session: Session,
    *,
    case_id: str,
    outcome: str,
    actor: str,
    note: str = "",
    now_utc: datetime | None = None,
) -> dict:
    """Record a human decision on a case.

    The domain rules decide whether the case is decidable; this function only
    persists the outcome. It refuses and reports the blockers otherwise.

    Raises:
        ValueError: unknown case, unknown outcome, or a case that cannot be decided
            yet (the message carries the blocker codes).
    """

    row = _require_case(session, case_id)
    try:
        resolved_outcome = ReviewDecisionValue(outcome)
    except ValueError as exc:
        raise ValueError("unknown_outcome") from exc

    domain = _to_domain(session, row)
    if not case_is_decidable(domain):
        raise ValueError("case_not_decidable:" + ",".join(decision_blockers(domain)))

    decided = record_decision(
        domain,
        outcome=resolved_outcome,
        actor=actor,
        note=note,
    )
    now = _as_utc(now_utc or datetime.now(UTC))
    record = decided.records[-1]
    session.add(
        DecisionCaseDecisionRecord(
            record_id=f"drec-{uuid4().hex[:24]}",
            case_id=case_id,
            outcome=record.outcome.value,
            actor=record.actor,
            note=record.note or None,
            evidence_refs_json=list(record.evidence_refs),
            recorded_at_utc=now,
        )
    )
    row.status = decided.status.value
    row.updated_at_utc = now
    record_audit_event(
        session,
        event_type="decision.case",
        principal=record.actor,
        action="decision_case_record",
        resource=f"decision_case:{case_id}",
        outcome=record.outcome.value,
        severity="warning" if record.outcome is ReviewDecisionValue.REJECTED else "info",
        detail=f"evidence={len(record.evidence_refs)}",
        source_system="decision",
        now_utc=now,
    )
    session.flush()
    return decision_case_payload(session, row)


def reopen_decision_case(
    session: Session,
    *,
    case_id: str,
    actor: str,
    now_utc: datetime | None = None,
) -> dict:
    """Reopen a decided case, preserving every record."""

    row = _require_case(session, case_id)
    domain = reopen_case(_to_domain(session, row))
    now = _as_utc(now_utc or datetime.now(UTC))
    row.status = domain.status.value
    row.updated_at_utc = now
    record_audit_event(
        session,
        event_type="decision.case",
        principal=normalize_principal(actor),
        action="decision_case_reopen",
        resource=f"decision_case:{case_id}",
        outcome="reopened",
        severity="info",
        detail="",
        source_system="decision",
        now_utc=now,
    )
    session.flush()
    return decision_case_payload(session, row)


def decision_case_payload(session: Session, row: DecisionCaseRecord) -> dict:
    """Serialize a case row (with its records) to the API payload shape."""

    domain = _to_domain(session, row)
    return {
        "case_id": domain.case_id,
        "objective": domain.objective,
        "status": domain.status.value,
        "created_by": domain.created_by,
        "created_at_utc": domain.created_at_utc,
        "gas_day": domain.gas_day,
        "delivery_product": domain.delivery_product,
        "hub_id": domain.hub_id,
        "portfolio_ref": domain.portfolio_ref,
        "snapshot_id": domain.snapshot_id,
        "reproducible": domain.reproducible,
        "assumptions": [
            {"key": item.key, "value": item.value, "source": item.source.value, "note": item.note}
            for item in domain.assumptions
        ],
        "alternatives": [
            {
                "alternative_id": item.alternative_id,
                "label": item.label,
                "description": item.description,
                "economics_ref": item.economics_ref,
                "warnings": list(item.warnings),
            }
            for item in domain.alternatives
        ],
        "evidence": [
            {
                "kind": item.kind.value,
                "ref": item.ref,
                "label": item.label,
                "as_of_utc": item.as_of_utc,
                "snapshot_id": item.snapshot_id,
            }
            for item in domain.evidence
        ],
        "ai_findings": list(domain.ai_findings),
        "warnings": list(domain.warnings),
        "records": [
            {
                "outcome": item.outcome.value,
                "actor": item.actor,
                "note": item.note,
                "evidence_refs": list(item.evidence_refs),
                "recorded_at_utc": item.recorded_at_utc,
            }
            for item in domain.records
        ],
        "decidable": case_is_decidable(domain),
        "blockers": list(decision_blockers(domain)),
    }


def _to_domain(session: Session, row: DecisionCaseRecord) -> DecisionCase:
    records = (
        session.query(DecisionCaseDecisionRecord)
        .filter(DecisionCaseDecisionRecord.case_id == row.case_id)
        .order_by(DecisionCaseDecisionRecord.recorded_at_utc.asc())
        .all()
    )
    return DecisionCase(
        case_id=row.case_id,
        objective=row.objective,
        created_by=row.created_by,
        created_at_utc=_as_utc(row.created_at_utc).isoformat(),
        status=DecisionCaseStatus(row.status),
        gas_day=row.gas_day or "",
        delivery_product=row.delivery_product or "",
        hub_id=row.hub_id or "",
        portfolio_ref=row.portfolio_ref or "",
        snapshot_id=row.snapshot_id or "",
        assumptions=tuple(
            DecisionAssumption(
                key=str(item.get("key", "")),
                value=str(item.get("value", "")),
                source=_assumption_source(item.get("source")),
                note=str(item.get("note", "")),
            )
            for item in row.assumptions_json or []
        ),
        alternatives=tuple(
            DecisionAlternative(
                alternative_id=str(item.get("alternative_id", "")),
                label=str(item.get("label", "")),
                description=str(item.get("description", "")),
                economics_ref=str(item.get("economics_ref", "")),
                warnings=tuple(str(value) for value in item.get("warnings", [])),
            )
            for item in row.alternatives_json or []
        ),
        evidence=tuple(
            DecisionEvidence(
                kind=_evidence_kind(item.get("kind")),
                ref=str(item.get("ref", "")),
                label=str(item.get("label", "")),
                as_of_utc=str(item.get("as_of_utc", "")),
                snapshot_id=str(item.get("snapshot_id", "")),
            )
            for item in row.evidence_json or []
        ),
        ai_findings=tuple(str(value) for value in row.ai_findings_json or []),
        warnings=tuple(str(value) for value in row.warnings_json or []),
        records=tuple(
            DecisionRecord(
                outcome=_outcome(record.outcome),
                actor=record.actor,
                note=record.note or "",
                recorded_at_utc=_as_utc(record.recorded_at_utc).isoformat(),
                evidence_refs=tuple(str(value) for value in record.evidence_refs_json or []),
            )
            for record in records
        ),
    )


def _require_case(session: Session, case_id: str) -> DecisionCaseRecord:
    row = session.get(DecisionCaseRecord, case_id)
    if row is None:
        raise ValueError("unknown_decision_case")
    return row


def _evidence_kind(value: object) -> DecisionEvidenceKind:
    try:
        return DecisionEvidenceKind(str(value))
    except ValueError:
        return DecisionEvidenceKind.MANUAL


def _assumption_source(value: object) -> DecisionAssumptionSource:
    try:
        return DecisionAssumptionSource(str(value))
    except ValueError:
        return DecisionAssumptionSource.BACKEND


def _outcome(value: object) -> ReviewDecisionValue:
    try:
        return ReviewDecisionValue(str(value))
    except ValueError:
        return ReviewDecisionValue.NEEDS_ATTENTION


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
