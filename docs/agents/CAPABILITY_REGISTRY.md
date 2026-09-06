# Capability Registry (CR-15)

Source: `src/eurogas_nexus/application/agents/registry.py`,
contracts in `src/eurogas_nexus/domain/agents/contracts.py`.

## What a capability answers

- What can I do? (`capability_id`, `name`, `domain`, `description`)
- What inputs are required and what does output mean? (`input_schema`,
  `output_schema`)
- Is it deterministic? (`determinism_class`)
- Does it write state? (`side_effect_class`)
- What permission and entitlement are required?
- What freshness/temporal/provenance contract applies?
- What are timeout, retry, and idempotency policies?
- Which version is this? (`capability_id@capability_version`)
- What is the agent action policy (auto / research / confirmation / human)?

## Determinism classes

`DETERMINISTIC`, `MODEL_BASED_DETERMINISTIC_INPUT`,
`LLM_NONDETERMINISTIC`, `OPERATIONAL_STATE_DEPENDENT`.

## Side-effect classes

`READ_ONLY`, `RESEARCH_OBJECT_WRITE`, `OPERATIONAL_WRITE`.
`TRADE_EXECUTION` intentionally does not exist.

## Discovery

- API: `GET /api/capabilities`, `/api/capabilities/search`,
  `/api/capabilities/{id}`.
- MCP: `list_capabilities`, `describe_capability`, `search_capabilities`.
- Search covers id/name/description/domain/tags, never SQL metadata.

## Invocation

`POST /api/capabilities/{id}/invoke` passes the authenticated principal into
the `CapabilityRuntime`. The runtime checks, in order: existence, status,
human-only/human-confirmation policy, permission, entitlement, input schema,
then handler execution. Failures are typed codes, not prose.
