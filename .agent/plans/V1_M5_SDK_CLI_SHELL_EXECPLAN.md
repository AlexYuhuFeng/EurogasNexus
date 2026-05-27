# V1 Milestone 5 SDK/CLI Shell ExecPlan

## 1. Goal
Add minimal SDK and CLI read-only health-check shell that calls backend API only.

## 2. Non-goals
- No mutating operations.
- No direct domain/module access from SDK/CLI.
- No business feature commands.

## 3. Product Boundary
SDK/CLI remain thin API clients for research-only backend surfaces.

## 4. Files To Create Or Modify
- `.agent/plans/V1_M5_SDK_CLI_SHELL_EXECPLAN.md`
- `src/eurogas_nexus/sdk/health_client.py`
- `src/eurogas_nexus/sdk/__init__.py`
- `src/eurogas_nexus/cli/health.py`
- `src/eurogas_nexus/cli/__init__.py`
- `docs/contracts/15_SDK_CLI_CONTRACT.md`
- `docs/contracts/19_FUNCTION_SIGNATURE_CATALOG.md`
- `tests/sdk/test_health_client.py`
- `tests/cli/test_health_cli.py`

## 5. Dependency Policy
Use existing dependencies only (httpx, pytest).

## 6. Data Policy
No local-file fallback; API is source for SDK/CLI data reads.

## 7. API Impact
No new API routes.

## 8. DB Impact
None.

## 9. Tests
- `tests/sdk/test_health_client.py`
- `tests/cli/test_health_cli.py`

## 10. Validation Commands
ruff check .
pytest -q tests/api tests/contract tests/integration tests/sdk tests/cli
python -c "from apps.api.main import app; print('app import ok'); print(len(app.routes))"

## 11. Acceptance Criteria
- SDK health client uses backend HTTP API.
- CLI health command uses SDK/API only.
- No direct domain module calls in SDK/CLI.

## 12. Rollback Notes
Revert SDK/CLI shell files and docs/tests updates.
