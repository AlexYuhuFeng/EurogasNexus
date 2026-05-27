# V1 Milestone 15 Ingestion Contract ExecPlan

## 1. Goal
Add ingestion shell contracts and tests to enforce traceability and no-live-dependency boundaries.

## 2. Non-goals
- No live connector integration.
- No scheduled pulls.
- No production ETL pipelines.

## 3. Product Boundary
Contract-shell only for ingestion payload and normalization outputs.

## 4. Files To Create Or Modify
- `.agent/plans/V1_M15_INGESTION_CONTRACT_EXECPLAN.md`
- `src/eurogas_nexus/ingestion/contracts.py`
- `src/eurogas_nexus/ingestion/__init__.py`
- `src/eurogas_nexus/ingestion/normalization/contracts.py`
- `src/eurogas_nexus/ingestion/normalization/__init__.py`
- `docs/contracts/10_INGESTION_ETL_CONTRACT.md`
- `docs/contracts/19_FUNCTION_SIGNATURE_CATALOG.md`
- `tests/ingestion/test_ingestion_contracts.py`
- `docs/operations/VALIDATION.md`

## 5. Dependency Policy
No new dependencies.

## 6. Data Policy
No silent local-file fallback semantics; traceability fields required by contract shell.

## 7. API Impact
None.

## 8. DB Impact
None.

## 9. Tests
- `tests/ingestion/test_ingestion_contracts.py`

## 10. Validation Commands
ruff check .
pytest -q tests/api tests/contract tests/integration tests/sdk tests/cli tests/release tests/security tests/workflow tests/streaming tests/unit tests/ingestion
python -c "from apps.api.main import app; print('app import ok'); print(len(app.routes))"

## 11. Acceptance Criteria
- Ingestion shell types include source traceability fields.
- Contract tests enforce no-live-dependency language and research-safe shell defaults.

## 12. Rollback Notes
Revert ingestion shell/tests/docs and this plan.
