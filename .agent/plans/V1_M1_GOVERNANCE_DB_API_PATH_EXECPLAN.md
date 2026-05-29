# V1 Milestone 1 Governance, DB Foundation, and API Path Normalization ExecPlan

## 1. Goal

Prepare Eurogas Nexus for systematic DB-first backend development by adding
repository governance, import-safe DB runtime helpers, Alembic safety defaults,
a non-destructive runtime DB validation script, and an API path normalization
policy.

## 2. Non-goals

- No trade execution, order entry, order routing, trade capture, nomination
  submission, official approval, legal advice, official trading
  recommendations, auto-trading, or ETRM replacement behavior.
- No frontend, desktop client, Node tooling, Kafka, Redis, Celery, live
  connectors, external API calls, LLM provider calls, or company SSO/OIDC.
- No live DB migrations or Docker startup.
- No real data, vendor data, internal business data, secrets, credentials, or
  strategy parameters.

## 3. Product boundary

This milestone is repository and runtime foundation only. PostgreSQL remains
the runtime source of truth, but all DB access must be explicit, lazy, and
non-destructive. Existing later-milestone scaffolding in this worktree is
preserved where it does not conflict with the Milestone 1 guardrails.

## 4. Files to create/modify

- Create `.github/workflows/ci.yml`
- Create `.github/pull_request_template.md`
- Create `.github/ISSUE_TEMPLATE/bug_report.md`
- Create `.github/ISSUE_TEMPLATE/feature_request.md`
- Create `SECURITY.md`
- Create `CONTRIBUTING.md`
- Create `docs/operations/LOCAL_DEVELOPMENT.md`
- Modify `docs/operations/DB_MIGRATIONS.md`
- Modify `docs/operations/VALIDATION.md`
- Create `docs/api/API_PATH_POLICY.md`
- Create `data/milestone_1/api_path_normalization_plan.md`
- Create `data/milestone_1/milestone_1_report.md`
- Create `data/milestone_1/db_foundation_report.json`
- Create `data/milestone_1/remaining_gaps.md`
- Modify `src/eurogas_nexus/db/__init__.py`
- Modify `src/eurogas_nexus/db/session.py`
- Create `src/eurogas_nexus/db/health.py`
- Create `src/eurogas_nexus/db/registry.py`
- Create `src/eurogas_nexus/db/models/__init__.py`
- Move existing SQLAlchemy model exports from `src/eurogas_nexus/db/models.py`
  into the models package if required by Python import behavior.
- Modify `src/eurogas_nexus/core/config.py`
- Modify `alembic.ini`
- Modify `alembic/env.py`
- Create `alembic/versions/.gitkeep`
- Create `scripts/ops/validate_v1_runtime_db.py`
- Modify `src/eurogas_nexus/api/routes/v1/health.py`
- Modify `src/eurogas_nexus/api/routes/internal/router.py`
- Modify `src/eurogas_nexus/api/routes/internal/health.py`
- Modify `src/eurogas_nexus/api/routes/dev/router.py`
- Modify `src/eurogas_nexus/api/routes/dev/health.py`
- Modify `src/eurogas_nexus/api/route_registration.py`
- Create/update tests under `tests/api`, `tests/contract`,
  `tests/integration`, and `tests/security`.

## 5. Dependency policy

Use only the existing approved stack: Python, FastAPI, Pydantic, SQLAlchemy,
Alembic, HTTPX, pytest, and Ruff. Do not add heavy or restricted-license
dependencies.

## 6. Data policy

No real data is added. Reports and tests use synthetic metadata only. Runtime
validation may read DB metadata when explicitly invoked by an operator, but it
does not write data, run migrations, or print secrets.

## 7. API impact

Preserve `GET /v1/health`. Add low-risk `GET /api/v1/health` compatibility
alias using the same handler. Normalize future policy so stable clients and SDKs
target `/api/v1`, internal routes use `/api/internal`, and dev routes use
`/api/dev`.

## 8. DB impact

No schema migration is executed. Add URL resolution, redaction, lazy engine and
session helpers, registry metadata, connectivity checks, and Alembic revision
inspection. Required table checks are read-only.

## 9. Tests

- `tests/integration/test_db_config.py`
- `tests/integration/test_db_health.py`
- `tests/integration/test_alembic_import_safe.py`
- `tests/security/test_db_url_redaction.py`
- `tests/api/test_api_path_policy.py`
- `tests/contract/test_import_boundaries.py`
- Update existing API profile tests where path prefixes are intentionally
  normalized.

## 10. Validation commands

```powershell
ruff check .
pytest -q tests/api tests/contract tests/integration tests/security
python -c "from apps.api.main import app; print('app import ok'); print(len(app.routes))"
```

## 11. Acceptance criteria

- Governance files and CI workflow exist.
- DB foundation functions exist and are import-safe.
- DB URL precedence is implemented and tested:
  `RUNTIME_STORE_DATABASE_URL`, then `DATABASE_URL`, then legacy
  `EUROGAS_NEXUS_DB_DSN`.
- DB URL redaction never exposes passwords.
- App import works without a DB URL.
- Alembic metadata import is safe and no migrations run during import.
- Runtime DB validation script is read-only and supports `--json`.
- `/v1/health` and `/api/v1/health` work.
- Ruff and targeted tests pass.

## 12. Rollback notes

Revert the governance docs/workflow, DB helper additions, validation script,
API path alias, and milestone reports. No DB rollback is needed because this
milestone does not run migrations or write to a database.
