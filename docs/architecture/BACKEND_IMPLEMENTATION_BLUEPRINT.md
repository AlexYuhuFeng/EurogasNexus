# Backend Implementation Blueprint

## Objective

Build the Eurogas Nexus backend as the authoritative product core. The backend
owns runtime truth, API contracts, ingestion control, governance, audit,
research output semantics, SDK/CLI access, and release validation.

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

Do not add frontend, desktop, Kafka, Redis, Celery, Node, Tauri, Electron, or
live connector dependencies in backend foundation milestones.

## Purpose Of SQLAlchemy

SQLAlchemy is the Python database access layer. In Eurogas Nexus it should:

- create engines and sessions lazily from the approved DB URL policy;
- define DB models and typed repository queries;
- manage transactions through explicit session boundaries;
- keep raw SQL isolated when SQL is needed;
- support Alembic migration metadata.

SQLAlchemy is not the database and must not connect during import. PostgreSQL
remains the runtime source of truth. Alembic remains the migration tool.

## Backend Milestone Sequence

### B1: Foundation And Governance

Status: complete in current worktree.

Owns:

- repository governance;
- API path policy;
- DB URL precedence/redaction;
- Alembic import safety;
- runtime DB validation script.

### B2: DB Runtime Hardening

Status: next.

Build:

- operator-ready DB runtime validation;
- explicit live local PostgreSQL validation path;
- required table registry linked to migration expectations;
- runtime store contract shell;
- migration lifecycle documentation;
- readiness reports.

Acceptance:

- app import requires no DB;
- runtime DB validation is read-only;
- live PostgreSQL validation works when a safe DB URL is configured;
- default tests do not require PostgreSQL;
- missing DB URL fails closed;
- no secrets printed;
- targeted tests pass.

### B3: Runtime Store Contracts

Build:

- repository interface pattern;
- DB-backed result envelope;
- no trial/release file fallback tests;
- dev fallback metadata shape if needed;
- runtime-store docs and contract tests.

Acceptance:

- API routes do not access DB directly;
- SDK/CLI do not import internal modules;
- domain modules remain FastAPI-free.

### B4: Reference Network Slice

Build:

- canonical ID policy;
- synthetic reference-network fixtures;
- schema plan for nodes/facilities/segments;
- read-only `/api/reference-network/*` contracts;
- source-reference and lineage fields.

Acceptance:

- no real vendor/operator data;
- future map clients can consume stable reference-network API shape;
- all outputs identify missing inputs and source assumptions.

### B5: Ingestion Control Plane

Build:

- connector definition model;
- ingestion job/run model;
- normalization result model;
- data-quality/freshness model;
- mocked connector interface.

Acceptance:

- no live external API calls;
- connectors do not analyze;
- ingestion records include source refs and lineage.

### B6: Governance, Entitlement, Audit

Build:

- entitlement decision model;
- audit event model;
- export policy model;
- fail-closed unknown commercial data behavior;
- research output metadata contract.

Acceptance:

- unknown commercial data cannot be exported by default;
- audit model is available for future write operations;
- research result envelope is tested.

### B7: First Research Workflow

Build one narrow workflow:

- route-cost input validation and assumptions report, or
- reference topology read model.

Acceptance:

- output includes assumptions, missing inputs, warnings, source references,
  lineage, `research_only`, and `human_review_required`;
- no official recommendation or execution semantics.

## Backend API Rules

- Stable routes use `/api`.
- Internal routes use `/api/internal`.
- Development routes use `/api/dev`.
- SDK and CLI call `/api`.
- Route handlers validate and delegate.
- Application services orchestrate.
- Runtime store reads/writes DB.
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
- migration revision.

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

## Backend Handoff

Every backend milestone final report should include:

- files changed;
- DB policy impact;
- API policy impact;
- tests run;
- route count;
- remaining gaps;
- recommended next milestone.
