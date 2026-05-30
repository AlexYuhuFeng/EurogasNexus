# CLI M1 Operator Commands Implementation Plan

> **For agentic workers:** Optional helper skills may be used if available, but
> this plan is fully executable by plain Claude Code CLI. Follow the checkbox
> tasks in order and update them as evidence is produced.

**Goal:** Build the first safe CLI command surface for backend health and runtime validation.

**Architecture:** CLI code lives in `src/eurogas_nexus/cli` and calls SDK/API clients. It does not import business internals.

**Tech Stack:** Python standard library plus approved project dependencies. Add a command framework only if a CLI milestone explicitly approves it.

---

## Activation Gate

Do not execute this plan until SDK M1 is complete or the selected CLI work can
call the existing SDK health helper safely.

## Internet Requirement

Internet required: no.

Reason: Initial CLI work can use Python standard library and existing SDK
helpers.

Fallback if offline: Not needed.

## Non-goals

- No mutating commands without explicit `--execute` guards.
- No direct DB business access.
- No vendor API or LLM calls.
- No order, trade, nomination, approval, or execution commands.
- No secrets printed.

## Files To Create Or Modify

- `src/eurogas_nexus/cli/__init__.py`
- `src/eurogas_nexus/cli/health.py`
- `src/eurogas_nexus/cli/runtime.py`
- `src/eurogas_nexus/cli/output.py`
- `tests/cli/test_health_cli.py`
- `tests/cli/test_runtime_cli.py`
- `tests/contract/test_sdk_cli_boundary.py`
- `docs/clients/CLI_CLIENT_DESIGN_SPEC.md`
- `data/cli_m1/cli_m1_report.md`

## Task 1: Write Boundary And Output Tests

- [ ] Assert CLI modules call SDK/API helpers rather than domain/application/DB
  internals.
- [ ] Assert JSON output is valid for runtime status helpers.
- [ ] Assert full DB URLs and passwords are redacted.

## Task 2: Implement Output Helpers

- [ ] Add compact human output helpers.
- [ ] Add JSON output helpers.
- [ ] Add `COMPLETE`, `PARTIAL`, `BLOCKED`, and `ERROR` status conventions.

## Task 3: Implement Health Helper

- [ ] Keep existing health helper compatible.
- [ ] Ensure errors are compact and secret-safe.
- [ ] Ensure output can be adapted into future command framework.

## Task 4: Implement Runtime Validation Helper

- [ ] Wrap read-only DB validation script behavior where appropriate.
- [ ] Do not run migrations.
- [ ] Do not print full DB URLs.
- [ ] Return non-zero-equivalent status data for missing URL, unreachable DB,
  and missing required tables.

## Validation

```powershell
ruff check .
pytest -q tests/cli tests/contract/test_sdk_cli_boundary.py tests/security/test_db_url_redaction.py
python -c "from apps.api.main import app; print('app import ok'); print(len(app.routes))"
```

## Acceptance Criteria

- CLI is API/SDK-backed.
- CLI is read-only by default.
- Secrets are redacted.
- Tests pass.
- No business feature or execution behavior is added.

## Rollback Notes

Revert CLI files, tests, and `data/cli_m1`.
