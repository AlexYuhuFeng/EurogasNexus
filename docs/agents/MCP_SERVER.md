# MCP Server (CR-15)

Source: `src/eurogas_nexus/mcp/server.py`.

## Adapter boundary

MCP request -> MCP adapter -> Capability Registry -> authorization ->
domain service -> typed `CapabilityResult`.

The server contains no business logic and no SQL. Legacy read/sandbox tool
names remain as compatibility aliases; duplicate names are owned by the
registry.

## Tool inventory

The MCP `tools/list` response is generated from active registry definitions
with `mcp_name` set (e.g. `resolve_entity`, `get_market_snapshot`,
`compute_hub_spread`, `calculate_route_economics`,
`validate_strategy_ir`, `run_strategy_backtest`).

## Principal context

- `EUROGAS_NEXUS_AGENT_PRINCIPAL` (default `service:mcp`)
- `EUROGAS_NEXUS_AGENT_ROLE` (default `ANALYST`)
- `EUROGAS_NEXUS_AGENT_DATA_SCOPES` (comma list; default `*`)

There is no AI-admin principal and no bypass path.

## Guardrails

- No `run_sql`, no table-row tools.
- No execution/order/nomination tool names.
- `RUNTIME_DECISION` legacy sandbox tools remain rejected.
- Permission/entitlement/schema failures return structured JSON in tool text.
