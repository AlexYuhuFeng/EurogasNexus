# Module Ownership Matrix

| Path | Ownership | Current Status |
| --- | --- | --- |
| `apps/api` | API process entrypoint | Active ASGI entrypoint |
| `apps/worker` | Future worker process | Reserved placeholder |
| `apps/scheduler` | Future scheduler process | Reserved placeholder |
| `src/eurogas_nexus/core` | Shared primitives | Active settings, errors, response envelopes |
| `src/eurogas_nexus/db` | Import-safe DB foundation: SQLAlchemy models, repositories, sessions, registry | Active runtime-store persistence and migration support |
| `src/eurogas_nexus/runtime_store` | Ephemeral runtime state contracts | Active contract definitions; runtime truth remains PostgreSQL |
| `src/eurogas_nexus/api` | FastAPI app, route profiles, routes, dependencies | Active public/internal/dev route surfaces |
| `src/eurogas_nexus/domain` | Pure domain models, calculations, and policy rules | Active, implemented domain areas only |
| `src/eurogas_nexus/domain/research` | Research-only calculation package (route cost, feasibility, allocation, netback, nowcast, backtest, shadow run) | Active; consolidated from legacy `workflows/` |
| `src/eurogas_nexus/application` | Workflow orchestration and application services | Active audit, retention, monitoring, source operations, storage/nomination composition |
| `src/eurogas_nexus/application/workflows` | Ingestion-run workflow orchestration | Active |
| `src/eurogas_nexus/ingestion` | Connectors, public-source ingestion, normalization | Active connector and normalization contracts; live calls remain gated |
| `src/eurogas_nexus/data_quality` | Data quality contracts | Active minimal contract definitions |
| `src/eurogas_nexus/streaming` | Optional SSE contracts | Active contract definitions only |
| `src/eurogas_nexus/governance` | Entitlement, audit, and export policy | Active |
| `src/eurogas_nexus/sdk` | Typed API consumer facade | Active Python SDK (expanded from Read-only health API client shell) |
| `src/eurogas_nexus/cli` | API-backed command interface | Active CLI (expanded from Read-only health check helper shell) |
| `src/eurogas_nexus/mcp` | Read-only stdio MCP tools | Active |
| `src/eurogas_nexus/optimization` | Deterministic optimization engines | Active network-flow, portfolio, storage, nomination |
| `src/eurogas_nexus/security` | Identity, API keys, OIDC, permissions, provider keys | Active |
| `src/eurogas_nexus/llm` | Backend-controlled LLM provider integration | Active DeepSeek integration |
| `src/eurogas_nexus/observations` | Observation domain models | Retained for contract compatibility; not part of public client package |

Reserved capabilities (external adapters, runtime authorization, audit sinks,
internal support, legacy quarantine) are documented in the contracts but are
not materialized as empty source packages. Source packages are created when an
implemented milestone provides their first module.

| `packages/python-sdk` | Future distributable Python SDK package | Placeholder; active SDK remains `src/eurogas_nexus/sdk` |
| `clients/web` | Browser/desktop Web workspace | Active React/Vite/MapLibre client |
| `clients/desktop` | Tauri desktop shell | Active Windows/Linux packaging shell |
| `infra` | Deployment component notes and assets | Active deployment documentation |
| `docs/` | Repository documentation | Active; authoritative index in `docs/README.md` |
| `data/` | Local fixtures and ignored artifacts | Not runtime truth |
| `tests/` | Python test suites | Active across API, contract, integration, unit, SDK, CLI, security, optimization, research |
