"""Persistence for agent runs, tool invocations, and research artifacts.

Read helpers return persisted CR-15 artifacts (plan, findings, StrategyIR,
validation, challenge report, review pack) with their identifiers, lineage,
entitlement state, and timestamps so the existing run surface can replay a
governed research run. Hidden reasoning is never stored or returned.
"""

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
    SeriesDefinitionRecord,
    StrategyRunRecord,
)
from eurogas_nexus.domain.agents.budget import ResearchBudget
from eurogas_nexus.domain.agents.challenge import ChallengeReport
from eurogas_nexus.domain.agents.research_plan import ResearchPlan
from eurogas_nexus.domain.agents.review_pack import ReviewPack
from eurogas_nexus.domain.agents.strategy_ir import (
    AGENT_RESEARCH_FEATURE_CATALOG_ID,
    StrategyIR,
    agent_research_feature_catalog,
    validate_strategy_ir,
)
from eurogas_nexus.domain.ontology.vocabulary import ReviewEntityType
from eurogas_nexus.domain.strategy_lab.registry import canonical_content_hash

#: Ordered CR-15 research artifact chain, matching the governed stage order.
ARTIFACT_CHAIN_ORDER: tuple[str, ...] = (
    "research_plan",
    "findings",
    "strategy_ir",
    "validation",
    "challenge_report",
    "review_pack",
)

#: Governed operation identifier rendered for each artifact of the chain.
ARTIFACT_OPERATION_IDS: dict[str, str] = {
    "research_plan": "agent.research.plan",
    "findings": "agent.research.findings",
    "strategy_ir": "agent.research.strategy_ir",
    "validation": "agent.research.validation",
    "challenge_report": "agent.research.challenge",
    "review_pack": "agent.research.review_pack",
}

#: Orchestration stage that produces each artifact (existing stage vocabulary).
ARTIFACT_STAGES: dict[str, str] = {
    "research_plan": "PLAN_DRAFTED",
    "findings": "DATA_ANALYSIS",
    "strategy_ir": "STRATEGY_SPEC_DRAFTED",
    "validation": "PLAN_VALIDATED",
    "challenge_report": "CHALLENGED",
    "review_pack": "READY_FOR_HUMAN_REVIEW",
}

#: Review entity kind a human uses to confirm one persisted agent review pack.
REVIEW_PACK_ENTITY_TYPE = ReviewEntityType.AGENT_REVIEW_PACK.value


def _now() -> datetime:
    return datetime.now(UTC)


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _digest(value: Any) -> str:
    return canonical_content_hash(value).removeprefix("sha256:")


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


def get_plan_for_run(session: Session, agent_run_id: str) -> AgentResearchPlanRecord | None:
    """Return the persisted research plan of one agent run, if any."""

    row = session.scalars(
        select(AgentResearchPlanRecord)
        .where(AgentResearchPlanRecord.agent_run_id == agent_run_id)
        .order_by(AgentResearchPlanRecord.created_at_utc.desc())
        .limit(1)
    ).first()
    if row is not None:
        return row
    run = session.get(AgentRunRecord, agent_run_id)
    if run is not None and run.research_plan_id:
        return get_plan(session, run.research_plan_id)
    return None


def list_findings_for_run(
    session: Session, agent_run_id: str, *, limit: int = 500
) -> list[AgentResearchFindingRecord]:
    """Return the persisted research findings of one agent run, oldest first."""

    return list(
        session.scalars(
            select(AgentResearchFindingRecord)
            .where(AgentResearchFindingRecord.agent_run_id == agent_run_id)
            .order_by(AgentResearchFindingRecord.created_at_utc.asc())
            .limit(max(1, min(limit, 2000)))
        )
    )


def get_challenge_report_for_run(
    session: Session, agent_run_id: str
) -> AgentChallengeReportRecord | None:
    """Return the latest persisted challenge report of one agent run, if any."""

    return session.scalars(
        select(AgentChallengeReportRecord)
        .where(AgentChallengeReportRecord.agent_run_id == agent_run_id)
        .order_by(AgentChallengeReportRecord.created_at_utc.desc())
        .limit(1)
    ).first()


