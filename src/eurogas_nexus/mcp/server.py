"""Read-only MCP server for Eurogas Nexus (Model Context Protocol, stdio).

Exposes decision-support read tools to LLM agents using the documented MCP
stdio transport (JSON-RPC 2.0). Every tool calls the backend through the SDK
and therefore inherits the release-profile auth gates (API token + principal
from the environment). There are NO write tools, no provider/LLM invocations,
and RUNTIME_DECISION contexts are rejected — this server is a read-side
consumer exactly like the CLI.

Protocol implemented: ``initialize``, ``notifications/initialized``,
``tools/list``, ``tools/call``. No new dependencies.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "eurogas-nexus-mcp"
SERVER_VERSION = "0.1.0"

DEFAULT_BASE_URL = "http://localhost:8000"

# Runtime decision contexts are never available through MCP tools.
_RUNTIME_DECISION = "RUNTIME_DECISION"


def _base_url() -> str:
    import os

    return os.environ.get("EUROGAS_NEXUS_API_BASE_URL", DEFAULT_BASE_URL).rstrip("/")


# ---------------------------------------------------------------------------
# Tool registry (read-only)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MCPTool:
    """One read-only MCP tool registration.

    Attributes:
        name: Tool name (JSON-RPC method id).
        description: Human-readable description for clients.
        input_schema: JSON Schema of the tool arguments.
        handler: Callable mapping arguments to a result.
    """

    name: str
    description: str
    input_schema: dict[str, Any]
    handler: Callable[[dict[str, Any]], Any]


def _tool_list_sources(arguments: dict[str, Any]) -> Any:
    from eurogas_nexus.sdk.sources import fetch_sources

    return fetch_sources(_base_url())


def _tool_market_observations(arguments: dict[str, Any]) -> Any:
    from eurogas_nexus.sdk.market import fetch_market_observations

    return fetch_market_observations(_base_url())


def _tool_fx_rates(arguments: dict[str, Any]) -> Any:
    from eurogas_nexus.sdk.market import fetch_fx_rates

    return fetch_fx_rates(_base_url())


def _tool_glossary_term(arguments: dict[str, Any]) -> Any:
    from eurogas_nexus.sdk.glossary import fetch_term

    term = str(arguments.get("term") or "").strip()
    if not term:
        raise ValueError("term is required")
    return fetch_term(_base_url(), term, lang=str(arguments.get("lang") or "en"))


def _tool_ontology(arguments: dict[str, Any]) -> Any:
    from eurogas_nexus.sdk.analysis import fetch_business_ontology

    return fetch_business_ontology(_base_url())


def _tool_review_decisions(arguments: dict[str, Any]) -> Any:
    from eurogas_nexus.sdk.review import fetch_review_decisions

    result = fetch_review_decisions(
        _base_url(),
        entity_type=arguments.get("entity_type"),
        entity_id=arguments.get("entity_id"),
        limit=int(arguments.get("limit") or 100),
    )
    return [row.model_dump() for row in result.data]


def _tool_calculate_route_cost(arguments: dict[str, Any]) -> Any:
    from eurogas_nexus.sdk.route_cost import calculate_route_cost

    result = calculate_route_cost(_base_url(), **arguments)
    return result.model_dump()


def _tool_optimize_route_sandbox(arguments: dict[str, Any]) -> Any:
    from eurogas_nexus.sdk.optimization import optimize_route

    decision_context = arguments.get("decision_context") or "SANDBOX_SCENARIO"
    if decision_context == _RUNTIME_DECISION:
        raise ValueError("RUNTIME_DECISION is not available through MCP tools")
    result = optimize_route(
        _base_url(),
        source=str(arguments["source"]),
        target=str(arguments["target"]),
        required_capacity_mwh=float(arguments["required_capacity_mwh"]),
        edges=arguments.get("edges") or [],
        accessible_tsos=arguments.get("accessible_tsos"),
        decision_context="SANDBOX_SCENARIO",
    )
    return result.data.model_dump()


TOOLS: tuple[MCPTool, ...] = (
    MCPTool(
        name="list_sources",
        description="List registered data sources with runtime posture and freshness.",
        input_schema={"type": "object", "properties": {}, "additionalProperties": False},
        handler=_tool_list_sources,
    ),
    MCPTool(
        name="get_market_observations",
        description="List recent normalized market observations (hub, tenor, price, FX->GBP).",
        input_schema={"type": "object", "properties": {}, "additionalProperties": False},
        handler=_tool_market_observations,
    ),
    MCPTool(
        name="get_fx_rates",
        description="List reference FX rates (EUR base).",
        input_schema={"type": "object", "properties": {}, "additionalProperties": False},
        handler=_tool_fx_rates,
    ),
    MCPTool(
        name="get_glossary_term",
        description="Look up one bilingual glossary term.",
        input_schema={
            "type": "object",
            "properties": {
                "term": {"type": "string"},
                "lang": {"type": "string", "enum": ["en", "zh-CN"]},
            },
            "required": ["term"],
            "additionalProperties": False,
        },
        handler=_tool_glossary_term,
    ),
    MCPTool(
        name="get_business_ontology",
        description="Return the typed business ontology (concepts, relations, guardrails).",
        input_schema={"type": "object", "properties": {}, "additionalProperties": False},
        handler=_tool_ontology,
    ),
    MCPTool(
        name="get_review_decisions",
        description="List trader review decisions (evidence trail).",
        input_schema={
            "type": "object",
            "properties": {
                "entity_type": {"type": "string"},
                "entity_id": {"type": "string"},
                "limit": {"type": "integer"},
            },
            "additionalProperties": False,
        },
        handler=_tool_review_decisions,
    ),
    MCPTool(
        name="calculate_route_cost",
        description=(
            "Calculate a route-cost scenario from tariff legs (decision support, "
            "research-only)."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "scenario_id": {"type": "string"},
                "source_resource_type": {"type": "string"},
                "start_point_id": {"type": "string"},
                "target_hub_or_point_id": {"type": "string"},
                "business_model": {"type": "string"},
                "gas_year": {"type": "string"},
                "capacity_product": {"type": "string"},
                "firmness": {"type": "string"},
                "tariff_legs": {"type": "array", "items": {"type": "object"}},
            },
            "required": [
                "scenario_id",
                "source_resource_type",
                "start_point_id",
                "target_hub_or_point_id",
                "business_model",
                "gas_year",
                "capacity_product",
                "firmness",
            ],
            "additionalProperties": False,
        },
        handler=_tool_calculate_route_cost,
    ),
    MCPTool(
        name="optimize_route_sandbox",
        description=(
            "What-if route optimization over client-supplied edges "
            "(SANDBOX_SCENARIO only; runtime decisions are not exposed)."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "source": {"type": "string"},
                "target": {"type": "string"},
                "required_capacity_mwh": {"type": "number"},
                "edges": {"type": "array", "items": {"type": "object"}},
                "accessible_tsos": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["source", "target", "required_capacity_mwh"],
            "additionalProperties": False,
        },
        handler=_tool_optimize_route_sandbox,
    ),
)

TOOLS_BY_NAME: dict[str, MCPTool] = {tool.name: tool for tool in TOOLS}


# ---------------------------------------------------------------------------
# JSON-RPC 2.0 dispatch
# ---------------------------------------------------------------------------


def _error(request_id: Any, code: int, message: str, data: Any = None) -> str:
    payload: dict[str, Any] = {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": code, "message": message},
    }
    if data is not None:
        payload["error"]["data"] = data
    return json.dumps(payload)


def handle_jsonrpc_line(line: str) -> str | None:
    """Handle one JSON-RPC message; return the response line or None."""

    try:
        message = json.loads(line)
    except ValueError:
        return _error(None, -32700, "Parse error")
    if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
        return _error(None, -32600, "Invalid Request")

    request_id = message.get("id")
    method = message.get("method")
    if method is None:
        return _error(request_id, -32600, "Invalid Request")

    if method == "initialize":
        return json.dumps(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "protocolVersion": PROTOCOL_VERSION,
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
                },
            }
        )
    if method == "notifications/initialized":
        return None
    if method == "tools/list":
        return json.dumps(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "tools": [
                        {
                            "name": tool.name,
                            "description": tool.description,
                            "inputSchema": tool.input_schema,
                        }
                        for tool in TOOLS
                    ]
                },
            }
        )
    if method == "tools/call":
        params = message.get("params") or {}
        tool_name = params.get("name")
        tool = TOOLS_BY_NAME.get(tool_name or "")
        if tool is None:
            return _error(request_id, -32602, f"Unknown tool: {tool_name!r}")
        arguments = params.get("arguments") or {}
        if not isinstance(arguments, dict):
            return _error(request_id, -32602, "arguments must be an object")
        try:
            result = tool.handler(arguments)
        except Exception as exc:  # tool failures are reported, not fatal
            return json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "content": [
                            {"type": "text", "text": f"tool error: {exc}"}
                        ],
                        "isError": True,
                    },
                }
            )
        return json.dumps(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(
                                result, ensure_ascii=False, default=str
                            ),
                        }
                    ],
                    "isError": False,
                },
            }
        )
    return _error(request_id, -32601, f"Method not found: {method!r}")


def run_stdio() -> int:
    """Read JSON-RPC messages from stdin and write responses to stdout."""

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        response = handle_jsonrpc_line(line)
        if response is not None:
            print(response, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(run_stdio())
