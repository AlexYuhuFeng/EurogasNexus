"""Read-only MCP server for Eurogas Nexus (Model Context Protocol, stdio).

Exposes decision-support read tools to LLM agents using the documented MCP
stdio transport (JSON-RPC 2.0). Every tool calls the backend through the SDK
and therefore inherits the release-profile auth gates (API token + principal
from the environment). There are NO write tools, no provider/LLM invocations,
and RUNTIME_DECISION contexts are rejected — this server is a read-side
consumer exactly like the CLI.

Protocol implemented: ``initialize``, ``notifications/initialized``,
``tools/list``, ``tools/call``. No new dependencies.

Deployment profile gate (first-customer-pilot finding CA-05): a customer-facing
deployment profile (``trial``/``release`` environment, or the ``release`` API profile)
refuses tool discovery and invocation - the exported tool handlers included - until the
persisted MCP service identity of architecture decision D6 is built. Development and
test worktrees keep the existing read-only surface.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from dataclasses import dataclass, replace
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
# Deployment profile gate (first-customer-pilot finding CA-05)
# ---------------------------------------------------------------------------
#
# MCP tools run as a deployment-configured service identity built from
# ``EUROGAS_NEXUS_AGENT_*`` environment values, and the transport cannot carry the calling
# user's identity (architecture findings C8, decision D6). Until the *persisted* service
# identity exists, a customer-facing deployment does not offer MCP tools at all: an
# environment-granted identity is an unowned authority, and an LLM-facing tool surface
# acting on it is exactly the pilot gap CA-05 records. Development and test worktrees keep
# the existing read-only surface.
#
# The profile is *resolved*, never re-derived: ``Settings`` is the authoritative reader of
# ``EUROGAS_NEXUS_ENV``/``EUROGAS_NEXUS_API_PROFILE`` (validated literals with documented
# defaults), so this gate cannot disagree with what the API itself believes. The allow-list
# below is fail-closed by construction: only the named development profiles enable tools,
# and a profile that cannot be resolved (unknown or malformed) is refused rather than
# treated as the default.

#: Deployment environments whose worktrees keep the development MCP tool surface.
_MCP_TOOL_ENVIRONMENTS = frozenset({"development", "test"})
#: API profiles whose worktrees keep the development MCP tool surface.
_MCP_TOOL_API_PROFILES = frozenset({"development", "internal"})


class MCPToolAccessDisabled(RuntimeError):
    """Raised when a deployment profile that does not offer MCP tools is asked for one.

    Raised rather than returned so an out-of-band caller of an exported tool handler
    (``TOOLS``/``TOOLS_BY_NAME``) cannot mistake the refusal for a tool result.
    """


def tool_access_disabled_reason() -> str | None:
    """Why this deployment does not offer MCP tools, or ``None`` when it does.

    Customer-facing deployments (``trial``/``release`` environment, or the ``release``
    API profile) refuse tool discovery and invocation until the persisted service
    identity of decision D6 exists. The check reads the authoritative settings resolver
    instead of re-reading the environment variables, and fails closed: a profile that
    cannot be resolved (unknown or malformed) is refused, never treated as development.
    """

    from eurogas_nexus.core.config import Settings

    try:
        settings = Settings.from_env()
    except Exception as exc:  # noqa: BLE001 - an unresolvable profile must fail closed
        return (
            "MCP tool access is disabled: the deployment profile could not be resolved "
            f"({type(exc).__name__}); an unknown or malformed profile fails closed."
        )
    if settings.environment not in _MCP_TOOL_ENVIRONMENTS:
        return (
            f"MCP tool access is disabled in the {settings.environment!r} deployment "
            "environment: MCP has no persisted service identity yet (decision D6), so a "
            "customer-facing deployment does not offer its tools."
        )
    if settings.api_profile not in _MCP_TOOL_API_PROFILES:
        return (
            f"MCP tool access is disabled in the {settings.api_profile!r} API profile: "
            "MCP has no persisted service identity yet (decision D6), so a customer-facing "
            "deployment does not offer its tools."
        )
    return None


def _require_tool_access() -> None:
    """Refuse tool invocation unless the deployment profile offers MCP tools."""

    reason = tool_access_disabled_reason()
    if reason is not None:
        raise MCPToolAccessDisabled(reason)


def _access_checked_handler(
    handler: Callable[[dict[str, Any]], Any],
) -> Callable[[dict[str, Any]], Any]:
    """Wrap one tool handler so the profile gate runs before any of its own code.

    The JSON-RPC dispatcher checks the gate before its lookup/audit step, but the handlers
    are exported (``TOOLS``/``TOOLS_BY_NAME``), so a caller can reach them without the
    dispatcher. This wrapper keeps that path honest: in a disabled profile it refuses
    before the handler body - and therefore before any capability runtime, SDK, provider
    or network call - can run.
    """

    def guarded(arguments: dict[str, Any]) -> Any:
        _require_tool_access()
        return handler(arguments)

    return guarded


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
        posture: How the tool is authorised. ``runtime-authorised`` means it invokes a
            registry capability through ``CapabilityRuntime``, which re-authorises the
            principal's permission and entitlement per call. ``deployment-principal``
            means it calls the SDK directly as the deployment's API principal, so it does
            **not** re-authorise per user (finding C8); such a call is audited as running
            outside the capability runtime so an operator can see the bypass in use.
    """

    name: str
    description: str
    input_schema: dict[str, Any]
    handler: Callable[[dict[str, Any]], Any]
    posture: str = "runtime-authorised"


