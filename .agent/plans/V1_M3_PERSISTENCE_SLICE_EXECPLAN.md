# V1 Milestone 3 Persistence Slice ExecPlan

## 1. Goal
Add a minimal non-business persistence slice for ingestion run metadata using PostgreSQL-oriented contracts.

## 2. Non-goals
- No market analytics/business features.
- No API route expansion.
- No live DB calls in import-time code.

## 3. Product Boundary
This milestone introduces neutral persistence artifacts only: ingestion run metadata model and repository boundary.

## 4. Files To Create Or Modify
- `.agent/plans/V1_M3_PERSISTENCE_SLICE_EXECPLAN.md`
- `src/eurogas_nexus/db/base.py`
- `src/eurogas_nexus/db/models.py`
- `src/eurogas_nexus/db/repositories.py`
- `src/eurogas_nexus/db/__init__.py`
- `docs/contracts/04_DB_CONTRACT.md`
- `docs/contracts/19_FUNCTION_SIGNATURE_CATALOG.md`
- `tests/contract/test_db_persistence_slice.py`

## 5. Dependency Policy
Use existing approved stack only.

## 6. Data Policy
PostgreSQL remains source of truth. No local file fallback semantics added.

## 7. API Impact
No new routes.

## 8. DB Impact
Add SQLAlchemy model metadata and repository protocol/adapter for ingestion run records.

## 9. Tests
- `tests/contract/test_db_persistence_slice.py`
- Existing tests unchanged.

## 10. Validation Commands
ruff check .
pytest -q tests/api tests/contract
python -c "from apps.api.main import app; print('app import ok'); print(len(app.routes))"

## 11. Acceptance Criteria
- DB model and repository contracts compile/import safely.
- Repository boundary does not leak Session to domain consumers.
- Existing API/import safety checks remain green.

## 12. Rollback Notes
Revert new DB model/repository files and docs updates.
