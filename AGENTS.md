# Eurogas Nexus Agent Guide

Eurogas Nexus is a European natural-gas market-intelligence, optimization, and
decision-support platform. This repository is in preview-release hardening for
a DB-first, API-first, SDK-supported product covering European pipeline gas,
LNG regas, storage, and beach-delivery resources. The active product includes
the backend/API, PostgreSQL runtime store, Python SDK, CLI, Web workspace, and
Windows/Linux desktop clients.

## Guardrails

- PostgreSQL is the runtime source of truth.
- Local files may be import templates, raw/canonical archives, reports,
  fixtures, or development fallback only.
- Trial and release modes must not silently fall back to local files.
- Public API routes use the stable unversioned `/api` prefix. Operator-only and
  development-only routes use `/api/internal` and `/api/dev` respectively.
  Do not reintroduce `/v1` or `/api/v1` aliases.
- SDK and CLI code must call the backend API, not internal domain modules.
- Clients access PostgreSQL-backed runtime data only through SDK/API
  boundaries. No client opens PostgreSQL connections, imports backend
  DB/runtime-store modules, or reads backend local data files directly.
- Connectors must not perform analytics.
- Domain modules must not import FastAPI.
- Streaming/Kafka is optional and must not become a source of truth.
- Vendor entitlement and export policy must fail closed for unknown commercial
  data.
- Analysis and optimization outputs must include assumptions, missing inputs,
  warnings, source references, lineage, and `human_review_required` where
  relevant. `meta.research_only` remains only as a temporary shared-envelope
  compatibility field; do not add it to new business-data payloads.
- Do not add broad capabilities without an approved ExecPlan under
  `.agent/plans/`.
- Do not call external APIs, market data providers, LLM providers, or live
  infrastructure from import-time code or tests.
- Do not add frontend, desktop, Node, Rust, Tauri, or client runtime
  dependencies during backend foundation milestones. These dependencies are
  allowed only inside selected web or Windows client milestones with documented
  dependency review and offline fallback.
- Do not add Kafka, Redis, Celery, company SSO/OIDC, or privileged commercial
  connector dependencies unless an ExecPlan explicitly scopes and reviews
  them.
- Do not add trade execution, order entry, order routing, trade capture,
  nomination submission, official approval, legal advice, official trading
  recommendations, auto-trading, ETRM replacement behavior, or company SSO/OIDC.
- Keep DB and runtime-store modules import-safe; importing the API must not
  open network sockets or database connections.
- Update contracts before broadening a module boundary.

## Dependency Policy

Allowed backend default stack: Python, FastAPI, Pydantic, SQLAlchemy, Alembic,
PostgreSQL, HTTPX, pandas, NumPy, PyArrow, python-dateutil, PyYAML, pytest, and
Ruff. Do not add dependencies unless they are necessary, permissive-licensed,
and documented.

Allowed client stack: React, TypeScript, Vite, plain CSS or CSS modules,
MapLibre GL, Rust, and Tauri for Windows/Linux desktop shells. Electron is not
approved.

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
pytest -q tests/api tests/contract tests/integration tests/ingestion tests/unit tests/optimization tests/sdk tests/cli tests/release tests/security
python -c "from apps.api.main import app; print('app import ok'); print(len(app.routes))"
```