#: The two postures a tool may declare. Anything else is a programming error.
TOOL_POSTURES: frozenset[str] = frozenset({"runtime-authorised", "deployment-principal"})


def _gate_tools(tools: tuple[MCPTool, ...]) -> tuple[MCPTool, ...]:
    """Return the tools with the deployment-profile gate wrapped around every handler."""

    return tuple(
        replace(tool, handler=_access_checked_handler(tool.handler)) for tool in tools
    )


def _tool_list_sources(arguments: dict[str, Any]) -> Any:
    from eurogas_nexus_sdk.sources import fetch_sources

    return fetch_sources(_base_url())


def _tool_market_observations(arguments: dict[str, Any]) -> Any:
    from eurogas_nexus_sdk.market import fetch_market_observations

    return fetch_market_observations(_base_url())


def _tool_fx_rates(arguments: dict[str, Any]) -> Any:
    from eurogas_nexus_sdk.market import fetch_fx_rates

    return fetch_fx_rates(_base_url())


def _tool_glossary_term(arguments: dict[str, Any]) -> Any:
    from eurogas_nexus_sdk.glossary import fetch_term

    term = str(arguments.get("term") or "").strip()
    if not term:
        raise ValueError("term is required")
    return fetch_term(_base_url(), term, lang=str(arguments.get("lang") or "en"))


def _tool_ontology(arguments: dict[str, Any]) -> Any:
    from eurogas_nexus_sdk.analysis import fetch_business_ontology

    return fetch_business_ontology(_base_url())


def _tool_weather_stations(arguments: dict[str, Any]) -> Any:
    from eurogas_nexus_sdk.weather import fetch_weather_stations

    return [
        row.model_dump() if hasattr(row, "model_dump") else row
        for row in fetch_weather_stations(_base_url())
    ]


def _tool_weather_observations(arguments: dict[str, Any]) -> Any:
    from eurogas_nexus_sdk.weather import fetch_weather_observations

    return [
        row.model_dump() if hasattr(row, "model_dump") else row
        for row in fetch_weather_observations(_base_url())
    ]


def _tool_hdd_cdd(arguments: dict[str, Any]) -> Any:
    from eurogas_nexus_sdk.weather import fetch_hdd_cdd

    return [
        row.model_dump() if hasattr(row, "model_dump") else row
        for row in fetch_hdd_cdd(_base_url())
    ]


def _tool_cost_observations(arguments: dict[str, Any]) -> Any:
    from eurogas_nexus_sdk.cost_observations import fetch_cost_observations

    return [
        row.model_dump()
        for row in fetch_cost_observations(
            _base_url(),
            scope_type=arguments.get("scope_type"),
            scope_id=arguments.get("scope_id"),
            as_of=arguments.get("as_of"),
        )
    ]


