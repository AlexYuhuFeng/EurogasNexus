# Product Delivery Master Plan

## Purpose

This is the full delivery map for Eurogas Nexus as one DB-backed gas trader
intelligence product across backend, SDK, CLI, Web, and Windows surfaces.

The plan now reflects the current worktree: all five surfaces exist for the
tested local V1 scope. Future work should harden and deepen those surfaces
without breaking the API and PostgreSQL source-of-truth boundaries.

## One Product, Five Active Surfaces

1. Backend service: FastAPI, domain workflows, source posture, route-cost,
   strategy, analysis, credentials, and runtime status.
2. PostgreSQL runtime store: SQLAlchemy models, Alembic migrations, repositories,
   source-of-truth runtime tables.
3. Python SDK: typed API consumer for operator scripts, notebooks, tests, and
   programmatic integration.
4. CLI: safe operator and validation command surface backed by SDK/API.
5. Web and Windows clients: presentation and workflow surfaces that consume
   `/api`; Windows packages the shared Web workspace through Tauri.

Runtime data access is always mediated by API boundaries:

```text
Web/Windows -> backend /api -> repositories -> PostgreSQL
SDK/CLI     -> backend /api -> repositories -> PostgreSQL
```

Clients must not read PostgreSQL, backend local files, raw vendor data,
historical project files, `.env`, or connector credentials directly.

## Current Active Scope

The active V1 release-candidate scope includes:

- `/api/health`, `/api/runtime/db`, reference network, physical/capacity,
  storage, LNG, market/FX, source posture, credentials, contracts/routes,
  route-cost, resource-pool, strategy-lab, glossary, analysis/report, and
  portfolio observation routes.
- Alembic migrations through `0012_entsog_capacity`.
- Runtime database validation and operator scripts.
- React/Vite map-first Web workspace.
- Tauri desktop shell wrapping the Web workspace.
- Documentation and tests for research-only boundaries, data policy, source
  posture, and client/API separation.

## Product Design Principles

- PostgreSQL is runtime truth.
- The home screen is map-first and resource-pool-native.
- Detailed tables and diagnostics belong on dedicated pages, not on the home
  map.
- Source health, missing inputs, stale data, entitlement, and blockers must be
  visible to traders.
- Analysis outputs must include assumptions, missing inputs, warnings, source
  references, lineage, `research_only`, and `human_review_required` where
  relevant.
- Every UI workflow must avoid order-entry, order-routing, nomination, booking,
  approval, settlement, official-recommendation, legal-advice, and auto-trading
  semantics.

## Surface Responsibilities

### Backend

Owns runtime data access, validation, ingestion, credentials, entitlement,
audit, domain workflows, and stable `/api` routes.

### SDK

Owns typed Python access to released `/api` routes. It preserves metadata and
does not import backend internals.

### CLI

Owns secret-safe operator checks and automation helpers. Read-only by default;
future mutating operator commands require explicit `--execute` and a selected
milestone.

### Web

Owns the trader cockpit and workspace UX:

- Network map and resource-pool cockpit;
- Capacity and TSO access;
- Market and FX observations;
- Scenario and route economics;
- EFET-style contract capture shell;
- Strategy evaluation;
- Review and analysis;
- read-only order/PnL observations;
- Source Center;
- Glossary;
- Runtime and Settings.

### Windows

Owns packaged desktop delivery of the same Web workspace through Tauri. It must
not become a local database, credential store, or connector runtime.

## Current Development Queue

Use `docs/architecture/NEXT_DEVELOPMENT_QUEUE.md` as the ordered queue. Current
work should focus on:

1. documentation alignment and cockpit structure;
2. live ingestion scheduling and source-health hardening;
3. entitlement, audit, and export-governance hardening;
4. persisted contract/resource-pool workflows through `/api`;
5. cockpit warning/evidence and route-allocation review UX.

## Internet Policy

Default: no internet required.

Internet may be used only when a selected task requires current package or
provider documentation, installing/updating approved dependencies, or validating
current public source behavior. Default tests must not call external APIs or
LLM providers.

## Historical Reference Policy

Historical projects and the Windows demo are product-intent references only.
Use them for workflow understanding and cautionary lessons. Do not copy source
code, old layouts as-is, raw data, `.env`, vendor files, secrets, or generated
reports.

## Master Completion Definition

The full product is complete only when:

- backend API contracts are stable and documented;
- PostgreSQL-backed runtime truth is implemented for approved domains;
- SDK and CLI consume the backend without bypassing API contracts;
- Web and Windows consume backend `/api` for real workflows;
- source health, entitlement, warnings, missing inputs, and lineage are visible;
- research outputs carry required metadata and human-review status;
- release validation passes for backend, SDK, CLI, Web, and desktop packaging.
