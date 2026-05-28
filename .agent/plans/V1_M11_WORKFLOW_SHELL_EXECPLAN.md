# V1 Milestone 11 Workflow Shell ExecPlan

## 1. Goal
Add a minimal application workflow shell for ingestion-run lookup with explicit repository abstraction boundaries.

## 2. Non-goals
- No business analytics logic.
- No direct DB/session usage in workflow.
- No API route additions.

## 3. Product Boundary
Application-layer orchestration shell only; persistence remains behind repository contract.

## 4. Files To Create Or Modify
- `.agent/plans/V1_M11_WORKFLOW_SHELL_EXECPLAN.md`
- `src/eurogas_nexus/application/workflows/ingestion_runs.py`
- `src/eurogas_nexus/application/workflows/__init__.py`
- `docs/contracts/08_APPLICATION_WORKFLOW_CONTRACT.md`
- `docs/contracts/19_FUNCTION_SIGNATURE_CATALOG.md`
- `tests/workflow/test_ingestion_run_workflow.py`
- `docs/operations/VALIDATION.md`

## 5. Dependency Policy
No new dependencies.

## 6. Data Policy
No local fallback paths; workflow consumes repository abstraction only.

## 7. API Impact
None.

## 8. DB Impact
None (workflow layer only).

## 9. Tests
- `tests/workflow/test_ingestion_run_workflow.py`

## 10. Validation Commands
ruff check .
pytest -q tests/api tests/contract tests/integration tests/sdk tests/cli tests/release tests/security tests/workflow
python -c "from apps.api.main import app; print('app import ok'); print(len(app.routes))"

## 11. Acceptance Criteria
- Workflow function composes repository contract without DB/session coupling.
- Workflow tests pass and validate boundary behavior.

## 12. Rollback Notes
Revert workflow shell, docs updates, and workflow tests.
