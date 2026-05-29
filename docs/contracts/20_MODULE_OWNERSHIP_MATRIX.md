# Module Ownership Matrix

| Path | Ownership | Current Status |
| --- | --- | --- |
| `apps/api` | API process entrypoint | Minimal ASGI shell |
| `apps/worker` | Future worker process | Reserved |
| `apps/scheduler` | Future scheduler process | Reserved |
| `src/eurogas_nexus/core` | Shared primitives | Minimal settings, errors, responses |
| `src/eurogas_nexus/db` | Database and repositories | Import-safe DB foundation, ingestion-run model/repository, migrations scaffold |
| `src/eurogas_nexus/runtime_store` | Ephemeral runtime state | Reserved |
| `src/eurogas_nexus/api` | FastAPI app and routes | Minimal health route |
| `src/eurogas_nexus/domain` | Pure domain model areas | Reserved |
| `src/eurogas_nexus/application` | Workflow orchestration | Reserved |
| `src/eurogas_nexus/infrastructure` | External adapters | Reserved |
| `src/eurogas_nexus/ingestion` | ETL and normalization | Reserved |
| `src/eurogas_nexus/data_quality` | Data quality checks | Reserved |
| `src/eurogas_nexus/streaming` | Future streaming contracts | Reserved |
| `src/eurogas_nexus/auth_runtime` | Runtime authorization | Reserved |
| `src/eurogas_nexus/audit` | Audit models and sinks | Reserved |
| `src/eurogas_nexus/governance` | Governance and entitlement | Reserved |
| `src/eurogas_nexus/sdk` | SDK facade | Read-only health API client shell |
| `src/eurogas_nexus/cli` | CLI commands | Read-only health check helper shell |
| `src/eurogas_nexus/internal` | Internal support | Reserved |
| `src/eurogas_nexus/legacy` | Legacy quarantine | Reserved |
| `clients/web` | Future web client | Placeholder with design docs |
| `clients/desktop` | Future desktop client | Placeholder with design docs |
| `docs/clients` | Client design authority | Active documentation package |
| `docs/design` | UX layout blueprints | Active documentation package |
| `packages/python-sdk` | Future SDK package | Empty placeholder |
| `infra/postgres` | PostgreSQL operator notes | Active documentation package |
| `infra` | Deployment assets | Documentation placeholders |
| `data` | Local data and fixtures | Empty placeholders |
| `tests` | Test suites | API, contract, integration, SDK, and CLI tests active |

