"""Registry-driven MCP adapter tests (CR-15)."""

from __future__ import annotations

import json

from eurogas_nexus.mcp.server import TOOLS_BY_NAME, handle_jsonrpc_line


def _call(name, arguments):
    response = handle_jsonrpc_line(
        json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": name, "arguments": arguments},
            }
        )
    )
    assert response is not None
    return json.loads(response)


def test_mcp_lists_registry_capability_tools() -> None:
    response = handle_jsonrpc_line(json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}))
    payload = json.loads(response)
    names = {tool["name"] for tool in payload["result"]["tools"]}
    for expected in [
        "list_capabilities",
        "resolve_entity",
        "compute_hub_spread",
        "calculate_route_economics",
        "validate_strategy_ir",
        "run_strategy_backtest",
    ]:
        assert expected in names


def test_mcp_invokes_registry_capability() -> None:
    result = _call(
        "compute_hub_spread",
        {
            "origin_hub": "NBP",
            "destination_hub": "TTF",
            "product": "DAY_AHEAD",
            "origin_value": 10,
            "destination_value": 12,
            "unit": "EUR/MWh",
        },
    )
    assert result["result"]["isError"] is False
    content = json.loads(result["result"]["content"][0]["text"])
    assert content["status"] == "SUCCESS"
    assert content["data"]["value"] == 2.0


def test_mcp_typed_input_validation_is_machine_readable() -> None:
    result = _call(
        "compute_hub_spread",
        {"origin_hub": "NBP", "destination_hub": "TTF", "origin_value": "x"},
    )
    assert result["result"]["isError"] is False
    content = json.loads(result["result"]["content"][0]["text"])
    assert content["status"] == "BLOCKED"


def test_mcp_permission_denial(monkeypatch) -> None:
    monkeypatch.setenv("EUROGAS_NEXUS_AGENT_ROLE", "VIEWER")
    result = _call("compute_distribution", {"values": [1, 2]})
    content = json.loads(result["result"]["content"][0]["text"])
    assert content["status"] == "BLOCKED"
    assert content["failure"]["code"] == "PERMISSION_DENIED"


def test_mcp_has_no_execution_or_sql_tools() -> None:
    names = set(TOOLS_BY_NAME)
    for banned in ("trade.execute", "order.place", "order.cancel", "nomination.submit", "run_sql"):
        assert banned not in names
    for name in names:
        tool = TOOLS_BY_NAME[name]
        assert "SELECT " not in tool.description.upper()


def test_the_mcp_pseudo_principal_grants_no_commercial_scope_by_default(monkeypatch) -> None:
    """Finding C8: an unconfigured MCP server is not a super-user over commercial data.

    The transport carries no user identity, so the pseudo-principal cannot inherit one -
    and it must not pretend to. Commercial families require an explicit, deliberate grant.
    """

    from eurogas_nexus.mcp.server import _agent_context

    for variable in (
        "EUROGAS_NEXUS_AGENT_ROLE",
        "EUROGAS_NEXUS_AGENT_PRINCIPAL",
        "EUROGAS_NEXUS_AGENT_DATA_SCOPES",
    ):
        monkeypatch.delenv(variable, raising=False)

    default = _agent_context()
    assert list(default.data_scopes) == []
    # The legacy wildcard is gone: nothing about the default reads every family.
    assert "*" not in list(default.data_scopes)
    assert default.principal_id == "service:mcp"

    # A deployment that grants scopes says so, and only what it says.
    monkeypatch.setenv("EUROGAS_NEXUS_AGENT_DATA_SCOPES", "ENTSOG, EEX")
    granted = _agent_context()
    assert list(granted.data_scopes) == ["ENTSOG", "EEX"]

    # An explicitly empty grant stays empty rather than falling back to a wildcard.
    monkeypatch.setenv("EUROGAS_NEXUS_AGENT_DATA_SCOPES", "")
    assert list(_agent_context().data_scopes) == []
