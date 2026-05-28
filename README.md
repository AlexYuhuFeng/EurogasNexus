# Eurogas Nexus

Eurogas Nexus V1.0 is being bootstrapped as a research-only,
server-deployed backend service with future Web, Desktop, and SDK clients. The
V1 target is a DB-first, API-first, SDK-ready internal backend for European
pipeline gas, LNG reGas, and beach delivery resource research.

This repository contains product architecture boundaries, import-safe DB foundation artifacts, Alembic migration scaffolding, and FastAPI/SDK/CLI health shells.

## Current Scope

- Backend service package under `src/eurogas_nexus`.
- Minimal FastAPI app importable from `apps.api.main`.
- Development and release API route profiles.
- Architecture contracts under `docs/contracts`.
- Test scaffolding for API, contract, integration, SDK, and CLI checks.
- PostgreSQL is the planned runtime source of truth; local files are limited to
  templates, archives, reports, fixtures, and development fallback.

## Documentation Map

- ExecPlans: `.agent/plans/` (Bootstrap + Milestones 2-7)
- Architecture: `docs/architecture/V1_BACKEND_ARCHITECTURE.md`
- Gap report: `docs/architecture/V1_GAP_REPORT.md`
- Contract index: `docs/contracts/00_CONTRACT_INDEX.md`
- Product boundary: `docs/policies/PRODUCT_BOUNDARY_POLICY.md`
- Dependency policy: `docs/policies/DEPENDENCY_POLICY.md`
- Data policy: `docs/policies/DATA_POLICY.md`
- API profiles: `docs/api/API_PROFILES.md`
- Validation: `docs/operations/VALIDATION.md`
- Research-only compliance: `docs/compliance/RESEARCH_ONLY_COMPLIANCE.md`
- Release readiness: `docs/release/V1_RELEASE_READINESS.md`

## Explicit Non-Goals For This Bootstrap

- No business features.
- No external API calls or LLM provider calls.
- No frontend, desktop client, Node tooling, React, Tauri, or Electron.
- No Kafka, Redis, Celery, live connectors, or company SSO/OIDC.
- No trade execution, order entry, order routing, trade capture, nomination
  submission, official approval, legal advice, official trading
  recommendations, auto-trading, ETRM replacement behavior, or company SSO/OIDC.

## Local Validation

```powershell
ruff check .
pytest -q tests/api tests/contract tests/integration tests/sdk tests/cli tests/release tests/security tests/integration tests/sdk tests/cli
python -c "from apps.api.main import app; print('app import ok'); print(len(app.routes))"
```

## API Shell

The health route is available at:

```text
GET /v1/health
```
