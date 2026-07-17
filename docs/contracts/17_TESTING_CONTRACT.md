# Testing Contract

## Purpose

Tests protect product boundaries before feature behavior exists.

Tests must not call external APIs, live connectors, LLM providers, or use real
vendor data. Use fixtures and dry-run behavior for all bootstrap tests.

## Test Taxonomy

- `tests/unit`: isolated unit behavior.
- `tests/integration`: database or adapter integration tests.
- `tests/api`: API app and route tests.
- `tests/sdk`: SDK tests.
- `tests/cli`: CLI tests.
- `tests/workflow`: application workflow tests.
- `tests/security`: authorization and security tests.
- `tests/contract`: repository, import, and architecture boundary tests.
- `tests/release`: release packaging tests.
- `tests/streaming`: future streaming contract tests.

## Current Required Checks

```powershell
ruff check .
pytest -q tests/api tests/contract tests/integration tests/ingestion tests/unit tests/optimization tests/sdk tests/cli tests/release tests/security
python -c "from apps.api.main import app; print('app import ok'); print(len(app.routes))"
```
