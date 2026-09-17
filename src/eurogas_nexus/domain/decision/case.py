"""Decision Case domain model (Architecture V2 08_DECISION_APPLICATION_AI.md section 1).

A Decision Case is the container that turns analysis into reviewable, human-owned
decision evidence:

```text
Decision Case
  Objective -> Active Context -> Analysis Snapshot -> Assumptions -> Alternatives
  -> Scenarios -> Economics/Optimisation -> Risk/Constraints -> Evidence
  -> AI Findings/Challenge -> Human Review -> Decision Record
```

Two rules are structural, not stylistic:

1. **A Decision Record is evidence and rationale, never execution approval.** The
   product does not enter orders, route them, submit nominations or settle; a
   record says what a named human concluded and why.
2. **A case cannot be decided without evidence.** The container refuses to record a
   decision while it has no evidence reference or no snapshot, so a decision always
   points at the material it was taken on.

The module is pure: immutable value objects plus validation. Persistence, HTTP and
UI are separate layers.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import UTC, datetime

from eurogas_nexus.domain.ontology.vocabulary import (
    DecisionAssumptionSource,
    DecisionCaseStatus,
    DecisionEvidenceKind,
    ReviewDecisionValue,
)

__all__ = [
    "DECISION_RECORD_IS_NOT_EXECUTION",
    "MAX_NOTE_LENGTH",
    "MAX_OBJECTIVE_LENGTH",
    "DecisionAlternative",
    "DecisionAssumption",
    "DecisionAssumptionSource",
    "DecisionCase",
    "DecisionCaseStatus",
    "DecisionEvidence",
    "DecisionEvidenceKind",
    "DecisionRecord",
    "add_evidence",
    "case_is_decidable",
    "case_summary",
    "decision_blockers",
    "record_decision",
    "reopen_case",
    "validate_decision_case",
]

# A Decision Record is never an instruction to execute anything.
DECISION_RECORD_IS_NOT_EXECUTION = True

MAX_OBJECTIVE_LENGTH = 500
MAX_NOTE_LENGTH = 2000


@dataclass(frozen=True, slots=True)
class DecisionAssumption:
    """One bounded input the alternatives were evaluated under."""

    key: str
    value: str
    source: DecisionAssumptionSource
    note: str = ""


@dataclass(frozen=True, slots=True)
class DecisionAlternative:
    """One option the case considered, with its economics reference."""

    alternative_id: str
    label: str
    description: str = ""
    economics_ref: str = ""
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class DecisionEvidence:
    """A reference to material the case rests on.

    ``snapshot_id`` is the reproducibility reference: when it is absent the case
    can still be reviewed, but a decision recorded on it cannot claim
    reproducibility from the case alone.
    """

    kind: DecisionEvidenceKind
    ref: str
    label: str = ""
    as_of_utc: str = ""
    snapshot_id: str = ""


@dataclass(frozen=True, slots=True)
class DecisionRecord:
    """A named human's conclusion about a case. Evidence, not approval to act."""

    outcome: ReviewDecisionValue
    actor: str
    note: str = ""
    recorded_at_utc: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    evidence_refs: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class DecisionCase:
    """The decision container itself."""

    case_id: str
    objective: str
    created_by: str
    created_at_utc: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    status: DecisionCaseStatus = DecisionCaseStatus.DRAFT
    gas_day: str = ""
    delivery_product: str = ""
    hub_id: str = ""
    portfolio_ref: str = ""
    snapshot_id: str = ""
    assumptions: tuple[DecisionAssumption, ...] = ()
    alternatives: tuple[DecisionAlternative, ...] = ()
    evidence: tuple[DecisionEvidence, ...] = ()
    ai_findings: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    records: tuple[DecisionRecord, ...] = ()

    @property
    def decided(self) -> bool:
        """Whether a decision has been recorded."""

        return bool(self.records)

    @property
    def reproducible(self) -> bool:
        """Whether the case carries an Analysis Snapshot to reproduce against."""

        return bool(self.snapshot_id) or any(item.snapshot_id for item in self.evidence)


