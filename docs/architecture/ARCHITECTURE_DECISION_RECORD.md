# Architecture Decision Record

## Purpose

This document records firm architecture decisions for Eurogas Nexus V1. It
exists to remove ambiguity for future implementation agents and to keep the
worktree aligned with the current gas-trader decision-support goal.

## Decision 1: V1 Is Backend-First And Multi-Surface

Decision:

Eurogas Nexus V1 includes a Python backend/API service, PostgreSQL runtime
store, Python SDK, CLI, React/Vite Web workspace, and Tauri desktop shell. It
is backend-first because all runtime truth and integration boundaries remain
behind `/api`, not because clients are absent.

Implication:

- Backend/API remains the authoritative runtime boundary.
- The Python SDK is a required V1 surface and targets `/api`.
- CLI, Web, and Windows clients consume `/api` contracts.
- Web is the primary trader workspace.
- Windows/Tauri packages the same Web workspace.
- Client work may continue under `clients/`, but clients must not connect
  directly to PostgreSQL or read backend local files.

## Decision 2: PostgreSQL Is Runtime Truth

Decision:

PostgreSQL is the runtime source of truth. Local files are not runtime truth in
trial or release modes.

Implication:

- Runtime reads/writes go through repositories.
- Alembic owns migrations.
- Local files are templates, archives, reports, fixtures, or explicit
  development fallback only.
- Demo data must be inserted into PostgreSQL with clear demo provenance.

## Decision 2A: Live PostgreSQL Validation Is In V1

Decision:

V1 supports explicit live local PostgreSQL validation when the operator
configures a safe DB URL.

Implication:

- App import, route registration, and default tests remain DB-free.
- Read-only validation against a live database is allowed through documented
  operator commands.
- Migration execution is explicit and must not run during import, startup, or
  default tests.
- Secrets and full DB URLs must never appear in output.

## Decision 3: Stable API Prefix Is `/api`

Decision:

New stable client-facing routes use `/api`.

Implication:

- SDK, CLI, Web, and Windows target `/api`.
- `/api/health` remains compatibility only.
- Internal routes use `/api/internal`.
- Development routes use `/api/dev`.

## Decision 4: Stack Boundaries Are Explicit

Decision:

Use Python/FastAPI/SQLAlchemy/Alembic for backend runtime, React/Vite/TypeScript
for Web, and Tauri/Rust only for the desktop shell.

Implication:

- Backend import paths must not depend on Node, React, Vite, Tauri, Rust,
  browser APIs, or desktop runtime APIs.
- Client code must not import backend internals.
- Electron is not approved for V1.
- Historical Rust/React/Tauri demos are product evidence, not source code to
  copy into this repository.

## Decision 5: Domain Work Is Slice-Based

Decision:

New product capability should be added as narrow slices with clear data,
contract, API, client, test, and documentation impact.

Implication:

- Each slice needs a contract doc or documented update.
- Each slice must state DB impact, API impact, data policy, tests, validation
  commands, and rollback notes when relevant.
- UI improvements should expose real backend capability or explicit missing
  inputs, not fabricated client-side data.

## Decision 6: Connectors Fetch, They Do Not Analyze

Decision:

Connectors are transport adapters only.

Implication:

- Connector output goes to ingestion/normalization.
- Analytics belong in domain/application layers after canonical data is stored.
- Live connectors require explicit entitlement and credential approval.
- Tests and imports must not make live external provider or LLM calls.

## Decision 7: SDK And CLI Are API Consumers

Decision:

SDK and CLI must call the backend API. They must not import domain,
application, runtime store, or DB internals.

Implication:

- SDK tests assert paths and response models.
- CLI tests mock SDK/API clients, not domain functions.
- SDK implementation follows `docs/clients/SDK_CLIENT_DESIGN_SPEC.md`.
- CLI implementation follows `docs/clients/CLI_CLIENT_DESIGN_SPEC.md`.
- SDK/CLI expansion should not be bundled into unrelated Web or Windows work.

## Decision 8: Output Metadata Is Mandatory For Decision Support

Decision:

Decision-support outputs must carry enough context for human review.

Implication:

Research and intelligence result models include:

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
- Do not copy old code, assets, data, `.env`, credentials, generated reports,
  or vendor artifacts.

## Decision 11: Product Boundary Is Decision Support Only

Decision:

Eurogas Nexus supports gas-trader intelligence and review. It does not execute
or officially recommend trades.

Implication:

V1 must not implement:

- order entry;
- order routing;
- order amendment or cancellation;
- trade capture;
- nomination submission;
- official approvals;
- settlement/accounting;
- legal advice;
- official trading recommendations;
- auto-trading;
- ETRM replacement behavior.

## Current Recommended Next Step

Follow `docs/architecture/NEXT_DEVELOPMENT_QUEUE.md`.

The current work item is V1 R22: documentation and client cockpit alignment.
Next work should improve documentation accuracy, client structure, Source
Center diagnostics, review evidence, and persisted contract/resource workflows
without weakening the backend/API boundary.
