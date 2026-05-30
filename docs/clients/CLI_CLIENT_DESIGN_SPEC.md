# CLI Client Design Spec

## Objective

The CLI is the operator and automation command surface for Eurogas Nexus. It
accesses runtime data through the Python SDK or backend API and provides safe
commands for health, runtime validation, source status, research workflow
inspection, and release checks.

## Product Boundary

The CLI is an API/operations client only.

Preferred data path:

```text
CLI -> Python SDK -> backend /api/v1 -> backend repositories -> PostgreSQL
```

Direct CLI calls to `/api/v1` are allowed only when the SDK does not yet expose
the selected route and the gap is documented.

It must not:

- import domain, application, runtime store, or DB internals for business
  behavior;
- read PostgreSQL directly except through explicitly documented ops scripts;
- call vendor APIs;
- call LLM providers;
- create orders, trades, nominations, approvals, or execution records;
- print secrets, full DB URLs, tokens, `.env`, or credentials.

## Source Location

```text
src/eurogas_nexus/cli/
```

## Command Style

CLI commands should be boring and explicit.

Rules:

- read-only commands are default;
- any future write-like command requires an explicit `--execute` guard;
- dry-run is default when a command could change state;
- output must be human-readable by default and support `--json` where useful;
- exit codes must distinguish success, partial, blocked, and error states.

## Initial Command Groups

### Health

Purpose:

- check backend health through SDK/API.

Example:

```powershell
eurogas-nexus health --base-url http://localhost:8000
```

Current implementation has a helper, not a full command framework.

### Runtime

Purpose:

- show runtime status and DB readiness through backend/API or ops validation
  scripts.

Future examples:

```powershell
eurogas-nexus runtime status --base-url http://localhost:8000 --json
eurogas-nexus runtime db-validate --json
```

### Sources

Purpose:

- inspect configured source posture, entitlement, and freshness.

No live connector execution unless a connector milestone explicitly allows it.

### Reference Network

Purpose:

- inspect reference-network entities and source/lineage metadata.

### Scenario

Purpose:

- validate scenario files or stdin against backend scenario validation.

No trade execution or nomination language.

### Research

Purpose:

- retrieve research outputs when backend slices exist.

Outputs must preserve assumptions, missing inputs, warnings, source references,
lineage, `research_only`, and `human_review_required`.

### Release

Purpose:

- run local validation packs and release-readiness checks.

Release commands must fail closed if secrets or raw data are detected.

## Output Rules

Human output:

- compact status lines;
- warnings visible near the top;
- redacted URLs;
- explicit `PARTIAL` and `BLOCKED` labels.

JSON output:

- stable keys;
- no secrets;
- includes `status`, `warnings`, `missing_inputs`, and `source_references` when
  applicable.

## Testing

CLI tests live under:

```text
tests/cli/
```

Required tests:

- CLI calls SDK/API, not domain internals;
- health command targets `/api/v1`;
- write-like commands require `--execute`;
- secret redaction is applied;
- JSON output is valid when `--json` is requested.

## First CLI Implementation Prompt

Use after SDK M1 exists:

```text
Read AGENTS.md, docs/clients/CLI_CLIENT_DESIGN_SPEC.md, docs/clients/SDK_CLIENT_DESIGN_SPEC.md, docs/contracts/15_SDK_CLI_CONTRACT.md, and .agent/plans/CLI_M1_OPERATOR_COMMANDS_EXECPLAN.md. Implement CLI M1 only. Keep commands safe, read-only by default, API-backed, and secret-redacted. Do not add mutating operational commands without explicit --execute guards.
```
