"""Governed capability invocation runtime (CR-15)."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from time import perf_counter
from typing import Any

from eurogas_nexus.domain.agents.contracts import (
    ActionPolicy,
    AgentInvocationContext,
    CapabilityDefinition,
    CapabilityFailureCode,
    CapabilityResult,
    CapabilityStatus,
)
from eurogas_nexus.security.authorization import authorize
from eurogas_nexus.security.identity import (
    AuthenticatedPrincipal,
    principal_allows_source_family,
)


class CapabilityRuntime:
    """Shared enforcement boundary for API, SDK, and MCP."""

    def __init__(self, registry) -> None:
        self.registry = registry

    def invoke(
        self,
        capability_id: str,
        arguments: dict[str, Any],
        context: AgentInvocationContext,
    ) -> CapabilityResult:
        definition = self.registry.get(capability_id)
        if definition is None:
            return CapabilityResult.blocked(
                capability=capability_id,
                capability_version="unknown",
                code=CapabilityFailureCode.UNKNOWN_CAPABILITY,
                detail=f"Unknown capability: {capability_id}",
            )
        if definition.status != CapabilityStatus.ACTIVE:
            return CapabilityResult.blocked(
                capability=capability_id,
                capability_version=definition.capability_version,
                code=CapabilityFailureCode.CAPABILITY_DISABLED,
                detail=f"Capability {capability_id} is {definition.status.value}",
            )
        if definition.action_policy == ActionPolicy.HUMAN_ONLY:
            return CapabilityResult.blocked(
                capability=capability_id,
                capability_version=definition.capability_version,
                code=CapabilityFailureCode.PERMISSION_DENIED,
                detail="HUMAN_ONLY capability is never agent-invokable",
            )
        if (
            definition.action_policy == ActionPolicy.HUMAN_CONFIRMATION
            and not context.human_confirmation
        ):
            return CapabilityResult.blocked(
                capability=capability_id,
                capability_version=definition.capability_version,
                code=CapabilityFailureCode.HUMAN_CONFIRMATION_REQUIRED,
                detail="Human confirmation is required for this capability",
            )

        permission_denied = _denied_permission(context, definition)
        if permission_denied:
            return CapabilityResult.blocked(
                capability=capability_id,
                capability_version=definition.capability_version,
                code=CapabilityFailureCode.PERMISSION_DENIED,
                detail=permission_denied,
            )
        entitlement_denied = _denied_entitlement(context, definition)
        if entitlement_denied:
            return CapabilityResult.blocked(
                capability=capability_id,
                capability_version=definition.capability_version,
                code=CapabilityFailureCode.ENTITLEMENT_DENIED,
                detail=entitlement_denied,
            )
        validation_error = validate_arguments(arguments, definition.input_schema)
        if validation_error:
            return CapabilityResult.blocked(
                capability=capability_id,
                capability_version=definition.capability_version,
                code=CapabilityFailureCode.INVALID_PRODUCT,
                detail=validation_error,
            )

        handler = self.registry.handler(capability_id)
        if handler is None:
            return CapabilityResult.blocked(
                capability=capability_id,
                capability_version=definition.capability_version,
                code=CapabilityFailureCode.INTERNAL_ERROR,
                detail="Capability handler is not registered",
            )
        started = perf_counter()
        try:
            result = handler(dict(arguments), context)
        except Exception as exc:  # capability failures are machine-readable
            return CapabilityResult.blocked(
                capability=capability_id,
                capability_version=definition.capability_version,
                code=CapabilityFailureCode.INTERNAL_ERROR,
                detail=f"{exc.__class__.__name__}: {exc}",
            )
        completed = datetime.now(UTC)
        metadata = result.execution_metadata
        metadata.capability_id = capability_id
        metadata.capability_version = definition.capability_version
        metadata.principal_id = context.principal_id
        metadata.agent_run_id = context.agent_run_id
        metadata.completed_at_utc = completed
        metadata.duration_ms = round((perf_counter() - started) * 1000, 3)
        metadata.input_hash = hash_object(arguments)
        return result


def _denied_permission(context: AgentInvocationContext, definition: CapabilityDefinition) -> str:
    principal = AuthenticatedPrincipal(
        principal_id=context.principal_id,
        name=context.principal_id,
        principal_type="USER",
        role=context.role,
        status="ACTIVE",
        data_scopes=tuple(context.data_scopes),
        roles=tuple(context.roles or [context.role]),
    )
    for permission in definition.required_permissions:
        decision = authorize(principal, permission)
        if not decision.allowed:
            return (
                f"permission {permission!r} not granted to {context.principal_id!r} "
                f"({decision.reason})"
            )
    return ""


def _denied_entitlement(
    context: AgentInvocationContext, definition: CapabilityDefinition
) -> str:
    policy = definition.entitlement_policy.strip()
    if not policy or policy.casefold() == "none":
        return ""
    families = [item.strip() for item in policy.split(",") if item.strip()]
    if not families:
        return ""
    principal = AuthenticatedPrincipal(
        principal_id=context.principal_id,
        name=context.principal_id,
        principal_type="USER",
        role=context.role,
        status="ACTIVE",
        data_scopes=tuple(context.data_scopes),
        roles=tuple(context.roles or [context.role]),
    )
    for family in families:
        if not principal_allows_source_family(principal, family):
            return f"source family {family!r} is not entitled for this principal"
    return ""


def validate_arguments(arguments: dict[str, Any], schema: dict[str, Any]) -> str:
    """Lightweight JSON-Schema subset used for capability input gates."""

    if schema.get("type") != "object":
        return "input_schema root must be type object"
    arguments = arguments or {}
    if not isinstance(arguments, dict):
        return "arguments must be an object"
    properties = schema.get("properties") or {}
    if schema.get("additionalProperties") is False:
        unknown = sorted(set(arguments) - set(properties))
        if unknown:
            return f"unknown fields: {unknown}"
    for name in schema.get("required") or []:
        if name not in arguments:
            return f"missing required field: {name}"
    for name, value in arguments.items():
        property_schema = properties.get(name)
        if property_schema is None:
            continue
        expected_type = property_schema.get("type")
        if expected_type == "string" and not isinstance(value, str):
            return f"{name} must be a string"
        if expected_type == "number" and isinstance(value, bool):
            return f"{name} must be a number"
        if expected_type in {"number", "integer"} and not isinstance(value, (int, float)):
            return f"{name} must be a number"
        if expected_type == "integer" and isinstance(value, float) and not value.is_integer():
            return f"{name} must be an integer"
        if expected_type == "boolean" and not isinstance(value, bool):
            return f"{name} must be a boolean"
        if expected_type == "array" and not isinstance(value, list):
            return f"{name} must be an array"
        if expected_type == "object" and not isinstance(value, dict):
            return f"{name} must be an object"
        if "enum" in property_schema and value not in property_schema["enum"]:
            return f"{name} must be one of {property_schema['enum']}"
    return ""


def hash_object(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
