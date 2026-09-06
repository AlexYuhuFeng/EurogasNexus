# Agent Capability Contract

Source of truth:
`src/eurogas_nexus/application/agents/registry.py` and
`src/eurogas_nexus/domain/agents/contracts.py`. CR-14 research contracts in
`src/eurogas_nexus/domain/research/capabilities.py` remain available as the
dataset capability family.

## Purpose

Agents (human co-pilots and future MCP adapters) call typed, permission-aware
analytical capabilities. They never receive DB table access, raw SQL, or UI
internals. MCP is an adapter in CR-15; this contract is transport-neutral and
does not depend on MCP being present.

## Registered capabilities

| Capability | Class | Side effect | Permission |
|---|---|---|---|
| `ontology.resolve_entity` | read_only_compute | none | research.read |
| `ontology.describe_entity` | read | none | research.read |
| `data.get_series_metadata` | read | none | research.read |
| `data.get_observations_as_of` | read_only_compute | none | research.read |
| `analytics.get_feature_definition` | read | none | research.read |
| `dataset.validate_spec` | read_only_compute | none | research.read |
| `dataset.build` | write_materialized | persists_snapshot | research.dataset.build |
| `dataset.inspect_snapshot` | read | none | research.read |
| `dataset.temporal_integrity_report` | read | none | research.read |
| `dataset.export` | export | persists_snapshot | research.dataset.export |

Each contract carries JSON input/output schemas, determinism flags,
freshness/provenance behavior, timeout seconds, and documented error codes.

## Invariants

- No capability name is a SQL table or column.
- Read capabilities never mutate state.
- `dataset.build` persists immutable snapshots with content hash, lineage,
  leakage issues, and dependency versions.
- `dataset.export` checks the snapshot entitlement envelope and returns
  `EXPORT_DENIED_ENTITLEMENT` or `EXPORT_DENIED_UNKNOWN_POLICY` rather than
  exporting silently.
- Capability descriptions do not expose SQL statements.

## Boundary

- Capabilities may answer research questions and materialize snapshots; they
  never place orders, submit nominations, or trigger execution.
- A future MCP server must adapt these contracts without adding a second,
  divergent semantic layer.

## CR-15 runtime registry

See [CAPABILITY_REGISTRY.md](CAPABILITY_REGISTRY.md). The runtime exposes 68
active capabilities with versioned metadata, discovery, permission/
entitlement gates, and MCP tool names. Capability version is recorded on
every ToolInvocation and AgentRun replay.
