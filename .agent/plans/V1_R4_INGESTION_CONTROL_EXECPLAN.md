# V1 R4 Source Registry and Ingestion Control Plane ExecPlan

## 1. Goal

Model ingestion jobs, runs, normalization status, source references, freshness,
and quality results. Define connector contracts for the seven V1 source families
(ECB, ENTSOG, GIE, EEX, Trayport, ICE OCM, weather). No live connector
execution — interfaces, mocks, and shells only.

## Internet Requirement

Internet required: no

Reason: This milestone creates interface shells, mocked connectors, and DB
models. No live external APIs are called. Tests use mocks and synthetic fixtures.

Fallback if offline: Not needed.

## 2. Non-goals

- No live connector execution.
- No live external API calls.
- No provider credentials.
- No scheduled ingestion runs.
- No market data, route cost, netback, or workflow logic.
- No frontend, desktop, Node, Rust work.

## 3. Product boundary

This milestone adds the ingestion control plane: source registry, connector
interfaces, ingestion run tracking, and normalization status. Connectors are
mocked — no live data fetches. The DB gets source registry and ingestion tracking
tables.

## 4. Files to create/modify

### New ingestion package
- `src/eurogas_nexus/ingestion/__init__.py`
- `src/eurogas_nexus/ingestion/contracts.py` — IngestionPayload, NormalizedRecord,
  IngestionJob, IngestionRun, NormalizationStatus, SourceRegistryEntry
- `src/eurogas_nexus/ingestion/connectors/__init__.py`
- `src/eurogas_nexus/ingestion/connectors/base.py` — Connector protocol, mock base
- `src/eurogas_nexus/ingestion/connectors/ecb.py` — ECB connector shell
- `src/eurogas_nexus/ingestion/connectors/entsog.py` — ENTSOG connector shell
- `src/eurogas_nexus/ingestion/connectors/gie.py` — GIE connector shell
- `src/eurogas_nexus/ingestion/connectors/eex.py` — EEX connector shell
- `src/eurogas_nexus/ingestion/connectors/trayport.py` — Trayport connector shell
- `src/eurogas_nexus/ingestion/connectors/ice_ocm.py` — ICE OCM connector shell
- `src/eurogas_nexus/ingestion/connectors/weather.py` — Weather connector shell

### New API routes
- `src/eurogas_nexus/api/routes/v1/sources.py` — GET /sources, GET /sources/{id},
  GET /ingestion-runs

### Updated files
- `src/eurogas_nexus/api/route_registration.py` — register sources router
- `src/eurogas_nexus/db/registry.py` — add source/ingestion tables
- `docs/contracts/10_INGESTION_ETL_CONTRACT.md` — update for R4

### New migration
- `alembic/versions/0004_r4_source_registry.py`

### Report
- `data/release_v1/r4_ingestion_control_report.md`

### Tests
- `tests/contract/test_ingestion_contracts.py`
- `tests/contract/test_connector_contracts.py`
- `tests/api/test_sources_api.py`

## 5. Dependency policy

No new dependencies.

## 6. Data policy

No real vendor data. No credentials. Synthetic fixtures only. Connector shells
are interface definitions with no live execution path.

## 7. API impact

New read-only routes under `/api/v1/`:
- GET /sources — list registered source systems
- GET /sources/{source_id} — single source detail
- GET /ingestion-runs — list ingestion runs with optional source filter

## 8. DB impact

New migration: 0004_r4_source_registry
No new DB tables — source registry and ingestion metadata are served from
in-memory fixture data at this milestone (DB tables come in later milestone when
persistence is required). Connector contracts are pure Python interfaces.

## 9. Tests

Required tests:
- Source registry entries have required fields (source_system, datasets, status).
- Connector protocol defines fetch contract.
- Mock connectors implement the protocol.
- All 7 connector shells are importable.
- Connectors do not call external APIs at import time.
- Ingestion run model tracks status, timestamps, source.
- Normalization status model preserves source traceability.
- API routes return 200 with fixture data.
- Default tests remain DB-free.

## 10. Validation commands

```powershell
ruff check .
pytest -q tests/contract/test_ingestion_contracts.py tests/contract/test_connector_contracts.py tests/api/test_sources_api.py
pytest -q tests/api tests/contract tests/integration tests/security tests/sdk tests/cli
python -c "from apps.api.main import app; print('app import ok'); print(len(app.routes))"
```

## 11. Acceptance criteria

- 7 connector shells exist (one per V1 source family).
- Connector protocol enforces fetch-only contract.
- Connectors perform no analytics.
- No live connector calls at import time or in tests.
- Source registry entries are importable and typed.
- Ingestion run model tracks source, status, timestamps.
- Normalization status preserves source traceability.
- API serves source registry data through fixtures.
- App import DB-connection free.
- Default tests DB-free.

## 12. Rollback notes

Revert ingestion package, API routes, route registration, tests, and report.
No DB rollback needed.
