# Target Product Architecture

## Product Vision

Eurogas Nexus should become an internal European gas research workspace where a
user can move from market context to physical context to scenario analysis in a
single governed system.

The product should answer questions such as:

- What gas assets, routes, hubs, markets, LNG terminals, storage sites, and
  delivery paths are relevant to a commercial question?
- What is the current or historical market, flow, capacity, storage, weather,
  outage, and tariff context?
- Which routes or market areas are plausible for a scenario?
- What assumptions, missing inputs, costs, risks, and data-quality warnings
  affect the result?
- What research output can be shared for human review with source references
  and lineage?

The historical Windows demo and older web/desktop projects show the intended
experience: a map-centric workspace with analysis rails, scenario inputs,
comparisons, reports, and runtime status. The current repository should build
the backend that makes that experience reliable.

## Target Users

Primary users:

- gas analysts;
- commercial researchers;
- strategy and fundamentals teams;
- operations-aware research users;
- internal reviewers who need provenance and warnings.

Secondary users:

- platform operators;
- data/governance owners;
- future client developers;
- SDK/CLI consumers.

## Core Workflows

### 1. Explore The Network

Users inspect European gas topology: hubs, market areas, nodes, routes,
interconnectors, LNG terminals, storage assets, beach delivery points, and
related physical constraints.

Backend support:

- canonical reference-network entities;
- source references and lineage;
- geometry/topology storage in PostgreSQL/PostGIS when approved;
- `/api` read APIs for future map clients.

### 2. Understand Market Context

Users inspect market prices, spreads, tariffs, flow/capacity signals, storage,
LNG, outages, weather, demand pressure, and freshness.

Backend support:

- governed ingestion;
- canonical observations;
- normalized units/currencies;
- data-quality and freshness metadata;
- entitlement-aware API responses.

### 3. Compose A Scenario

Users define a research scenario: resource, source, destination, route intent,
volume, price assumptions, cost assumptions, timing, and notes.

Backend support:

- scenario input contract;
- validation of missing inputs;
- canonical route/context resolution;
- assumption tracking.

### 4. Compare Candidates

Users compare possible routes, corridors, markets, or delivery choices with
transparent cost, warning, feasibility, and data-quality context.

Backend support:

- research-only calculation results;
- candidate ranking as analysis, not instruction;
- warnings and risk flags;
- source references and lineage.

### 5. Produce A Research Output

Users create a decision-support brief or report for human review.

Backend support:

- report-output contract;
- export entitlement check;
- required disclaimers;
- traceability to inputs, assumptions, and sources.

## Target System Components

### Backend API

The backend API is the central product contract. It should expose stable
`/api` routes for clients, internal routes for operators, and development
routes for local diagnostics.

Responsibilities:

- validate requests;
- call application workflows;
- return consistent response envelopes;
- expose health/readiness;
- keep route profiles separate.

### Application Workflows

Application workflows orchestrate domain operations. They should be small,
explicit, and testable.

Responsibilities:

- combine repositories and domain logic;
- enforce workflow-level validation;
- produce output metadata;
- avoid FastAPI and direct database dependencies.

### Domain Modules

Domain modules define research concepts and pure rules. They should not own
runtime access or HTTP behavior.

Initial domain priorities:

- reference network;
- topology/assets;
- ingestion metadata;
- market observation metadata;
- route-cost inputs;
- research output envelopes.

Later domain priorities:

- indicative netback;
- feasibility;
- allocation;
- strategy lab;
- nowcast;
- monitoring;
- reporting.

### Runtime Store

Runtime store modules are the DB-backed repository layer.

Responsibilities:

- all runtime DB reads and writes;
- typed query interfaces;
- transactions and idempotency;
- source references;
- lineage;
- schema versioning.

### Database

PostgreSQL is the runtime source of truth. PostGIS becomes the geometry store
when spatial persistence is approved.

Responsibilities:

- canonical runtime state;
- governed metadata;
- lineage and audit metadata;
- migration history through Alembic.

### Ingestion And Normalization

Ingestion brings external data into the system through explicit stages:

```text
connector -> raw archive -> normalization -> canonical archive -> PostgreSQL -> API
```

Connectors should fetch; normalizers should transform; runtime stores should
persist; services should analyze. These roles should not be mixed.

### Governance And Audit

Governance should be visible in the data model, not hidden in comments.

Responsibilities:

- entitlement decisions;
- export policy;
- audit events;
- source sensitivity;
- human-review flags;
- fail-closed behavior for unknown commercial data.

### Python SDK

The SDK is the required typed programmatic API client for V1. It should use
`/api` and never
reach into internal domain, DB, or local runtime files.

Design authority:

- `docs/clients/SDK_CLIENT_DESIGN_SPEC.md`

### CLI

The CLI is the operator and automation command surface. It should call SDK/API
clients, stay read-only by default, redact secrets, and require explicit
execution guards for any future write-like operation.

Design authority:

- `docs/clients/CLI_CLIENT_DESIGN_SPEC.md`

### Future Clients

Future web and Windows clients should be built after backend contracts are
stable. The Windows demo can inform workflow intent, but the user experience
should be redesigned around clear information hierarchy, warnings, lineage,
runtime status, and API-backed state.

Client design authority:

- `docs/clients/CLIENT_DESIGN_SYSTEM.md`
- `docs/clients/CLIENT_API_CONTRACT.md`
- `docs/clients/WEB_CLIENT_DESIGN_SPEC.md`
- `docs/clients/WINDOWS_CLIENT_DESIGN_SPEC.md`
- `docs/design/UX_LAYOUT_BLUEPRINTS.md`

## Target Data Model Themes

Data model authority:

- `docs/data/CANONICAL_DATA_MODEL_BLUEPRINT.md`

Every durable record should answer:

- What is it?
- What source produced it?
- When was it observed, retrieved, transformed, and loaded?
- What schema version produced it?
- What lineage chain led to it?
- What quality/freshness state applies?
- What entitlement/export state applies?
- Who or what changed it?

## Target Response Themes

API surface authority:

- `docs/api/API_SURFACE_BLUEPRINT.md`
- `docs/product/RESEARCH_WORKFLOW_BLUEPRINT.md`

Research outputs should include:

- assumptions;
- missing inputs;
- warnings;
- source references;
- lineage;
- freshness;
- data quality;
- `research_only`;
- `human_review_required`.

## Delivery Philosophy

Build the system as a sequence of narrow, reliable slices:

1. Make the repository safe and understandable.
2. Make PostgreSQL and migrations explicit.
3. Build the runtime store.
4. Add one canonical data slice.
5. Add ingestion metadata.
6. Add governance/audit.
7. Add one research workflow.
8. Only then expand domains and clients.

This is how the platform reaches the historical product ambition without
repeating the historical failure mode of building too much surface area before
the source of truth is stable.
