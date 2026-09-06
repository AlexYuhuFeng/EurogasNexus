"""Persistence for agent runs, tool invocations, and research artifacts."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from eurogas_nexus.db.models import (
    AgentChallengeReportRecord,
    AgentResearchBudgetRecord,
    AgentResearchFindingRecord,
    AgentResearchPlanRecord,
    AgentReviewPackRecord,
    AgentRunRecord,
    AgentToolInvocationRecord,
)
from eurogas_nexus.domain.agents.budget import ResearchBudget
from eurogas_nexus.domain.agents.challenge import ChallengeReport
from eurogas_nexus.domain.agents.research_plan import ResearchPlan
from eurogas_nexus.domain.agents.review_pack import ReviewPack


def _now() -> datetime:
    return datetime.now(UTC)


def create_agent_run(
    session: Session,
    *,
    agent_run_id: str,
    principal_id: str,
    user_objective: str,
    agent_profile: str = "MARKET_RESEARCHER",
    model_provider: str = "DETERMINISTIC",
    model_id: str = "rule-based-plan/v1",
    correlation_request_id: str | None = None,
    status: str = "RECEIVED",
    current_stage: str = "OBJECTIVE_RECEIVED",
) -> AgentRunRecord:
    row = AgentRunRecord(
        agent_run_id=agent_run_id,
        principal_id=principal_id,
        user_objective=user_objective,
        agent_profile=agent_profile,
        model_provider=model_provider,
        model_id=model_id,
        correlation_request_id=correlation_request_id,
        status=status,
        current_stage=current_stage,
        started_at_utc=_now(),
    )
    session.add(row)
    session.flush()
    return row


def get_agent_run(session: Session, agent_run_id: str) -> AgentRunRecord | None:
    return session.get(AgentRunRecord, agent_run_id)


def list_agent_runs(session: Session, *, limit: int = 100) -> list[AgentRunRecord]:
    return list(
        session.scalars(
            select(AgentRunRecord)
            .order_by(AgentRunRecord.created_at_utc.desc())
            .limit(max(1, min(limit, 500)))
        )
    )


def update_agent_run(
    session: Session,
    row: AgentRunRecord,
    *,
    status: str | None = None,
    current_stage: str | None = None,
    research_plan_id: str | None = None,
    artifacts_created: list[str] | None = None,
    evidence_dependencies: list[str] | None = None,
    warnings: list[str] | None = None,
    blockers: list[str] | None = None,
    token_cost_metadata: dict[str, Any] | None = None,
    final_output_reference: str | None = None,
    completed: bool = False,
) -> AgentRunRecord:
    if status is not None:
        row.status = status
    if current_stage is not None:
        row.current_stage = current_stage
    if research_plan_id is not None:
        row.research_plan_id = research_plan_id
    if artifacts_created is not None:
        row.artifacts_created = artifacts_created
    if evidence_dependencies is not None:
        row.evidence_dependencies = evidence_dependencies
    if warnings is not None:
        row.warnings = warnings
    if blockers is not None:
        row.blockers = blockers
    if token_cost_metadata is not None:
        row.token_cost_metadata = token_cost_metadata
    if final_output_reference is not None:
        row.final_output_reference = final_output_reference
    if completed:
        row.completed_at_utc = _now()
    session.flush()
    return row


def persist_tool_invocation(
    session: Session,
    *,
    invocation_id: str,
    agent_run_id: str | None,
    capability_id: str,
    capability_version: str,
    principal_id: str,
    input_hash: str,
    input_summary: dict[str, Any],
    status: str,
    output_reference: str | None = None,
    output_hash: str | None = None,
    evidence_refs: list[str] | None = None,
    warnings: list[str] | None = None,
    error_code: str | None = None,
    duration_ms: float | None = None,
    entitlement_state: str = "NOT_APPLICABLE",
    started_at_utc: datetime | None = None,
    completed_at_utc: datetime | None = None,
) -> AgentToolInvocationRecord:
    row = AgentToolInvocationRecord(
        invocation_id=invocation_id,
        agent_run_id=agent_run_id,
        capability_id=capability_id,
        capability_version=capability_version,
        principal_id=principal_id,
        input_hash=input_hash,
        input_summary=input_summary,
        status=status,
        output_reference=output_reference,
        output_hash=output_hash,
        evidence_refs=evidence_refs or [],
        warnings=warnings or [],
        error_code=error_code,
        duration_ms=duration_ms,
        entitlement_state=entitlement_state,
        started_at_utc=started_at_utc or _now(),
        completed_at_utc=completed_at_utc,
    )
    session.add(row)
    session.flush()
    return row


def list_tool_invocations(
    session: Session, agent_run_id: str, *, limit: int = 500
) -> list[AgentToolInvocationRecord]:
    return list(
        session.scalars(
            select(AgentToolInvocationRecord)
            .where(AgentToolInvocationRecord.agent_run_id == agent_run_id)
            .order_by(AgentToolInvocationRecord.started_at_utc.asc())
            .limit(max(1, min(limit, 2000)))
        )
    )


def persist_plan(session: Session, plan: ResearchPlan) -> AgentResearchPlanRecord:
    row = AgentResearchPlanRecord(
        research_plan_id=plan.research_plan_id,
        agent_run_id=plan.agent_run_id,
        objective=plan.objective,
        question=plan.question,
        market_scope=plan.market_scope,
        entities=plan.entities,
        product=plan.product,
        horizon=plan.horizon,
        hypotheses_to_test=plan.hypotheses_to_test,
        required_evidence=[item.model_dump(mode="json") for item in plan.required_evidence],
        analyses=[item.model_dump(mode="json") for item in plan.analyses],
        data_quality_requirements=plan.data_quality_requirements,
        statistical_requirements=plan.statistical_requirements,
        strategy_generation_allowed=plan.strategy_generation_allowed,
        stopping_conditions=plan.stopping_conditions,
        status="VALIDATED",
        created_by=plan.created_by,
    )
    session.add(row)
    session.flush()
    return row


def get_plan(session: Session, plan_id: str) -> AgentResearchPlanRecord | None:
    return session.get(AgentResearchPlanRecord, plan_id)


def update_plan_validation(
    session: Session, row: AgentResearchPlanRecord, issues: list[dict], status: str
) -> AgentResearchPlanRecord:
    row.validation_issues = issues
    row.status = status
    session.flush()
    return row


def persist_finding(
    session: Session, row: AgentResearchFindingRecord
) -> AgentResearchFindingRecord:
    session.add(row)
    session.flush()
    return row


def persist_budget(session: Session, budget: ResearchBudget) -> AgentResearchBudgetRecord:
    payload = budget.model_dump(mode="json", exclude={"created_at_utc"})
    row = AgentResearchBudgetRecord(**payload, created_at_utc=budget.created_at_utc)
    session.add(row)
    session.flush()
    return row


def persist_challenge_report(
    session: Session, report: ChallengeReport
) -> AgentChallengeReportRecord:
    row = AgentChallengeReportRecord(
        challenge_report_id=report.challenge_report_id,
        agent_run_id=report.agent_run_id,
        strategy_version_id=report.strategy_version_id,
        backtest_run_id=report.backtest_run_id,
        items=[item.model_dump(mode="json") for item in report.items],
        overall_result=report.overall_result.value,
        recommended_follow_up=report.recommended_follow_up,
    )
    session.add(row)
    session.flush()
    return row


def persist_review_pack(session: Session, pack: ReviewPack) -> AgentReviewPackRecord:
    row = AgentReviewPackRecord(
        review_pack_id=pack.review_pack_id,
        agent_run_id=pack.agent_run_id,
        objective=pack.objective,
        research_plan=pack.research_plan,
        key_findings=pack.key_findings,
        strategy_specification=pack.strategy_specification,
        backtest=pack.backtest,
        robustness=pack.robustness,
        challenge_report=pack.challenge_report,
        data_provenance=pack.data_provenance,
        warnings=pack.warnings,
        known_limitations=pack.known_limitations,
        alternative_hypotheses=pack.alternative_hypotheses,
        status=pack.status,
    )
    session.add(row)
    session.flush()
    return row


def replay_payload(session: Session, row: AgentRunRecord) -> dict[str, Any]:
    invocations = [
        {
            "invocation_id": item.invocation_id,
            "capability_id": item.capability_id,
            "capability_version": item.capability_version,
            "started_at": item.started_at_utc.isoformat(),
            "completed_at": (item.completed_at_utc.isoformat() if item.completed_at_utc else None),
            "input_hash": item.input_hash,
            "input_summary": item.input_summary,
            "status": item.status,
            "output_reference": item.output_reference,
            "evidence_refs": item.evidence_refs,
            "warnings": item.warnings,
            "error_code": item.error_code,
            "duration_ms": item.duration_ms,
            "entitlement_state": item.entitlement_state,
        }
        for item in list_tool_invocations(session, row.agent_run_id)
    ]
    return {
        "agent_run_id": row.agent_run_id,
        "user_objective": row.user_objective,
        "principal_id": row.principal_id,
        "agent_profile": row.agent_profile,
        "model_provider": row.model_provider,
        "model_id": row.model_id,
        "status": row.status,
        "current_stage": row.current_stage,
        "research_plan_id": row.research_plan_id,
        "artifacts_created": row.artifacts_created,
        "evidence_dependencies": row.evidence_dependencies,
        "warnings": row.warnings,
        "blockers": row.blockers,
        "token_cost_metadata": row.token_cost_metadata,
        "final_output_reference": row.final_output_reference,
        "started_at": row.started_at_utc.isoformat(),
        "completed_at": row.completed_at_utc.isoformat() if row.completed_at_utc else None,
        "agent_runtime_version": row.agent_runtime_version,
        "tool_invocations": invocations,
        "hidden_chain_of_thought": None,
    }
