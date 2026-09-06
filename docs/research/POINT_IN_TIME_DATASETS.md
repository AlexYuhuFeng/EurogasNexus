# Point-in-Time Datasets (CR-14)

This document is the operator/analyst-facing companion to
`DATASET_ARCHITECTURE.md`.

## Build via API

1. Seed the semantic catalog once:
   `python scripts/research/seed_research_catalog.py`.
2. Validate a spec:
   `POST /api/research/datasets/validate` with a `DatasetSpec` JSON payload.
3. Build and persist:
   `POST /api/research/datasets` with `{"dataset_spec": {...},
   "materialize": true}`.
4. Inspect metadata and quality:
   `GET /api/research/datasets/{dataset_snapshot_id}` and
   `GET /api/research/datasets/{dataset_snapshot_id}/quality`.
5. Export under the entitlement gate:
   `POST /api/research/datasets/{dataset_snapshot_id}/export`
   (`parquet` or `csv`).

## Eligibility pseudocode

For each `forecast_origin`:

- `available_at <= origin` is the only positive proof.
- `ingested_at` is never used as event time.
- Forecast series: choose the latest eligible vintage.
- Simulated series: excluded unless `allow_simulated=true`.
- Feature value is computed from the selected rows only.
- Target label is computed from actuals after `origin + horizon`.

## Leakage and split policy

Leakage codes include:

- `OBSERVATION_AVAILABLE_AFTER_ORIGIN` (blocker)
- `FORECAST_ISSUED_AFTER_ORIGIN` (blocker)
- `TARGET_USED_AS_FEATURE` (blocker)
- `TEMPORAL_INSUFFICIENT_IN_STRICT_DATASET` (blocker)
- `TEMPORAL_APPROXIMATE_IN_STRICT_DATASET` (blocker)
- `UNBOUNDED_FORWARD_FILL` (warning)

`DatasetSplit` supports time-based train/validation/evaluation windows with
`embargo_before` and `gap_after`; no split overlaps.

## Reproducibility

The same spec + same evidence records produce the same `content_hash` and
snapshot id. Every snapshot stores feature/target dependency versions, source
lineage, and the ontology version. Snapshot rows are immutable once
persisted.

## UAT evidence (local PostgreSQL 16)

`uat-cr14-representative-v3` (48 hourly origins, 2026-09-04 00Z to
2026-09-06 00Z):

- 192 rows, 14 columns; 183 observed / 9 missing; coverage 95.31%.
- No leakage issues; exploratory mode and simulated inputs are explicit.
- Build elapsed ~0.043s.
- Parquet 5,803 bytes; CSV 36,672 bytes under
  `output/research/cr14-uat-representative/`.
