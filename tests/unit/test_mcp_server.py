"""MCP server JSON-RPC dispatch tests (P3, stdlib only)."""

import json

from eurogas_nexus.mcp.server import (
    TOOLS,
    TOOLS_BY_NAME,
    handle_jsonrpc_line,
)


def _send(request: dict) -> dict:
    response = handle_jsonrpc_line(json.dumps(request))
    assert response is not None
    return json.loads(response)


def test_initialize_handshake() -> None:
    result = _send(
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
    )
    assert result["result"]["protocolVersion"] == "2024-11-05"
    assert result["result"]["serverInfo"]["name"] == "eurogas-nexus-mcp"


def test_initialized_notification_gets_no_response() -> None:
    response = handle_jsonrpc_line(
        json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"})
    )
    assert response is None


def test_tools_list_declares_read_only_tools() -> None:
    result = _send({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    names = [tool["name"] for tool in result["result"]["tools"]]
    assert "list_sources" in names
    assert "get_market_observations" in names
    assert "calculate_route_cost" in names
    assert "optimize_route_sandbox" in names
    assert "get_weather_stations" in names
    assert "get_hdd_cdd" in names
    assert "optimize_resource_pool_sandbox" in names
    assert "optimize_capacity_sandbox" in names
    assert "optimize_storage_dispatch_sandbox" in names
    assert "optimize_nomination_window_sandbox" in names
    for tool in result["result"]["tools"]:
        assert tool["inputSchema"]["type"] == "object"


def test_tools_call_unknown_tool_returns_error() -> None:
    result = _send(
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "nope", "arguments": {}},
        }
    )
    assert result["error"]["code"] == -32602


def test_tools_call_reports_tool_failures_as_is_error() -> None:
    result = _send(
        {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {"name": "get_glossary_term", "arguments": {}},
        }
    )
    assert result["result"]["isError"] is True
    assert "required" in result["result"]["content"][0]["text"]


def test_tools_call_optimize_sandbox_rejects_runtime_decision() -> None:
    result = _send(
        {
            "jsonrpc": "2.0",
            "id": 5,
            "method": "tools/call",
            "params": {
                "name": "optimize_route_sandbox",
                "arguments": {
                    "source": "A",
                    "target": "B",
                    "required_capacity_mwh": 1,
                    "decision_context": "RUNTIME_DECISION",
                },
            },
        }
    )
    assert result["result"]["isError"] is True
    assert "RUNTIME_DECISION" in result["result"]["content"][0]["text"]


def test_parse_error_and_unknown_method() -> None:
    response = handle_jsonrpc_line("{not json")
    assert json.loads(response)["error"]["code"] == -32700

    result = _send({"jsonrpc": "2.0", "id": 6, "method": "bogus"})
    assert result["error"]["code"] == -32601


def test_tools_are_unique_and_registered(monkeypatch) -> None:
    names = [tool.name for tool in TOOLS]
    assert len(names) == len(set(names))
    assert set(TOOLS_BY_NAME) == set(names)
    # No write tools exist: every handler is read-only by construction.
    assert "optimize_route_sandbox" in TOOLS_BY_NAME


def test_tools_call_list_sources_returns_sdk_data(monkeypatch) -> None:
    def fake_sources(base_url):
        return [{"source_system": "ENTSOG", "connectivity_status": "active"}]

    monkeypatch.setattr("eurogas_nexus_sdk.sources.fetch_sources", fake_sources)

    result = _send(
        {
            "jsonrpc": "2.0",
            "id": 7,
            "method": "tools/call",
            "params": {"name": "list_sources", "arguments": {}},
        }
    )
    assert result["result"]["isError"] is False
    assert '"ENTSOG"' in result["result"]["content"][0]["text"]


def test_tools_call_weather_stations_returns_sdk_data(monkeypatch) -> None:
    def fake_stations(base_url):
        return [{
            "station_id": "ws-1", "name": "Amsterdam", "country": "NL",
            "lat": 52.0, "lon": 4.9,
        }]

    monkeypatch.setattr("eurogas_nexus_sdk.weather.fetch_weather_stations", fake_stations)

    result = _send(
        {
            "jsonrpc": "2.0",
            "id": 10,
            "method": "tools/call",
            "params": {"name": "get_weather_stations", "arguments": {}},
        }
    )
    assert result["result"]["isError"] is False
    assert '"Amsterdam"' in result["result"]["content"][0]["text"]


def test_tools_call_capacity_sandbox_rejects_runtime_decision() -> None:
    result = _send(
        {
            "jsonrpc": "2.0",
            "id": 11,
            "method": "tools/call",
            "params": {
                "name": "optimize_capacity_sandbox",
                "arguments": {
                    "products": [],
                    "required_capacity_mwh": 100,
                    "decision_context": "RUNTIME_DECISION",
                },
            },
        }
    )
    assert result["result"]["isError"] is True
    assert "RUNTIME_DECISION" in result["result"]["content"][0]["text"]
