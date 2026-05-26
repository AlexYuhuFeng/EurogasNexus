# V1 Bootstrap ExecPlan

## 1. Goal

Bootstrap Eurogas Nexus as a research-only, DB-first, API-first, SDK-ready
backend monorepo for European pipeline gas, LNG reGas, and beach delivery
resource research.

The milestone creates product structure, architecture contracts, policy docs,
minimal Python packaging, and an import-safe FastAPI health shell. It does not
implement business features.

## 2. Non-goals

- No business analytics or recommendation features.
- No external API calls or LLM provider calls.
- No frontend, desktop, React, Tauri, Electron, or Node tooling.
- No Redis, Celery, Kafka dependency, or live streaming runtime.
- No live connectors or vendor data pulls.
- No trade execution, order entry, order routing, trade capture, nomination
  submission, official approval, legal advice, official trading
  recommendation, auto-trading, ETRM replacement, or company SSO/OIDC.

## 3. Product Boundary

Eurogas Nexus V1 is an internal research support backend. It may organize data,
serve API responses, prepare future workflow boundaries, and support future SDK
clients.

It must not present itself as an official trading system, legal advisory system,
approval system, ETRM replacement, execution system, or nomination submission
system. Any future analysis output must carry assumptions, missing inputs,
warnings, source references, lineage, `research_only`, and
`human_review_required` where relevant.

## 4. Files To Create Or Modify

- Root files: `pyproject.toml`, `README.md`, `.gitignore`, `.env.example`,
  `AGENTS.md`.
- Agent plans: `.agent/PLANS.md`, `.agent/plans/V1_BOOTSTRAP_EXECPLAN.md`.
- App shells: `apps/api`, `apps/worker`, `apps/scheduler`.
- Backend package: `src/eurogas_nexus`.
- Contract docs: `docs/contracts`.
- Policy and operating docs: `docs/architecture`, `docs/policies`,
  `docs/api`, `docs/operations`, `docs/compliance`, `docs/release`.
- Placeholder product roots: `clients`, `packages`, `release`, `dist`,
  `infra`, `tests`, `scripts`, `data`, `alembic`.

## 5. Dependency Policy

Allowed default stack: Python, FastAPI, Pydantic, SQLAlchemy, Alembic,
PostgreSQL, HTTPX, pandas, NumPy, PyArrow, python-dateutil, PyYAML, pytest, and
Ruff.

This milestone uses only the minimal runtime and dev dependencies needed for the
API shell and tests: FastAPI, Pydantic, SQLAlchemy, Alembic, HTTPX, pytest, and
Ruff. Heavy optional dependencies are deferred.

Do not add GPL, LGPL, AGPL, SSPL, BUSL, Elastic, Redis-RSAL, Commons-Clause, or
PolyForm dependencies without explicit review.

## 6. Data Policy

PostgreSQL is the runtime source of truth. Local files may be import templates,
raw/canonical archives, reports, fixtures, snapshots, or development fallback
only.

Trial and release modes must not silently fall back to local files. Tests must
not use real vendor data, call live external APIs, or call live connectors. Use
fixtures and dry-run behavior.

Vendor entitlement and export policy must fail closed for unknown commercial
data.

## 7. API Impact

Create a minimal FastAPI app factory and expose `app` from `apps.api.main`.

Current public route:

```text
GET /v1/health
```

Development and release route profiles exist. Stable V1, internal, and
development-only routes remain separated by package and profile. No business
routes are created.

## 8. DB Impact

No database connection is required at import time. No engine, session, model, or
migration behavior is implemented in this milestone.

The `src/eurogas_nexus/db` package and `alembic/` directory are reserved for a
future PostgreSQL-backed persistence milestone.

## 9. Tests

- `tests/api/test_app_import.py`
- `tests/api/test_health_api.py`
- `tests/contract/test_product_boundary.py`

Tests cover app import, health route behavior, expected product directories,
forbidden dependency tokens, and import-time DB isolation.

## 10. Validation Commands

```powershell
ruff check .
pytest -q tests/api tests/contract
python -c "from apps.api.main import app; print('app import ok'); print(len(app.routes))"
```

## 11. Acceptance Criteria

- `from apps.api.main import app` works.
- The app exposes a health route at `/v1/health`.
- Development and release API profiles exist.
- API import does not require DB, network, secrets, external APIs, or LLM calls.
- Repository topology matches the V1 bootstrap contract.
- Contracts and policy docs capture research-only, DB-first, API-first,
  SDK-ready boundaries.
- Deferred or unavailable runtime pieces are reported honestly as `PARTIAL` or
  `BLOCKED`.

## 12. Rollback Notes

This milestone is structural. Rollback can remove the created files and
directories without data migration.

If dependency installation fails or tooling is unavailable, keep source and docs
intact, report validation as `BLOCKED`, and rerun validation once the Python
environment has FastAPI, pytest, and Ruff installed.

