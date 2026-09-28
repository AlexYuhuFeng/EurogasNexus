"""MCP deployment-profile gate tests (first-customer-pilot finding CA-05).

The pilot mitigation: a customer-facing deployment profile (``trial``/``release``
environment, or the ``release`` API profile) refuses MCP tool discovery and invocation
until the persisted service identity of architecture decision D6 is built. Development
and test worktrees keep the existing read-only surface, and the CI handshake smoke shape
(``initialize`` answered with no explicit profile) is pinned here so it cannot regress.

Every test in this module runs with a deliberately hostile agent identity - role
``ADMIN``, wildcard data scopes, a named principal and a deployment token - so a refusal
below is proved to be the deployment profile's, never the pseudo-identity's configuration.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from eurogas_nexus.mcp.server import (
    TOOLS_BY_NAME,
    MCPToolAccessDisabled,
    handle_jsonrpc_line,
    tool_access_disabled_reason,
)

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def _hostile_agent_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    """A maximal ``EUROGAS_NEXUS_AGENT_*`` grant is never authority for this gate."""

    monkeypatch.setenv("EUROGAS_NEXUS_AGENT_ROLE", "ADMIN")
    monkeypatch.setenv("EUROGAS_NEXUS_AGENT_DATA_SCOPES", "*")
    monkeypatch.setenv("EUROGAS_NEXUS_AGENT_PRINCIPAL", "service:mcp-pilot-gate")
    monkeypatch.setenv("EUROGAS_NEXUS_PUBLIC_API_TOKEN", "pilot-gate-token")


@pytest.fixture(autouse=True)
def _development_profile(monkeypatch: pytest.MonkeyPatch) -> None:
    """The module's baseline profile; the matrix tests override it per case."""

    monkeypatch.setenv("EUROGAS_NEXUS_ENV", "development")
    monkeypatch.setenv("EUROGAS_NEXUS_API_PROFILE", "development")


def _send(request: dict) -> dict:
    response = handle_jsonrpc_line(json.dumps(request))
    assert response is not None
    return json.loads(response)


def _call(name: str, arguments: dict) -> dict:
    return _send(
        {
            "jsonrpc": "2.0",
            "id": 7,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        }
    )


@pytest.mark.parametrize(
    ("environment", "api_profile", "expected_available"),
    [
        ("development", "development", True),
        ("test", "development", True),
        ("development", "internal", True),
        ("development", "release", False),
        ("trial", "development", False),
        ("trial", "release", False),
        ("release", "release", False),
    ],
)
def test_profile_matrix_follows_the_authoritative_resolver(
    monkeypatch: pytest.MonkeyPatch,
    environment: str,
    api_profile: str,
    expected_available: bool,
) -> None:
    monkeypatch.setenv("EUROGAS_NEXUS_ENV", environment)
    monkeypatch.setenv("EUROGAS_NEXUS_API_PROFILE", api_profile)
    assert (tool_access_disabled_reason() is None) is expected_available


def test_unset_profile_stays_the_documented_development_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Repository default: an unset profile is development, which keeps the surface.

    A customer deployment therefore has to set the release profile explicitly; the
    operator bundle does (``deploy/runtime/compose.yaml`` sets both variables), and the
    deployment docs state that an unset profile is the developer default rather than a
    pilot-safe statement.
    """

    monkeypatch.delenv("EUROGAS_NEXUS_ENV", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_API_PROFILE", raising=False)
    assert tool_access_disabled_reason() is None


@pytest.mark.parametrize("value", ["prod", "Trial", "RELEASE", "production"])
def test_unknown_environment_fails_closed(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setenv("EUROGAS_NEXUS_ENV", value)
    assert tool_access_disabled_reason() is not None
    listing = _send({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    assert listing["result"]["tools"] == []


def test_unknown_api_profile_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EUROGAS_NEXUS_API_PROFILE", "pilot")
    assert tool_access_disabled_reason() is not None


def test_malformed_deployment_configuration_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A profile the authoritative resolver cannot read is refused, not defaulted."""

    monkeypatch.setenv("EUROGAS_NEXUS_ALLOW_ANONYMOUS_CALLERS", "perhaps")
    reason = tool_access_disabled_reason()
    assert reason is not None
    assert "could not be resolved" in reason


