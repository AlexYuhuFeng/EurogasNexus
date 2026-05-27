# V1 Milestone 14 API Profile Contract ExecPlan

## 1. Goal
Harden API profile separation contracts for v1/internal/dev route packages.

## 2. Non-goals
- No new business endpoints.
- No auth/governance runtime implementation.
- No DB behavior changes.

## 3. Product Boundary
Profile and route-registration contract hardening only.

## 4. Files To Create Or Modify
- `.agent/plans/V1_M14_API_PROFILE_CONTRACT_EXECPLAN.md`
- `src/eurogas_nexus/api/routes/internal/router.py`
- `src/eurogas_nexus/api/routes/dev/router.py`
- `src/eurogas_nexus/api/route_registration.py`
- `docs/api/API_PROFILES.md`
- `docs/contracts/06_API_CONTRACT.md`
- `tests/api/test_route_registration_profiles.py`
- `docs/operations/VALIDATION.md`

## 5. Dependency Policy
No new dependencies.

## 6. Data Policy
No data-path changes.

## 7. API Impact
No new public endpoints; profile-gated empty routers are explicitly wired.

## 8. DB Impact
None.

## 9. Tests
- `tests/api/test_route_registration_profiles.py`

## 10. Validation Commands
ruff check .
pytest -q tests/api tests/contract tests/integration tests/sdk tests/cli tests/release tests/security tests/workflow tests/streaming tests/unit
python -c "from apps.api.main import app; print('app import ok'); print(len(app.routes))"

## 11. Acceptance Criteria
- Route registration explicitly handles v1/internal/dev package routers by profile flags.
- Tests validate dev/internal routes are absent in release and currently absent in development until endpoints are added.

## 12. Rollback Notes
Revert profile contract files/tests/docs.
