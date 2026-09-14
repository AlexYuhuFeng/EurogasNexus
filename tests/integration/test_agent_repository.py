"""Repository integration tests for CR-15 agent replay artifacts."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import StrategyRunRecord
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


def _seed_run_with_artifacts(session, *, run_id: str = "agent-run-chain"):
    """Persist one agent run with a plan, finding, challenge report, and pack."""

    run = repo.create_agent_run(
        session,
        agent_run_id=run_id,
        principal_id="analyst-1",
        user_objective="Does NBP trade above TTF?",
        agent_profile="STRATEGY_RESEARCHER",
    )
    repo.persist_tool_invocation(
        session,
        invocation_id=f"inv-{run_id}",
        agent_run_id=run_id,
        capability_id="analytics.spread_distribution",
        capability_version="v1",
        principal_id="analyst-1",
        input_hash="a" * 64,
        input_summary={"left_values": 5, "right_values": 5},
        status="SUCCESS",
        evidence_refs=["market.price.NBP.DAY_AHEAD"],
        entitlement_state="ENTITLED",
    )
    plan = deterministic_plan("Does NBP trade above TTF?", agent_run_id=run_id)
    repo.persist_plan(session, plan)
    row = repo.get_plan(session, plan.research_plan_id)
    repo.update_plan_validation(session, row, issues=[], status="VALIDATED")
    repo.persist_finding(
        session,
        repo.AgentResearchFindingRecord(
            finding_id=f"finding-{run_id}",
            research_plan_id=plan.research_plan_id,
            agent_run_id=run_id,
            question=plan.question,
            statistic="mean_spread",
            value="2.0",
            unit="EUR/MWh",
            sample="5",
            methodology="deterministic",
            evidence=["market.price.NBP.DAY_AHEAD"],
        ),
    )
    repo.persist_challenge_report(
        session,
        ChallengeReport(
            challenge_report_id=f"challenge-{run_id}",
            agent_run_id=run_id,
            backtest_run_id="backtest-run-1",
            overall_result=ChallengeResult.PASS,
        ),
    )
    repo.persist_review_pack(
        session,
        ReviewPack(
            review_pack_id=f"review-{run_id}",
            agent_run_id=run_id,
            objective=run.user_objective,
            research_plan=plan.model_dump(mode="json"),
            strategy_specification={
                "hypothesis": "Persisted StrategyIR without components.",
                "universe": {
                    "origin_hub": "TTF",
                    "destination_hub": "NBP",
                    "product": "DAY_AHEAD",
                    "currency": "GBP",
                },
                "components": [],
            },
            backtest={"run_id": "backtest-run-1"},
        ),
    )
    repo.update_agent_run(
        session,
        run,
        status="READY_FOR_HUMAN_REVIEW",
        current_stage="READY_FOR_HUMAN_REVIEW",
        research_plan_id=plan.research_plan_id,
        artifacts_created=[f"review-{run_id}"],
        evidence_dependencies=["runtime market observations"],
        warnings=["STRATEGY_GENERATION_NOT_REQUESTED"],
        final_output_reference=f"review-{run_id}",
        completed=True,
    )
    session.flush()
    return run, plan


def test_run_artifacts_are_readable_through_repository_helpers(session) -> None:
    run, plan = _seed_run_with_artifacts(session)

    assert repo.get_plan_for_run(session, run.agent_run_id).research_plan_id == (
        plan.research_plan_id
    )
    assert [item.finding_id for item in repo.list_findings_for_run(session, run.agent_run_id)] == [
        f"finding-{run.agent_run_id}"
    ]
    assert repo.get_challenge_report_for_run(session, run.agent_run_id).overall_result == "PASS"
    assert repo.get_review_pack_for_run(session, run.agent_run_id).review_pack_id == (
        f"review-{run.agent_run_id}"
    )
    assert repo.get_plan_for_run(session, "agent-run-missing") is None
    assert repo.list_findings_for_run(session, "agent-run-missing") == []


def test_replay_payload_carries_identity_lineage_and_rights(session) -> None:
    run, plan = _seed_run_with_artifacts(session)
    session.add(
        StrategyRunRecord(
            run_id="backtest-run-1",
            strategy_id="strategy-1",
            run_mode="BACKTEST",
            status="COMPLETED",
            started_at_utc=datetime.now(UTC),
            dataset_snapshot_id="strategy-snapshot-1",
            input_snapshot={},
            result_snapshot={},
            source_refs=["market.price.NBP.DAY_AHEAD"],
            warnings=[],
            missing_inputs=[],
            research_only=True,
            human_review_required=True,
        )
    )
    session.flush()

    replay = repo.replay_payload(session, run)
    assert replay["hidden_chain_of_thought"] is None
    assert replay["review_entity_type"] == "agent_review_pack"
    assert replay["fixture"]["fixture_id"].startswith("fixture-")
    assert replay["fixture"]["evidence_refs"] == ["market.price.NBP.DAY_AHEAD"]

    assert set(replay["artifacts"]) == set(repo.ARTIFACT_CHAIN_ORDER)
    assert replay["artifact_chain"]["present"] == list(repo.ARTIFACT_CHAIN_ORDER)
    assert replay["artifact_chain"]["complete"] is True

    plan_envelope = replay["artifacts"]["research_plan"]
    assert plan_envelope["artifact_id"] == plan.research_plan_id
    assert plan_envelope["operation_id"] == "agent.research.plan"
    assert plan_envelope["stage"] == "PLAN_DRAFTED"
    assert plan_envelope["lineage"]["upstream_artifact_ids"] == []
    assert plan_envelope["rights"]["entitlement_state"] == "ENTITLED"
    assert plan_envelope["rights"]["principal_id"] == "analyst-1"
    assert plan_envelope["timestamps"]["created_at"]

    findings = replay["artifacts"]["findings"]
    assert findings["artifact_ids"] == [f"finding-{run.agent_run_id}"]
    assert findings["lineage"]["upstream_artifact_ids"] == [plan.research_plan_id]
    assert findings["lineage"]["producing_invocation_ids"] == [f"inv-{run.agent_run_id}"]
    assert findings["lineage"]["snapshot_ids"] == ["strategy-snapshot-1"]
    assert findings["lineage"]["source_references"] == ["market.price.NBP.DAY_AHEAD"]

    validation = replay["artifacts"]["validation"]["payload"]
    assert validation["plan_status"] == "VALIDATED"
    assert validation["strategy_ir_validation"]["ok"] is False
    assert {issue["code"] for issue in validation["strategy_ir_validation"]["issues"]} == {
        "STRATEGY_INVALID"
    }
    assert validation["strategy_ir_validation_source"] == "recomputed:validate_strategy_ir"

    challenge = replay["artifacts"]["challenge_report"]
    assert challenge["artifact_id"] == f"challenge-{run.agent_run_id}"
    assert challenge["payload"]["backtest_run_id"] == "backtest-run-1"
    assert "backtest-run-1" in challenge["lineage"]["upstream_artifact_ids"]

    pack = replay["artifacts"]["review_pack"]
    assert pack["artifact_id"] == f"review-{run.agent_run_id}"
    assert pack["payload"]["human_confirmation"]["decisions"] == []
    assert pack["lineage"]["snapshot_ids"] == ["strategy-snapshot-1"]
    for envelope in replay["artifacts"].values():
        assert envelope["hidden_chain_of_thought"] is None
        assert envelope["replay_identity"]["replay_id"].startswith("replay-")

    summary = repo.artifact_chain_summary(session, run)
    assert summary["artifact_ids"]["review_pack"] == [f"review-{run.agent_run_id}"]
    assert repo.list_review_confirmation_decisions(session, f"review-{run.agent_run_id}") == []


def test_artifact_chain_summary_reports_every_missing_artifact(session) -> None:
    run = repo.create_agent_run(
        session,
        agent_run_id="agent-run-bare",
        principal_id="analyst-1",
        user_objective="No artifact was produced for this objective yet.",
    )
    session.flush()

    summary = repo.artifact_chain_summary(session, run)
    assert summary["complete"] is False
    assert summary["present"] == []
    assert summary["missing"] == list(repo.ARTIFACT_CHAIN_ORDER)

    replay = repo.replay_payload(session, run)
    assert replay["hidden_chain_of_thought"] is None
    assert set(replay["artifacts"]) == set(repo.ARTIFACT_CHAIN_ORDER)
    assert all(not item["present"] for item in replay["artifacts"].values())
    assert all(item["payload"] is None for item in replay["artifacts"].values())
