"""Agent-native capability and research orchestration API (CR-15).

The capability invoke endpoint is a governed semantic RPC, not a generic
unrestricted remote procedure endpoint: every call passes the authenticated
principal through the CapabilityRuntime permission/entitlement boundary.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from eurogas_nexus.application.agents.registry import register_builtin_capabilities
from eurogas_nexus.application.agents.runtime import CapabilityRuntime
from eurogas_nexus.domain.agents.contracts import (
    AgentInvocationContext,
)
from eurogas_nexus.domain.agents.research_plan import (
    ResearchPlan,
    validate_research_plan,
)
from eurogas_nexus.domain.agents.strategy_ir import (
    compile_strategy_ir,
    validate_strategy_ir,
)

router = APIRouter(tags=["agents"])


class CapabilityInvokeRequest(BaseModel):
    arguments: dict[str, Any] = Field(default_factory=dict)
    human_confirmation: bool = False
    confirmation_note: str = Field(default="", max_length=500)


class ResearchRunRequest(BaseModel):
    objective: str = Field(min_length=8, max_length=4000)
    agent_profile: str = Field(default="STRATEGY_RESEARCHER", max_length=32)
    strategy_generation_allowed: bool = False
    strategy_ir: dict[str, Any] | None = None
    frozen_strategy_version_id: str | None = Field(default=None, max_length=128)
    period_start_utc: str | None = None
    period_end_utc: str | None = None


class PlanValidateRequest(BaseModel):
    plan: ResearchPlan


def _env(data: object, request: Request, *, source: str, warnings: list[str] | None = None) -> dict:
    return {
        "data": data,
        "meta": {
            "research_only": True,
            "human_review_required": True,
            "source_references": [source],
            "warnings": warnings or [],
        },
    }


def _registry():
    return register_builtin_capabilities()


def _runtime() -> CapabilityRuntime:
    return CapabilityRuntime(_registry())


def _principal(request: Request) -> AgentInvocationContext:
    identity = getattr(request.state, "identity", None)
    if identity is None:
        return AgentInvocationContext(
            principal_id="service:public-api",
            role="ANALYST",
            roles=["ANALYST"],
            data_scopes=["*"],
        )
    return AgentInvocationContext(
        principal_id=identity.principal_id,
        role=identity.role,
        roles=list(identity.roles or [identity.role]),
        data_scopes=list(identity.data_scopes or []),
        correlation_request_id=getattr(request.state, "request_id", None),
    )


def _db_configured() -> bool:
    from eurogas_nexus.db.session import resolve_database_url

    return resolve_database_url() is not None


def _session():
    if not _db_configured():
        raise HTTPException(
            status_code=503,
            detail="Runtime PostgreSQL is required for agent research persistence.",
        )
    from eurogas_nexus.db.session import get_session_factory

    return get_session_factory()()


@router.get("/api/capabilities")
def list_capabilities(
    request: Request,
    domain: str | None = Query(default=None),
) -> dict:
    definitions = _registry().list_definitions()
    if domain:
        definitions = [item for item in definitions if item.domain.value == domain]
    return _env(
        [item.public_metadata() for item in definitions],
        request,
        source="domain-contract",
    )


@router.get("/api/capabilities/search")
def search_capabilities(
    request: Request,
    q: str = Query(default="", max_length=120),
) -> dict:
    return _env(
        [item.public_metadata() for item in _registry().search(q)],
        request,
        source="domain-contract",
    )


@router.get("/api/capabilities/{capability_id}")
def describe_capability(capability_id: str, request: Request) -> dict:
    definition = _registry().get(capability_id)
    if definition is None:
        raise HTTPException(status_code=404, detail=f"Unknown capability: {capability_id}")
    return _env(definition.public_metadata(), request, source="domain-contract")


@router.post("/api/capabilities/{capability_id}/invoke")
def invoke_capability(
    capability_id: str,
    body: CapabilityInvokeRequest,
    request: Request,
) -> dict:
    principal = _principal(request)
    result = _runtime().invoke(capability_id, body.arguments, principal)
    if result.status == "SUCCESS":
        return _env(result.model_dump(mode="json"), request, source="capability-runtime")
    return _env(
        result.model_dump(mode="json"),
        request,
        source="capability-runtime",
        warnings=result.warnings,
    )


@router.get("/api/agent/profiles")
def list_agent_profiles(request: Request) -> dict:
    from eurogas_nexus.domain.agents.contracts import DEFAULT_AGENT_PROFILES

    return _env(
        [item.model_dump(mode="json") for item in DEFAULT_AGENT_PROFILES],
        request,
        source="domain-contract",
    )


@router.post("/api/agent/research")
def run_research(body: ResearchRunRequest, request: Request) -> dict:
    from eurogas_nexus.application.agents.research_orchestrator import (
        GovernedResearchOrchestrator,
    )

    principal = _principal(request)
    run_id = f"agent-run-{uuid4().hex[:20]}"
    with _session() as session:
        orchestrator = GovernedResearchOrchestrator()
        outcome = orchestrator.run_research(
            session,
            run_id=run_id,
            principal=principal,
            objective=body.objective,
            agent_profile=body.agent_profile,
            strategy_generation_allowed=body.strategy_generation_allowed,
            strategy_ir_payload=body.strategy_ir,
            frozen_strategy_version_id=body.frozen_strategy_version_id,
            period_start_utc=body.period_start_utc,
            period_end_utc=body.period_end_utc,
        )
        session.commit()
    return _env(
        outcome.payload(),
        request,
        source="agent-runtime",
        warnings=outcome.warnings,
    )


@router.get("/api/agent/runs")
def list_agent_runs(
    request: Request,
    limit: int = Query(default=100, ge=1, le=500),
) -> dict:
    with _session() as session:
        from eurogas_nexus.db.repositories import agents

        rows = agents.list_agent_runs(session, limit=limit)
        data = [
            {
                "agent_run_id": row.agent_run_id,
                "principal_id": row.principal_id,
                "objective": row.user_objective,
                "agent_profile": row.agent_profile,
                "status": row.status,
                "current_stage": row.current_stage,
                "artifacts_created": row.artifacts_created,
                "model_provider": row.model_provider,
                "model_id": row.model_id,
                "created_at": row.created_at_utc.isoformat(),
                "completed_at": row.completed_at_utc.isoformat() if row.completed_at_utc else None,
            }
            for row in rows
        ]
    return _env(data, request, source="runtime-postgresql")


@router.get("/api/agent/runs/{agent_run_id}")
def get_agent_run(agent_run_id: str, request: Request) -> dict:
    with _session() as session:
        from eurogas_nexus.db.repositories import agents

        row = agents.get_agent_run(session, agent_run_id)
        if row is None:
            raise HTTPException(status_code=404, detail=f"Unknown agent run: {agent_run_id}")
        data = {
            "agent_run_id": row.agent_run_id,
            "principal_id": row.principal_id,
            "user_objective": row.user_objective,
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
        }
    return _env(data, request, source="runtime-postgresql")


@router.get("/api/agent/runs/{agent_run_id}/replay")
def replay_agent_run(agent_run_id: str, request: Request) -> dict:
    with _session() as session:
        from eurogas_nexus.db.repositories import agents

        row = agents.get_agent_run(session, agent_run_id)
        if row is None:
            raise HTTPException(status_code=404, detail=f"Unknown agent run: {agent_run_id}")
        data = agents.replay_payload(session, row)
    return _env(data, request, source="runtime-postgresql")


@router.post("/api/agent/plans/validate")
def validate_plan(body: PlanValidateRequest, request: Request) -> dict:
    principal = _principal(request)
    if _db_configured():
        with _session() as session:
            from eurogas_nexus.db.models import (
                CanonicalEntityRecord,
                SeriesDefinitionRecord,
            )

            known = {row.canonical_entity_id for row in session.query(CanonicalEntityRecord).all()}
            series = {
                row.series_id: {"source_family": row.source_class, "history_days": 30}
                for row in session.query(SeriesDefinitionRecord).all()
            }
    else:
        known = set(body.plan.entities)
        series = {}
    result = validate_research_plan(
        body.plan,
        known_entities=known,
        available_series=series,
        entitled_source_families=set(principal.data_scopes),
    )
    return _env(result.model_dump(mode="json"), request, source="domain-contract")


@router.post("/api/agent/strategy-ir/validate")
def validate_strategy_ir_route(body: dict[str, Any], request: Request) -> dict:
    try:
        from eurogas_nexus.domain.agents.strategy_ir import StrategyIR

        parsed = StrategyIR.model_validate(body.get("strategy_ir") or {})
        result = validate_strategy_ir(parsed)
        compiled_hash = compile_strategy_ir(parsed).content_hash() if result.ok else None
        return _env(
            {
                "ok": result.ok,
                "issues": [item.model_dump(mode="json") for item in result.issues],
                "compiled_content_hash": compiled_hash,
            },
            request,
            source="domain-contract",
        )
    except Exception as exc:
        return _env({"ok": False, "issues": [str(exc)]}, request, source="domain-contract")
