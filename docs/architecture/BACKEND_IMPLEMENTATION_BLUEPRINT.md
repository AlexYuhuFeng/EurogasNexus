# Backend Implementation Blueprint

## Objective

Eurogas Nexus uses the backend as the authoritative product core. The backend
owns runtime truth, API contracts, ingestion control, governance, audit,
research output semantics, SDK/CLI access, and release validation.

The current worktree already includes active Web and Windows clients, but those
clients remain API consumers. They do not bypass the backend or read
PostgreSQL directly.

## Architecture

```text
apps/api
  -> src/eurogas_nexus/api
  -> src/eurogas_nexus/application
  -> src/eurogas_nexus/domain
  -> src/eurogas_nexus/runtime_store
  -> src/eurogas_nexus/db
  -> PostgreSQL
```

Client boundary:

```text
SDK / CLI / Web / Windows -> /api -> backend services -> runtime store -> PostgreSQL
```

## Required Backend Stack

- Python 3.11+
- FastAPI
- Pydantic
- SQLAlchemy
- Alembic
- HTTPX
- PyYAML
- pytest
- Ruff

Backend foundation work must stay import-safe, DB-lazy, and testable without a
live database. Client tooling belongs under `clients/` and must not leak into
backend import paths.

## Purpose Of SQLAlchemy

SQLAlchemy is the Python database access layer. In Eurogas Nexus it should:

- create engines and sessions lazily from the approved DB URL policy;
- define DB models and typed repository queries;
- manage transactions through explicit session boundaries;
- keep raw SQL isolated when SQL is needed;
- support Alembic migration metadata.

SQLAlchemy is not the database and must not connect during import. PostgreSQL
remains the runtime source of truth. Alembic remains the migration tool.

## Backend Milestone State

### B1: Foundation And Governance

Status: `complete-in-current-worktree`

Owns:

- repository governance;
- API path policy;
- DB URL precedence/redaction;
- Alembic import safety;
- runtime DB validation script.

### B2: DB Runtime Hardening

Status: `complete-in-current-worktree`

Owns:

- operator-ready DB runtime validation;
- explicit live local PostgreSQL validation path;
- required table registry linked to migration expectations;
- runtime store contract shell;
- migration lifecycle documentation;
- readiness reports.

### B3: Runtime Store Contracts

Status: `complete-in-current-worktree`

Owns:

- repository interface pattern;
- DB-backed result envelope;
- no trial/release file fallback tests;
- metadata shape for assumptions, warnings, lineage, and source references.

### B4: Reference Network Slice

Status: `complete-in-current-worktree`

Owns:

- canonical ID policy;
- schema and repositories for nodes/facilities/segments;
- read-only `/api/reference-network/*` contracts;
- source-reference and lineage fields.

### B5: Ingestion Control Plane

Status: `complete-in-current-worktree`

Owns:

- connector definition model;
- ingestion job/run model;
- normalization result model;
- data-quality/freshness model;
- no import-time external calls.

### B6: Governance, Entitlement, Audit

Status: `partial-current-worktree`

Owns:

- entitlement decision model;
- audit event model;
- credential route boundary;
- fail-closed posture for unknown commercial data.

Remaining production work:

- stronger auth and role model;
- export policy enforcement;
- secret-manager integration;
- entitlement-driven filtering for commercial provider data.

### B7: Research And Decision-Support Workflows

Status: `active-current-worktree`

Owns:

- route-cost and resource-pool workflows;
- strategy-lab evaluation;
- LLM/report analysis boundary;
- read-only market-positioning portfolio observations.

Acceptance for all new workflows:

- output includes assumptions, missing inputs, warnings, source references,
  lineage, `research_only`, and `human_review_required`;
- no official recommendation or execution semantics;
- no order entry, routing, amendment, cancellation, trade capture, nomination,
  or ETRM replacement behavior.

## Backend API Rules

- Stable routes use `/api`.
- Internal routes use `/api/internal`.
- Development routes use `/api/dev`.
- SDK, CLI, Web, and Windows call `/api`.
- Route handlers validate and delegate.
- Application services orchestrate.
- Runtime store reads/writes PostgreSQL.
- Connectors fetch only through approved ingestion workflows.

## Backend Data Rules

Every durable runtime record must define:

- owner module;
- primary key;
- canonical identifier;
- source references;
- lineage;
- schema version;
- timestamps;
- data scope;
- migration revision where applicable.

## Backend Validation

Run:

```powershell
ruff check .
pytest -q tests/api tests/contract tests/integration tests/security
python -c "from apps.api.main import app; print('app import ok'); print(len(app.routes))"
```

CI-targeted:

```powershell
pytest -q tests/api tests/contract tests/integration tests/sdk tests/cli tests/release tests/security
```

Client build verification is separate but required before release:

```powershell
npm --prefix clients/web run build
```

## Backend Handoff

Every backend milestone final report should include:

- files changed;
- DB policy impact;
- API policy impact;
- tests run;
- route count;
- remaining gaps;
- recommended next work from `docs/architecture/NEXT_DEVELOPMENT_QUEUE.md`.
