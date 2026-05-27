# Ingestion ETL Contract

## Purpose

`src/eurogas_nexus/ingestion` owns future data ingestion boundaries and
normalization steps.

## Rules

- Raw data lands under `data/raw` only for local fixtures or manual bootstrap
  work.
- Canonicalized local artifacts land under `data/canonical`.
- Normalization must preserve source traceability.
- Ingestion jobs must be runnable without live external dependencies in tests.
- Local files are never a silent fallback in trial or release modes.

## Forbidden In Bootstrap

- Live connectors.
- Scheduled external pulls.
- Provider credentials.
- Production ETL jobs.


## Milestone 15 Additions

- Added `IngestionPayload` and `NormalizedRecord` shell types with explicit source-traceability fields.
- Added ingestion contract tests to preserve no-live-dependency and traceability boundaries.