def _tool_applicable_cost(arguments: dict[str, Any]) -> Any:
    from eurogas_nexus_sdk.cost_observations import resolve_cost_observation

    result = resolve_cost_observation(
        _base_url(),
        scope_type=str(arguments["scope_type"]),
        scope_id=str(arguments["scope_id"]),
        as_of=str(arguments["as_of"]),
        entitlement_scope=arguments.get("entitlement_scope"),
    )
    return result.model_dump()


def _tool_get_optimization_run(arguments: dict[str, Any]) -> Any:
    from eurogas_nexus_sdk.optimization import fetch_optimization_run

    result = fetch_optimization_run(_base_url(), str(arguments["run_id"]))
    return result.data.model_dump()


def _reject_runtime(arguments: dict[str, Any]) -> None:
    if (arguments.get("decision_context") or "SANDBOX_SCENARIO") == _RUNTIME_DECISION:
        raise ValueError("RUNTIME_DECISION is not available through MCP tools")


def _tool_optimize_resource_pool_sandbox(arguments: dict[str, Any]) -> Any:
    from eurogas_nexus_sdk.optimization import optimize_resource_pool

    _reject_runtime(arguments)
    result = optimize_resource_pool(
        _base_url(),
        resources=arguments["resources"],
        sale_options=arguments["sale_options"],
        accessible_tsos=arguments.get("accessible_tsos"),
        portfolio_id=arguments.get("portfolio_id"),
        decision_context="SANDBOX_SCENARIO",
    )
    return result.data.model_dump()


def _tool_optimize_capacity_sandbox(arguments: dict[str, Any]) -> Any:
    from eurogas_nexus_sdk.optimization import optimize_capacity

    _reject_runtime(arguments)
    result = optimize_capacity(
        _base_url(),
        products=arguments["products"],
        required_capacity_mwh=float(arguments["required_capacity_mwh"]),
        expected_throughput_mwh=(
            float(arguments["expected_throughput_mwh"])
            if arguments.get("expected_throughput_mwh") is not None
            else None
        ),
        allow_interruptible=bool(arguments.get("allow_interruptible", True)),
        decision_context="SANDBOX_SCENARIO",
    )
    return result.data.model_dump()


def _tool_optimize_contracts_sandbox(arguments: dict[str, Any]) -> Any:
    from eurogas_nexus_sdk.optimization import optimize_contracts

    _reject_runtime(arguments)
    result = optimize_contracts(
        _base_url(),
        resources=arguments["resources"],
        market_price_gbp_mwh=float(arguments["market_price_gbp_mwh"]),
        demand_limit_mwh=float(arguments["demand_limit_mwh"]),
        decision_context="SANDBOX_SCENARIO",
    )
    return result.data.model_dump()


def _tool_optimize_storage_dispatch_sandbox(arguments: dict[str, Any]) -> Any:
    from eurogas_nexus_sdk.optimization import optimize_storage_dispatch

    _reject_runtime(arguments)
    result = optimize_storage_dispatch(
        _base_url(),
        facility=arguments.get("facility"),
        periods=arguments.get("periods"),
        inventory_step_mwh=float(arguments.get("inventory_step_mwh") or 1.0),
        decision_context="SANDBOX_SCENARIO",
        max_periods=int(arguments.get("max_periods") or 5),
    )
    return result.data.model_dump()


def _tool_optimize_nomination_window_sandbox(arguments: dict[str, Any]) -> Any:
    from eurogas_nexus_sdk.optimization import optimize_nomination_window

    _reject_runtime(arguments)
    result = optimize_nomination_window(
        _base_url(),
        initial_quantity_mwh=float(arguments["initial_quantity_mwh"]),
        instructions=arguments["instructions"],
        windows=arguments.get("windows"),
        decision_context="SANDBOX_SCENARIO",
        gas_day=arguments.get("gas_day"),
    )
    return result.data.model_dump()


def _tool_review_decisions(arguments: dict[str, Any]) -> Any:
    from eurogas_nexus_sdk.review import fetch_review_decisions

    result = fetch_review_decisions(
        _base_url(),
        entity_type=arguments.get("entity_type"),
        entity_id=arguments.get("entity_id"),
        limit=int(arguments.get("limit") or 100),
    )
    return [row.model_dump() for row in result.data]


