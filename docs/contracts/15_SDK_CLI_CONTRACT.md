# SDK CLI Contract

## Purpose

`src/eurogas_nexus/sdk` and `packages/python-sdk` are reserved for a future
Python SDK. `src/eurogas_nexus/cli` is reserved for future operational commands.

## Bootstrap State

Only package and directory boundaries exist.

## Rules

- SDK methods must target documented API contracts.
- CLI commands must be safe by default and require explicit confirmation for
  mutating operations.
- SDK and CLI tests belong under `tests/sdk` and `tests/cli`.
- SDK and CLI code must call the backend API, not internal domain modules.

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
