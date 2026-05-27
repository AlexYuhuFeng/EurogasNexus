# V1 Milestone 8 Release Contract ExecPlan

## 1. Goal
Add release-focused contract checks to enforce profile and policy boundaries.

## 2. Non-goals
- No deployment implementation.
- No auth/governance runtime implementation.
- No business feature delivery.

## 3. Product Boundary
Contract and documentation hardening for release-readiness gates only.

## 4. Files To Create Or Modify
- `.agent/plans/V1_M8_RELEASE_CONTRACT_EXECPLAN.md`
- `tests/release/test_release_readiness_contract.py`
- `docs/release/V1_RELEASE_READINESS.md`
- `docs/operations/VALIDATION.md`

## 5. Dependency Policy
No new dependencies.

## 6. Data Policy
No data-path behavior changes.

## 7. API Impact
None (contract checks only).

## 8. DB Impact
None.

## 9. Tests
- `tests/release/test_release_readiness_contract.py`

## 10. Validation Commands
ruff check .
pytest -q tests/api tests/contract tests/integration tests/sdk tests/cli tests/release
python -c "from apps.api.main import app; print('app import ok'); print(len(app.routes))"

## 11. Acceptance Criteria
- Release profile contract checks run under tests/release.
- Release readiness doc reflects validated/partial items with explicit scope.

## 12. Rollback Notes
Revert release test/docs additions.