@pytest.mark.parametrize("environment", ["trial", "release"])
def test_customer_facing_profiles_refuse_discovery_and_invocation(
    monkeypatch: pytest.MonkeyPatch, environment: str
) -> None:
    monkeypatch.setenv("EUROGAS_NEXUS_ENV", environment)

    initialized = _send({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    result = initialized["result"]
    # The handshake itself still succeeds: a client is told there are no tools...
    assert result["protocolVersion"] == "2024-11-05"
    assert "tools" not in result["capabilities"]
    assert "disabled" in result["instructions"]

    listing = _send({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    assert listing["result"]["tools"] == []

    # ...and both tool families - a legacy SDK tool and a registry capability - refuse.
    for name in ("list_sources", "compute_hub_spread"):
        refusal = _call(name, {})
        assert refusal["error"]["code"] == -32000
        assert "disabled" in refusal["error"]["message"]
        assert refusal["error"]["data"]["code"] == "mcp_tools_disabled"


def test_release_api_profile_refuses_in_a_development_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("EUROGAS_NEXUS_ENV", "development")
    monkeypatch.setenv("EUROGAS_NEXUS_API_PROFILE", "release")

    reason = tool_access_disabled_reason()
    assert reason is not None
    assert "API profile" in reason
    listing = _send({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    assert listing["result"]["tools"] == []


def test_refusal_happens_before_audit_sdk_and_handler(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The refusal reaches no audit write, SDK call, capability runtime or handler body."""

    monkeypatch.setenv("EUROGAS_NEXUS_ENV", "release")
    calls: list[str] = []

    def _record(**kwargs):
        calls.append("audit")
        return "audit-1"

    def _fetch_sources(base_url):
        calls.append("sdk")
        return []

    def _invoke(self, capability_id, arguments, context):
        calls.append("runtime")
        return None

    monkeypatch.setattr("eurogas_nexus.application.audit_service.record_audit_event", _record)
    monkeypatch.setattr("eurogas_nexus_sdk.sources.fetch_sources", _fetch_sources)
    monkeypatch.setattr(
        "eurogas_nexus.application.agents.runtime.CapabilityRuntime.invoke", _invoke
    )

    for name in ("list_sources", "compute_hub_spread"):
        refusal = _call(name, {})
        assert refusal["error"]["data"]["code"] == "mcp_tools_disabled"
    assert calls == []


def test_exported_handlers_refuse_direct_invocation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``TOOLS_BY_NAME`` is reachable without JSON-RPC; the gate guards that path too."""

    monkeypatch.setenv("EUROGAS_NEXUS_ENV", "release")
    calls: list[str] = []

    monkeypatch.setattr(
        "eurogas_nexus_sdk.sources.fetch_sources",
        lambda base_url: calls.append("sdk") or [],
    )
    monkeypatch.setattr(
        "eurogas_nexus.application.agents.runtime.CapabilityRuntime.invoke",
        lambda *args, **kwargs: calls.append("runtime"),
    )

    for name in ("list_sources", "compute_hub_spread"):
        with pytest.raises(MCPToolAccessDisabled) as refusal:
            TOOLS_BY_NAME[name].handler({})
        assert "disabled" in str(refusal.value)
    assert calls == []


def test_development_keeps_the_existing_tool_surface(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The mitigation preserves the development/test surface (existing MCP behaviour)."""

    # The gate is profile-based, so this test may step back from the module's hostile
    # identity to the documented development configuration. The hostile identity is not
    # authority either: with role ADMIN the same call still reaches the capability runtime
    # and is refused there (PERMISSION_DENIED), which the refusal tests never need to model.
    monkeypatch.setenv("EUROGAS_NEXUS_AGENT_ROLE", "ANALYST")
    monkeypatch.setenv("EUROGAS_NEXUS_AGENT_DATA_SCOPES", "")
    assert tool_access_disabled_reason() is None

    initialized = _send({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    assert initialized["result"]["capabilities"] == {"tools": {"listChanged": False}}
    assert "instructions" not in initialized["result"]

    listing = _send({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    names = {tool["name"] for tool in listing["result"]["tools"]}
    assert {"list_sources", "compute_hub_spread"} <= names

    arguments = {
        "origin_hub": "NBP",
        "destination_hub": "TTF",
        "product": "DAY_AHEAD",
        "origin_value": 10,
        "destination_value": 12,
        "unit": "EUR/MWh",
    }
    content = json.loads(_call("compute_hub_spread", arguments)["result"]["content"][0]["text"])
    assert content["status"] == "SUCCESS"
    assert content["data"]["value"] == 2.0

    # The exported handler is a pass-through when the profile allows tools.
    direct = TOOLS_BY_NAME["compute_hub_spread"].handler(arguments)
    assert direct["status"] == "SUCCESS"


def _run_stdio(messages: list[dict], *, overrides: dict[str, str], unset: tuple[str, ...] = ()):
    env = os.environ.copy()
    for name in unset:
        env.pop(name, None)
    env.update(overrides)
    env["PYTHONPATH"] = os.pathsep.join(
        [
            str(ROOT / "src"),
            str(ROOT / "packages" / "python-sdk" / "src"),
            *[part for part in env.get("PYTHONPATH", "").split(os.pathsep) if part],
        ]
    )
    completed = subprocess.run(
        [sys.executable, "-m", "eurogas_nexus.mcp.server"],
        input="".join(json.dumps(message) + "\n" for message in messages),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        cwd=ROOT,
        timeout=120,
    )
    assert completed.returncode == 0, completed.stderr
    return [json.loads(line) for line in completed.stdout.splitlines() if line.strip()]


def test_stdio_subprocess_refuses_in_a_customer_facing_deployment() -> None:
    """The real transport refuses: nothing to discover, nothing invocable, no side effect."""

    responses = _run_stdio(
        [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": "list_sources", "arguments": {}},
            },
        ],
        overrides={
            "EUROGAS_NEXUS_ENV": "release",
            "EUROGAS_NEXUS_API_PROFILE": "release",
            "EUROGAS_NEXUS_AGENT_ROLE": "ADMIN",
            "EUROGAS_NEXUS_AGENT_DATA_SCOPES": "*",
            "EUROGAS_NEXUS_AGENT_PRINCIPAL": "service:mcp",
            "EUROGAS_NEXUS_PUBLIC_API_TOKEN": "pilot-gate-token",
        },
    )

    assert [response["id"] for response in responses] == [1, 2, 3]
    assert "tools" not in responses[0]["result"]["capabilities"]
    assert responses[1]["result"]["tools"] == []
    assert responses[2]["error"]["code"] == -32000
    assert responses[2]["error"]["data"]["code"] == "mcp_tools_disabled"


def test_stdio_subprocess_keeps_the_ci_handshake_shape() -> None:
    """The CI smoke (``initialize`` with no explicit profile) keeps answering."""

    responses = _run_stdio(
        [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        ],
        overrides={},
        unset=("EUROGAS_NEXUS_ENV", "EUROGAS_NEXUS_API_PROFILE"),
    )

    assert responses[0]["result"]["protocolVersion"] == "2024-11-05"
    assert responses[0]["result"]["serverInfo"]["name"] == "eurogas-nexus-mcp"
    assert "tools" in responses[0]["result"]["capabilities"]
    assert responses[1]["result"]["tools"]
