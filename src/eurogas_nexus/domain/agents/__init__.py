"""Agent-native research contracts (CR-15)."""

from eurogas_nexus.domain.agents.challenge import ChallengeReport, ChallengeResult
from eurogas_nexus.domain.agents.contracts import (
    ActionPolicy,
    AgentContext,
    AgentInvocationContext,
    AgentRunStatus,
    CapabilityDefinition,
    CapabilityDomain,
    CapabilityFailure,
    CapabilityFailureCode,
    CapabilityRelationship,
    CapabilityResult,
    CapabilityStatus,
    DeterminismClass,
    IdempotencyClass,
    RetryPolicy,
    SideEffectClass,
)

__all__ = [
    "ActionPolicy",
    "ChallengeReport",
    "ChallengeResult",
    "AgentContext",
    "AgentInvocationContext",
    "AgentRunStatus",
    "CapabilityDefinition",
    "CapabilityDomain",
    "CapabilityFailure",
    "CapabilityFailureCode",
    "CapabilityRelationship",
    "CapabilityResult",
    "CapabilityStatus",
    "DeterminismClass",
    "IdempotencyClass",
    "RetryPolicy",
    "SideEffectClass",
]