def _tool_calculate_route_cost(arguments: dict[str, Any]) -> Any:
    from eurogas_nexus_sdk.route_cost import calculate_route_cost

    result = calculate_route_cost(_base_url(), **arguments)
    return result.model_dump()


def _tool_optimize_route_sandbox(arguments: dict[str, Any]) -> Any:
    from eurogas_nexus_sdk.optimization import optimize_route

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


_LEGACY_TOOLS_RAW: tuple[MCPTool, ...] = (
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
        name="get_weather_stations",
        description="List weather stations (empty until a runtime source is ingested).",
        input_schema={"type": "object", "properties": {}, "additionalProperties": False},
        handler=_tool_weather_stations,
    ),
    MCPTool(
        name="get_weather_observations",
        description="List weather observations (empty until a runtime source is ingested).",
        input_schema={"type": "object", "properties": {}, "additionalProperties": False},
        handler=_tool_weather_observations,
    ),
    MCPTool(
        name="get_hdd_cdd",
        description="List heating/cooling degree-day series (empty until ingested).",
        input_schema={"type": "object", "properties": {}, "additionalProperties": False},
        handler=_tool_hdd_cdd,
    ),
    MCPTool(
        name="get_cost_observations",
        description=(
            "List time-windowed route/point/LNG cost observations "
            "(TSO, contract, secondary transfer, auction, slot)."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "scope_type": {"type": "string"},
                "scope_id": {"type": "string"},
                "as_of": {"type": "string"},
            },
            "additionalProperties": False,
        },
        handler=_tool_cost_observations,
    ),
    MCPTool(
        name="get_applicable_cost",
        description=(
            "Resolve the applicable cost for a route/point/LNG terminal using "
            "entitlement priority."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "scope_type": {"type": "string"},
                "scope_id": {"type": "string"},
                "as_of": {"type": "string"},
                "entitlement_scope": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["scope_type", "scope_id", "as_of"],
            "additionalProperties": False,
        },
        handler=_tool_applicable_cost,
    ),
    MCPTool(
        name="get_optimization_run",
        description="Fetch one persisted optimization run for evidence reconstruction.",
        input_schema={
            "type": "object",
            "properties": {"run_id": {"type": "string"}},
            "required": ["run_id"],
            "additionalProperties": False,
        },
        handler=_tool_get_optimization_run,
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
    MCPTool(
        name="optimize_resource_pool_sandbox",
        description=(
            "What-if resource-pool allocation over client-supplied resources and "
            "sale options (SANDBOX_SCENARIO only)."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "portfolio_id": {"type": "string"},
                "resources": {"type": "array", "items": {"type": "object"}},
                "sale_options": {"type": "array", "items": {"type": "object"}},
                "accessible_tsos": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["resources", "sale_options"],
            "additionalProperties": False,
        },
        handler=_tool_optimize_resource_pool_sandbox,
    ),
    MCPTool(
        name="optimize_capacity_sandbox",
        description="What-if capacity product selection (SANDBOX_SCENARIO only).",
        input_schema={
            "type": "object",
            "properties": {
                "products": {"type": "array", "items": {"type": "object"}},
                "required_capacity_mwh": {"type": "number"},
                "expected_throughput_mwh": {"type": "number"},
                "allow_interruptible": {"type": "boolean"},
            },
            "required": ["products", "required_capacity_mwh"],
            "additionalProperties": False,
        },
        handler=_tool_optimize_capacity_sandbox,
    ),
    MCPTool(
        name="optimize_contracts_sandbox",
        description=(
            "What-if daily contract take recommendation over client-supplied "
            "resources (SANDBOX_SCENARIO only)."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "resources": {"type": "array", "items": {"type": "object"}},
                "market_price_gbp_mwh": {"type": "number"},
                "demand_limit_mwh": {"type": "number"},
            },
            "required": ["resources", "market_price_gbp_mwh", "demand_limit_mwh"],
            "additionalProperties": False,
        },
        handler=_tool_optimize_contracts_sandbox,
    ),
    MCPTool(
        name="optimize_storage_dispatch_sandbox",
        description=(
            "What-if storage inject/withdraw/hold assessment "
            "(SANDBOX_SCENARIO only; no booking or nomination action)."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "facility": {"type": "object"},
                "periods": {"type": "array", "items": {"type": "object"}},
                "inventory_step_mwh": {"type": "number"},
                "max_periods": {"type": "integer"},
            },
            "additionalProperties": False,
        },
        handler=_tool_optimize_storage_dispatch_sandbox,
    ),
    MCPTool(
        name="optimize_nomination_window_sandbox",
        description=(
            "Assess nomination/renomination windows against submitted instructions "
            "(SANDBOX_SCENARIO only; nothing is submitted)."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "initial_quantity_mwh": {"type": "number"},
                "instructions": {"type": "array", "items": {"type": "object"}},
                "windows": {"type": "array", "items": {"type": "object"}},
                "gas_day": {"type": "string"},
            },
            "required": ["initial_quantity_mwh", "instructions"],
            "additionalProperties": False,
        },
        handler=_tool_optimize_nomination_window_sandbox,
    ),
)

