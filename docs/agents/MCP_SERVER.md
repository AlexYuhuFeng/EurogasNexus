# MCP Server (CR-15)

Source: `src/eurogas_nexus/mcp/server.py`.

## Adapter boundary

MCP request -> MCP adapter -> Capability Registry -> authorization ->
domain service -> typed `CapabilityResult`.

The server contains no business logic and no SQL. Legacy read/sandbox tool
names remain as compatibility aliases; duplicate names are owned by the
registry.

## Deployment profile gate (first-customer-pilot finding CA-05)

Customer-facing deployments do not offer MCP tools. The server resolves the
deployment profile through the authoritative settings (`EUROGAS_NEXUS_ENV`,
`EUROGAS_NEXUS_API_PROFILE`) and refuses tool discovery and invocation when the
profile is `trial`/`release` or the API profile is `release`:

- `initialize` still succeeds (protocol handshake, server info) but offers no
  `tools` capability and carries the refusal reason in `instructions`;
- `tools/list` returns an empty tool list;
- `tools/call` returns a JSON-RPC error (`-32000`, data
  `{"code": "mcp_tools_disabled"}`) before the tool lookup, the audit write, the
  capability runtime, the SDK and any provider/network call;
- the exported handlers (`TOOLS`, `TOOLS_BY_NAME`) refuse direct invocation with
  `MCPToolAccessDisabled`, so reaching a tool without the JSON-RPC dispatcher is
  not a bypass.

An unknown or malformed profile fails closed (refused, never treated as
development), and no environment flag, role or data-scope grant re-enables the
surface: `EUROGAS_NEXUS_AGENT_ROLE`, `EUROGAS_NEXUS_AGENT_DATA_SCOPES` and
tokens are not authority for this gate. Development (`development`, `test`) and
the `internal` API profile keep the existing read-only tool surface. This is a
pilot-scope mitigation, not a permanent retirement of the MCP surface and not a
security acceptance: the persisted MCP service identity of architecture decision
D6 remains open work, and the tools still act as a deployment-configured service
principal, never the calling user. The headless worker identity of D7 now
resolves a deployment-named persisted SERVICE principal and re-checks it at the
provider boundary before any credential load or provider call; its production
provisioning and revocation evidence remains open.

Deployments that are intended to be customer-facing must state the release
profile explicitly (`deploy/runtime/compose.yaml` sets both variables); an unset
profile is the documented development default and says nothing about safety.
This is an adapter deployment control, not a boundary against a host operator
who can change those variables or invoke underlying application code. Backend
API authentication remains independently required; persisted service identity
is still necessary before offering MCP to customers.

## Tool inventory

The MCP `tools/list` response is generated from active registry definitions
with `mcp_name` set (e.g. `resolve_entity`, `get_market_snapshot`,
`compute_hub_spread`, `calculate_route_economics`,
`validate_strategy_ir`, `run_strategy_backtest`).

## Principal context

- `EUROGAS_NEXUS_AGENT_PRINCIPAL` (default `service:mcp`)
- `EUROGAS_NEXUS_AGENT_ROLE` (default `ANALYST`)
- `EUROGAS_NEXUS_AGENT_DATA_SCOPES` (comma list; default empty - no commercial
  grant, so an unconfigured server cannot read licensed families)

There is no AI-admin principal and no bypass path.

## Guardrails

- No `run_sql`, no table-row tools.
- No execution/order/nomination tool names.
- `RUNTIME_DECISION` legacy sandbox tools remain rejected.
- Permission/entitlement/schema failures return structured JSON in tool text.
