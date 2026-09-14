"""Review decision repository tests."""

from unittest.mock import MagicMock

import pytest

from eurogas_nexus.db.repositories.review import (
    list_review_decisions,
    record_review_decision,
)
from eurogas_nexus.domain.ontology.vocabulary import (
    ReviewEntityType,
    coerce_review_entity_type,
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


def test_record_review_decision_accepts_an_agent_review_pack() -> None:
    session = MagicMock()
    result = record_review_decision(
        session,
        entity_type="agent_review_pack",
        entity_id="review-abc123",
        actor="trader-a",
        decision="accepted",
    )

    assert ReviewEntityType.AGENT_REVIEW_PACK.value == "agent_review_pack"
    assert result["entity_type"] == "agent_review_pack"
    assert result["entity_id"] == "review-abc123"


def test_record_review_decision_rejects_unknown_kind_without_writing() -> None:
    session = MagicMock()

    with pytest.raises(ValueError, match="unknown review entity type"):
        record_review_decision(
            session,
            entity_type="agent_replay",
            entity_id="review-abc123",
            actor="trader-a",
            decision="accepted",
        )

    assert session.add.call_count == 0
    assert session.flush.call_count == 0


@pytest.mark.parametrize("value", ["agent_replay", "", "AGENT_REVIEW_PACK", "strategy-run"])
def test_coerce_review_entity_type_fails_closed(value: str) -> None:
    with pytest.raises(ValueError, match="unknown review entity type"):
        coerce_review_entity_type(value)


def test_coerce_review_entity_type_accepts_known_kinds() -> None:
    assert coerce_review_entity_type("agent_review_pack") is ReviewEntityType.AGENT_REVIEW_PACK
    assert coerce_review_entity_type("strategy_run") is ReviewEntityType.STRATEGY_RUN


def test_list_review_decisions_empty() -> None:
    session = MagicMock()
    query = MagicMock()
    session.query.return_value = query
    query.filter.return_value = query
    query.order_by.return_value.limit.return_value.all.return_value = []

    assert list_review_decisions(session) == []
