# Repository Contract

## Purpose

The repository is a product-level monorepo for a European gas intelligence
workspace with backend/API, PostgreSQL runtime store, Python SDK, CLI, React
Web workspace, and Tauri desktop shell.

The product is DB-first, API-first, client-active, and decision-support only.

## Required Roots

- `apps/`: deployable process entry points.
- `src/eurogas_nexus/`: backend package.
- `clients/`: Web and desktop client code.
- `packages/python-sdk/src/eurogas_nexus_sdk/`: typed Python SDK consumer.
- `dist/releases/`: tracked release-output placeholder; generated release files
  are ignored.
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

## Phase Restrictions

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

Large changes require a public ExecPlan recorded through
`docs/engineering/EXECPLAN_INDEX.md` with scope, files, tests, acceptance
criteria, and non-goals. Changes that introduce a new normative boundary first
follow `docs/engineering/RFC_PROCESS.md`. CI-generated release assets are
staged under `release-assets/` and Tauri bundle directories; neither generated
path is source material or a required repository root. The tracked
`dist/releases/.gitkeep` preserves the local release-output boundary.
