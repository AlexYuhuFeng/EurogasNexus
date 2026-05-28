# V1 Milestone 2 DB Foundation ExecPlan

## 1. Goal

Establish an import-safe PostgreSQL persistence foundation for Eurogas Nexus V1
without introducing business features.

## 2. Non-goals

- No domain/business models or analytics.
- No runtime DB connection attempts during module import.
- No live external API, vendor, or connector calls.
- No expansion of API surface beyond existing shell behavior.

## 3. Product Boundary

This milestone only provides persistence boundaries, configuration, and migration
scaffolding. It does not implement business workflows or data products.

## 4. Files To Create Or Modify

- `.agent/plans/V1_M2_DB_FOUNDATION_EXECPLAN.md`
- `src/eurogas_nexus/core/config.py`
- `src/eurogas_nexus/db/settings.py`
- `src/eurogas_nexus/db/engine.py`
- `src/eurogas_nexus/db/session.py`
- `src/eurogas_nexus/db/base.py`
- `src/eurogas_nexus/db/__init__.py`
- `alembic.ini`
- `alembic/env.py`
- `alembic/script.py.mako`
- `alembic/versions/0001_m2_baseline.py`
- `tests/contract/test_db_foundation.py`

## 5. Dependency Policy

Use existing approved dependencies only (SQLAlchemy, Alembic, Pydantic, pytest,
Ruff). No new third-party libraries.

## 6. Data Policy

PostgreSQL remains runtime source of truth. Local files are scaffolding only.
No fixture or code path may imply silent local-file fallback in trial/release.

## 7. API Impact

No new routes. Existing API import and `/v1/health` behavior remain unchanged.

## 8. DB Impact

Introduce lazy engine/session factories. Engine creation is callable at runtime,
not import time. Add Alembic baseline scaffolding and empty baseline revision.

## 9. Tests

- `tests/contract/test_db_foundation.py`
- Existing API and contract tests unchanged.

## 10. Validation Commands

```powershell
ruff check .
pytest -q tests/api tests/contract
python -c "from apps.api.main import app; print('app import ok'); print(len(app.routes))"
```

## 11. Acceptance Criteria

- DB modules import without opening DB/network sockets.
- Engine/session factories are available and lazy.
- Alembic baseline files exist and parse correctly.
- API import contract remains valid.

## 12. Rollback Notes

Remove the added DB scaffold modules and Alembic files; restore prior placeholders.
No data migration rollback needed because no runtime migrations are executed.


## Post-implementation Hardening

- Normalize DB configuration around `DatabaseSettings` as the canonical runtime type.
- Add env parsing edge-case tests for DB booleans and blank DSN normalization.
- Add dedicated import-safety test ensuring API import does not import DB/SQLAlchemy modules.
