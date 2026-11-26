"""Governed capability invocation runtime (CR-15).

Every call returns a :class:`CapabilityResult` whose execution metadata names the capability,
its version, the principal, the agent run and a hash of the arguments, refusals included, so a
trace of what was refused reads like a trace of what ran (CODEX-1). A successful result also
carries a hash of its output, and is refused when it does not have the shape its
``output_schema`` declares: a caller never has to re-check a result's envelope itself.

A ``HUMAN_CONFIRMATION`` capability runs only on the confirmation of a signed-in person: a
model acting for an AI use cannot confirm, nor can a deployment token or a service account.
The confirmation, and every call of a capability that writes, is audited with the capability's
qualified id and the argument hash, so the record says who confirmed which version of what.

A synchronous handler cannot be stopped from here; a call that overruns its declared
``timeout_policy`` is reported in the result's warnings rather than presented as on time.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from datetime import UTC, datetime
from time import perf_counter
from typing import Any

from pydantic import BaseModel

from eurogas_nexus.domain.agents.contracts import (
    ActionPolicy,
    AgentInvocationContext,
    CapabilityDefinition,
    CapabilityFailureCode,
    CapabilityResult,
    CapabilityStatus,
    SideEffectClass,
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
        started = perf_counter()
        definition = self.registry.get(capability_id)
        result = self._invoke(definition, capability_id, arguments, context)
        version = definition.capability_version if definition else result.capability_version
        _stamp(result, capability_id, version, arguments, context, started)
        if definition is not None:
            if result.status == "SUCCESS":
                overrun = _timeout_overrun(definition, result.execution_metadata.duration_ms)
                if overrun:
                    result.warnings.append(overrun)
            _audit(definition, result, context)
        return result

    def _invoke(
        self,
        definition: CapabilityDefinition | None,
        capability_id: str,
        arguments: dict[str, Any],
        context: AgentInvocationContext,
    ) -> CapabilityResult:
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
        if context.ai_use:
            ai_refusal = _denied_ai_tool(context, capability_id)
            if ai_refusal:
                return CapabilityResult.blocked(
                    capability=capability_id,
                    capability_version=definition.capability_version,
                    code=CapabilityFailureCode.PERMISSION_DENIED,
                    detail=f"ai_tool_not_allowed: {ai_refusal}",
                )
        if definition.action_policy == ActionPolicy.HUMAN_ONLY:
            return CapabilityResult.blocked(
                capability=capability_id,
                capability_version=definition.capability_version,
                code=CapabilityFailureCode.PERMISSION_DENIED,
                detail="HUMAN_ONLY capability is never agent-invokable",
            )
        if definition.action_policy == ActionPolicy.HUMAN_CONFIRMATION:
            refusal = _confirmation_refusal(context)
            if refusal:
                return CapabilityResult.blocked(
                    capability=capability_id,
                    capability_version=definition.capability_version,
                    code=CapabilityFailureCode.HUMAN_CONFIRMATION_REQUIRED,
                    detail=refusal,
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
        try:
            result = handler(dict(arguments), context)
        except Exception as exc:  # capability failures are machine-readable
            return CapabilityResult.blocked(
                capability=capability_id,
                capability_version=definition.capability_version,
                code=CapabilityFailureCode.INTERNAL_ERROR,
                detail=f"{exc.__class__.__name__}: {exc}",
            )
        if not isinstance(result, CapabilityResult):
            return CapabilityResult.blocked(
                capability=capability_id,
                capability_version=definition.capability_version,
                code=CapabilityFailureCode.INTERNAL_ERROR,
                detail="handler did not return a CapabilityResult",
            )
        if result.status == "SUCCESS":
            problem = output_problem(result.data, definition.output_schema)
            if problem:
                return CapabilityResult.blocked(
                    capability=capability_id,
                    capability_version=definition.capability_version,
                    code=CapabilityFailureCode.INTERNAL_ERROR,
                    detail=f"result does not match the declared output_schema: {problem}",
                )
            result.execution_metadata.output_hash = hash_object(_plain(result.data))
        return result


def _stamp(
    result: CapabilityResult,
    capability_id: str,
    capability_version: str,
    arguments: Any,
    context: AgentInvocationContext,
    started: float,
) -> None:
    """Name the call on its result, whatever the outcome (a refusal is traced like a run)."""

    metadata = result.execution_metadata
    metadata.capability_id = capability_id
    metadata.capability_version = capability_version
    metadata.principal_id = context.principal_id
    metadata.agent_run_id = context.agent_run_id
    metadata.completed_at_utc = datetime.now(UTC)
    metadata.duration_ms = round((perf_counter() - started) * 1000, 3)
    metadata.input_hash = hash_object(arguments)


def _confirmation_refusal(context: AgentInvocationContext) -> str:
    """Why this call's confirmation does not count, or ``""`` when it does."""

    if not context.human_confirmation:
        return "Human confirmation is required for this capability"
    if context.ai_use:
        return (
            f"a model acting for the AI use {context.ai_use!r} cannot confirm on a person's "
            "behalf; the person confirms in their own call"
        )
    if str(context.principal_type).upper() != "USER":
        return (
            f"confirmation must come from a signed-in person; {context.principal_id!r} is a "
            f"{str(context.principal_type).lower()} principal"
        )
    return ""