def validate_decision_case(case: DecisionCase) -> tuple[str, ...]:
    """Return the rule violations of a case, most structural first (empty is valid)."""

    violations: list[str] = []
    if not case.case_id.strip():
        violations.append("case_id_required")
    if not case.objective.strip():
        violations.append("objective_required")
    elif len(case.objective) > MAX_OBJECTIVE_LENGTH:
        violations.append("objective_too_long")
    if not case.created_by.strip():
        violations.append("created_by_required")
    for record in case.records:
        if not record.actor.strip():
            violations.append("record_actor_required")
        if len(record.note) > MAX_NOTE_LENGTH:
            violations.append("record_note_too_long")
    if case.status is DecisionCaseStatus.DECIDED and not case.records:
        violations.append("decided_case_requires_record")
    return tuple(violations)


def case_is_decidable(case: DecisionCase) -> bool:
    """Whether the case may accept a decision record.

    A case needs evidence and a clean structure: deciding on an empty container is
    exactly the "decision without evidence" the architecture forbids.
    """

    return bool(case.evidence) and not validate_decision_case(case)


def decision_blockers(case: DecisionCase) -> tuple[str, ...]:
    """Human-readable reasons the case cannot be decided yet."""

    blockers = list(validate_decision_case(case))
    if not case.evidence:
        blockers.append("evidence_required")
    if not case.reproducible:
        blockers.append("snapshot_recommended")
    return tuple(blockers)


def record_decision(
    case: DecisionCase,
    *,
    outcome: ReviewDecisionValue,
    actor: str,
    note: str = "",
) -> DecisionCase:
    """Append a decision record, returning a new case.

    Raises:
        ValueError: when the case is not decidable, or the actor is missing. The
            error carries the blocker codes, so a caller can explain the refusal.
    """

    if not actor.strip():
        raise ValueError("record_actor_required")
    if not case_is_decidable(case):
        raise ValueError("case_not_decidable:" + ",".join(decision_blockers(case)))
    if len(note) > MAX_NOTE_LENGTH:
        raise ValueError("record_note_too_long")

    record = DecisionRecord(
        outcome=outcome,
        actor=actor.strip(),
        note=note,
        evidence_refs=tuple(item.ref for item in case.evidence),
    )
    return replace(
        case,
        status=DecisionCaseStatus.DECIDED,
        records=(*case.records, record),
    )


def reopen_case(case: DecisionCase) -> DecisionCase:
    """Reopen a decided case. The history is preserved; nothing is deleted."""

    if not case.decided:
        return case
    return replace(case, status=DecisionCaseStatus.REOPENED)


def add_evidence(case: DecisionCase, evidence: DecisionEvidence) -> DecisionCase:
    """Attach evidence, deduplicating by kind and reference."""

    if not evidence.ref.strip():
        return case
    existing = {(item.kind, item.ref) for item in case.evidence}
    if (evidence.kind, evidence.ref) in existing:
        return case
    snapshot_id = case.snapshot_id or evidence.snapshot_id
    return replace(case, evidence=(*case.evidence, evidence), snapshot_id=snapshot_id)


def case_summary(case: DecisionCase) -> dict[str, object]:
    """Compact, safe summary for a list view: no free-text body, no secrets."""

    return {
        "case_id": case.case_id,
        "objective": case.objective[:160],
        "status": case.status.value,
        "gas_day": case.gas_day,
        "delivery_product": case.delivery_product,
        "hub_id": case.hub_id,
        "evidence_count": len(case.evidence),
        "alternative_count": len(case.alternatives),
        "assumption_count": len(case.assumptions),
        "record_count": len(case.records),
        "reproducible": case.reproducible,
        "last_record": (
            {
                "outcome": case.records[-1].outcome.value,
                "actor": case.records[-1].actor,
                "recorded_at_utc": case.records[-1].recorded_at_utc,
            }
            if case.records
            else None
        ),
    }
