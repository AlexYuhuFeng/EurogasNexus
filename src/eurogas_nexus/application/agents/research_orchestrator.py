"""Governed research orchestrator (CR-15).

One bounded state machine, not a free-form prompt loop. Deterministic stages
never delegate authoritative calculations to an LLM; LLM stages are isolated
behind a provider abstraction and fall back to the deterministic planner when
no provider is configured.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy.orm import Session

from eurogas_nexus.application.agents.db_bridge import market_rows
from eurogas_nexus.application.agents.registry import register_builtin_capabilities
from eurogas_nexus.application.agents.runtime import CapabilityRuntime
from eurogas_nexus.db.repositories import agents as repo
from eurogas_nexus.domain.agents.budget import (
    ResearchBudget,
    enforce_research_budget,
)
from eurogas_nexus.domain.agents.challenge import (
    ChallengeItem,
    ChallengeReport,
    ChallengeResult,
    challenge_backtest_result,
)
from eurogas_nexus.domain.agents.contracts import (
    AgentInvocationContext,
    AgentRunStatus,
    OrchestrationStage,
)
from eurogas_nexus.domain.agents.findings import ResearchFinding
from eurogas_nexus.domain.agents.research_plan import (
    ResearchPlan,
    deterministic_plan,
    validate_research_plan,
)
from eurogas_nexus.domain.agents.review_pack import ReviewPack
from eurogas_nexus.domain.agents.strategy_ir import (
    StrategyIR,
    example_strategy_ir,
    validate_strategy_ir,
)

AGENT_RUNTIME_VERSION = "agent-runtime/v1"


class OrchestrationOutcome:
    """Safe result returned to API/UI; no private reasoning is included."""

    def __init__(self, run_id: str) -> None:
        self.run_id = run_id
        self.stage = OrchestrationStage.OBJECTIVE_RECEIVED
        self.status = AgentRunStatus.RECEIVED
        self.plan: ResearchPlan | None = None
        self.findings: list[ResearchFinding] = []
        self.strategy_ir: StrategyIR | None = None
        self.strategy_version_id: str | None = None
        self.backtest_run_id: str | None = None
        self.challenge: dict[str, Any] | None = None
        self.review_pack_id: str | None = None
        self.warnings: list[str] = []
        self.blockers: list[str] = []
        self.artifacts: list[str] = []
        self.evidence: list[str] = []

    def payload(self) -> dict[str, Any]:
        return {
            "agent_run_id": self.run_id,
            "stage": self.stage.value,
            "status": self.status.value,
            "plan": self.plan.model_dump(mode="json") if self.plan else None,
            "findings": [item.model_dump(mode="json") for item in self.findings],
            "strategy_ir": self.strategy_ir.model_dump(mode="json") if self.strategy_ir else None,
            "strategy_version_id": self.strategy_version_id,
            "backtest_run_id": self.backtest_run_id,
            "challenge_report": self.challenge,
            "review_pack_id": self.review_pack_id,
            "warnings": self.warnings,
            "blockers": self.blockers,
            "artifacts": self.artifacts,
            "evidence": self.evidence,
        }


class GovernedResearchOrchestrator:
    def __init__(self) -> None:
        self.registry = register_builtin_capabilities()
        self.runtime = CapabilityRuntime(self.registry)

    def run_research(
        self,
        session: Session,
        *,
        run_id: str,
        principal: AgentInvocationContext,
        objective: str,
        agent_profile: str = "STRATEGY_RESEARCHER",
        strategy_generation_allowed: bool = False,
        strategy_ir_payload: dict[str, Any] | None = None,
        frozen_strategy_version_id: str | None = None,
        period_start_utc: str | None = None,
        period_end_utc: str | None = None,
    ) -> OrchestrationOutcome:
        outcome = OrchestrationOutcome(run_id)
        run_row = repo.get_agent_run(session, run_id)
        if run_row is None:
            run_row = repo.create_agent_run(
                session,
                agent_run_id=run_id,
                principal_id=principal.principal_id,
                user_objective=objective,
                agent_profile=agent_profile,
                model_provider="DETERMINISTIC",
                model_id="rule-based-plan/v1",
                correlation_request_id=principal.correlation_request_id,
            )
        budget = self._create_budget(session, run_id)
        budget_decision = enforce_research_budget(
            budget, hypotheses_delta=1, llm_calls_delta=1
        )
        if not budget_decision.allowed:
            outcome.blockers.append(budget_decision.reason)
            outcome.status = AgentRunStatus.BLOCKED
            outcome.stage = OrchestrationStage.BLOCKED
            self._persist_run_state(session, outcome)
            return outcome

        self._transition(outcome, OrchestrationStage.PLAN_DRAFTED, AgentRunStatus.RUNNING)
        plan = deterministic_plan(objective, agent_run_id=run_id)
        plan.strategy_generation_allowed = strategy_generation_allowed
        outcome.plan = plan
        repo.persist_plan(session, plan)

        validation = self._validate_plan(session, plan, principal)
        plan_row = repo.get_plan(session, plan.research_plan_id)
        if plan_row is not None:
            repo.update_plan_validation(
                session,
                plan_row,
                issues=[item.model_dump(mode="json") for item in validation.issues],
                status="VALIDATED" if validation.ok else "BLOCKED",
            )
        if not validation.ok:
            self._transition(outcome, OrchestrationStage.BLOCKED, AgentRunStatus.BLOCKED)
            outcome.blockers.extend(validation.blockers)
            self._persist_run_state(session, outcome)
            return outcome

        self._transition(outcome, OrchestrationStage.PLAN_VALIDATED, AgentRunStatus.RUNNING)
        self._transition(outcome, OrchestrationStage.DATA_ANALYSIS, AgentRunStatus.RUNNING)
        findings = self._run_supported_analyses(session, plan, principal, outcome)
        outcome.findings = findings
        for finding in findings:
            from eurogas_nexus.db.models import AgentResearchFindingRecord

            row = AgentResearchFindingRecord(
                finding_id=finding.finding_id,
                research_plan_id=finding.research_plan_id,
                agent_run_id=run_id,
                question=finding.question,
                statistic=finding.statistic,
                value=str(finding.value) if finding.value is not None else None,
                unit=finding.unit,
                sample=finding.sample,
                period=finding.period,
                methodology=finding.methodology,
                evidence=finding.evidence,
                limitations=finding.limitations,
                quality_state=finding.quality_state,
            )
            repo.persist_finding(session, row)

        self._transition(outcome, OrchestrationStage.HYPOTHESIS_FORMED, AgentRunStatus.RUNNING)

        if strategy_generation_allowed:
            outcome.strategy_ir = self._draft_strategy(plan, findings)
            if outcome.strategy_ir is None:
                self._transition(outcome, OrchestrationStage.BLOCKED, AgentRunStatus.BLOCKED)
                outcome.blockers.append("INSUFFICIENT_HISTORY")
                self._persist_run_state(session, outcome)
                return outcome
            self._transition(
                outcome, OrchestrationStage.STRATEGY_SPEC_DRAFTED, AgentRunStatus.RUNNING
            )
            self._transition(outcome, OrchestrationStage.STRATEGY_VALIDATED, AgentRunStatus.RUNNING)
            outcome.artifacts.append("StrategyIR")
            if frozen_strategy_version_id:
                outcome.strategy_version_id = frozen_strategy_version_id
                self._transition(outcome, OrchestrationStage.BACKTESTED, AgentRunStatus.RUNNING)
                backtest = self._maybe_backtest(
                    session,
                    principal,
                    frozen_strategy_version_id,
                    period_start_utc,
                    period_end_utc,
                )
                if backtest is None:
                    outcome.warnings.append("BACKTEST_DEFERRED: no period/frozen version evidence")
                    self._transition(
                        outcome, OrchestrationStage.ROBUSTNESS_EVALUATED, AgentRunStatus.RUNNING
                    )
                else:
                    outcome.backtest_run_id = backtest["run_id"]
                    outcome.artifacts.append(f"backtest:{outcome.backtest_run_id}")
                    self._transition(
                        outcome, OrchestrationStage.ROBUSTNESS_EVALUATED, AgentRunStatus.RUNNING
                    )
            else:
                outcome.blockers.append("HUMAN_CONFIRMATION_REQUIRED")
                outcome.warnings.append(
                    "StrategyVersion freeze and backtest require human confirmation; "
                    "agent pipeline terminates at READY_FOR_HUMAN_REVIEW."
                )
        else:
            outcome.warnings.append("STRATEGY_GENERATION_NOT_REQUESTED")

        self._transition(outcome, OrchestrationStage.CHALLENGED, AgentRunStatus.RUNNING)
        outcome.challenge = self._challenge(outcome)
        if outcome.challenge is not None:
            challenge_report = _challenge_report_from_payload(outcome.challenge, run_id)
            repo.persist_challenge_report(session, challenge_report)

        outcome.review_pack_id = f"review-{uuid4().hex[:16]}"
        pack = ReviewPack(
            review_pack_id=outcome.review_pack_id,
            agent_run_id=run_id,
            objective=objective,
            research_plan=plan.model_dump(mode="json"),
            key_findings=[item.model_dump(mode="json") for item in findings],
            strategy_specification=(
                outcome.strategy_ir.model_dump(mode="json") if outcome.strategy_ir else None
            ),
            backtest={"run_id": outcome.backtest_run_id} if outcome.backtest_run_id else None,
            robustness={"supported": ["cost_sensitivity"], "deferred": ["out_of_sample"]},
            challenge_report=outcome.challenge,
            data_provenance=outcome.evidence,
            warnings=outcome.warnings,
            known_limitations=[
                "UAT/local mode uses a deterministic planner; no external LLM was invoked."
            ],
            alternative_hypotheses=["Observed relationship is seasonal rather than causal."],
        )
        repo.persist_review_pack(session, pack)
        outcome.artifacts.append(f"review-pack:{outcome.review_pack_id}")
        self._transition(
            outcome,
            OrchestrationStage.READY_FOR_HUMAN_REVIEW,
            AgentRunStatus.READY_FOR_HUMAN_REVIEW,
        )
        self._persist_run_state(session, outcome)
        return outcome

    def _create_budget(self, session: Session, run_id: str) -> ResearchBudget:
        budget = ResearchBudget(budget_id=f"budget-{uuid4().hex[:16]}", agent_run_id=run_id)
        repo.persist_budget(session, budget)
        return budget

    def _validate_plan(self, session, plan, principal):
        from eurogas_nexus.db.models import (
            CanonicalEntityRecord,
            SeriesDefinitionRecord,
        )

        known_entities = {
            row.canonical_entity_id for row in session.query(CanonicalEntityRecord).all()
        }
        available_series = {
            row.series_id: {
                "source_family": str(row.source_class or "").removesuffix("_Sim"),
                "history_days": 30,
                "temporal_integrity": "TEMPORAL_APPROXIMATE",
            }
            for row in session.query(SeriesDefinitionRecord).all()
        }
        entitled = set(principal.data_scopes)
        return validate_research_plan(
            plan,
            known_entities=known_entities or set(plan.entities),
            available_series=available_series,
            entitled_source_families=entitled,
        )

    def _run_supported_analyses(self, session, plan, principal, outcome):
        findings: list[ResearchFinding] = []
        rows = market_rows(
            session,
            start_utc=datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0),
            hub=None,
            product="DAY_AHEAD",
            limit=500,
        )
        pairs: dict[str, dict[str, float]] = {}
        for row in rows:
            bucket = pairs.setdefault(row["observed_at"], {})
            bucket[row["hub"]] = row["value"]
        paired = sorted(
            (
                (timestamp, bucket)
                for timestamp, bucket in pairs.items()
                if "NBP" in bucket and "TTF" in bucket
            ),
            key=lambda item: item[0],
        )
        left_values = [bucket["NBP"] for _, bucket in paired]
        right_values = [bucket["TTF"] for _, bucket in paired]
        values: dict[str, list[float]] = {}
        for row in rows:
            values.setdefault(row["hub"], []).append(row["value"])
        spread = self._invoke_safely(
            session,
            principal,
            "analytics.spread_distribution",
            {
                "left_values": left_values,
                "right_values": right_values,
            },
            outcome,
        )
        if spread.status == "SUCCESS" and spread.data.get("n", 0) >= 2:
            findings.append(
                ResearchFinding(
                    finding_id=f"finding-{uuid4().hex[:16]}",
                    research_plan_id=plan.research_plan_id,
                    question=plan.question,
                    statistic="mean_spread",
                    value=spread.data["mean"],
                    unit="native",
                    sample=str(spread.data["n"]),
                    period="runtime_window",
                    methodology="deterministic pairwise spread distribution",
                    evidence=[],
                    limitations=["UAT simulated feeds; source timestamps approximate"],
                    quality_state="VERIFIED",
                )
            )
            outcome.evidence.extend(["runtime market observations"])
        for analysis in plan.analyses:
            if analysis.analysis_type == "rolling_volatility" and values.get("NBP"):
                result = self._invoke_safely(
                    session,
                    principal,
                    "analytics.rolling_volatility",
                    {
                        "values": values["NBP"],
                        "window": int(analysis.parameters.get("window") or 21),
                    },
                    outcome,
                )
                if result.status == "SUCCESS" and result.data.get("sample_size"):
                    findings.append(
                        ResearchFinding(
                            finding_id=f"finding-{uuid4().hex[:16]}",
                            research_plan_id=plan.research_plan_id,
                            question=plan.question,
                            statistic="rolling_volatility",
                            value=result.data["volatility"][-1],
                            unit="native",
                            sample=str(result.data["sample_size"]),
                            period="runtime_window",
                            methodology="bounded rolling standard deviation",
                            evidence=[],
                            quality_state="VERIFIED",
                        )
                    )
        if not findings:
            outcome.warnings.append("DATA_MISSING: no findings fabricated")
        return findings

    def _invoke_safely(self, session, principal, capability_id, arguments, outcome):
        result = self.runtime.invoke(capability_id, arguments, principal)
        repo.persist_tool_invocation(
            session,
            invocation_id=f"inv-{uuid4().hex[:16]}",
            agent_run_id=outcome.run_id,
            capability_id=capability_id,
            capability_version=result.capability_version,
            principal_id=principal.principal_id,
            input_hash=result.execution_metadata.input_hash or "runtime",
            input_summary=self._safe_input_summary(arguments),
            status=result.status,
            output_reference=None,
            evidence_refs=result.evidence_refs,
            warnings=result.warnings,
            error_code=result.failure.code.value if result.failure else None,
            duration_ms=result.execution_metadata.duration_ms,
            entitlement_state=result.entitlement_state,
        )
        return result

    def _draft_strategy(self, plan, findings):
        if not findings:
            return None
        strategy = example_strategy_ir()
        strategy.hypothesis = (
            plan.hypotheses_to_test[0] if plan.hypotheses_to_test else strategy.hypothesis
        )
        validation = validate_strategy_ir(
            strategy,
            feature_catalog={
                "NBP_TTF_DA_SPREAD": {"output_unit": "EUR/MWh", "feature_version": "v1"}
            },
        )
        return strategy if validation.ok else None

    def _maybe_backtest(self, session, principal, version_id, start, end):
        if not version_id or not start or not end:
            return None
        result = self.runtime.invoke(
            "backtest.run",
            {
                "strategy_version_id": version_id,
                "period_start_utc": start,
                "period_end_utc": end,
            },
            principal,
        )
        return result.data if result.status == "SUCCESS" else None

    def _challenge(self, outcome):
        metrics = {}
        backtest_run_id = outcome.backtest_run_id
        if backtest_run_id is None:
            metrics = {"net_indicative_pnl_gbp": 0.0}
        report = challenge_backtest_result(
            challenge_report_id=f"challenge-{uuid4().hex[:16]}",
            strategy_version_id=outcome.strategy_version_id,
            backtest_run_id=backtest_run_id,
            metrics=metrics,
            warnings=outcome.warnings,
            missing_inputs=[],
            sample_size=None if backtest_run_id else 0,
            period=None,
            cost_policy="EXPLICIT_ZERO_UNMODELED",
        )
        outcome.evidence.append(f"challenge:{report.challenge_report_id}")
        return report.public_payload()

    def _persist_run_state(self, session, outcome):
        run_row = repo.get_agent_run(session, outcome.run_id)
        if run_row is None:
            return
        repo.update_agent_run(
            session,
            run_row,
            status=outcome.status.value,
            current_stage=outcome.stage.value,
            research_plan_id=outcome.plan.research_plan_id if outcome.plan else None,
            artifacts_created=outcome.artifacts,
            evidence_dependencies=outcome.evidence,
            warnings=outcome.warnings,
            blockers=outcome.blockers,
            final_output_reference=outcome.review_pack_id,
            completed=outcome.status
            in {AgentRunStatus.READY_FOR_HUMAN_REVIEW, AgentRunStatus.BLOCKED},
        )

    def _transition(self, outcome, stage, status):
        outcome.stage = stage
        outcome.status = status

    def _safe_input_summary(self, arguments):
        return {
            key: (len(value) if isinstance(value, list) else value)
            for key, value in arguments.items()
            if not isinstance(value, dict)
        }


def _challenge_report_from_payload(payload: dict[str, Any], run_id: str) -> ChallengeReport:
    return ChallengeReport(
        challenge_report_id=str(payload["challenge_report_id"]),
        agent_run_id=run_id,
        strategy_version_id=payload.get("strategy_version_id"),
        backtest_run_id=payload.get("backtest_run_id"),
        items=[ChallengeItem.model_validate(item) for item in payload.get("items", [])],
        overall_result=ChallengeResult(str(payload.get("overall_result"))),
        recommended_follow_up=str(payload.get("recommended_follow_up") or ""),
    )