#: Every legacy tool runs as the deployment's API principal through the SDK, so it does not
#: re-authorise permission or entitlement per user (architecture finding C8). The posture is
#: declared rather than implied: it is published in ``tools/list`` and every call is audited
#: as running outside the capability runtime.
_LEGACY_TOOLS: tuple[MCPTool, ...] = tuple(
    replace(tool, posture="deployment-principal") for tool in _LEGACY_TOOLS_RAW
)

_CAPABILITY_TOOLS: tuple[MCPTool, ...] = ()
_LEGACY_NAMES = {tool.name for tool in _CAPABILITY_TOOLS}
_LEGACY_COMPAT_TOOLS = tuple(tool for tool in _LEGACY_TOOLS if tool.name not in _LEGACY_NAMES)
TOOLS: tuple[MCPTool, ...] = _gate_tools((*_CAPABILITY_TOOLS, *_LEGACY_COMPAT_TOOLS))
TOOLS_BY_NAME: dict[str, MCPTool] = {tool.name: tool for tool in TOOLS}


# ---------------------------------------------------------------------------
# Registry-driven capability tools (CR-15)
# ---------------------------------------------------------------------------


def _published_description(tool: MCPTool) -> str:
    """The description a client sees, with the tool's authorisation posture stated.

    A client cannot infer from a name whether a tool re-authorises per user, so the posture
    is published twice: as a structured field and in the prose a human reads first.
    """

    if tool.posture == "deployment-principal":
        return (
            f"{tool.description} Runs as the deployment's API principal through the SDK: it "
            "does not re-authorise permission or entitlement per user, and every call is "
            "audited as running outside the capability runtime."
        )
    return (
        f"{tool.description} Invokes a registry capability, "
        "which re-authorises the caller per call."
    )


def _audit_deployment_principal_call(tool: MCPTool) -> None:
    """Record a call that ran outside the capability runtime (finding C8).

    Best-effort by construction: the audit service already swallows an unavailable store,
    and an audit failure must never change what the tool returns.
    """

    if tool.posture != "deployment-principal":
        return
    try:
        from eurogas_nexus.application.audit_service import record_audit_event

        record_audit_event(
            event_type="governance.access",
            action="mcp.tool.invoked",
            resource=f"mcp_tool:{tool.name}",
            principal="service:mcp",
            outcome="outside_capability_runtime",
            severity="warning",
            detail=(
                "deployment-principal tool invoked through the SDK; it does not "
                "re-authorise permission or entitlement per user"
            ),
            source_system="mcp",
        )
    except Exception:  # noqa: BLE001 - auditing must never break the tool call
        return


