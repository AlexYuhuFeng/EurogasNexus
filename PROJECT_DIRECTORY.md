# Project Directory

## Purpose

This file is the current directory map and ownership boundary for Eurogas
Nexus. It intentionally does not list every file. For detailed module rules use
the contracts and client docs linked below; for the verified current shape use
[docs/architecture/CURRENT_PAUSE_POINT.md](docs/architecture/CURRENT_PAUSE_POINT.md).

## Root layout

```text
.agent/                 Historical agent ExecPlans and planning evidence
.agents/                Agent-scoped task artifacts (not runtime input)
.github/                CI workflows, issue templates, and PR template
alembic/                Alembic migrations and migration env
apps/                   Process entrypoints only (api active; worker/scheduler reserved)
clients/                API-consuming clients: web/ and desktop/
data/                   Ignored local artifacts and fixtures; never runtime truth
deploy/                 Runtime container deployment files
dist/                   Release output placeholder; generated artifacts are ignored
docs/                   Current, runbook, design-reference, and archived documentation
infra/                  Deployment component notes (deployment, docker, nginx, postgres, systemd)
installer/              Windows installer sources
output/                 Untracked generated material; never commit
packages/               Reserved future distributable packages (placeholders only)
release/                Source-controlled release-blueprint placeholder
scripts/                CI, dev, ops, release, and security scripts
src/eurogas_nexus/      Backend Python package (the only backend runtime package)
tests/                  Python test suite (api, contract, integration, unit, sdk, etc.)
tmp/                    Ignored scratch space
```

Local or ignored tool directories may also exist (`.venv`, `.local-runtime`,
`node_modules`, `clients/*/dist`) and are never runtime truth or commit
material.

## Documentation layout

```text
docs/api/                API surface and path policies
docs/architecture/       Architecture policies, ADR record, status and queue
docs/archive/            Archived/superseded documents (read-only provenance)
docs/clients/            Client contracts and UI standards
docs/compliance/         Compliance notes
docs/contracts/          Normative repository contracts
docs/data/               Canonical data model blueprints
docs/deployment/         Deployment roles and installer runbooks
docs/design/             UI audits and visual references
docs/engineering/        Coding standards and RFC process
docs/ontology/           OWL model and natural-gas semantic backbone
docs/operations/         Operator and development runbooks
docs/policies/           Product, data, dependency, and archive policies
docs/product/            Product capability and workflow specifications
docs/release/            Release readiness, security evidence, and backlog
docs/sdk/                Reserved SDK design notes
```

The authoritative navigation order is in
[docs/README.md](docs/README.md) (English) and
[docs/README-CN.md](docs/README-CN.md) (Mandarin).

## Product surfaces

Eurogas Nexus is delivered through five active surfaces:

1. Backend service — `apps/api` + `src/eurogas_nexus`.
2. PostgreSQL runtime store — Alembic-managed schema under `alembic/versions`.
3. Python SDK — `src/eurogas_nexus/sdk`.
4. CLI — `src/eurogas_nexus/cli`.
5. Web and Windows/Linux clients — `clients/web` and `clients/desktop`.

PostgreSQL is the runtime source of truth. SDK, CLI, Web, and desktop clients
consume `/api` or the SDK; they never read PostgreSQL, backend local files, raw
vendor data, or credentials directly.

## Backend ownership boundaries

`apps/` contains process entrypoints only. Business logic, route
implementations, persistence, and workflows belong under `src/eurogas_nexus`:

```text
src/eurogas_nexus/api/             FastAPI app, route profiles, routes, dependencies
src/eurogas_nexus/application/     Workflow orchestration and application services
src/eurogas_nexus/db/              SQLAlchemy models, repositories, sessions, registry
src/eurogas_nexus/domain/          Domain models and calculations
src/eurogas_nexus/ingestion/       Connectors and normalization boundaries
src/eurogas_nexus/optimization/    Deterministic optimization engines
src/eurogas_nexus/security/        Tokens, credentials, permissions, identity helpers
src/eurogas_nexus/governance/      Entitlement and audit policy
src/eurogas_nexus/sdk/             Typed API consumer facade
src/eurogas_nexus/cli/             API-backed command interface
src/eurogas_nexus/mcp/             Read-only stdio MCP tools
src/eurogas_nexus/streaming/       Optional SSE contracts
```

Other `src/eurogas_nexus` subdirectories exist for audit, data quality,
infrastructure, legacy, LLM, observations, runtime-store contracts, and
workflows. Treat them as backend-owned; do not import them from SDK, CLI, or
client code.

Backend work activates `apps/api`, `src/eurogas_nexus`, `alembic`, `scripts`,
`tests`, and backend docs. Database schema changes require an Alembic migration;
do not add a second datastore.

## Client ownership boundaries

```text
clients/web/src/App.tsx                 composition root only
clients/web/src/app/hooks/             workflow state and lifecycle
clients/web/src/app/model/             derived decision view models
clients/web/src/app/shell/             persistent application/map shell
clients/web/src/app/workspaces/        workspace-to-page wiring
clients/web/src/components/            domain page rendering
clients/web/src/components/ui/         shared UI primitives (WorkspaceTabs, PanelHeader,
                                        StatusBadge, MetricStrip)
clients/web/src/api/                   backend transport and DTOs
clients/web/src/stores/                API and preference state
clients/web/src/i18n/                  English and Mandarin resources
clients/web/src/styles/                global CSS (deliberate changes only)
```

The Web workspace is the single UI source for browser, Windows, and Linux
packaging. `clients/desktop` is the Tauri shell only and packages
`clients/web/dist`.

Read [docs/clients/README.md](docs/clients/README.md),
[docs/clients/WEB_APPLICATION_ARCHITECTURE-EN.md](docs/clients/WEB_APPLICATION_ARCHITECTURE-EN.md),
and [docs/clients/UI_CONTENT_STANDARDS.md](docs/clients/UI_CONTENT_STANDARDS.md)
before adding Web behavior.

## Activation rules

- Backend work activates `apps/api`, `src/eurogas_nexus`, `alembic`, `scripts`,
  `tests`, and backend docs.
- SDK work activates `src/eurogas_nexus/sdk` and `tests/sdk`. The directory
  `packages/python-sdk` is a reserved placeholder; the active SDK lives in the
  backend package.
- CLI work activates `src/eurogas_nexus/cli` and `tests/cli`.
- Web work activates `clients/web` and uses `npm run build` plus the
  `clients/web/tests` suite.
- Windows/Linux work activates `clients/desktop`, `installer`, `deploy`, and
  release scripts only when packaging is in scope.
- Directories without an active milestone remain documentation or placeholders.
  Do not add runtime behavior just because a folder exists.

## Directory rule

Keep one owner per runtime area. If a change crosses an ownership boundary,
update the relevant contract first, add a boundary test, and keep generated
`output/`, `dist/`, `tmp/`, and local data directories out of Git.
