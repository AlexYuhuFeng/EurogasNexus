# V1 Milestone 6 Boundary Hardening ExecPlan

## 1. Goal
Harden SDK/CLI and API boundary contracts to prevent accidental architectural drift.

## 2. Non-goals
- No new business features.
- No new external integrations.
- No API route expansion.

## 3. Product Boundary
Contract-only improvements that verify module boundaries and profile behavior.

## 4. Files To Create Or Modify
- `.agent/plans/V1_M6_BOUNDARY_HARDENING_EXECPLAN.md`
- `tests/contract/test_sdk_cli_boundary.py`
- `tests/api/test_api_profiles.py`
- `docs/contracts/06_API_CONTRACT.md`
- `docs/contracts/15_SDK_CLI_CONTRACT.md`

## 5. Dependency Policy
Use existing stack only.

## 6. Data Policy
No data source behavior changes.

## 7. API Impact
No routes added; verify profile gating behavior.

## 8. DB Impact
None.

## 9. Tests
- `tests/contract/test_sdk_cli_boundary.py`
- `tests/api/test_api_profiles.py`

## 10. Validation Commands
ruff check .
pytest -q tests/api tests/contract tests/integration tests/sdk tests/cli
python -c "from apps.api.main import app; print('app import ok'); print(len(app.routes))"

## 11. Acceptance Criteria
- SDK/CLI contract tests prove no domain-module coupling.
- API profile tests verify docs/openapi exposure rules.
- Existing suites remain green.

## 12. Rollback Notes
Revert boundary tests/docs and this plan file.
