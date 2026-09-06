"""First-class agent capability contracts (CR-15).

Capability metadata is deliberately richer than an HTTP route registration.
It answers WHAT/INPUTS/OUTPUT-MEANING/DETERMINISM/WRITES/PERMISSION/
ENTITLEMENT/FRESHNESS/PROVENANCE/FAILURE/RETRY for orchestration and audit.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class CapabilityDomain(StrEnum):
    ONTOLOGY = "ontology"
    MARKET = "market"
    NETWORK = "network"
    CAPACITY = "capacity"
    PORTFOLIO = "portfolio"
    ROUTE = "route"
    SCENARIO = "scenario"
    OPTIMIZATION = "optimization"
    ANALYTICS = "analytics"
    DATASET = "dataset"
    STRATEGY = "strategy"
    BACKTEST = "backtest"
    SHADOW = "shadow"
    REVIEW = "review"
    OPERATIONS = "operations"
    CAPABILITIES = "capabilities"


class DeterminismClass(StrEnum):
    DETERMINISTIC = "DETERMINISTIC"
    MODEL_BASED_DETERMINISTIC_INPUT = "MODEL_BASED_DETERMINISTIC_INPUT"
    LLM_NONDETERMINISTIC = "LLM_NONDETERMINISTIC"
    OPERATIONAL_STATE_DEPENDENT = "OPERATIONAL_STATE_DEPENDENT"


class SideEffectClass(StrEnum):
    READ_ONLY = "READ_ONLY"
    RESEARCH_OBJECT_WRITE = "RESEARCH_OBJECT_WRITE"
    OPERATIONAL_WRITE = "OPERATIONAL_WRITE"


class ActionPolicy(StrEnum):
    AUTO_ALLOWED = "AUTO_ALLOWED"
    AGENT_ALLOWED_WITHIN_RESEARCH = "AGENT_ALLOWED_WITHIN_RESEARCH"
    HUMAN_CONFIRMATION = "HUMAN_CONFIRMATION"
    HUMAN_ONLY = "HUMAN_ONLY"


class IdempotencyClass(StrEnum):
    IDEMPOTENT = "IDEMPOTENT"
    NOT_IDEMPOTENT = "NOT_IDEMPOTENT"
    CONDITIONAL_IDEMPOTENT = "CONDITIONAL_IDEMPOTENT"


class CapabilityStatus(StrEnum):
    ACTIVE = "ACTIVE"
    DISABLED = "DISABLED"
    DEPRECATED = "DEPRECATED"


class CapabilityFailureCode(StrEnum):
    ENTITY_NOT_FOUND = "ENTITY_NOT_FOUND"
    AMBIGUOUS_ENTITY = "AMBIGUOUS_ENTITY"
    INVALID_PRODUCT = "INVALID_PRODUCT"
    DATA_MISSING = "DATA_MISSING"
    DATA_STALE = "DATA_STALE"
    DATA_RESTRICTED = "DATA_RESTRICTED"
    ENTITLEMENT_DENIED = "ENTITLEMENT_DENIED"
    TEMPORAL_INTEGRITY_INSUFFICIENT = "TEMPORAL_INTEGRITY_INSUFFICIENT"
    CAPACITY_UNKNOWN = "CAPACITY_UNKNOWN"
    ROUTE_BLOCKED = "ROUTE_BLOCKED"
    INVALID_UNIT = "INVALID_UNIT"
    INSUFFICIENT_HISTORY = "INSUFFICIENT_HISTORY"
    STRATEGY_INVALID = "STRATEGY_INVALID"
    BACKTEST_BLOCKED = "BACKTEST_BLOCKED"
    OPTIMIZATION_INFEASIBLE = "OPTIMIZATION_INFEASIBLE"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    HUMAN_CONFIRMATION_REQUIRED = "HUMAN_CONFIRMATION_REQUIRED"
    TIMEOUT = "TIMEOUT"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    UNKNOWN_CAPABILITY = "UNKNOWN_CAPABILITY"
    CAPABILITY_DISABLED = "CAPABILITY_DISABLED"


class CapabilityRelationship(BaseModel):
    requires: list[str] = Field(default_factory=list)
    produces: list[str] = Field(default_factory=list)
    commonly_followed_by: list[str] = Field(default_factory=list)


class RetryPolicy(BaseModel):
    max_attempts: int = Field(default=1, ge=0, le=5)
    backoff_seconds: float = Field(default=0.0, ge=0, le=60)
    retryable_error_codes: list[str] = Field(default_factory=list)


class CapabilityDefinition(BaseModel):
    """Versioned semantic contract for one agent-invokable capability."""

    capability_id: str = Field(pattern=r"^[a-z][a-z0-9._-]{2,127}$")
    name: str
    domain: CapabilityDomain
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    determinism_class: DeterminismClass
    side_effect_class: SideEffectClass = SideEffectClass.READ_ONLY
    required_permissions: list[str] = Field(default_factory=lambda: ["capability.invoke"])
    entitlement_policy: str = "none"
    freshness_requirements: str = "none"
    temporal_semantics: str = "as_of_request"
    provenance_contract: str = "returns_source_references"
    timeout_policy: str = "30s"
    retry_policy: RetryPolicy = Field(default_factory=RetryPolicy)
    idempotency: IdempotencyClass = IdempotencyClass.NOT_IDEMPOTENT
    capability_version: str = "v1"
    status: CapabilityStatus = CapabilityStatus.ACTIVE
    owner: str = "research"
    action_policy: ActionPolicy = ActionPolicy.AUTO_ALLOWED
    tags: list[str] = Field(default_factory=list)
    error_codes: list[str] = Field(default_factory=list)
    relationships: CapabilityRelationship = Field(default_factory=CapabilityRelationship)
    mcp_name: str | None = None
    handler_key: str = ""

    def qualified_id(self) -> str:
        return f"{self.capability_id}@{self.capability_version}"

    def public_metadata(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class CapabilityFailure(BaseModel):
    code: CapabilityFailureCode
    detail: str
    retryable: bool = False


class CapabilityExecutionMetadata(BaseModel):
    invocation_id: str = ""
    agent_run_id: str | None = None
    principal_id: str = ""
    capability_id: str = ""
    capability_version: str = ""
    started_at_utc: datetime = Field(default_factory=lambda: datetime.now(UTC))
    completed_at_utc: datetime | None = None
    duration_ms: float | None = None
    input_hash: str = ""
    output_hash: str | None = None
    retry_count: int = 0


class CapabilityResult(BaseModel):
    """Shared envelope + typed domain payload.

    ``data`` remains typed by the capability output schema; the envelope never
    replaces the semantic payload.
    """

    status: str = "SUCCESS"  # SUCCESS | BLOCKED | FAILED
    capability: str
    capability_version: str
    as_of: datetime = Field(default_factory=lambda: datetime.now(UTC))
    data: Any = None
    evidence_refs: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    entitlement_state: str = "NOT_APPLICABLE"
    quality_state: str = "VERIFIED"
    failure: CapabilityFailure | None = None
    execution_metadata: CapabilityExecutionMetadata = Field(
        default_factory=CapabilityExecutionMetadata
    )

    @classmethod
    def success(
        cls,
        *,
        capability: str,
        capability_version: str,
        data: Any,
        evidence_refs: list[str] | None = None,
        warnings: list[str] | None = None,
        quality_state: str = "VERIFIED",
        entitlement_state: str = "NOT_APPLICABLE",
    ) -> CapabilityResult:
        return cls(
            status="SUCCESS",
            capability=capability,
            capability_version=capability_version,
            data=data,
            evidence_refs=evidence_refs or [],
            warnings=warnings or [],
            quality_state=quality_state,
            entitlement_state=entitlement_state,
        )

    @classmethod
    def blocked(
        cls,
        *,
        capability: str,
        capability_version: str,
        code: CapabilityFailureCode,
        detail: str,
        blockers: list[str] | None = None,
        warnings: list[str] | None = None,
    ) -> CapabilityResult:
        return cls(
            status="BLOCKED",
            capability=capability,
            capability_version=capability_version,
            blockers=[*(blockers or []), code.value],
            warnings=warnings or [],
            quality_state="BLOCKED",
            failure=CapabilityFailure(code=code, detail=detail),
        )


class AgentInvocationContext(BaseModel):
    """Authenticated principal context for one capability invocation."""

    principal_id: str
    role: str = "ANALYST"
    roles: list[str] = Field(default_factory=lambda: ["ANALYST"])
    data_scopes: list[str] = Field(default_factory=list)
    agent_run_id: str | None = None
    correlation_request_id: str | None = None
    human_confirmation: bool = False
    confirmation_note: str = ""


class AgentRunStatus(StrEnum):
    RECEIVED = "RECEIVED"
    PLANNING = "PLANNING"
    RUNNING = "RUNNING"
    BLOCKED = "BLOCKED"
    READY_FOR_HUMAN_REVIEW = "READY_FOR_HUMAN_REVIEW"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class OrchestrationStage(StrEnum):
    OBJECTIVE_RECEIVED = "OBJECTIVE_RECEIVED"
    PLAN_DRAFTED = "PLAN_DRAFTED"
    PLAN_VALIDATED = "PLAN_VALIDATED"
    DATA_ANALYSIS = "DATA_ANALYSIS"
    HYPOTHESIS_FORMED = "HYPOTHESIS_FORMED"
    STRATEGY_SPEC_DRAFTED = "STRATEGY_SPEC_DRAFTED"
    STRATEGY_VALIDATED = "STRATEGY_VALIDATED"
    BACKTESTED = "BACKTESTED"
    ROBUSTNESS_EVALUATED = "ROBUSTNESS_EVALUATED"
    CHALLENGED = "CHALLENGED"
    READY_FOR_HUMAN_REVIEW = "READY_FOR_HUMAN_REVIEW"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class AgentContext(BaseModel):
    """Safe semantic context passed to an agent (never whole frontend state)."""

    workspace: str = ""
    gas_day: str | None = None
    product: str | None = None
    selected_hub: str | None = None
    resource_id: str | None = None
    route_id: str | None = None
    scenario_id: str | None = None
    strategy_id: str | None = None
    strategy_version_id: str | None = None
    run_id: str | None = None


class AgentProfile(BaseModel):
    profile_id: str
    name: str
    role_description: str
    deterministic_stages: list[str] = Field(default_factory=list)
    llm_stages: list[str] = Field(default_factory=list)


DEFAULT_AGENT_PROFILES: tuple[AgentProfile, ...] = (
    AgentProfile(
        profile_id="MARKET_RESEARCHER",
        name="Market Researcher",
        role_description="Read market evidence and produce structured findings.",
        deterministic_stages=["DATA_ANALYSIS"],
        llm_stages=["PLAN_DRAFTED", "HYPOTHESIS_FORMED"],
    ),
    AgentProfile(
        profile_id="STRATEGY_RESEARCHER",
        name="Strategy Researcher",
        role_description="Plan, analyze, draft, validate, and backtest research strategies.",
        deterministic_stages=["DATA_ANALYSIS", "STRATEGY_VALIDATED", "BACKTESTED"],
        llm_stages=["PLAN_DRAFTED", "HYPOTHESIS_FORMED", "STRATEGY_SPEC_DRAFTED"],
    ),
    AgentProfile(
        profile_id="RISK_CHALLENGER",
        name="Risk Challenger",
        role_description="Attempt to invalidate a candidate strategy from evidence.",
        deterministic_stages=["CHALLENGED"],
        llm_stages=[],
    ),
    AgentProfile(
        profile_id="REVIEW_ASSISTANT",
        name="Review Assistant",
        role_description="Prepare structured evidence for a human reviewer.",
        deterministic_stages=["READY_FOR_HUMAN_REVIEW"],
        llm_stages=["READY_FOR_HUMAN_REVIEW"],
    ),
)

PROFILES_BY_ID = {profile.profile_id: profile for profile in DEFAULT_AGENT_PROFILES}
