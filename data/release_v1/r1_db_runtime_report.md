# R1: DB Runtime Foundation Report

**Milestone ID:** R1
**Status:** COMPLETE
**Date:** 2026-05-29

## Evidence

- App import works without DB: `apps.api.main` does not load `eurogas_nexus.db` or `sqlalchemy`.
- DB URL precedence: `RUNTIME_STORE_DATABASE_URL` > `DATABASE_URL` > `EUROGAS_NEXUS_DB_DSN`.
- DB URL redaction tested: passwords replaced with `***` in logs, reports, and errors.
- Required table registry: `alembic_version` (0001_m2_baseline), `ingestion_runs` (0002_m4_create_ingestion_runs).
- Runtime validation is read-only: `SELECT 1`, `information_schema.tables`, and `alembic_version` queries only.
- Live PostgreSQL validation is documented as an explicit operator action (`scripts/ops/validate_v1_runtime_db.py`).
- Default tests remain DB-free: no test requires PostgreSQL.
- Runtime store contracts: `ResultEnvelope`, `RepositoryFactory`, `_no_file_fallback_in_trial_or_release`.
- Alembic env imports metadata safely without running migrations.

## Files Changed

- `src/eurogas_nexus/db/registry.py`
- `src/eurogas_nexus/db/health.py`
- `src/eurogas_nexus/db/__init__.py`
- `src/eurogas_nexus/runtime_store/contracts.py`
- `scripts/ops/validate_v1_runtime_db.py`
- `docs/operations/LIVE_POSTGRESQL_V1.md`
- `docs/operations/DB_RUNTIME_HARDENING.md`
- `docs/operations/DB_MIGRATIONS.md`
- `docs/contracts/04_DB_CONTRACT.md`
- `docs/contracts/05_RUNTIME_STORE_CONTRACT.md`
- `data/milestone_2/db_runtime_hardening_report.md`
- `data/milestone_2/db_runtime_hardening_report.json`
- `tests/integration/test_db_config.py`
- `tests/integration/test_db_health.py`
- `tests/integration/test_alembic_import_safe.py`
- `tests/contract/test_db_runtime_hardening.py`
- `tests/security/test_db_url_redaction.py`

## DB Impact

No business schemas. No automatic migrations. DB checks are read-only and operator-invoked.
Required table registry is tied to migration revisions `0001_m2_baseline` and `0002_m4_create_ingestion_runs`.

## API Impact

No new public business routes. Health routes remain unchanged.

## Validation

```powershell
ruff check .
pytest -q tests/api tests/contract tests/integration tests/security tests/sdk tests/cli
python -c "from apps.api.main import app; print('app import ok'); print(len(app.routes))"
```

## Next Milestone

R2: Runtime Store and Governance Foundation
