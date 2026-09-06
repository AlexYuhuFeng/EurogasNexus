"""Repository integration tests for CR-15 agent replay artifacts."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.db.base import Base
from eurogas_nexus.db.repositories import agents as repo
from eurogas_nexus.domain.agents.budget import ResearchBudget
from eurogas_nexus.domain.agents.challenge import (
    ChallengeReport,
    ChallengeResult,
)
from eurogas_nexus.domain.agents.research_plan import deterministic_plan
from eurogas_nexus.domain.agents.review_pack import ReviewPack


@pytest.fixture()
def session():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def test_agent_run_replay_persists_observable_trace_only(session) -> None:
    run = repo.create_agent_run(
        session,
        agent_run_id="agent-run-1",
        principal_id="analyst-1",
        user_objective="Does NBP trade above TTF?",
        agent_profile="STRATEGY_RESEARCHER",
        model_provider="DETERMINISTIC",
        model_id="rule-based-plan/v1",
    )
    repo.persist_tool_invocation(
        session,
        invocation_id="inv-1",
        agent_run_id=run.agent_run_id,
        capability_id="analytics.distribution",
        capability_version="v1",
        principal_id="analyst-1",
        input_hash="a" * 64,
        input_summary={"values_count": 3},
        status="SUCCESS",
        output_reference="finding-1",
        output_hash="b" * 64,
        evidence_refs=["market.price.NBP.DAY_AHEAD"],
        duration_ms=12.5,
    )
    plan = deterministic_plan("Does NBP trade above TTF?", agent_run_id=run.agent_run_id)
    repo.persist_plan(session, plan)
    repo.persist_finding(
        session,
        repo.AgentResearchFindingRecord(
            finding_id="finding-1",
            research_plan_id=plan.research_plan_id,
            agent_run_id=run.agent_run_id,
            question=plan.question,
            statistic="mean_spread",
            value="1.2",
            unit="EUR/MWh",
            sample="3",
            methodology="deterministic",
            evidence=["obs-1"],
        ),
    )
    repo.persist_budget(
        session,
        ResearchBudget(budget_id="budget-1", agent_run_id=run.agent_run_id),
    )
    repo.persist_challenge_report(
        session,
        ChallengeReport(
            challenge_report_id="challenge-1",
            agent_run_id=run.agent_run_id,
            overall_result=ChallengeResult.PASS,
        ),
    )
    repo.persist_review_pack(
        session,
        ReviewPack(
            review_pack_id="review-1",
            agent_run_id=run.agent_run_id,
            objective=run.user_objective,
            research_plan=plan.model_dump(mode="json"),
            warnings=["none"],
        ),
    )
    repo.update_agent_run(
        session,
        run,
        status="READY_FOR_HUMAN_REVIEW",
        current_stage="READY_FOR_HUMAN_REVIEW",
        research_plan_id=plan.research_plan_id,
        artifacts_created=["review-1"],
        evidence_dependencies=["obs-1"],
        final_output_reference="review-1",
        completed=True,
    )
    session.flush()

    replay = repo.replay_payload(session, run)
    assert replay["agent_run_id"] == "agent-run-1"
    assert replay["hidden_chain_of_thought"] is None
    assert replay["tool_invocations"][0]["capability_id"] == "analytics.distribution"
    assert replay["tool_invocations"][0]["capability_version"] == "v1"
    assert replay["tool_invocations"][0]["evidence_refs"] == ["market.price.NBP.DAY_AHEAD"]
    assert replay["artifacts_created"] == ["review-1"]
    assert replay["status"] == "READY_FOR_HUMAN_REVIEW"

    rows = repo.list_agent_runs(session)
    assert [row.agent_run_id for row in rows] == ["agent-run-1"]
    assert repo.get_agent_run(session, "missing") is None
