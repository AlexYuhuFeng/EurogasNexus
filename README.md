# Eurogas Nexus

Eurogas Nexus V1.0 is being prepared as a research-only, DB-first, API-first,
SDK-required internal platform for European pipeline gas, LNG reGas, and beach
delivery resource research. V1 includes backend/API, PostgreSQL runtime store,
Python SDK, CLI, web workspace, and Windows client shell.

This repository contains product architecture boundaries, import-safe DB foundation artifacts, Alembic migration scaffolding, and FastAPI/SDK/CLI health shells.

## Current Scope

- Backend service package under `src/eurogas_nexus`.
- Minimal FastAPI app importable from `apps.api.main`.
- Development, internal, and release API route profiles.
- Architecture contracts under `docs/contracts`.
- Test scaffolding for API, contract, integration, SDK, and CLI checks.
- PostgreSQL is the runtime source of truth; live local PostgreSQL validation is
  part of V1 when a safe DB URL is configured. Local files are limited to
  templates, archives, reports, fixtures, and development fallback.

## Documentation Map

- ExecPlans: `.agent/plans/`
- Claude Code local launch and full V1 prompt: `CLAUDE_CODE_START_HERE.md`
- Claude Code implementation directives: `docs/architecture/CLAUDE_CODE_IMPLEMENTATION_DIRECTIVES.md`
- Target product architecture: `docs/architecture/TARGET_PRODUCT_ARCHITECTURE.md`
- Whole project capability blueprint: `docs/architecture/WHOLE_PROJECT_CAPABILITY_BLUEPRINT.md`
- Claude Code master execution index: `docs/architecture/CLAUDE_CODE_MASTER_EXECUTION_INDEX.md`
- Reference evidence log: `docs/architecture/REFERENCE_EVIDENCE_LOG.md`
- North star: `docs/architecture/PROJECT_NORTH_STAR.md`
- Architecture decisions: `docs/architecture/ARCHITECTURE_DECISION_RECORD.md`
- Claude Code delivery brief: `docs/architecture/CLAUDE_CODE_DELIVERY_BRIEF.md`
- Claude Code goal-mode entrypoint: `docs/architecture/CLAUDE_CODE_GOAL_MODE.md`
- Claude Code start prompts: `docs/architecture/CLAUDE_CODE_START_PROMPTS.md`
- Current pause point: `docs/architecture/CURRENT_PAUSE_POINT.md`
- Claude Code execution playbook: `docs/architecture/CLAUDE_CODE_EXECUTION_PLAYBOOK.md`
- Next development queue: `docs/architecture/NEXT_DEVELOPMENT_QUEUE.md`
- Offline Claude Code guide: `docs/architecture/OFFLINE_CLAUDE_CODE_GUIDE.md`
- Live PostgreSQL V1 policy: `docs/operations/LIVE_POSTGRESQL_V1.md`
- Worktree handoff: `docs/operations/WORKTREE_HANDOFF.md`
- Client design index: `docs/clients/README.md`
- Client tech stack: `docs/clients/CLIENT_TECH_STACK.md`
- Client i18n/theme spec: `docs/clients/CLIENT_I18N_THEME_SPEC.md`
- SDK client design spec: `docs/clients/SDK_CLIENT_DESIGN_SPEC.md`
- CLI client design spec: `docs/clients/CLI_CLIENT_DESIGN_SPEC.md`
- Client design system: `docs/clients/CLIENT_DESIGN_SYSTEM.md`
- Web client design spec: `docs/clients/WEB_CLIENT_DESIGN_SPEC.md`
- Windows client design spec: `docs/clients/WINDOWS_CLIENT_DESIGN_SPEC.md`
- UX layout blueprints: `docs/design/UX_LAYOUT_BLUEPRINTS.md`
- Reference lessons: `docs/architecture/REFERENCE_PROJECT_LESSONS.md`
- Future client UX reference: `docs/architecture/FUTURE_CLIENT_UX_REFERENCE.md`
- Domain delivery map: `docs/architecture/V1_DOMAIN_DELIVERY_MAP.md`
- Stepwise roadmap: `docs/architecture/V1_STEPWISE_DELIVERY_ROADMAP.md`
- Architecture: `docs/architecture/V1_BACKEND_ARCHITECTURE.md`
- Gap report: `docs/architecture/V1_GAP_REPORT.md`
- Contract index: `docs/contracts/00_CONTRACT_INDEX.md`
- Product boundary: `docs/policies/PRODUCT_BOUNDARY_POLICY.md`
- Dependency policy: `docs/policies/DEPENDENCY_POLICY.md`
- Data policy: `docs/policies/DATA_POLICY.md`
- API profiles: `docs/api/API_PROFILES.md`
- API surface blueprint: `docs/api/API_SURFACE_BLUEPRINT.md`
- Canonical data model blueprint: `docs/data/CANONICAL_DATA_MODEL_BLUEPRINT.md`
- Research workflow blueprint: `docs/product/RESEARCH_WORKFLOW_BLUEPRINT.md`
- Real-time market intelligence blueprint: `docs/product/REAL_TIME_MARKET_INTELLIGENCE_BLUEPRINT.md`
- Documentation completion audit: `data/documentation_handoff/project_docs_completion_audit.md`
- Validation: `docs/operations/VALIDATION.md`
- Research-only compliance: `docs/compliance/RESEARCH_ONLY_COMPLIANCE.md`
- Release readiness: `docs/release/V1_RELEASE_READINESS.md`
- Full V1 release scope: `docs/release/V1_FULL_PROJECT_RELEASE_SCOPE.md`
- Full V1 release execution plan: `docs/release/V1_FULL_PROJECT_RELEASE_EXECUTION_PLAN.md`
- V1 release milestone backlog: `docs/release/V1_RELEASE_MILESTONE_BACKLOG.md`
- V1 release acceptance matrix: `docs/release/V1_RELEASE_ACCEPTANCE_MATRIX.md`
- V1 release ExecPlan template: `docs/release/V1_RELEASE_EXECPLAN_TEMPLATE.md`

## Explicit Non-Goals For This Bootstrap

- No business features.
- No external API calls or LLM provider calls.
- No frontend, desktop client, Node tooling, React, Tauri, or Rust during
  backend foundation milestones. Web and Windows milestones may add their
  approved client tooling when selected.
- No Electron.
- No Kafka, Redis, Celery, live connectors, or company SSO/OIDC.
- No trade execution, order entry, order routing, trade capture, nomination
  submission, official approval, legal advice, official trading
  recommendations, auto-trading, ETRM replacement behavior, or company SSO/OIDC.

## Local Validation

```powershell
ruff check .
pytest -q tests/api tests/contract tests/integration tests/sdk tests/cli tests/release tests/security
python -c "from apps.api.main import app; print('app import ok'); print(len(app.routes))"
```

## API Shell

The health route is available at:

```text
GET /v1/health
GET /api/v1/health
```

New SDK and CLI callers should target `/api/v1`. `/v1` remains a bootstrap
compatibility path.
