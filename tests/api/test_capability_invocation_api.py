"""Capability invocation through the public route (Architecture V2 Wave 7/CR-15).

`CapabilityRuntime.invoke` enforces each capability's declared posture: ``HUMAN_ONLY`` is never
invoked, ``HUMAN_CONFIRMATION`` requires the caller's confirmation, and permissions, data scopes
and argument validation are checked before a handler runs. The public route accepted a
``human_confirmation`` field and then dropped it while building the invocation context, which
made every ``HUMAN_CONFIRMATION`` capability permanently uncallable *and* told the caller its
confirmation was required - a governance control turned into a dead end.

These tests pin the plumbing rather than the runtime's own rules (covered by
`tests/unit/test_agent_capability_runtime.py`): the flag reaches the runtime, the refusal codes
stay stable, and a refusal comes back as a readable result rather than an exception. The policies
are exercised through capabilities registered for the test, because the builtin catalogue does not
currently declare any capability under those two policies - which is itself worth knowing when
reading the surface that offers invocation.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from eurogas_nexus.api.app import create_app
from eurogas_nexus.application.agents.registry import CapabilityRegistry
from eurogas_nexus.application.agents.runtime import CapabilityRuntime
from eurogas_nexus.domain.agents.contracts import (
    ActionPolicy,
    AgentInvocationContext,
    CapabilityDefinition,
    CapabilityDomain,
    CapabilityResult,
    DeterminismClass,
)


def _definition(capability_id: str, policy: ActionPolicy) -> CapabilityDefinition:
    return CapabilityDefinition(
        capability_id=capability_id,
        name=capability_id,
        domain=CapabilityDomain.MARKET,
        description="test capability",
        input_schema={"type": "object", "properties": {}},
        output_schema={"type": "object"},
        determinism_class=DeterminismClass.DETERMINISTIC,
        action_policy=policy,
    )


def _client(monkeypatch: pytest.MonkeyPatch, policy: ActionPolicy) -> tuple[TestClient, str]:
    """A client whose capability catalogue is one crafted capability of the given policy."""

    capability_id = "test.policy.capability"

    def handler(arguments: dict, context: AgentInvocationContext) -> CapabilityResult:
        return CapabilityResult.success(
            capability=capability_id,
            capability_version="v1",
            data={"confirmation_seen": context.human_confirmation},
        )

    registry = CapabilityRegistry()
    registry.register(_definition(capability_id, policy), handler)
    monkeypatch.setattr(
        "eurogas_nexus.api.routes.public.agents._registry",
        lambda: registry,
    )
    monkeypatch.setattr(
        "eurogas_nexus.api.routes.public.agents._runtime",
        lambda: CapabilityRuntime(registry),
    )
    return TestClient(create_app()), capability_id


def test_a_confirmation_capability_refuses_without_the_flag(monkeypatch) -> None:
    client, capability_id = _client(monkeypatch, ActionPolicy.HUMAN_CONFIRMATION)

    response = client.post(
        f"/api/capabilities/{capability_id}/invoke",
        json={"arguments": {}, "human_confirmation": False},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "BLOCKED"
    assert data["failure"]["code"] == "HUMAN_CONFIRMATION_REQUIRED"


def test_the_callers_confirmation_reaches_the_runtime(monkeypatch) -> None:
    # The flag is what the runtime reads; before the fix it never arrived, so the capability
    # could not be invoked at all while the caller was told to confirm what it had confirmed.
    client, capability_id = _client(monkeypatch, ActionPolicy.HUMAN_CONFIRMATION)

    refused = client.post(f"/api/capabilities/{capability_id}/invoke", json={"arguments": {}})
    confirmed = client.post(
        f"/api/capabilities/{capability_id}/invoke",
        json={
            "arguments": {},
            "human_confirmation": True,
            "confirmation_note": "reviewed the alert evidence",
        },
    )

    assert refused.json()["data"]["failure"]["code"] == "HUMAN_CONFIRMATION_REQUIRED"
    # With the confirmation carried, the runtime no longer refuses for that reason: the handler
    # runs and the answer is the capability's own.
    assert confirmed.json()["data"]["status"] == "SUCCESS"
    assert confirmed.json()["data"]["failure"] is None


def test_a_human_only_capability_is_never_invoked_even_with_confirmation(monkeypatch) -> None:
    client, capability_id = _client(monkeypatch, ActionPolicy.HUMAN_ONLY)

    response = client.post(
        f"/api/capabilities/{capability_id}/invoke",
        json={"arguments": {}, "human_confirmation": True},
    )

    data = response.json()["data"]
    assert data["status"] == "BLOCKED"
    assert data["failure"]["code"] == "PERMISSION_DENIED"
    assert "HUMAN_ONLY" in data["failure"]["detail"]


def test_the_context_carries_the_confirmation_and_the_note() -> None:
    # The unit-level assertion behind the route fix: the context the route builds must carry both
    # the flag and the note, so the runtime decides on facts rather than on a default.
    from eurogas_nexus.api.routes.public import agents as agents_route

    class _State:
        pass

    class _Request:
        state = _State()

    confirmed = agents_route._principal(
        _Request(), human_confirmation=True, confirmation_note="note"
    )
    silent = agents_route._principal(_Request())

    assert (confirmed.human_confirmation, confirmed.confirmation_note) == (True, "note")
    # A caller that says nothing is not treated as having confirmed.
    assert (silent.human_confirmation, silent.confirmation_note) == (False, "")


def test_an_unknown_capability_is_a_blocked_result_not_a_crash(monkeypatch) -> None:
    client, _capability_id = _client(monkeypatch, ActionPolicy.HUMAN_CONFIRMATION)

    response = client.post(
        "/api/capabilities/not.a.capability/invoke",
        json={"arguments": {}},
    )

    assert response.status_code == 200
    data: dict[str, Any] = response.json()["data"]
    assert data["status"] == "BLOCKED"
    assert data["failure"]["code"] == "UNKNOWN_CAPABILITY"


def test_the_invoke_body_cannot_claim_authority() -> None:
    # A confirmation satisfies one policy check and buys no authority: the body's fields are the
    # arguments, the flag and the note - there is no field in which a caller could assert a
    # principal, a role or a data scope.
    from eurogas_nexus.api.routes.public.agents import CapabilityInvokeRequest

    assert set(CapabilityInvokeRequest.model_fields) == {
        "arguments",
        "human_confirmation",
        "confirmation_note",
    }
