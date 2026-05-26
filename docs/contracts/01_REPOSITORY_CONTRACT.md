# Repository Contract

## Purpose

The repository is a product-level monorepo for a research-only,
server-deployed backend service with future Web, Desktop, and SDK clients. V1
is DB-first, API-first, and SDK-ready.

## Required Roots

- `apps/`: deployable process entrypoints.
- `src/eurogas_nexus/`: backend package.
- `clients/`: future client shells only.
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

## V1.0 Bootstrap Restrictions

- Do not add frontend implementation.
- Do not add desktop implementation.
- Do not add Node tooling.
- Do not add live data connectors.
- Do not add trade execution, order entry, order routing, trade capture,
  nomination submission, official approval, official recommendation,
  auto-trading, legal advice, ETRM replacement, or company SSO/OIDC behavior.

## Planning Rule

Large changes require an ExecPlan under `.agent/plans/` with scope, files,
tests, acceptance criteria, and non-goals.
