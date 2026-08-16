"""Review decision repository tests."""

from unittest.mock import MagicMock

from eurogas_nexus.db.repositories.review import (
    list_review_decisions,
    record_review_decision,
)


def test_record_review_decision_persists_and_audits() -> None:
    session = MagicMock()
    result = record_review_decision(
        session,
        entity_type="intraday_opportunity",
        entity_id="opp-1",
        actor="trader-a",
        decision="accepted",
        note="looks actionable",
    )

    assert result["entity_type"] == "intraday_opportunity"
    assert result["entity_id"] == "opp-1"
    assert result["actor"] == "trader-a"
    assert result["decision"] == "accepted"
    assert result["note"] == "looks actionable"
    assert result["decision_id"].startswith("review-")
    # decision row + audit event are both added
    assert session.add.call_count == 2


def test_list_review_decisions_empty() -> None:
    session = MagicMock()
    query = MagicMock()
    session.query.return_value = query
    query.filter.return_value = query
    query.order_by.return_value.limit.return_value.all.return_value = []

    assert list_review_decisions(session) == []
