# V1 Milestone 7 Docs + Ownership Alignment ExecPlan

## 1. Goal
Align repository documentation and ownership matrix with implemented Milestones 2-6 artifacts.

## 2. Non-goals
- No runtime feature additions.
- No API/DB behavior changes.
- No new dependencies.

## 3. Product Boundary
Documentation and contract alignment only.

## 4. Files To Create Or Modify
- `.agent/plans/V1_M7_DOCS_ALIGNMENT_EXECPLAN.md`
- `docs/contracts/20_MODULE_OWNERSHIP_MATRIX.md`
- `docs/operations/VALIDATION.md`
- `README.md`
- `tests/contract/test_docs_alignment.py`

## 5. Dependency Policy
Use existing dependencies only.

## 6. Data Policy
No data path changes.

## 7. API Impact
None.

## 8. DB Impact
None.

## 9. Tests
- `tests/contract/test_docs_alignment.py`
- existing validation suites.

## 10. Validation Commands
ruff check .
pytest -q tests/api tests/contract tests/integration tests/sdk tests/cli
python -c "from apps.api.main import app; print('app import ok'); print(len(app.routes))"

## 11. Acceptance Criteria
- Docs reflect active DB/SDK/CLI and test surface status.
- Validation docs reflect current required command set.
- Contract test guards key alignment points.

## 12. Rollback Notes
Revert docs and associated contract tests.
