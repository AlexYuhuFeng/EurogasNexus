# V1 Domain Delivery Map

## Purpose

This document maps the full Eurogas Nexus ambition into backend delivery slices.
It prevents future implementation agents from treating every historical module
as immediately in scope.

## Product Capability Universe

Eurogas Nexus may eventually cover:

- topology and physical network modeling;
- assets, facilities, hubs, markets, routes, and corridors;
- ENTSOG capacity/flow/outage context;
- GIE storage and LNG context;
- market prices, FX, tariffs, fees, and regulated cost context;
- route cost, indicative netback, feasibility, allocation, and strategy
  analysis;
- weather-adjusted demand and nowcast context;
- monitoring, alerts, anomaly detection, and research reporting;
- SDK, CLI, and future web/Windows clients.

V1 does not implement all of this at once. V1 builds the backend foundation and
then adds narrow research-only slices.

## Priority Layers

### Foundation Layer

Must exist before domain behavior:

- repository governance;
- import safety;
- DB URL resolution and redaction;
- lazy SQLAlchemy engine/session helpers;
- Alembic migration lifecycle;
- `/api/v1` route policy;
- app import without DB;
- SDK/CLI API-only boundary;
- validation commands.

### Runtime Truth Layer

Must exist before production-like reads/writes:

- PostgreSQL required-table registry;
- runtime store interface;
- repository factory;
- transaction/session lifecycle;
- DB unavailable behavior;
- no trial/release local-file fallback;
- migration state reporting;
- operator runbooks.

### Data Governance Layer

Must exist before real source data:

- source-reference model;
- lineage model;
- freshness and quality model;
- entitlement decision model;
- export policy;
- audit event contract;
- research-output metadata contract.

### Domain Slice Layer

Only after the above layers are testable, add one domain slice at a time.

## Domain Slice Order

### Slice A: Reference Network

Purpose:

- establish canonical topology identifiers and read-only reference-network
  contracts.

Entities:

- network node;
- facility;
- segment;
- zone;
- market area;
- source reference.

API:

- `/api/v1/reference-network/health`
- `/api/v1/reference-network/nodes`
- `/api/v1/reference-network/facilities`
- `/api/v1/reference-network/segments`

Data policy:

- synthetic fixtures only until source entitlement is approved;
- no raw ENTSOG/GIE/vendor data committed.

### Slice B: Ingestion Control Plane

Purpose:

- model ingestion jobs/runs and normalization status without running live
  connectors.

Entities:

- connector definition;
- ingestion job;
- ingestion run;
- source reference;
- normalization result;
- data quality result.

API:

- `/api/v1/ingestion/health`
- `/api/v1/ingestion/runs`
- `/api/v1/ingestion/sources`

Data policy:

- mocked connector tests only;
- no live external API calls.

### Slice C: Market Observation Metadata

Purpose:

- store market observation metadata and canonical unit/currency policy before
  analytics.

Entities:

- dataset;
- market venue;
- market observation;
- unit/currency normalization metadata;
- source reference.

API:

- `/api/v1/market-data/health`
- `/api/v1/market-data/datasets`
- `/api/v1/market-data/observations`

Data policy:

- synthetic observations only until licensed source usage is approved.

### Slice D: Route Cost Inputs

Purpose:

- model route-cost input requirements before calculating results.

Entities:

- route;
- route leg;
- cost component;
- tariff reference;
- calculation assumption.

API:

- `/api/v1/route-cost/inputs`
- `/api/v1/route-cost/assumptions`

Output policy:

- no official recommendation;
- no execution instruction;
- `research_only` and `human_review_required` required.

### Slice E: Indicative Analysis Outputs

Purpose:

- introduce narrow, research-only outputs after input/source/governance
  contracts exist.

Possible outputs:

- route cost result;
- indicative netback result;
- feasibility result;
- scenario comparison result.

Required fields:

- assumptions;
- missing inputs;
- warnings;
- source references;
- lineage;
- `research_only`;
- `human_review_required`.

## Modules To Keep Reserved Until Approved

These directories may exist as placeholders but should not grow runtime behavior
without a scoped milestone:

- `domain/netback`;
- `domain/feasibility`;
- `domain/allocation`;
- `domain/strategy_lab`;
- `domain/nowcast`;
- `domain/monitoring`;
- `domain/reporting`;
- `infrastructure/connectors`;
- `streaming`;
- `auth_runtime`;
- `audit`;
- `governance`.

## Historical Module Translation

Historical modules and docs map to current V1 concepts as follows:

| Historical area | Current V1 treatment |
| --- | --- |
| Web/Tauri client | Future client reference only |
| Map shell | Future API consumer requirement |
| Local SQLite/runtime files | Not runtime truth |
| Rust/axum API | Architecture reference, not current stack |
| Broad Python services | Cautionary example of domain sprawl |
| LLM/RAG gateway | Deferred future research support only |
| Live source configs | Connector contract reference only |
| Generated reports | Report-output policy reference only |

## Acceptance Rule For New Slices

A domain slice is not ready for implementation unless it has:

- milestone ExecPlan;
- contract doc;
- DB impact doc;
- API path doc;
- data policy;
- tests;
- validation commands;
- explicit non-goals;
- rollback notes.

If any of these are missing, Codex should add documentation first and stop
before runtime code.
