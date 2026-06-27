# R12: SDK Release Surface Report

**Milestone ID:** R12 | **Status:** COMPLETE | **Date:** 2026-05-29

## Evidence

- 10 SDK client modules: reference_network, sources, market, physical, lng,
  storage, weather, contracts, glossary, workflows, research, health_client.
- All clients target `/api` via httpx 鈥?no backend internal imports.
- Typed Pydantic models for all route groups.
- Research computation clients (POST endpoints) for route-cost, netback,
  feasibility, allocation, monitoring, nowcast, backtest, shadow-run.
- SDK import does not load db, runtime_store, workflows, ingestion,
  observations, or governance modules (boundary test passes).

## Files

- `src/eurogas_nexus/sdk/__init__.py` 鈥?updated
- `src/eurogas_nexus/sdk/reference_network.py`
- `src/eurogas_nexus/sdk/sources.py`
- `src/eurogas_nexus/sdk/market.py`
- `src/eurogas_nexus/sdk/physical.py`
- `src/eurogas_nexus/sdk/lng.py`
- `src/eurogas_nexus/sdk/storage.py`
- `src/eurogas_nexus/sdk/weather.py`
- `src/eurogas_nexus/sdk/contracts.py`
- `src/eurogas_nexus/sdk/glossary.py`
- `src/eurogas_nexus/sdk/workflows.py`
- `src/eurogas_nexus/sdk/research.py`
- `tests/sdk/test_sdk_clients.py` (4 tests)

## Validation

- ruff: All checks passed
- pytest: 286 passed
- app: import ok, 52 routes

## Next: R13 CLI Release Surface
