# Architecture Decision Record

## Purpose

This document records the firm architecture decisions for Eurogas Nexus V1. It
exists to remove ambiguity for future implementation agents.

## Decision 1: V1 Is Backend-First And Multi-Surface

Decision:

Eurogas Nexus V1 includes a Python backend/API service, PostgreSQL runtime
store, Python SDK, CLI, web workspace, and Windows client shell. Delivery is
phased: backend and API contracts come first, then SDK/CLI, then web, then
Windows packaging.

Implication:

- Build backend API, DB, governance, ingestion, and research-output contracts
  before broad client workflows.
- The Python SDK is a required V1 surface and must target `/api/v1`.
- Keep `clients/web` and `clients/desktop` free of runtime code until the
  selected release milestone activates them.
- Maintain client design docs under `docs/clients/` so client implementation
  has a clear target.
- Use the Windows demo only as UX reference for future client milestones.

## Decision 2: PostgreSQL Is Runtime Truth

Decision:

PostgreSQL is the runtime source of truth. Local files are not runtime truth in
trial or release modes.

Implication:

- Runtime reads/writes go through repositories.
- Alembic owns migrations.
- Local files are templates, archives, reports, fixtures, or explicit
  development fallback only.

## Decision 2A: Live PostgreSQL Validation Is In V1

Decision:

V1 must support explicit live local PostgreSQL validation when the operator
configures a safe DB URL.

Implication:

- App import, route registration, and default tests remain DB-free.
- Read-only validation against a live database is allowed through documented
  operator commands.
- Migration execution is explicit and must not run during import, startup, or
  default tests.
- Secrets and full DB URLs must never appear in output.

## Decision 3: Stable API Prefix Is `/api/v1`

Decision:

New stable client-facing routes use `/api/v1`.

Implication:

- SDK and CLI target `/api/v1`.
- `/v1/health` remains compatibility only.
- Internal routes use `/api/internal`.
- Development routes use `/api/dev`.

## Decision 4: Python Stack Remains Minimal

Decision:

Use the approved Python stack for V1: FastAPI, Pydantic, SQLAlchemy, Alembic,
HTTPX, pandas/NumPy/PyArrow where explicitly needed later, PyYAML, pytest, and
Ruff.

Implication:

- Do not add Node, React, Tauri, Rust, Kafka, Redis, Celery, or live connector
  dependencies in backend foundation milestones.
- React/Vite/TypeScript are allowed only in selected web milestones.
- Tauri/Rust are allowed only in selected Windows milestones.
- Electron is not approved for V1.
- Do not copy the historical Rust/React/Tauri implementations.

## Decision 5: Domain Work Is Slice-Based

Decision:

Only one domain slice should be implemented at a time after foundation layers
are ready.

Implication:

- The first domain slice should be reference network, not route-cost/netback or
  strategy.
- Each slice needs a contract doc, DB impact, API impact, data policy, tests,
  validation commands, and rollback notes.

## Decision 6: Connectors Fetch, They Do Not Analyze

Decision:

Connectors are transport adapters only.

Implication:

- Connector output goes to ingestion/normalization.
- Analytics belong in domain/application layers after canonical data is stored.
- Live connectors require explicit entitlement and credential approval.

## Decision 7: SDK And CLI Are API Consumers

Decision:

SDK and CLI must call the backend API. They must not import domain, application,
runtime store, or DB internals.

Implication:

- SDK tests assert paths and response models.
- CLI tests mock SDK/API clients, not domain functions.
- SDK implementation follows `docs/clients/SDK_CLIENT_DESIGN_SPEC.md`.
- CLI implementation follows `docs/clients/CLI_CLIENT_DESIGN_SPEC.md`.
- SDK/CLI expansion has dedicated ExecPlans and should not be bundled into web
  or Windows work.

## Decision 8: Output Metadata Is Mandatory For Research Results

Decision:

Research outputs must carry enough context for human review.

Implication:

Research result models include:

- assumptions;
- missing inputs;
- warnings;
- source references;
- lineage;
- `research_only`;
- `human_review_required`.

## Decision 9: Offline Work Is The Default For Local Agents

Decision:

Future local implementation sessions are assumed offline unless the user says
otherwise.

Implication:

- Plans must state `Internet required: no` for local work.
- Tasks needing current external docs must state `Internet required: yes` and an
  offline fallback.
- Offline fallback means mocks, interfaces, tests, and gap reports.

## Decision 10: Historical Projects Are Evidence, Not Source

Decision:

Historical Desktop projects and demos inform product intent and failure
patterns. They are not source code for the current repo.

Implication:

- Extract workflow and architecture lessons.
- Do not copy old code, assets, data, `.env`, credentials, generated reports, or
  vendor artifacts.

## Current Recommended Next Step

Finish documentation-first alignment, then run Milestone 2: DB runtime
hardening.

Milestone 2 must produce operator-ready DB validation, migration lifecycle docs,
required-table registry alignment, and repository/runtime-store contracts before
any broad business feature work.
