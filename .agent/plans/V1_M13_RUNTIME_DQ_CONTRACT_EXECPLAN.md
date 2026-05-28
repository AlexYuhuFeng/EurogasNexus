# V1 Milestone 13 Runtime-Store + Data-Quality Contract ExecPlan

## 1. Goal
Add import-safe interface shells for runtime store and data quality, with contract tests enforcing non-authoritative and deterministic boundaries.

## 2. Non-goals
- No Redis/cache adapters.
- No live quality gate enforcement in API.
- No business workflows.

## 3. Product Boundary
Interface-only additions; no operational adapters.

## 4. Files To Create Or Modify
- `.agent/plans/V1_M13_RUNTIME_DQ_CONTRACT_EXECPLAN.md`
- `src/eurogas_nexus/runtime_store/contracts.py`
- `src/eurogas_nexus/runtime_store/__init__.py`
- `src/eurogas_nexus/data_quality/contracts.py`
- `src/eurogas_nexus/data_quality/__init__.py`
- `docs/contracts/05_RUNTIME_STORE_CONTRACT.md`
- `docs/contracts/11_DATA_QUALITY_CONTRACT.md`
- `docs/contracts/19_FUNCTION_SIGNATURE_CATALOG.md`
- `tests/unit/test_runtime_store_contracts.py`
- `tests/unit/test_data_quality_contracts.py`
- `docs/operations/VALIDATION.md`

## 5. Dependency Policy
No new dependencies.

## 6. Data Policy
Runtime store remains non-authoritative; data quality checks are deterministic/read-only.

## 7. API Impact
None.

## 8. DB Impact
None.

## 9. Tests
- `tests/unit/test_runtime_store_contracts.py`
- `tests/unit/test_data_quality_contracts.py`

## 10. Validation Commands
ruff check .
pytest -q tests/api tests/contract tests/integration tests/sdk tests/cli tests/release tests/security tests/workflow tests/streaming tests/unit
python -c "from apps.api.main import app; print('app import ok'); print(len(app.routes))"

## 11. Acceptance Criteria
- Runtime store and data quality shells are import-safe and dependency-free.
- Unit/contract tests enforce core boundary statements.

## 12. Rollback Notes
Revert shell files/tests/docs updates.
