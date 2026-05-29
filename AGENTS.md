# Eurogas Nexus Agent Guide

Eurogas Nexus is a research-only European gas decision-support platform. This
repository is in the V1.0 release preparation phase for a DB-first, API-first,
SDK-required internal platform covering European pipeline gas, LNG reGas, and
beach delivery resource research. V1 includes the backend/API, PostgreSQL
runtime store, Python SDK, CLI, web workspace, and Windows client shell.

## Guardrails

- PostgreSQL is the runtime source of truth.
- Local files may be import templates, raw/canonical archives, reports,
  fixtures, or development fallback only.
- Trial and release modes must not silently fall back to local files.
- API routes must remain separated into stable `v1`, `internal`, and `dev`
  profiles.
- SDK and CLI code must call the backend API, not internal domain modules.
- Clients access PostgreSQL-backed runtime data only through SDK/API
  boundaries. No client opens PostgreSQL connections, imports backend
  DB/runtime-store modules, or reads backend local data files directly.
- Connectors must not perform analytics.
- Domain modules must not import FastAPI.
- Streaming/Kafka is optional and must not become a source of truth.
- Vendor entitlement and export policy must fail closed for unknown commercial
  data.
- Analysis outputs must include assumptions, missing inputs, warnings, source
  references, lineage, `research_only`, and `human_review_required` where
  relevant.
- Do not add business features until a milestone document allows them.
- Do not call external APIs, market data providers, LLM providers, or live
  infrastructure from import-time code or tests.
- Do not add frontend, desktop, Node, Rust, Tauri, or client runtime
  dependencies during backend foundation milestones. These dependencies are
  allowed only inside selected web or Windows client milestones with documented
  dependency review and offline fallback.
- Do not add Kafka, Redis, Celery, company SSO/OIDC, or live connector
  dependencies in V1 unless a later milestone explicitly scopes and reviews
  them.
- Do not add trade execution, order entry, order routing, trade capture,
  nomination submission, official approval, legal advice, official trading
  recommendations, auto-trading, ETRM replacement behavior, or company SSO/OIDC
  in V1.
- Keep DB and runtime-store modules import-safe; importing the API must not
  open network sockets or database connections.
- Update contracts before broadening a module boundary.

## Dependency Policy

Allowed backend default stack: Python, FastAPI, Pydantic, SQLAlchemy, Alembic,
PostgreSQL, HTTPX, pandas, NumPy, PyArrow, python-dateutil, PyYAML, pytest, and
Ruff. Do not add dependencies unless they are necessary, permissive-licensed,
and documented.

Allowed client stack only when a selected client milestone requires it: React,
TypeScript, Vite, plain CSS or CSS modules, MapLibre GL where available, Rust,
and Tauri for the Windows shell. Electron is not approved for V1.

Do not add GPL, LGPL, AGPL, SSPL, BUSL, Elastic, Redis-RSAL, Commons-Clause, or
PolyForm dependencies without explicit review.

## Planning

Before large changes, create or update an ExecPlan under `.agent/plans/`. Each
milestone plan must include:

1. Goal
2. Non-goals
3. Product boundary
4. Files to create/modify
5. Dependency policy
6. Data policy
7. API impact
8. DB impact
9. Tests
10. Validation commands
11. Acceptance criteria
12. Rollback notes

Do not implement beyond the milestone scope. If a requirement is unclear, create
a gap report instead of inventing behavior. If a live external API would be
needed, mock it and document credential requirements. If DB is unavailable, app
import must still pass. If a feature is incomplete, report `PARTIAL` or
`BLOCKED` honestly.

## Validation

Run these checks before handing over changes:

```powershell
ruff check .
pytest -q tests/api tests/contract
python -c "from apps.api.main import app; print('app import ok'); print(len(app.routes))"
```
