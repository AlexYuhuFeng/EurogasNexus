# V1 Reference Architecture Alignment ExecPlan

## 1. Goal

Use historical local Eurogas Nexus implementations as reference evidence to
clarify the current repository's product north star, architecture boundaries,
stepwise roadmap, and failure patterns to avoid.

## 2. Non-goals

- Do not copy historical source code, secrets, real data, vendor data, raw
  market data, contracts, credentials, or business strategy parameters.
- Do not add frontend, desktop, Node, Rust, Docker, Kafka, Redis, Celery, live
  connectors, LLM providers, or company SSO/OIDC to the current V1 bootstrap.
- Do not implement business features.
- Do not run external APIs, live connectors, Docker, or live DB migrations.

## 3. Product boundary

This is architecture and documentation alignment only. The current repository
remains a research-only, DB-first, API-first, SDK-ready Python backend service
bootstrap. Historical implementations inform direction but are not authoritative
runtime code.

## 4. Files to create/modify

- `.agent/plans/V1_REFERENCE_ARCHITECTURE_ALIGNMENT_EXECPLAN.md`
- `docs/architecture/PROJECT_NORTH_STAR.md`
- `docs/architecture/REFERENCE_PROJECT_LESSONS.md`
- `docs/architecture/V1_STEPWISE_DELIVERY_ROADMAP.md`
- `docs/architecture/V1_BACKEND_ARCHITECTURE.md`
- `docs/architecture/V1_GAP_REPORT.md`
- `docs/contracts/00_CONTRACT_INDEX.md`
- `README.md`
- `tests/contract/test_architecture_alignment.py`

## 5. Dependency policy

No dependency changes.

Internet required: no

Reason: This milestone uses local repository docs, local Desktop reference
folders, and local tests only.

Fallback if offline: Not needed.

## 6. Data policy

Historical projects are read as local reference material only. Do not import or
commit their data artifacts, `.env` files, vendor documents, raw market data, or
generated reports.

## 7. API impact

No API runtime changes. Existing `/v1/health` compatibility and `/api/v1/health`
preferred stable alias remain unchanged.

## 8. DB impact

No DB schema changes, migrations, or live DB calls. Documentation continues to
state PostgreSQL as the runtime source of truth.

## 9. Tests

Add contract tests that assert architecture docs exist and preserve the DB-first,
API-first, research-only, no-front-end-in-V1 boundary.

## 10. Validation commands

```powershell
ruff check .
pytest -q tests/contract/test_architecture_alignment.py
pytest -q tests/api tests/contract tests/integration tests/security
python -c "from apps.api.main import app; print('app import ok'); print(len(app.routes))"
```

## 11. Acceptance criteria

- Current repo contains clear north-star, reference-lessons, and stepwise-roadmap
  docs.
- Docs reconcile the historical web/platform ambition with the current V1
  backend-only guardrails.
- Docs identify historical failure patterns: desktop-first drift, local-file
  runtime truth, domain sprawl, live connector/LLM temptation, and over-broad
  route/API surfaces.
- Tests pass without external services.

## 12. Rollback notes

Remove the added architecture docs/tests and revert README/contract index
updates. No runtime rollback is required.
