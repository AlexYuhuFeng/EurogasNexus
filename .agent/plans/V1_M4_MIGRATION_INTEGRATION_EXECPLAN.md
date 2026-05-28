# V1 Milestone 4 Migration + Integration ExecPlan

## 1. Goal
Add first concrete schema migration for ingestion run metadata and validate migration/repository behavior with integration checks.

## 2. Non-goals
- No business analytics or recommendations.
- No new API routes.
- No import-time DB/network operations.

## 3. Product Boundary
This milestone is persistence lifecycle validation only: migration chain and DB integration checks.

## 4. Files To Create Or Modify
- `.agent/plans/V1_M4_MIGRATION_INTEGRATION_EXECPLAN.md`
- `alembic/versions/0002_m4_create_ingestion_runs.py`
- `docs/operations/DB_MIGRATIONS.md`
- `docs/contracts/04_DB_CONTRACT.md`
- `tests/contract/test_db_migrations_contract.py`
- `tests/integration/test_ingestion_runs_repository.py`

## 5. Dependency Policy
Use approved existing stack only.

## 6. Data Policy
PostgreSQL remains runtime source of truth. Tests may use isolated temporary DB for lifecycle checks only.

## 7. API Impact
None.

## 8. DB Impact
Adds DDL migration for `ingestion_runs`; validates repository read contract against real SQLAlchemy session.

## 9. Tests
- `tests/contract/test_db_migrations_contract.py`
- `tests/integration/test_ingestion_runs_repository.py`
- existing suites.

## 10. Validation Commands
ruff check .
pytest -q tests/api tests/contract tests/integration
python -c "from apps.api.main import app; print('app import ok'); print(len(app.routes))"

## 11. Acceptance Criteria
- Migration file exists and chains to baseline.
- Migration declares expected ingestion run columns.
- Integration test validates repository mapping against persisted row.

## 12. Rollback Notes
Revert migration and tests/docs if required; no production migration execution in this milestone.
