# SDK M1 API Client Implementation Plan

> **For agentic workers:** Optional helper skills may be used if available, but
> this plan is fully executable by plain Claude Code CLI. Follow the checkbox
> tasks in order and update them as evidence is produced.

**Goal:** Expand the Python SDK into a safe typed API client shell for stable `/api/v1` backend routes.

**Architecture:** SDK code lives in `src/eurogas_nexus/sdk` and calls the backend API only. Packaging under `packages/python-sdk` remains deferred.

**Tech Stack:** Python, HTTPX, Pydantic, pytest, Ruff.

---

## Activation Gate

Do not execute this plan until backend API response contracts are stable enough
for the selected SDK methods.

## Internet Requirement

Internet required: no.

Reason: The repository already declares the approved Python stack.

Fallback if offline: Not needed.

## Non-goals

- No SDK package publishing.
- No direct DB access.
- No imports from domain, application, runtime store, or DB internals.
- No vendor API or LLM calls.
- No trading, order, nomination, approval, or execution methods.

## Files To Create Or Modify

- `src/eurogas_nexus/sdk/client.py`
- `src/eurogas_nexus/sdk/config.py`
- `src/eurogas_nexus/sdk/errors.py`
- `src/eurogas_nexus/sdk/models.py`
- `src/eurogas_nexus/sdk/health_client.py`
- `src/eurogas_nexus/sdk/runtime_client.py`
- `src/eurogas_nexus/sdk/__init__.py`
- `tests/sdk/test_sdk_client.py`
- `tests/sdk/test_health_client.py`
- `tests/contract/test_sdk_cli_boundary.py`
- `packages/python-sdk/README.md`
- `data/sdk_m1/sdk_m1_report.md`

## Task 1: Write Boundary Tests

- [ ] Assert SDK modules do not import `eurogas_nexus.domain`,
  `eurogas_nexus.application`, `eurogas_nexus.runtime_store`, or
  `eurogas_nexus.db`.
- [ ] Assert health client uses `/api/v1/health`.
- [ ] Assert SDK exceptions redact secret-like URL parts.

## Task 2: Implement Client Config And Errors

- [ ] Add base URL normalization.
- [ ] Add timeout configuration.
- [ ] Add typed exceptions for connection, timeout, HTTP status, validation,
  restricted, partial feature, and unexpected errors.
- [ ] Ensure string representations are secret-safe.

## Task 3: Implement Health And Runtime Clients

- [ ] Keep existing health behavior compatible.
- [ ] Add runtime status client only if backend route exists; otherwise add an
  explicit `PartialFeatureError`.
- [ ] Preserve backend response metadata when present.

## Task 4: Update SDK README And Report

- [ ] Document supported methods.
- [ ] Document unsupported planned methods.
- [ ] Document no-direct-DB/no-vendor/no-execution policy.
- [ ] Write `data/sdk_m1/sdk_m1_report.md`.

## Validation

```powershell
ruff check .
pytest -q tests/sdk tests/contract/test_sdk_cli_boundary.py
python -c "from apps.api.main import app; print('app import ok'); print(len(app.routes))"
```

## Acceptance Criteria

- SDK targets `/api/v1`.
- SDK is API-only.
- SDK errors are secret-safe.
- Tests pass.
- Packaging remains deferred.

## Rollback Notes

Revert SDK files, tests, package README changes, and `data/sdk_m1`.
