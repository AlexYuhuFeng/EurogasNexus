# V1 Stepwise Delivery Roadmap

## Purpose

This roadmap turns the project north star into a controlled backend delivery
sequence. It keeps the historical ambition visible while preventing the current
repo from repeating failed implementation patterns.

## Milestone 1: Governance, DB Foundation, API Path Policy

Status: `complete-in-current-worktree`

Goal:

- Establish repository governance and public-repo safety rules.
- Make DB URL resolution, redaction, lazy engine/session creation, and runtime
  DB validation explicit.
- Normalize stable API clients toward `/api` while preserving `/api/health`.

Exit evidence:

- Governance files exist.
- App import works without a DB URL.
- Ruff and targeted API/contract/integration/security tests pass.
- Runtime DB validation script is read-only and fail-closed.

## Milestone 2: DB Runtime Hardening

Phrase for implementation agents: DB runtime hardening.

Goal:

- Convert the current DB foundation into an operator-ready PostgreSQL runtime
  boundary.
- Add live local PostgreSQL validation that can run against explicit operator
  configuration without requiring a live DB for default tests.
- Add migration lifecycle checks and runbooks.
- Keep trial/release modes fail-closed when DB is unavailable.

Key deliverables:

- DB runtime readiness report.
- Required table catalog tied to Alembic revisions.
- Repository factory contract.
- Operator runbook for local/test PostgreSQL validation.
- Secret-safe read-only runtime DB validation.

## Milestone 3: Runtime Store And Repository Contracts

Goal:

- Define DB-first runtime store interfaces before adding business domains.
- Ensure API routes and SDK/CLI surfaces do not call internal domain modules or
  local files.

Key deliverables:

- `runtime_store` contract modules.
- Repository result metadata: assumptions, missing inputs, warnings, source
  references, lineage, `research_only`, `human_review_required`.
- Tests proving file fallback is unavailable in trial/release modes.

## Milestone 4: Canonical Reference Network Slice

Goal:

- Add the first narrow canonical data slice for reference network metadata,
  using source-shaped fixtures and DB-backed models only.
- Keep topology and map-readiness as backend API contracts; no frontend client
  implementation.

Key deliverables:

- Canonical identifier policy.
- Network node/facility/segment schema plan.
- Read-only `/api` reference-network contract.
- Source-shaped fixture import template only.

## Milestone 5: Ingestion And Data Quality Control Plane

Goal:

- Add ingestion-run, source-reference, lineage, freshness, and data-quality
  metadata boundaries.
- Keep connectors mocked and disabled by default.

Key deliverables:

- Connector contract interfaces that perform no analytics.
- Ingestion run repository.
- Data-quality result model.
- No live connector calls in tests or import-time code.

## Milestone 6: Governance, Entitlement, Audit, And Auth Runtime

Goal:

- Add fail-closed governance and audit foundations before exposing richer data.
- Keep company SSO/OIDC deferred unless explicitly approved by a future scope
  change.

Key deliverables:

- Entitlement decision model.
- Audit event model.
- Auth runtime contract with local/test-only behavior.
- Export policy checks for unknown commercial data.

## Milestone 7: Research Output Contract

Goal:

- Define how analysis outputs are represented before adding analytics or domain
  calculations.

Required output metadata:

- assumptions;
- missing inputs;
- warnings;
- source references;
- lineage;
- `research_only`;
- `human_review_required`.

## Milestone 8: First Research Domain Slice

Goal:

- Add one narrow research-only domain workflow after DB, API, runtime store,
  governance, and output contracts are in place.

Candidate:

- Reference topology read model or route-cost input contract, not a trading
  recommendation or execution workflow.

## Required Client Milestones

SDK, CLI, web, and Windows desktop client work must consume SDK/API-backed
`/api` contracts. The Python SDK is required for V1. CLI should call the SDK
first when available. Web and Windows reach PostgreSQL-backed runtime data only
through backend `/api` routes. The Desktop `eurogas nexus.exe` demo may
inform workflow intent for visual clients, but UI/UX requires redesign. Client
design docs now live under `docs/clients/` and `docs/design/`. Runtime client
implementation starts only when a client milestone is explicitly selected.

## Always Forbidden In V1

- trade execution;
- order entry;
- order routing;
- trade capture;
- nomination submission;
- official approval;
- legal advice;
- official trading recommendation;
- auto-trading;
- ETRM replacement behavior;
- frontend or desktop runtime implementation during backend milestones;
- live connectors without entitlement approval;
- external API or LLM provider calls from tests or import-time code.
