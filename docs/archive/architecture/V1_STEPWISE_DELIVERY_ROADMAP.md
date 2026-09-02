# V1 Stepwise Delivery Roadmap

## Purpose

This roadmap records how Eurogas Nexus reached the current V1
release-candidate shape and how future work should continue without replaying
early foundation milestones.

The active product is a PostgreSQL-backed gas trader intelligence workspace:
backend/API, SDK, CLI, React/Vite Web, and Tauri desktop shell are all present.
The product remains decision support only.

## Completed Foundation Milestones

### Milestone 1: Governance, DB Foundation, API Path Policy

Status: `complete-in-current-worktree`

Delivered:

- repository governance and public-repo safety rules;
- DB URL precedence, redaction, lazy engine/session creation, and runtime DB
  validation policy;
- stable client API prefix `/api`;
- import-safe FastAPI entry point.

### Milestone 2: DB Runtime Hardening

Status: `complete-in-current-worktree`

Historical implementation phrase: DB runtime hardening.

Delivered:

- read-only PostgreSQL runtime validation;
- Alembic-backed required-table inspection;
- migration lifecycle documentation;
- secret-safe DB readiness reports;
- runtime DB failure modes for unavailable, missing-table, and connected
  states.

### Milestone 3: Runtime Store And Repository Contracts

Status: `complete-in-current-worktree`

Delivered:

- DB-first repository boundaries;
- source references, assumptions, missing inputs, warnings, lineage,
  `research_only`, and `human_review_required` metadata patterns;
- tests preventing trial/release local-file fallback.

### Milestone 4: Canonical Reference Network Slice

Status: `complete-in-current-worktree`

Delivered:

- canonical reference nodes and route-candidate map edges;
- read-only `/api/reference-network/*` contracts;
- map-consumable topology and source metadata.

### Milestone 5: Ingestion And Data Quality Control Plane

Status: `complete-in-current-worktree`

Delivered:

- ingestion-run and source-reference model;
- source diagnostics and freshness surfaces;
- public/keyed source slots for ECB, ENTSOG, GIE storage/LNG, tariffs, and
  licensed commercial providers.

### Milestone 6: Governance, Entitlement, Audit, And Auth Runtime

Status: `partial-current-worktree`

Delivered:

- entitlement and audit foundations;
- credential submission through backend routes;
- restricted commercial-provider posture in Source Center.

Remaining:

- production-grade multi-user auth;
- stronger entitlement/export enforcement;
- secret-manager integration.

### Milestone 7: Research Output Contract

Status: `complete-in-current-worktree`

Delivered:

- route-cost, resource-pool, strategy, LLM/report, and review outputs that
  remain research/decision-support artifacts;
- mandatory human-review and warning metadata.

### Milestone 8: First Research Domain Slices

Status: `complete-in-current-worktree`

Delivered:

- route-cost comparison;
- resource-pool sale-option optimization;
- capacity, tariff, storage, LNG, market, glossary, and read-only portfolio
  observation surfaces.

## Active Client Milestones

SDK, CLI, Web, and Windows are active V1 client surfaces.

Rules:

- SDK and CLI consume released `/api` contracts.
- Web is the primary trader workspace.
- Windows/Tauri packages the same Web workspace.
- Clients must not connect directly to PostgreSQL.
- Clients must not read raw provider files, backend local files, `.env`, or
  plaintext credentials.
- Provider credentials are backend-owned and write-only from client forms.

Current client work should improve structure, diagnostics, persisted
contract/resource workflows, review evidence, and browser/desktop quality.

## Current Development Queue

Use `docs/architecture/NEXT_DEVELOPMENT_QUEUE.md` for the ordered queue.

Current priority:

- V1 R22: documentation and client cockpit alignment.

Upcoming priorities:

- ingestion scheduling and source health;
- entitlement, audit, and export-governance hardening;
- persisted EFET-style contract/resource-pool workflow;
- cockpit warning/evidence drill-down.

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
- browser-side provider calls;
- direct client-to-PostgreSQL access;
- plaintext credential return to clients;
- live connectors without entitlement and credential approval;
- external API or LLM provider calls from tests or import-time code.
