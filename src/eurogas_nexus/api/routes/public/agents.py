"""Agent-native capability API (CR-15).

The capability invoke endpoint is a governed semantic RPC, not a generic
unrestricted remote procedure endpoint: every call passes the authenticated
principal through the CapabilityRuntime permission/entitlement boundary.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from eurogas_nexus.api.errors import ApiError
from eurogas_nexus.application.agents.registry import register_builtin_capabilities
from eurogas_nexus.application.agents.runtime import CapabilityRuntime
from eurogas_nexus.domain.agents.contracts import AgentInvocationContext

router = APIRouter(tags=["agents"])


class CapabilityInvokeRequest(BaseModel):
    """One capability invocation request."""

    arguments: dict[str, Any] = Field(default_factory=dict)
    human_confirmation: bool = False
    confirmation_note: str = Field(default="", max_length=500)


def _env(data: object, request: Request, *, source: str, warnings: list[str] | None = None) -> dict:
    """Wrap a response in the research-only envelope."""

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


def _principal(
    request: Request,
    *,
    human_confirmation: bool = False,
    confirmation_note: str = "",
) -> AgentInvocationContext:
    """The invocation context for one call.

    ``human_confirmation`` is the caller's answer to a capability whose ``action_policy`` is
    ``HUMAN_CONFIRMATION``: the runtime refuses such a capability without it. It counts only
    from a signed-in person (``principal_type`` ``USER``), never from the deployment token or a
    service account.
    """

    identity = getattr(request.state, "identity", None)
    if identity is None:
        # Fail closed (CODEX-1). The app-wide identity dependency attaches a principal or
        # refuses with 401 before this route runs, so this is reached only when the router is
        # mounted without it.
        raise HTTPException(
            status_code=401,
            detail={
                "error": "authentication_required",
                "message": "A capability call needs the caller's identity.",
            },
        )
    return AgentInvocationContext(
        principal_id=identity.principal_id,
        role=identity.role,
        roles=list(identity.roles or [identity.role]),
        data_scopes=list(identity.data_scopes or []),
        correlation_request_id=getattr(request.state, "request_id", None),
        human_confirmation=human_confirmation,
        confirmation_note=confirmation_note,
        principal_type=str(getattr(identity, "principal_type", "") or "SERVICE"),
    )


@router.get("/api/capabilities")
def list_capabilities(
    request: Request,
    domain: str | None = Query(default=None),
) -> dict:
    """List the registered capability catalogue, optionally by domain."""

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
    """Search the registered capability catalogue."""

    return _env(
        [item.public_metadata() for item in _registry().search(q)],
        request,
        source="domain-contract",
    )


@router.get("/api/capabilities/{capability_id}")
def describe_capability(capability_id: str, request: Request) -> dict:
    """Describe one registered capability."""

    definition = _registry().get(capability_id)
    if definition is None:
        raise ApiError(
            404,
            "agent_capability_not_found",
            f'Unknown capability: {capability_id}',
            params={"capability_id": capability_id},
        )
    return _env(definition.public_metadata(), request, source="domain-contract")


@router.post("/api/capabilities/{capability_id}/invoke")
def invoke_capability(
    capability_id: str,
    body: CapabilityInvokeRequest,
    request: Request,
) -> dict:
    """Invoke one registered capability under the caller's own authority.

    The runtime enforces the capability's declared posture: ``HUMAN_ONLY`` is never invoked,
    ``HUMAN_CONFIRMATION`` requires the caller's confirmation flag, and permissions, data scopes
    and argument validation are checked before the handler runs. A refusal is returned as a
    ``BLOCKED`` result with its stable failure code rather than raised, so the caller can read
    exactly which control stopped it.
    """

    principal = _principal(
        request,
        human_confirmation=body.human_confirmation,
        confirmation_note=body.confirmation_note,
    )
    result = _runtime().invoke(capability_id, body.arguments, principal)
    if result.status == "SUCCESS":
        return _env(result.model_dump(mode="json"), request, source="capability-runtime")
    return _env(
        result.model_dump(mode="json"),
        request,
        source="capability-runtime",
        warnings=result.warnings,
    )
