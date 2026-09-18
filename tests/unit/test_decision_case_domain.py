"""Decision Case domain tests (Architecture V2 Wave 6).

The two structural rules this module exists to enforce: a decision is evidence and
rationale rather than execution approval, and a case cannot be decided without
evidence pointing at the material it was taken on.
"""

from __future__ import annotations

import pytest

from eurogas_nexus.domain.decision import (
    DECISION_RECORD_IS_NOT_EXECUTION,
    MAX_OBJECTIVE_LENGTH,
    DecisionAlternative,
    DecisionAssumption,
    DecisionAssumptionSource,
    DecisionCase,
    DecisionCaseStatus,
    DecisionEvidence,
    DecisionEvidenceKind,
    add_evidence,
    case_is_decidable,
    case_summary,
    decision_blockers,
    record_decision,
    reopen_case,
    validate_decision_case,
)
from eurogas_nexus.domain.ontology.vocabulary import ReviewDecisionValue


def _case(**overrides: object) -> DecisionCase:
    base: dict[str, object] = {
        "case_id": "case-1",
        "objective": "Decide where tomorrow's NBP resource should go.",
        "created_by": "analyst.one",
        "gas_day": "2026-09-15",
        "delivery_product": "day-ahead",
        "hub_id": "NBP",
    }
    base.update(overrides)
    return DecisionCase(**base)  # type: ignore[arg-type]


def test_a_decision_record_is_evidence_not_execution_approval() -> None:
    assert DECISION_RECORD_IS_NOT_EXECUTION is True


def test_an_empty_case_cannot_be_decided() -> None:
    case = _case()

    assert case_is_decidable(case) is False
    blockers = decision_blockers(case)
    assert "evidence_required" in blockers
    assert "snapshot_recommended" in blockers

    with pytest.raises(ValueError) as excinfo:
        record_decision(
            case,
            outcome=ReviewDecisionValue.ACCEPTED,
            actor="reviewer.one",
        )
    assert "case_not_decidable" in str(excinfo.value)
    assert "evidence_required" in str(excinfo.value)


def test_evidence_makes_a_case_decidable_and_records_the_evidence_refs() -> None:
    case = add_evidence(
        _case(),
        DecisionEvidence(
            kind=DecisionEvidenceKind.ROUTE_RECOMMENDATION,
            ref="route-rec-9",
            label="NBP route recommendation",
            as_of_utc="2026-09-15T06:00:00+00:00",
            snapshot_id="snap-42",
        ),
    )

    assert case.reproducible is True
    assert case.snapshot_id == "snap-42"
    assert case_is_decidable(case) is True

    decided = record_decision(
        case,
        outcome=ReviewDecisionValue.ACCEPTED,
        actor="reviewer.one",
        note="Capacity confirmed for the gas day.",
    )

    assert decided.status is DecisionCaseStatus.DECIDED
    assert decided.decided is True
    assert decided.records[-1].actor == "reviewer.one"
    assert decided.records[-1].outcome is ReviewDecisionValue.ACCEPTED
    assert decided.records[-1].evidence_refs == ("route-rec-9",)
    assert decided.records[-1].recorded_at_utc
    # The original case is untouched: recording returns a new value.
    assert case.records == ()
    assert case.status is DecisionCaseStatus.DRAFT


def test_a_decision_still_requires_a_named_human() -> None:
    case = add_evidence(
        _case(),
        DecisionEvidence(kind=DecisionEvidenceKind.MARKET_CONTEXT, ref="market-ctx-1"),
    )

    with pytest.raises(ValueError) as excinfo:
        record_decision(case, outcome=ReviewDecisionValue.ACCEPTED, actor="   ")
    assert "record_actor_required" in str(excinfo.value)

    with pytest.raises(ValueError) as excinfo:
        record_decision(
            case,
            outcome=ReviewDecisionValue.REJECTED,
            actor="reviewer.one",
            note="x" * 2001,
        )
    assert "record_note_too_long" in str(excinfo.value)


def test_structure_validation_is_explicit() -> None:
    assert validate_decision_case(_case()) == ()
    assert "case_id_required" in validate_decision_case(_case(case_id=" "))
    assert "objective_required" in validate_decision_case(_case(objective=""))
    assert "objective_too_long" in validate_decision_case(
        _case(objective="x" * (MAX_OBJECTIVE_LENGTH + 1))
    )
    assert "created_by_required" in validate_decision_case(_case(created_by=""))

    # A DECIDED case without a record is an inconsistent state, not a valid one.
    inconsistent = DecisionCase(
        case_id="case-2",
        objective="Objective",
        created_by="analyst",
        status=DecisionCaseStatus.DECIDED,
    )
    assert "decided_case_requires_record" in validate_decision_case(inconsistent)


def test_reopening_preserves_history() -> None:
    case = add_evidence(
        _case(),
        DecisionEvidence(kind=DecisionEvidenceKind.RESEARCH_DATASET, ref="ds-1"),
    )
    decided = record_decision(case, outcome=ReviewDecisionValue.ACCEPTED, actor="reviewer.one")
    reopened = reopen_case(decided)

    assert reopened.status is DecisionCaseStatus.REOPENED
    assert reopened.records == decided.records
    assert reopen_case(case) is case


def test_evidence_is_deduplicated_and_carries_the_assumptions() -> None:
    case = add_evidence(
        _case(
            assumptions=(
                DecisionAssumption(
                    key="storage_level_pct",
                    value="62",
                    source=DecisionAssumptionSource.MARKET_DATA,
                ),
            ),
            alternatives=(
                DecisionAlternative(
                    alternative_id="alt-1",
                    label="Route via Zeebrugge",
                    economics_ref="econ-1",
                    warnings=("partial capacity",),
                ),
            ),
        ),
        DecisionEvidence(kind=DecisionEvidenceKind.SCENARIO, ref="scenario-1"),
    )
    again = add_evidence(
        case, DecisionEvidence(kind=DecisionEvidenceKind.SCENARIO, ref="scenario-1")
    )
    assert again is case

    assert add_evidence(case, DecisionEvidence(kind=DecisionEvidenceKind.MANUAL, ref=" ")) is case

    summary = case_summary(case)
    assert summary["evidence_count"] == 1
    assert summary["alternative_count"] == 1
    assert summary["assumption_count"] == 1
    assert summary["record_count"] == 0
    assert summary["reproducible"] is False
    assert summary["last_record"] is None
    assert set(summary) == {
        "case_id",
        "objective",
        "status",
        "gas_day",
        "delivery_product",
        "hub_id",
        "evidence_count",
        "alternative_count",
        "assumption_count",
        "record_count",
        "reproducible",
        "last_record",
    }