def get_review_pack_for_run(
    session: Session, agent_run_id: str
) -> AgentReviewPackRecord | None:
    """Return the latest persisted review pack of one agent run, if any."""

    return session.scalars(
        select(AgentReviewPackRecord)
        .where(AgentReviewPackRecord.agent_run_id == agent_run_id)
        .order_by(AgentReviewPackRecord.created_at_utc.desc())
        .limit(1)
    ).first()


def list_review_confirmation_decisions(session: Session, review_pack_id: str) -> list[dict]:
    """Return the human review decisions recorded against one review pack."""

    from eurogas_nexus.db.repositories.review import list_review_decisions

    return list_review_decisions(
        session,
        entity_type=REVIEW_PACK_ENTITY_TYPE,
        entity_id=review_pack_id,
        limit=100,
    )


def load_run_artifacts(session: Session, row: AgentRunRecord) -> dict[str, Any]:
    """Load every persisted CR-15 artifact row belonging to one agent run.

    The StrategyIR has no table of its own: the persisted copy of the reviewed
    specification lives on the review pack, so it is read from there.
    """

    pack = get_review_pack_for_run(session, row.agent_run_id)
    return {
        "plan": get_plan_for_run(session, row.agent_run_id),
        "findings": list_findings_for_run(session, row.agent_run_id),
        "challenge_report": get_challenge_report_for_run(session, row.agent_run_id),
        "review_pack": pack,
        "strategy_ir": (pack.strategy_specification if pack is not None else None),
    }


def artifact_chain_summary(session: Session, row: AgentRunRecord) -> dict[str, Any]:
    """Return the presence/identity summary of one run's artifact chain."""

    artifacts = load_run_artifacts(session, row)
    presence = _artifact_presence(artifacts)
    return {
        "order": list(ARTIFACT_CHAIN_ORDER),
        "present": [name for name in ARTIFACT_CHAIN_ORDER if presence[name]],
        "missing": [name for name in ARTIFACT_CHAIN_ORDER if not presence[name]],
        "complete": all(presence.values()),
        "artifact_ids": _artifact_identifiers(row, artifacts),
    }


def _artifact_presence(artifacts: dict[str, Any]) -> dict[str, bool]:
    """Single source of truth for which chain artifacts are persisted."""

    plan = artifacts["plan"]
    return {
        "research_plan": plan is not None,
        "findings": bool(artifacts["findings"]),
        "strategy_ir": bool(artifacts["strategy_ir"]),
        "validation": plan is not None,
        "challenge_report": artifacts["challenge_report"] is not None,
        "review_pack": artifacts["review_pack"] is not None,
    }


def replay_payload(session: Session, row: AgentRunRecord) -> dict[str, Any]:
    """Return the observable replay payload for one agent run.

    The payload carries the whole persisted CR-15 artifact chain - plan,
    findings, StrategyIR, validation, challenge report, review pack - with each
    artifact's operation/artifact identifier, fixture and replay identity,
    lineage, entitlement state, and timestamps. Hidden reasoning and execution
    semantics are never included: ``hidden_chain_of_thought`` stays ``None``.
    """

    invocations = list_tool_invocations(session, row.agent_run_id)
    artifacts, chain = _artifact_chain(session, row, invocations)
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
        "review_entity_type": REVIEW_PACK_ENTITY_TYPE,
        "fixture": _fixture_identity(row, invocations),
        "artifact_chain": chain,
        "artifacts": artifacts,
        "tool_invocations": [_invocation_payload(item) for item in invocations],
        "hidden_chain_of_thought": None,
    }


