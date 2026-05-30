# V1 Milestone 2 DB Runtime Hardening ExecPlan

## 1. Goal

Make the Eurogas Nexus DB runtime boundary operator-ready while preserving
import safety and avoiding business-domain expansion.

## Internet Requirement

Internet required: no

Reason: This milestone uses local Python code, SQLAlchemy/Alembic behavior,
repository docs, and local tests. No external documentation or live service is
required.

Fallback if offline: Not needed.

## 2. Non-goals

- No market data, topology, route-cost, netback, feasibility, allocation,
  strategy, nowcast, monitoring, or reporting business features.
- No frontend, desktop, Node, Rust, Kafka, Redis, Celery, or live connector
  work.
- No Docker startup.
- No automatic migration execution.
- No automatic migration execution.
- No implicit live DB migration during import, API startup, or default tests.

## 3. Product boundary

This milestone strengthens the backend foundation. PostgreSQL remains runtime
truth. A real local PostgreSQL instance is an explicit V1 runtime-readiness
target when the operator configures a safe DB URL, but app import must continue
to work without DB credentials or network access.

## 4. Files to create/modify

- `src/eurogas_nexus/db/registry.py`
- `src/eurogas_nexus/db/health.py`
- `src/eurogas_nexus/db/session.py`
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

## 5. Dependency policy

No new dependencies.

## 6. Data policy

No real data. No vendor data. No raw market data. No committed credentials.
Synthetic fixtures only if needed.

## 7. API impact

No new public business routes. Health routes remain unchanged.

## 8. DB impact

No business schemas. No automatic migrations. DB checks are read-only and
operator-invoked. The live PostgreSQL path must be documented and safe to run
against a local real PostgreSQL database when a DB URL is configured.

## 9. Tests

Required tests:

- DB URL precedence and blank handling.
- DB URL redaction.
- missing DB URL fails closed.
- `SELECT 1` connectivity check is read-only.
- live DB validation skips or reports clearly when no URL is configured.
- Alembic env imports metadata safely.
- app import does not require DB.
- required table registry is deterministic.
- runtime store contracts expose result metadata fields for future DB-backed
  reads.

## 10. Validation commands

```powershell
ruff check .
pytest -q tests/integration/test_db_config.py tests/integration/test_db_health.py tests/integration/test_alembic_import_safe.py tests/security/test_db_url_redaction.py tests/contract/test_db_runtime_hardening.py
pytest -q tests/api tests/contract tests/integration tests/security
python -c "from apps.api.main import app; print('app import ok'); print(len(app.routes))"
```

## 11. Acceptance criteria

- DB runtime docs clearly explain operator validation.
- Runtime validation script never prints full DB URLs.
- Runtime validation script performs no writes.
- Required table registry is tied to known migration expectations.
- Live PostgreSQL validation is documented as an explicit operator action.
- Default tests remain DB-free.
- Runtime store contract exists for future repository work.
- App import remains DB-connection free.
- Targeted validation passes.

## 12. Rollback notes

Revert the DB runtime hardening docs, reports, runtime store contract additions,
and tests. No DB rollback is required because this milestone does not execute
migrations.
