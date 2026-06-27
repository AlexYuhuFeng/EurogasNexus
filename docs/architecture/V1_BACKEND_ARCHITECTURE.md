# V1 Backend Architecture

Eurogas Nexus V1 is a research-only backend service. It is designed as a
server-deployed Python service with worker, scheduler, Web, Windows/Tauri,
Python SDK, and CLI surfaces using a shared `/api` API boundary.

For the product north star and historical-reference interpretation, see
`PROJECT_NORTH_STAR.md` and `REFERENCE_PROJECT_LESSONS.md`.

## Architectural Posture

- DB-first: PostgreSQL is the runtime source of truth.
- API-first: clients interact through backend API contracts.
- SDK-ready: SDK and CLI surfaces call the API, not internal modules.
- Import-safe: application import must not connect to DB, network, secrets,
  external APIs, LLM providers, or live connectors.
- Research-only: outputs must not be official trading recommendations, legal
  advice, approvals, execution instructions, or nomination submissions.
- Stepwise: historical implementations are reference material, not runtime
  code to import wholesale.

## Layer Map

```text
apps
  api              process entrypoint
  worker           future background process
  scheduler        future scheduled process

src/eurogas_nexus
  core             import-safe settings, errors, response primitives
  api              FastAPI app, route profiles, routes, dependencies
  db               PostgreSQL persistence boundary
  runtime_store    runtime coordination contracts
  ingestion        source import and normalization
  observations     observation contracts
  workflows        research-only workflow calculations
  governance       policy and entitlement checks
  sdk              API client facade
  cli              API-backed command interface
  security         backend-owned credential encryption helpers
```

## Client Direction

Web, Windows/Tauri, Python SDK, and CLI clients consume backend APIs. They must
not import domain, DB, or workflow internals, and they must not persist provider
API keys locally. Windows packages the shared Web bundle so UI/UX updates are
made once and reflected across both client surfaces.

## Current Runtime

- `apps.api.main` exposes `app`.
- `src/eurogas_nexus/api/app.py` creates the FastAPI app.
- `src/eurogas_nexus/api/route_profiles.py` defines development, internal, and
  release profiles.
- `GET /api/health` remains as compatibility.
- `GET /api/health` is the preferred stable health path.
- PostgreSQL is available for local development via `docker compose up -d`.
- DB foundation layer is import-safe: lazy engine/session factories, Alembic
  scaffolding, neutral persistence metadata.
- Alembic migrations are available through `0005_public_source_credentials`.
- Explicit live ingestion exists for ECB FX, ENTSOG operational flow, and GIE
  AGSI/ALSI when the operator invokes `scripts/ops/ingest_public_sources.py`.

## Deferred Runtime

- Production scheduler/retry/monitoring for live ingestion.
- Production auth, audit, entitlement, and export-governance enforcement.
- Commercial provider execution for EEX, ICE OCM, Trayport, Kpler, Platts,
  weather, broker, and LLM providers until credentials and entitlement review
  are complete.

## Delivery Roadmap

Architecture work proceeds through `V1_STEPWISE_DELIVERY_ROADMAP.md`. Business
features wait until DB, runtime store, API, governance, entitlement, and
research-output contracts are explicit and tested.
