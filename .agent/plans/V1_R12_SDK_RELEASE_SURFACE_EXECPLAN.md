# V1 R12 SDK Release Surface ExecPlan

## 1. Goal

Expand the Python SDK to cover all released `/api/v1` route groups. Each module
provides typed Pydantic models and client functions calling the backend API.
No backend internal imports.

## 2. Internet: no (all local Python)

## 3. Files

- `src/eurogas_nexus/sdk/__init__.py` — re-export all clients
- `src/eurogas_nexus/sdk/reference_network.py` — nodes, edges, facilities, hubs
- `src/eurogas_nexus/sdk/sources.py` — sources, ingestion runs
- `src/eurogas_nexus/sdk/market.py` — observations, FX, spreads
- `src/eurogas_nexus/sdk/physical.py` — flows, capacity, outages
- `src/eurogas_nexus/sdk/lng.py` — terminals, observations
- `src/eurogas_nexus/sdk/storage.py` — sites, observations
- `src/eurogas_nexus/sdk/weather.py` — stations, observations, HDD/CDD
- `src/eurogas_nexus/sdk/contracts.py` — capacity, routes
- `src/eurogas_nexus/sdk/workflows.py` — workflow fixtures
- `src/eurogas_nexus/sdk/glossary.py` — glossary
- `src/eurogas_nexus/sdk/research.py` — POST computation endpoints
- `tests/sdk/test_sdk_clients.py`
- `data/release_v1/r12_sdk_release_surface_report.md`

## 4. Acceptance

- SDK calls `/api/v1` only.
- SDK does not import backend internals.
- Typed clients for all route groups.
- All client functions redact secrets in errors.
