"""Decision deadlines are structured, sortable and auditable (#58)."""

from datetime import UTC, datetime

import pytest

from eurogas_nexus.domain.decision import (
    DecisionCase,
    DecisionCaseStatus,
    DecisionRecord,
    deadline_sort_key,
    deadline_state,
    parse_decision_due,
)
from eurogas_nexus.domain.ontology.vocabulary import ReviewDecisionValue


def _case(case_id: str, due: str = "", **kwargs) -> DecisionCase:
    return DecisionCase(
        case_id=case_id, objective="o", created_by="a", decision_due_at_utc=due, **kwargs
    )


def test_an_offset_time_is_normalised_to_utc() -> None:
    parsed = parse_decision_due("2026-03-29T09:30:00+02:00")
    assert parsed == datetime(2026, 3, 29, 7, 30, tzinfo=UTC)
    assert parse_decision_due("2026-03-29T07:30:00Z") == parsed


def test_a_naive_or_garbled_time_is_refused_and_none_is_allowed() -> None:
    with pytest.raises(ValueError, match="decision_due_timezone_required"):
        parse_decision_due("2026-03-29T09:30:00")
    with pytest.raises(ValueError, match="decision_due_invalid"):
        parse_decision_due("tomorrow noon")
    assert parse_decision_due(None) is None
    assert parse_decision_due("  ") is None


def test_open_cases_sort_by_due_time_regardless_of_creation_order() -> None:
    late = _case("case-b", "2026-11-06T16:00:00+00:00")
    early = _case("case-z", "2026-11-06T10:00:00+00:00")
    none = _case("case-a")
    decided = _case(
        "case-c",
        "2026-11-06T09:00:00+00:00",
        status=DecisionCaseStatus.DECIDED,
    )
    # The input order stands for the listing order (newest first); only open cases with a
    # deadline move ahead of it.
    ordered = sorted([decided, none, late, early], key=deadline_sort_key)
    assert [case.case_id for case in ordered] == ["case-z", "case-b", "case-c", "case-a"]


def test_due_overdue_and_decision_timing() -> None:
    due = "2026-11-06T12:00:00+00:00"
    assert deadline_state(_case("c"), datetime(2026, 11, 6, tzinfo=UTC)) == "none"
    assert deadline_state(_case("c", due), datetime(2026, 11, 6, 11, tzinfo=UTC)) == "due"
    assert deadline_state(_case("c", due), datetime(2026, 11, 6, 13, tzinfo=UTC)) == "overdue"
    record = DecisionRecord(
        outcome=list(ReviewDecisionValue)[0],
        actor="b",
        recorded_at_utc="2026-11-06T12:30:00+00:00",
    )
    late = _case("c", due, records=(record,), status=DecisionCaseStatus.DECIDED)
    assert deadline_state(late) == "decided_late"
    on_time = _case(
        "c",
        "2026-11-06T13:00:00+00:00",
        records=(record,),
        status=DecisionCaseStatus.DECIDED,
    )
    assert deadline_state(on_time) == "decided_on_time"