def _agent_context():
    """The principal an MCP capability invocation runs as.

    Architecture V2 finding C8: MCP used to default its data scopes to ``*``, which made an
    unconfigured MCP server a super-user over every commercial family - the opposite of the
    rule that AI inherits the invoking user's authority and has no bypass. The transport
    does not carry a user identity here, so the pseudo-principal cannot inherit anything;
    what it can do is fail closed.

    The default is therefore **no commercial grant**:

    - ``EUROGAS_NEXUS_AGENT_DATA_SCOPES`` must name the families this server may read;
      public baseline families (operator input, ENTSOG, GIE, ECB, weather) stay available
      to any active principal, exactly as they are on the API;
    - ``EUROGAS_NEXUS_AGENT_PRINCIPAL`` and ``EUROGAS_NEXUS_AGENT_ROLE`` still describe
      *who* the server acts as, and a deployment that grants scopes does so deliberately
      rather than by omission.

    Carrying the calling user's identity across the MCP transport, and retiring the legacy
    read/sandbox tools that bypass the capability runtime, remain open halves of C8.
    """

    import os

    from eurogas_nexus.domain.agents.contracts import AgentInvocationContext

    role = os.environ.get("EUROGAS_NEXUS_AGENT_ROLE", "ANALYST")
    scopes = os.environ.get("EUROGAS_NEXUS_AGENT_DATA_SCOPES", "")
    return AgentInvocationContext(
        principal_id=os.environ.get("EUROGAS_NEXUS_AGENT_PRINCIPAL", "service:mcp"),
        role=role,
        roles=[role],
        data_scopes=[item.strip() for item in scopes.split(",") if item.strip()],
    )


def _build_capability_tools():
    from eurogas_nexus.application.agents.registry import register_builtin_capabilities
    from eurogas_nexus.application.agents.runtime import CapabilityRuntime

    registry = register_builtin_capabilities()
    runtime = CapabilityRuntime(registry)
    tools = []
    for definition in registry.list_definitions():
        if not definition.mcp_name:
            continue

        def handler(arguments, _definition=definition):
            result = runtime.invoke(_definition.capability_id, arguments, _agent_context())
            return result.model_dump(mode="json")

        tools.append(
            MCPTool(
                name=definition.mcp_name,
                description=definition.description,
                input_schema=definition.input_schema,
                handler=handler,
            )
        )
    return tuple(tools)


# Rebuild the exported tool list with registry tools first and legacy
# read/sandbox aliases second (duplicate names are registry-owned).
_CAPABILITY_TOOLS = _build_capability_tools()
_LEGACY_NAMES = {tool.name for tool in _CAPABILITY_TOOLS}
_LEGACY_COMPAT_TOOLS = tuple(
    tool for tool in _LEGACY_TOOLS if tool.name not in _LEGACY_NAMES
)
TOOLS: tuple[MCPTool, ...] = _gate_tools((*_CAPABILITY_TOOLS, *_LEGACY_COMPAT_TOOLS))
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
        reason = tool_access_disabled_reason()
        result: dict[str, Any] = {
            "protocolVersion": PROTOCOL_VERSION,
            # A disabled profile offers no tools capability rather than tools a client
            # may not call (the same shape as a server without that capability).
            "capabilities": {"tools": {"listChanged": False}} if reason is None else {},
            "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
        }
        if reason is not None:
            # Say why, rather than leaving the client to infer it from an empty tool list.
            result["instructions"] = reason
        return json.dumps({"jsonrpc": "2.0", "id": request_id, "result": result})
    if method == "notifications/initialized":
        return None
    if method == "tools/list":
        # Empty rather than an error: a client that skipped ``initialize``'s capabilities
        # still learns there is nothing to call, and no handler is reachable from here.
        reason = tool_access_disabled_reason()
        listed: list[dict[str, Any]] = []
        if reason is None:
            listed = [
                {
                    "name": tool.name,
                    "description": _published_description(tool),
                    "inputSchema": tool.input_schema,
                    # Published so a client can see how a tool is authorised rather
                    # than assuming every tool re-authorises per user (finding C8).
                    "posture": tool.posture,
                }
                for tool in TOOLS
            ]
        return json.dumps(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {"tools": listed},
            }
        )
    if method == "tools/call":
        reason = tool_access_disabled_reason()
        if reason is not None:
            # Refuse before the tool lookup, the audit write, the capability runtime, the
            # SDK and every provider/network call: a disabled profile has no path that
            # reaches a tool body, on this transport or through an exported handler.
            return _error(
                request_id,
                -32000,
                reason,
                {"code": "mcp_tools_disabled"},
            )
        params = message.get("params") or {}
        tool_name = params.get("name")
        tool = TOOLS_BY_NAME.get(tool_name or "")
        if tool is None:
            return _error(request_id, -32602, f"Unknown tool: {tool_name!r}")
        arguments = params.get("arguments") or {}
        if not isinstance(arguments, dict):
            return _error(request_id, -32602, "arguments must be an object")
        try:
            _audit_deployment_principal_call(tool)
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
