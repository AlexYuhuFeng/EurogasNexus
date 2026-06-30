# Repository Contract

## Purpose

The repository is a product-level monorepo for a V1 European gas intelligence
workspace with backend/API, PostgreSQL runtime store, Python SDK, CLI, React
Web workspace, and Tauri desktop shell.

V1 is DB-first, API-first, client-active, and decision-support only.

## Required Roots

- `apps/`: deployable process entry points.
- `src/eurogas_nexus/`: backend package.
- `clients/`: Web and desktop client code.
- `packages/`: future distributable packages.
- `release/` and `dist/releases/`: release preparation and artifacts.
- `infra/`: deployment templates and service configuration.
- `docs/`: architecture, policy, API, SDK, operations, compliance, release docs.
- `tests/`: unit, integration, API, SDK, CLI, workflow, security, contract,
  release, and streaming tests.
- `scripts/`: development, operations, audit, and release scripts.
- `data/`: local manual, raw, canonical, export, report, snapshot, and fixture
  data.
- `alembic/`: migration boundary.

## Runtime Boundary

- PostgreSQL is the runtime source of truth.
- Backend repositories own DB access.
- Stable client routes use `/api`.
- SDK, CLI, Web, and Windows consume backend API contracts.
- Clients do not connect directly to PostgreSQL.
- Clients do not read `.env`, raw vendor files, backend local runtime files, or
  plaintext credentials.
- Provider credentials are backend-owned and are never returned in plaintext.

## V1 Phase Restrictions

- Do not add live data connectors without credential, entitlement, and operator
  approval.
- Do not add backend dependencies on frontend, desktop, browser, Node, or Tauri
  runtime APIs.
- Do not add client dependencies that bypass the backend API boundary.
- Do not add trade execution, order entry, order routing, trade capture,
  nomination submission, official approval, official recommendation,
  auto-trading, legal advice, ETRM replacement, or company SSO/OIDC behavior
  unless a future scope change explicitly approves it.

## Planning Rule

Large changes require an ExecPlan under `.agent/plans/` with scope, files,
tests, acceptance criteria, and non-goals.
