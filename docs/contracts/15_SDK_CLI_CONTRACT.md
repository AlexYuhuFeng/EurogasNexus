# SDK CLI Contract

## Purpose

`src/eurogas_nexus/sdk` and `packages/python-sdk` are reserved for the required
V1 Python SDK. `src/eurogas_nexus/cli` is reserved for operational commands
that call the SDK/API.

## Bootstrap State

The SDK and CLI expose a read-only health shell. Future expansion is governed by
`docs/clients/SDK_CLIENT_DESIGN_SPEC.md`,
`docs/clients/CLI_CLIENT_DESIGN_SPEC.md`,
`.agent/plans/SDK_M1_API_CLIENT_EXECPLAN.md`, and
`.agent/plans/CLI_M1_OPERATOR_COMMANDS_EXECPLAN.md`.

## Rules

- SDK methods must target documented API contracts.
- CLI commands must be safe by default and require explicit confirmation for
  mutating operations.
- SDK and CLI tests belong under `tests/sdk` and `tests/cli`.
- SDK and CLI code must call the backend API, not internal domain modules.
- CLI should call the SDK first for runtime data, and may call `/api/v1`
  directly only for a documented SDK gap.
- SDK and CLI must preserve research metadata, warnings, missing inputs, source
  references, lineage, `research_only`, and `human_review_required` when the
  backend provides them.

## Forbidden In Bootstrap

- Publishing SDK packages.
- Adding command frameworks.
- Implementing mutating operational commands.


## Milestone 5 Additions

- SDK exposes read-only `fetch_health(base_url)` API client.
- CLI exposes read-only `run_health_check(base_url)` helper.
- Both SDK and CLI call backend HTTP API surfaces only.


## Milestone 6 Additions

- AST-level boundary tests verify SDK/CLI do not import domain or application modules.
