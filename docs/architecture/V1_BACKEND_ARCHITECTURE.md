# V1 Backend Architecture

Eurogas Nexus V1 is a research-only backend service. It is designed as a
server-deployed Python service with future worker, scheduler, Web, Desktop, and
SDK clients.

## Architectural Posture

- DB-first: PostgreSQL is the runtime source of truth.
- API-first: clients interact through backend API contracts.
- SDK-ready: SDK and CLI surfaces must call the API, not internal modules.
- Import-safe: application import must not connect to DB, network, secrets,
  external APIs, LLM providers, or live connectors.
- Research-only: outputs must not be official trading recommendations, legal
  advice, approvals, execution instructions, or nomination submissions.

## Layer Map

```text
apps
  api              process entrypoint
  worker           future background process
  scheduler        future scheduled process

src/eurogas_nexus
  core             import-safe settings, errors, response primitives
  api              FastAPI app, route profiles, routes, dependencies
  application      future workflow orchestration
  domain           pure research domain packages
  db               future PostgreSQL persistence boundary
  runtime_store    future ephemeral runtime coordination
  infrastructure   future adapters, object store, secrets
  ingestion        future source import and normalization
  data_quality     future data checks
  streaming        future optional streaming contracts
  auth_runtime     future authorization runtime
  audit            future audit events and sinks
  governance       future policy and entitlement checks
  sdk              future API client facade
  cli              future API-backed command interface
```

## Client Direction

Future Web, Desktop, Python SDK, and CLI clients must consume backend APIs.
They must not import domain, DB, or workflow internals.

## Current Runtime

The current runtime is intentionally minimal:

- `apps.api.main` exposes `app`.
- `src/eurogas_nexus/api/app.py` creates the FastAPI app.
- `src/eurogas_nexus/api/route_profiles.py` defines development and release
  profiles.
- `GET /v1/health` returns shell status only.

## Deferred Runtime

- PostgreSQL connection and Alembic migrations.
- Worker and scheduler execution.
- Auth, audit, entitlement, and governance enforcement.
- Ingestion, data quality, connectors, and streaming.
- SDK and CLI implementation.

