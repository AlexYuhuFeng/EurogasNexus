"""Agent-run and research-artifact persistence models (CR-15)."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from eurogas_nexus.db.base import Base


def _now() -> datetime:
    return datetime.now(UTC)


class AgentRunRecord(Base):
    """Observable orchestration trace; never hidden chain-of-thought."""

    __tablename__ = "agent_runs"
    __table_args__ = (
        Index("ix_agent_runs_principal_created", "principal_id", "created_at_utc"),
        Index("ix_agent_runs_status", "status"),
    )

    agent_run_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    principal_id: Mapped[str] = mapped_column(String(64), nullable=False)
    agent_profile: Mapped[str] = mapped_column(
        String(32), nullable=False, default="MARKET_RESEARCHER"
    )
    model_provider: Mapped[str] = mapped_column(String(32), nullable=False, default="DETERMINISTIC")
    model_id: Mapped[str] = mapped_column(String(64), nullable=False, default="rule-based-plan/v1")
    user_objective: Mapped[str] = mapped_column(Text(), nullable=False)
    research_plan_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="RECEIVED")
    current_stage: Mapped[str] = mapped_column(
        String(32), nullable=False, default="OBJECTIVE_RECEIVED"
    )
    artifacts_created: Mapped[list[str]] = mapped_column(JSON, default=list)
    evidence_dependencies: Mapped[list[str]] = mapped_column(JSON, default=list)
    warnings: Mapped[list[str]] = mapped_column(JSON, default=list)
    blockers: Mapped[list[str]] = mapped_column(JSON, default=list)
    token_cost_metadata: Mapped[dict] = mapped_column(JSON, default=dict)
    final_output_reference: Mapped[str | None] = mapped_column(String(256), nullable=True)
    correlation_request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    agent_runtime_version: Mapped[str] = mapped_column(String(32), default="agent-runtime/v1")
    started_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    completed_at_utc: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class AgentToolInvocationRecord(Base):
    """One capability invocation with version, safe input summary, and evidence."""

    __tablename__ = "agent_tool_invocations"
    __table_args__ = (
        Index("ix_agent_tool_invocations_run", "agent_run_id"),
        Index("ix_agent_tool_invocations_capability", "capability_id"),
    )

    invocation_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    agent_run_id: Mapped[str | None] = mapped_column(
        String(128), ForeignKey("agent_runs.agent_run_id"), nullable=True
    )
    capability_id: Mapped[str] = mapped_column(String(128), nullable=False)
    capability_version: Mapped[str] = mapped_column(String(32), nullable=False)
    principal_id: Mapped[str] = mapped_column(String(64), nullable=False)
    started_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    completed_at_utc: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    input_summary: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="SUCCESS")
    output_reference: Mapped[str | None] = mapped_column(String(256), nullable=True)
    output_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    evidence_refs: Mapped[list[str]] = mapped_column(JSON, default=list)
    warnings: Mapped[list[str]] = mapped_column(JSON, default=list)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    duration_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    entitlement_state: Mapped[str] = mapped_column(String(32), default="NOT_APPLICABLE")


class AgentResearchPlanRecord(Base):
    __tablename__ = "agent_research_plans"

    research_plan_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    agent_run_id: Mapped[str | None] = mapped_column(
        String(128), ForeignKey("agent_runs.agent_run_id"), nullable=True
    )
    objective: Mapped[str] = mapped_column(Text(), nullable=False)
    question: Mapped[str] = mapped_column(Text(), nullable=False)
    market_scope: Mapped[list[str]] = mapped_column(JSON, default=list)
    entities: Mapped[list[str]] = mapped_column(JSON, default=list)
    product: Mapped[str] = mapped_column(String(32), default="DAY_AHEAD")
    horizon: Mapped[str] = mapped_column(String(16), default="D1")
    hypotheses_to_test: Mapped[list[str]] = mapped_column(JSON, default=list)
    required_evidence: Mapped[list[dict]] = mapped_column(JSON, default=list)
    analyses: Mapped[list[dict]] = mapped_column(JSON, default=list)
    data_quality_requirements: Mapped[dict] = mapped_column(JSON, default=dict)
    statistical_requirements: Mapped[dict] = mapped_column(JSON, default=dict)
    strategy_generation_allowed: Mapped[bool] = mapped_column(default=False)
    stopping_conditions: Mapped[list[str]] = mapped_column(JSON, default=list)
    validation_issues: Mapped[list[dict]] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(32), default="DRAFT")
    created_by: Mapped[str] = mapped_column(String(64), default="agent")
    created_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class AgentResearchFindingRecord(Base):
    __tablename__ = "agent_research_findings"
    __table_args__ = (Index("ix_agent_research_findings_plan", "research_plan_id"),)

    finding_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    research_plan_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    agent_run_id: Mapped[str | None] = mapped_column(
        String(128), ForeignKey("agent_runs.agent_run_id"), nullable=True
    )
    question: Mapped[str] = mapped_column(Text(), nullable=False)
    statistic: Mapped[str] = mapped_column(String(64), nullable=False)
    value: Mapped[str | None] = mapped_column(String(128), nullable=True)
    unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    sample: Mapped[str] = mapped_column(String(64), default="")
    period: Mapped[str] = mapped_column(String(64), default="")
    methodology: Mapped[str] = mapped_column(Text(), default="")
    evidence: Mapped[list[str]] = mapped_column(JSON, default=list)
    limitations: Mapped[list[str]] = mapped_column(JSON, default=list)
    quality_state: Mapped[str] = mapped_column(String(32), default="VERIFIED")
    created_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class AgentResearchBudgetRecord(Base):
    __tablename__ = "agent_research_budgets"

    budget_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    agent_run_id: Mapped[str | None] = mapped_column(
        String(128), ForeignKey("agent_runs.agent_run_id"), nullable=True
    )
    max_hypotheses: Mapped[int] = mapped_column(Integer, default=3)
    max_parameter_variants: Mapped[int] = mapped_column(Integer, default=8)
    max_backtest_runs: Mapped[int] = mapped_column(Integer, default=5)
    max_llm_calls: Mapped[int] = mapped_column(Integer, default=12)
    time_budget_seconds: Mapped[int] = mapped_column(Integer, default=900)
    token_budget: Mapped[int] = mapped_column(Integer, default=100000)
    hypotheses_used: Mapped[int] = mapped_column(Integer, default=0)
    parameter_variants_used: Mapped[int] = mapped_column(Integer, default=0)
    backtest_runs_used: Mapped[int] = mapped_column(Integer, default=0)
    llm_calls_used: Mapped[int] = mapped_column(Integer, default=0)
    tokens_used: Mapped[int] = mapped_column(Integer, default=0)
    selection_criterion: Mapped[str] = mapped_column(
        String(128), default="highest_validated_risk_adjusted_result"
    )
    final_holdout_period: Mapped[dict] = mapped_column(JSON, default=dict)
    final_holdout_inspections: Mapped[int] = mapped_column(Integer, default=0)
    max_final_holdout_inspections: Mapped[int] = mapped_column(Integer, default=1)
    created_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class AgentChallengeReportRecord(Base):
    __tablename__ = "agent_challenge_reports"
    __table_args__ = (Index("ix_agent_challenge_reports_version", "strategy_version_id"),)

    challenge_report_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    agent_run_id: Mapped[str | None] = mapped_column(
        String(128), ForeignKey("agent_runs.agent_run_id"), nullable=True
    )
    strategy_version_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    backtest_run_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    items: Mapped[list[dict]] = mapped_column(JSON, default=list)
    overall_result: Mapped[str] = mapped_column(String(32), default="PASS")
    recommended_follow_up: Mapped[str] = mapped_column(Text(), default="")
    created_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class AgentReviewPackRecord(Base):
    __tablename__ = "agent_review_packs"
    __table_args__ = (Index("ix_agent_review_packs_run", "agent_run_id"),)

    review_pack_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    agent_run_id: Mapped[str | None] = mapped_column(
        String(128), ForeignKey("agent_runs.agent_run_id"), nullable=True
    )
    objective: Mapped[str] = mapped_column(Text(), nullable=False)
    research_plan: Mapped[dict] = mapped_column(JSON, default=dict)
    key_findings: Mapped[list[dict]] = mapped_column(JSON, default=list)
    strategy_specification: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    backtest: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    robustness: Mapped[dict] = mapped_column(JSON, default=dict)
    challenge_report: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    data_provenance: Mapped[list[str]] = mapped_column(JSON, default=list)
    warnings: Mapped[list[str]] = mapped_column(JSON, default=list)
    known_limitations: Mapped[list[str]] = mapped_column(JSON, default=list)
    alternative_hypotheses: Mapped[list[str]] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(32), default="READY_FOR_HUMAN_REVIEW")
    created_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