def _invocation_payload(item: AgentToolInvocationRecord) -> dict[str, Any]:
    return {
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


def _artifact_chain(
    session: Session,
    row: AgentRunRecord,
    invocations: list[AgentToolInvocationRecord],
) -> tuple[dict[str, Any], dict[str, Any]]:
    artifacts = load_run_artifacts(session, row)
    fixture = _fixture_identity(row, invocations)
    rights = _rights_block(row, invocations)
    lineage = _lineage_block(session, row, artifacts, invocations)
    plan = artifacts["plan"]
    findings = artifacts["findings"]
    challenge = artifacts["challenge_report"]
    pack = artifacts["review_pack"]
    strategy_spec = artifacts["strategy_ir"]

    plan_id = plan.research_plan_id if plan is not None else row.research_plan_id
    finding_ids = [item.finding_id for item in findings]
    strategy_ir_id = (
        f"strategy-ir-{_digest(strategy_spec)[:20]}" if strategy_spec else None
    )
    validation_id = f"validation:{plan_id}" if plan_id else None
    findings_id = f"findings:{plan_id}" if (plan_id and finding_ids) else None

    plan_payload = _plan_payload(plan) if plan is not None else None
    findings_payload = [_finding_payload(item) for item in findings] if findings else None
    validation_payload = _validation_payload(row, plan, strategy_spec) if plan_id else None
    challenge_payload = _challenge_payload(challenge) if challenge is not None else None
    pack_payload = _review_pack_payload(pack) if pack is not None else None
    if pack_payload is not None:
        pack_payload["human_confirmation"] = {
            "entity_type": REVIEW_PACK_ENTITY_TYPE,
            "entity_id": pack.review_pack_id,
            "decisions": list_review_confirmation_decisions(session, pack.review_pack_id),
        }

    entries = {
        "research_plan": {
            "artifact_id": plan_id,
            "artifact_ids": [plan_id] if plan_id else [],
            "payload": plan_payload,
            "created_at": plan.created_at_utc if plan is not None else None,
            "lineage": {**lineage, "upstream_artifact_ids": []},
        },
        "findings": {
            "artifact_id": findings_id,
            "artifact_ids": finding_ids,
            "payload": findings_payload,
            "created_at": findings[0].created_at_utc if findings else None,
            "lineage": {
                **lineage,
                "upstream_artifact_ids": [plan_id] if plan_id else [],
                "producing_invocation_ids": [
                    item.invocation_id
                    for item in invocations
                    if item.capability_id.startswith("analytics.")
                ],
            },
        },
        "strategy_ir": {
            "artifact_id": strategy_ir_id,
            "artifact_ids": [strategy_ir_id] if strategy_ir_id else [],
            "payload": strategy_spec if strategy_spec else None,
            "created_at": pack.created_at_utc if (pack is not None and strategy_spec) else None,
            "lineage": {
                **lineage,
                "upstream_artifact_ids": [
                    item for item in [plan_id, *finding_ids] if item
                ],
            },
        },
        "validation": {
            "artifact_id": validation_id,
            "artifact_ids": [validation_id] if validation_id else [],
            "payload": validation_payload,
            "created_at": plan.created_at_utc if plan is not None else None,
            "lineage": {
                **lineage,
                "upstream_artifact_ids": [
                    item for item in [plan_id, strategy_ir_id] if item
                ],
            },
        },
        "challenge_report": {
            "artifact_id": challenge.challenge_report_id if challenge is not None else None,
            "artifact_ids": [challenge.challenge_report_id] if challenge is not None else [],
            "payload": challenge_payload,
            "created_at": challenge.created_at_utc if challenge is not None else None,
            "lineage": {
                **lineage,
                "upstream_artifact_ids": [
                    item
                    for item in [
                        plan_id,
                        strategy_ir_id,
                        challenge.strategy_version_id if challenge is not None else None,
                        challenge.backtest_run_id if challenge is not None else None,
                    ]
                    if item
                ],
            },
        },
        "review_pack": {
            "artifact_id": pack.review_pack_id if pack is not None else None,
            "artifact_ids": [pack.review_pack_id] if pack is not None else [],
            "payload": pack_payload,
            "created_at": pack.created_at_utc if pack is not None else None,
            "lineage": {
                **lineage,
                "upstream_artifact_ids": [
                    item
                    for item in [
                        plan_id,
                        *finding_ids,
                        strategy_ir_id,
                        challenge.challenge_report_id if challenge is not None else None,
                    ]
                    if item
                ],
            },
        },
    }

    presence = _artifact_presence(artifacts)
    envelopes = {
        name: _artifact_envelope(
            artifact_type=name,
            run=row,
            fixture=fixture,
            rights=rights,
            **entry,
        )
        for name, entry in entries.items()
    }
    for name, envelope in envelopes.items():
        envelope["present"] = presence[name]
    summaries = {
        name: {
            "artifact_id": envelope["artifact_id"],
            "artifact_ids": envelope["artifact_ids"],
            "present": envelope["present"],
            "content_hash": envelope["replay_identity"]["content_hash"],
        }
        for name, envelope in envelopes.items()
    }
    summary = {
        "order": list(ARTIFACT_CHAIN_ORDER),
        "present": [
            name for name in ARTIFACT_CHAIN_ORDER if envelopes[name]["present"]
        ],
        "missing": [
            name for name in ARTIFACT_CHAIN_ORDER if not envelopes[name]["present"]
        ],
        "artifact_ids": _artifact_identifiers(row, artifacts),
    }
    summary["complete"] = not summary["missing"]
    summary["chain_hash"] = canonical_content_hash(summaries)
    return envelopes, summary


def _artifact_envelope(
    *,
    artifact_type: str,
    run: AgentRunRecord,
    fixture: dict[str, Any],
    rights: dict[str, Any],
    artifact_id: str | None,
    artifact_ids: list[str],
    payload: Any,
    created_at: datetime | None,
    lineage: dict[str, Any],
) -> dict[str, Any]:
    content_hash = canonical_content_hash(
        {
            "artifact_type": artifact_type,
            "artifact_id": artifact_id,
            "artifact_ids": artifact_ids,
            "payload": payload,
        }
    )
    return {
        "artifact_type": artifact_type,
        "operation_id": ARTIFACT_OPERATION_IDS[artifact_type],
        "stage": ARTIFACT_STAGES[artifact_type],
        "present": payload is not None,
        "artifact_id": artifact_id,
        "artifact_ids": artifact_ids,
        "agent_run_id": run.agent_run_id,
        "fixture": fixture,
        "replay_identity": {
            "replay_id": f"replay-{_digest(content_hash)[:20]}",
            "content_hash": content_hash,
            "deterministic": True,
        },
        "lineage": lineage,
        "rights": rights,
        "timestamps": {
            "created_at": _iso(created_at),
            "run_started_at": _iso(run.started_at_utc),
            "run_completed_at": _iso(run.completed_at_utc),
        },
        "payload": payload,
        "hidden_chain_of_thought": None,
    }


def _artifact_identifiers(row: AgentRunRecord, artifacts: dict[str, Any]) -> dict[str, Any]:
    plan = artifacts["plan"]
    findings = artifacts["findings"]
    challenge = artifacts["challenge_report"]
    pack = artifacts["review_pack"]
    strategy_spec = artifacts["strategy_ir"]
    plan_id = plan.research_plan_id if plan is not None else row.research_plan_id
    strategy_ir_id = f"strategy-ir-{_digest(strategy_spec)[:20]}" if strategy_spec else None
    return {
        "research_plan": [plan_id] if plan_id else [],
        "findings": [item.finding_id for item in findings],
        "strategy_ir": [strategy_ir_id] if strategy_ir_id else [],
        "validation": [f"validation:{plan_id}"] if plan_id else [],
        "challenge_report": (
            [challenge.challenge_report_id] if challenge is not None else []
        ),
        "review_pack": [pack.review_pack_id] if pack is not None else [],
    }


def _fixture_identity(
    row: AgentRunRecord, invocations: list[AgentToolInvocationRecord]
) -> dict[str, Any]:
    """Identify the frozen inputs one run was produced from."""

    identity = canonical_content_hash(
        {
            "agent_run_id": row.agent_run_id,
            "principal_id": row.principal_id,
            "agent_profile": row.agent_profile,
            "model_provider": row.model_provider,
            "model_id": row.model_id,
            "user_objective": row.user_objective,
            "inputs": [
                {
                    "capability_id": item.capability_id,
                    "capability_version": item.capability_version,
                    "input_hash": item.input_hash,
                }
                for item in invocations
            ],
        }
    )
    return {
        "fixture_id": f"fixture-{_digest(identity)[:20]}",
        "fixture_kind": "PERSISTED_RUN_INPUTS",
        "evidence_refs": sorted(
            {ref for item in invocations for ref in (item.evidence_refs or [])}
        ),
        "tool_invocation_ids": [item.invocation_id for item in invocations],
        "deterministic_model": {
            "model_provider": row.model_provider,
            "model_id": row.model_id,
        },
    }


def _rights_block(
    row: AgentRunRecord, invocations: list[AgentToolInvocationRecord]
) -> dict[str, Any]:
    """Aggregate the persisted entitlement state seen while producing artifacts.

    Aggregation fails closed: any denied invocation marks the whole run DENIED.
    """

    states = sorted({str(item.entitlement_state or "NOT_APPLICABLE") for item in invocations})
    if "DENIED" in states:
        state = "DENIED"
    elif not states:
        state = "NOT_APPLICABLE"
    elif len(states) == 1:
        state = states[0]
    else:
        state = "MIXED"
    return {
        "entitlement_state": state,
        "entitlement_states": states,
        "principal_id": row.principal_id,
        "evaluated_invocation_ids": [item.invocation_id for item in invocations],
        "policy_boundary": "CapabilityRuntime",
    }


def _lineage_block(
    session: Session,
    row: AgentRunRecord,
    artifacts: dict[str, Any],
    invocations: list[AgentToolInvocationRecord],
) -> dict[str, Any]:
    """Describe which sources and snapshots produced the run's artifacts."""

    plan = artifacts["plan"]
    series_ids = _plan_series_ids(plan)
    snapshot_ids = set()
    source_references: set[str] = set()
    for item in invocations:
        for key, value in (item.input_summary or {}).items():
            if isinstance(value, str) and value and "snapshot_id" in key:
                snapshot_ids.add(value)
        if item.output_reference and "snapshot" in item.output_reference:
            snapshot_ids.add(item.output_reference)
    pack = artifacts["review_pack"]
    backtest_run_id = None
    if pack is not None and isinstance(pack.backtest, dict):
        backtest_run_id = pack.backtest.get("run_id")
    challenge = artifacts["challenge_report"]
    if backtest_run_id is None and challenge is not None:
        backtest_run_id = challenge.backtest_run_id
    if backtest_run_id:
        strategy_run = session.get(StrategyRunRecord, str(backtest_run_id))
        if strategy_run is not None:
            if strategy_run.dataset_snapshot_id:
                snapshot_ids.add(strategy_run.dataset_snapshot_id)
            source_references.update(str(str(item)) for item in (strategy_run.source_refs or []))
    return {
        "upstream_artifact_ids": [],
        "producing_invocation_ids": [],
        "source_families": _series_source_families(session, series_ids),
        "series_ids": series_ids,
        "snapshot_ids": sorted(snapshot_ids),
        "source_references": sorted(source_references),
        "evidence_dependencies": list(row.evidence_dependencies or []),
    }


def _plan_series_ids(plan: AgentResearchPlanRecord | None) -> list[str]:
    if plan is None:
        return []
    series: list[str] = []
    for requirement in plan.required_evidence or []:
        if isinstance(requirement, dict) and requirement.get("series_id"):
            series.append(str(requirement["series_id"]))
    for analysis in plan.analyses or []:
        if isinstance(analysis, dict):
            series.extend(str(item) for item in (analysis.get("input_series") or []))
    return sorted(set(series))


def _series_source_families(session: Session, series_ids: list[str]) -> list[str]:
    if not series_ids:
        return []
    rows = session.scalars(
        select(SeriesDefinitionRecord.source_class).where(
            SeriesDefinitionRecord.series_id.in_(series_ids)
        )
    ).all()
    return sorted({str(value) for value in rows if value})


def _plan_payload(row: AgentResearchPlanRecord) -> dict[str, Any]:
    return {
        "research_plan_id": row.research_plan_id,
        "agent_run_id": row.agent_run_id,
        "objective": row.objective,
        "question": row.question,
        "market_scope": row.market_scope,
        "entities": row.entities,
        "product": row.product,
        "horizon": row.horizon,
        "hypotheses_to_test": row.hypotheses_to_test,
        "required_evidence": row.required_evidence,
        "analyses": row.analyses,
        "data_quality_requirements": row.data_quality_requirements,
        "statistical_requirements": row.statistical_requirements,
        "strategy_generation_allowed": row.strategy_generation_allowed,
        "stopping_conditions": row.stopping_conditions,
        "status": row.status,
        "created_by": row.created_by,
        "created_at": _iso(row.created_at_utc),
    }


def _finding_payload(row: AgentResearchFindingRecord) -> dict[str, Any]:
    return {
        "finding_id": row.finding_id,
        "research_plan_id": row.research_plan_id,
        "agent_run_id": row.agent_run_id,
        "question": row.question,
        "statistic": row.statistic,
        "value": row.value,
        "unit": row.unit,
        "sample": row.sample,
        "period": row.period,
        "methodology": row.methodology,
        "evidence": row.evidence,
        "limitations": row.limitations,
        "quality_state": row.quality_state,
        "created_at": _iso(row.created_at_utc),
    }


def _validation_payload(
    run: AgentRunRecord,
    plan: AgentResearchPlanRecord | None,
    strategy_spec: dict[str, Any] | None,
) -> dict[str, Any]:
    """Return persisted plan validation plus the strategy-IR validation view.

    Plan validation issues are persisted facts. The StrategyIR is re-validated
    on read from the persisted specification because only a passing IR is ever
    persisted; the derived view is labelled as recomputed and never treated as
    stored evidence.
    """

    strategy_validation: dict[str, Any] | None = None
    if strategy_spec:
        try:
            parsed = StrategyIR.model_validate(strategy_spec)
            result = validate_strategy_ir(
                parsed, feature_catalog=agent_research_feature_catalog()
            )
            issues = [item.model_dump(mode="json") for item in result.issues]
            strategy_validation = {"ok": result.ok, "issues": issues}
        except (ValueError, TypeError):
            strategy_validation = {
                "ok": False,
                "issues": [
                    {
                        "code": "STRATEGY_INVALID",
                        "detail": "persisted StrategyIR payload cannot be re-validated",
                        "field": None,
                    }
                ],
            }
    return {
        "plan_id": plan.research_plan_id if plan is not None else None,
        "plan_status": plan.status if plan is not None else None,
        "plan_validation_issues": list(plan.validation_issues or []) if plan is not None else [],
        "plan_validation_source": (
            "persisted:agent_research_plans.validation_issues"
            if plan is not None
            else "not_applicable"
        ),
        "strategy_ir_validation": strategy_validation,
        "strategy_ir_validation_source": (
            "recomputed:validate_strategy_ir" if strategy_spec else "not_applicable"
        ),
        "feature_catalog_id": AGENT_RESEARCH_FEATURE_CATALOG_ID,
        "run_blockers": list(run.blockers or []),
        "run_warnings": list(run.warnings or []),
    }


def _challenge_payload(row: AgentChallengeReportRecord) -> dict[str, Any]:
    return {
        "challenge_report_id": row.challenge_report_id,
        "agent_run_id": row.agent_run_id,
        "strategy_version_id": row.strategy_version_id,
        "backtest_run_id": row.backtest_run_id,
        "items": row.items,
        "overall_result": row.overall_result,
        "recommended_follow_up": row.recommended_follow_up,
        "created_at": _iso(row.created_at_utc),
    }


def _review_pack_payload(row: AgentReviewPackRecord) -> dict[str, Any]:
    return {
        "review_pack_id": row.review_pack_id,
        "agent_run_id": row.agent_run_id,
        "objective": row.objective,
        "research_plan": row.research_plan,
        "key_findings": row.key_findings,
        "strategy_specification": row.strategy_specification,
        "backtest": row.backtest,
        "robustness": row.robustness,
        "challenge_report": row.challenge_report,
        "data_provenance": row.data_provenance,
        "warnings": row.warnings,
        "known_limitations": row.known_limitations,
        "alternative_hypotheses": row.alternative_hypotheses,
        "status": row.status,
        "created_at": _iso(row.created_at_utc),
    }
