# V1 Milestone 10 Validation Unification ExecPlan

## 1. Goal
Unify validation commands across docs and provide a single runnable validation script.

## 2. Non-goals
- No feature behavior changes.
- No new dependencies.
- No CI platform integration.

## 3. Product Boundary
Operational consistency hardening only.

## 4. Files To Create Or Modify
- `.agent/plans/V1_M10_VALIDATION_UNIFICATION_EXECPLAN.md`
- `scripts/ops/validate_repo.sh`
- `docs/operations/VALIDATION.md`
- `docs/contracts/17_TESTING_CONTRACT.md`
- `README.md`
- `tests/contract/test_validation_consistency.py`

## 5. Dependency Policy
Use existing tools only (bash, python, pytest, ruff).

## 6. Data Policy
No data-path changes.

## 7. API Impact
None.

## 8. DB Impact
None.

## 9. Tests
- `tests/contract/test_validation_consistency.py`

## 10. Validation Commands
ruff check .
pytest -q tests/api tests/contract tests/integration tests/sdk tests/cli tests/release tests/security
python -c "from apps.api.main import app; print('app import ok'); print(len(app.routes))"

## 11. Acceptance Criteria
- Single validation script exists and mirrors documented required checks.
- Testing/operations/readme docs are aligned on required validation command set.

## 12. Rollback Notes
Revert script, docs, and contract tests.
