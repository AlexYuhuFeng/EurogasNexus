# Performance Baseline — CR-11

Methodology is recorded with every number. These are engineering baselines,
not contractual SLAs.

## September 30 Local Source-Status Verification

Authenticated `GET /api/sources` on the existing local PostgreSQL deployment
took 6.539 seconds before the read-query correction, and 1.327, 0.363 and
0.351 seconds after restarting the API with it. Each response contained 24
sources. This is an isolated local observation, not a controlled load comparison
or customer SLO acceptance. Startup concurrency, cold-cache effects and
production-sized workloads still need validation. No migration or business-data
mutation was performed for these measurements.

## Environment

- Date: 2026-09-07
- Repository HEAD: current `main` at CR-11 implementation
- Hardware: local Windows developer workstation
- Database: local PostgreSQL 16 container (`eurogas_nexus_cr10`), migration
  head `0029_enterprise_identity_v1`, ~24 source runtime rows, empty
  strategy/ingestion rows in the scratch store
- Harness: `scripts/ops/performance_baseline.py`, in-process ASGI transport,
  400 requests, 10 concurrent requests, 8 representative paths
- Software: Python 3.13 local, same FastAPI/SQLAlchemy versions as the repo

## Measured results

```text
latency_ms:
  p50 = 20.9
  p95 = 1172.3
  p99 = 2173.9
  mean = 257.2
errors = 0
elapsed = 11.5s for 400 requests
```

The p95/p99 tail is dominated by `/api/sources` and
`/api/runtime/source-operations`, which intentionally perform multiple
read-only source/state queries per request. This is the evidence basis for the
budget below; the broad CI load smoke remains a coarser guard
(200 requests, 8 concurrency, p95 ≤ 1000ms in-process without the configured
runtime DB).

## Background baselines

- Dataops scheduler scan: 0.0118s for 24 sources.
- Freshness evaluation: 0.0002s for 24 sources.
- Authorization expansion: 8–28 microseconds per role.
- Audit insertion: 20.7ms (one PostgreSQL append).
- ECB live ingestion: 12 normalized rows, succeeded (public source).

## Source Center read shape (2026-09-30)

Baseline `f3b89bc`. The authenticated Source Center read (`GET /api/sources`)
annotates every registered source with runtime counts, newest observation,
newest run, newest succeeded run, newest failed run, credentials and
certification. Three shapes in that read grew with history rather than with the
number of registered sources:

- `_latest_ingestion_status_by_source` loaded **every** persisted
  `ingestion_runs` row through the ORM (one `SELECT ... ORDER BY
  started_at_utc DESC`, no bound) and kept the first match per source in Python.
  The simulated market price worker writes a run per source per 10-second tick
  (`src/eurogas_nexus/ingestion/simulated_market_prices.py`:
  `DEFAULT_SIMULATED_MARKET_PRICE_INTERVALS_SECONDS`), so this read grows without
  bound with pilot uptime.
- `_runtime_source_counts` issued one `COUNT(*)` per registered source system:
  thirteen reads of `market_observations` per request (eleven price systems,
  Weather, ECB) plus four screen-order reads.
- `/api/ingestion-runs` read the same full run history and applied its `limit` in
  Python, so the listing's cost did not depend on the requested page size.

### Worker diagnostic (scratch SQLite store, not the live measurement)

A scratch SQLite store shaped like the runtime store (40,000 market observations
across six systems, 100,000 ingestion runs across six sources, one credential
and one runtime-state row) was read through the same route functions, counting
statements and rows hydrated:

```text
phase                                 before                        after
_runtime_source_counts                32 statements, 155 ms         17 statements, 59 ms
  of which market_observations counts 13                            1
_latest_ingestion_status_by_source    1 statement, 100,000 rows,    3 statements, 6 rows,
                                      3,733 ms                      470 ms
_sources_with_runtime_status (total)  42 statements, 3,818 ms       29 statements, 522 ms
```

The live PostgreSQL store has `ix_market_observations_source_time` (migration
0010) and `ix_ingestion_runs_source_started` (migration 0028), so its per-system
scans and the per-source ranking can use indexes the scratch store does not
declare. The statement and hydrated-row counts are the durable evidence; the
millisecond values are SQLite-local and indicative only. The live before/after
measurement on the parent's local PostgreSQL store, and SQL review, are owned by
the parent review; this file does not claim a live figure.

### Replacement shapes

- `_latest_run_per_source` ranks each source's runs with `row_number() OVER
  (PARTITION BY source_id ORDER BY started_at_utc DESC, run_id DESC)` and
  hydrates only rank 1. `run_id` is a new deterministic tie-break for runs that
  share a `started_at_utc`; the previous shape left those ties to the database.
  Latest / latest-succeeded / latest-failed results and the repository payload
  are otherwise unchanged, and rows with no run still produce no bucket
  (missing stays missing).
- `_row_counts_by_source_system` reads one grouped `COUNT(*)` per observation
  table. The four screen-order systems keep the previous `source_system ==
  system OR provider_id == system` semantics by combining grouped
  `(source_system, provider_id)` counts in Python; the both-at-once row is still
  counted once.
- `/api/ingestion-runs` now applies its `source_id` filter and `limit` in the
  database. An empty `source_id` keeps the legacy unfiltered behaviour.

### Remaining shapes (not changed here)

- Eight TSO-tariff `COUNT(*)` reads on the small transcribed tariff table, the
  six per-table `MAX(observed_at_utc)` group-bys in
  `_runtime_source_latest_observed`, and the full credentials / runtime-state /
  certification reads are bounded by table or source count but still one walk
  each. The next useful measurement is `EXPLAIN (ANALYZE, BUFFERS)` for
  `GET /api/sources` on the live store, or `pg_stat_statements` sorted by total
  time, before changing any of them.
- Pre-existing behaviour preserved deliberately: run-status matching in this
  read recognises only the legacy lowercase `succeeded` / `failed` values. Runs
  written by the CR-09 scheduler use uppercase `SUCCEEDED` / `FAILED`
  (`IngestionRunStatus`), so they currently affect neither the failure
  connectivity state nor the last-success/last-failure timestamps. Changing that
  is a functional decision, not a performance fix, and was left for review.

## Methodology rules

- Always record environment, row counts, concurrency, warm/cold state, duration,
  version, and git SHA.
- Report p50/p95/p99, not only mean.
- Re-run with the documented harness after material query/index changes.
