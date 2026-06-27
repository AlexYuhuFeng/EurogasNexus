# R4: Source Registry and Ingestion Control Plane Report

**Milestone ID:** R4
**Status:** COMPLETE
**Date:** 2026-05-29

## Evidence

- Source registry contracts: SourceRegistryEntry, SourceStatus enum.
- Ingestion run model: IngestionRun, IngestionRunStatus enum.
- Normalization status model: NormalizationStatus enum, NormalizedRecord.
- Ingestion payload: IngestionPayload with source traceability.
- Connector base protocol: Connector (fetch-only), ConnectorMetadata.
- MockConnector: returns empty payloads, never calls external APIs.
- 7 connector shells: ECB, ENTSOG, GIE, EEX, Trayport, ICE OCM, Weather.
- Each connector declares datasets, entitlement requirements, freshness
  expectations, export restrictions.
- 3 new API routes: GET /sources, GET /sources/{id}, GET /ingestion-runs.
- All routes serve synthetic fixture data (7 sources, 3 ingestion runs).
- Connectors perform no analytics 鈥?fetch contract only.
- No live connector execution at import time or in tests.

## Files Created / Modified

- `src/eurogas_nexus/ingestion/__init__.py` 鈥?Updated exports
- `src/eurogas_nexus/ingestion/contracts.py` 鈥?SourceRegistryEntry, IngestionRun,
  IngestionPayload, NormalizedRecord, status enums
- `src/eurogas_nexus/ingestion/connectors/__init__.py` 鈥?Connector exports
- `src/eurogas_nexus/ingestion/connectors/base.py` 鈥?Connector protocol,
  MockConnector, ConnectorMetadata
- `src/eurogas_nexus/ingestion/connectors/ecb.py` 鈥?ECB FX connector shell
- `src/eurogas_nexus/ingestion/connectors/entsog.py` 鈥?ENTSOG connector shell
- `src/eurogas_nexus/ingestion/connectors/gie.py` 鈥?GIE connector shell
- `src/eurogas_nexus/ingestion/connectors/eex.py` 鈥?EEX connector shell
- `src/eurogas_nexus/ingestion/connectors/trayport.py` 鈥?Trayport connector shell
- `src/eurogas_nexus/ingestion/connectors/ice_ocm.py` 鈥?ICE OCM connector shell
- `src/eurogas_nexus/ingestion/connectors/weather.py` 鈥?Weather connector shell
- `src/eurogas_nexus/api/routes/public/sources.py` 鈥?3 read-only API routes
- `src/eurogas_nexus/api/route_registration.py` 鈥?Registered sources router
- `.agent/plans/V1_R4_INGESTION_CONTROL_EXECPLAN.md` 鈥?ExecPlan
- `data/release_v1/r4_ingestion_control_report.md` 鈥?This report
- `tests/contract/test_ingestion_contracts.py` 鈥?Contract tests (7)
- `tests/contract/test_connector_contracts.py` 鈥?Connector tests (6)
- `tests/api/test_sources_api.py` 鈥?API tests (7)

## DB Impact

No new DB tables. Connector contracts are pure Python interfaces. Source registry
and ingestion run data served from in-memory fixtures.

## API Impact

3 new read-only routes: GET /api/sources, GET /api/sources/{id},
GET /api/ingestion-runs. Route count: 14 鈫?17.

## Validation

- ruff: All checks passed
- pytest: 178 passed (was 158 before R4; +20 new tests)
- app: import ok, 17 routes

## Next Milestone

R5: Context Observation Slices (market, flow, LNG, storage, weather observations)