#: ``30s``, ``120s``, ``2m``: the declared bound a handler is expected to finish within.
_TIMEOUT_POLICY = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*(ms|s|m)\s*$")


def declared_timeout_seconds(policy: str) -> float | None:
    """The seconds a ``timeout_policy`` declares, or ``None`` when it declares no bound."""

    match = _TIMEOUT_POLICY.match(str(policy or ""))
    if match is None:
        return None
    value, unit = float(match.group(1)), match.group(2)
    return value / 1000 if unit == "ms" else value * 60 if unit == "m" else value


def _timeout_overrun(definition: CapabilityDefinition, duration_ms: float | None) -> str:
    bound = declared_timeout_seconds(definition.timeout_policy)
    if bound is None or duration_ms is None or duration_ms <= bound * 1000:
        return ""
    return (
        f"TIMEOUT_OVERRUN: ran {duration_ms / 1000:.1f} s against a declared "
        f"{definition.timeout_policy}; a synchronous handler is not stopped, so the result "
        "arrived late"
    )


_JSON_TYPES: dict[str, tuple[type, ...]] = {
    "object": (Mapping, BaseModel),
    "array": (list, tuple),
    "string": (str,),
    "boolean": (bool,),
    "number": (int, float),
    "integer": (int,),
}


def output_problem(data: Any, schema: Mapping[str, Any]) -> str:
    """Where ``data`` breaks the shallow output schema a capability declares, or ``""``.

    The same JSON-Schema subset as :func:`validate_arguments`: the root ``type`` and, for an
    object, its ``required`` fields.
    """

    expected = (schema or {}).get("type")
    if not expected:
        return ""
    kinds = _JSON_TYPES.get(str(expected))
    if kinds is None:
        return f"unsupported output_schema type {expected!r}"
    if data is None or not isinstance(data, kinds) or (
        expected in {"number", "integer"} and isinstance(data, bool)
    ):
        return f"expected {expected}, got {type(data).__name__}"
    if expected == "object":
        held = data.model_dump() if isinstance(data, BaseModel) else data
        missing = [name for name in (schema.get("required") or []) if name not in held]
        if missing:
            return f"missing required field(s): {', '.join(map(str, missing))}"
    return ""


def _plain(value: Any) -> Any:
    return value.model_dump(mode="json") if isinstance(value, BaseModel) else value


def _audit(
    definition: CapabilityDefinition, result: CapabilityResult, context: AgentInvocationContext
) -> None:
    """Audit a confirmed call, a refused confirmation and every call of a writing capability.

    Best-effort, like every read-path audit: a missing store never changes the result. The
    row holds the qualified capability id and hashes, never the arguments or the output.
    """

    confirmation = definition.action_policy == ActionPolicy.HUMAN_CONFIRMATION
    writes = definition.side_effect_class != SideEffectClass.READ_ONLY
    refused_confirmation = (
        confirmation
        and context.human_confirmation
        and result.failure is not None
        and result.failure.code == CapabilityFailureCode.HUMAN_CONFIRMATION_REQUIRED
    )
    if not (writes or refused_confirmation or (confirmation and context.human_confirmation)):
        return
    from eurogas_nexus.application.audit_service import record_audit_event

    metadata = result.execution_metadata
    if refused_confirmation:
        action, outcome, severity = "agent.capability.confirmation_refused", "denied", "warning"
    elif confirmation and context.human_confirmation:
        action = "agent.capability.confirmed"
        outcome = "success" if result.status == "SUCCESS" else "blocked"
        severity = "info"
    else:
        action = "agent.capability.invoked"
        outcome = "success" if result.status == "SUCCESS" else "blocked"
        severity = "info"
    parts = [
        f"capability={definition.qualified_id()}",
        f"side_effect={definition.side_effect_class.value}",
        f"input_hash={metadata.input_hash}",
    ]
    if metadata.output_hash:
        parts.append(f"output_hash={metadata.output_hash}")
    if result.failure is not None:
        parts.append(f"failure={result.failure.code.value}")
    if context.ai_use:
        parts.append(f"ai_use={context.ai_use}")
    if context.agent_run_id:
        parts.append(f"agent_run_id={context.agent_run_id}")
    if confirmation and context.confirmation_note:
        parts.append(f"note={context.confirmation_note}")
    record_audit_event(
        event_type="governance.agent_capability",
        action=action,
        resource=f"capability:{definition.qualified_id()}"[:128],
        principal=context.principal_id[:64],
        outcome=outcome,
        severity=severity,
        detail="; ".join(parts)[:900],
        source_system="agent-runtime",
        request_id=context.correlation_request_id,
    )


def _denied_ai_tool(context: AgentInvocationContext, capability_id: str) -> str:
    """GOV-1: a model may call only what its use and one of the caller's roles allow.

    The refusal is audited; the audit is best-effort, the refusal is not.
    """

    from eurogas_nexus.application.ai_controls import ai_tool_refusal, record_ai_tool_refusal

    use = str(context.ai_use)
    refusal = ai_tool_refusal(use, list(context.roles or [context.role]), capability_id)
    if refusal:
        record_ai_tool_refusal(
            use=use,
            principal_id=context.principal_id,
            capability_id=capability_id,
            reason=refusal,
            request_id=context.correlation_request_id,
        )
    return refusal


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
