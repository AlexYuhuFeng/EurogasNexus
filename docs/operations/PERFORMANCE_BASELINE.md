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

- `_latest_run_per_source` ranks each source's runs with `row_number() OVER`
  and hydrates only rank 1: the unscoped "latest" role orders by
  `started_at_utc DESC, run_id DESC`, while the success/failure roles order by
  the completion instant (`finished_at_utc` falling back to `started_at_utc`),
  then `started_at_utc DESC, run_id DESC`. The repository payload and the
  missing-vs-empty behaviour are unchanged, and rows with no run still produce
  no bucket (missing stays missing). The role ordering is corrected in the
  run-status milestone below.
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
- Run-status classification (corrected 2026-10-01, after the bounded-read
  milestone): the read model classifies each stored status through the
  canonical `IngestionRunStatus` vocabulary plus one explicit compatibility
  mapping for the four legacy lowercase spellings written by the pre-CR-09
  ingestor and simulator (`queued`/`running`/`succeeded`/`failed`). Any other
  stored value stays unknown. `SUCCEEDED_WITH_WARNINGS` counts as a success
  (it can set `last_success_at_utc`) but stays visibly qualified with the
  `last_ingestion_succeeded_with_warnings` diagnostic; `QUEUED`/`RUNNING`
  (pending), `CANCELLED` and unknown statuses are never reported as success or
  failure. The newest success/failure is selected by the completion instant
  that `last_success_at_utc` / `last_failure_at_utc` expose. Evidence for this
  correction is the focused API test suite; it is not production acceptance.
- The compatibility mapping now lives in
  `domain/dataops/run_status.py` and is shared by the source read, the
  monitoring alert scanner, `pipeline_health` and the Prometheus exporter, so
  `FAILED` and `failed` count identically everywhere. Read shapes this does not
  change: `monitoring_service._source_failure_candidates` and
  `pipeline_health` still read the newest 500 persisted runs **globally**
  (per-source streaks are lower bounds when history exceeds the window), and
  `application/dataops_observability.prometheus_metrics` loaded the full
  persisted run table per scrape (since 2026-11-26, P1-C, it reads grouped
  aggregates instead). The first is a documented limitation, not measurements; a bounded per-source streak query
  or an indexed `COUNT(*)` for the failure counter would be the next
  optimisation candidates if profiling justifies them.

## Source Center and physical reads with real ENTSOG data (2026-11-17)

Measured in-process (FastAPI test client, development profile) against a scratch
PostgreSQL 16 holding a live ENTSOG read: 29,909 flow rows, 11,113 capacity rows, 789
reference points.

| Read | Before | After |
|---|---|---|
| `GET /api/sources`, warm | 1.1-1.4 s, 138 statements | 0.27-0.37 s, 54 statements |
| `GET /api/sources`, first call of a process | 2.3 s, 138 statements | 2.4 s, 107 statements (fills the caches) |
| `GET /api/physical/flows` (volume mode) | 4-7 s (whole table loaded and validated in Python) | 0.14 s (filter in SQL; 2026-11-16) |
| `GET /api/physical/capacity` | 2.3 s | unchanged (2.6 s, same read) |

What changed for `/api/sources`:

- 60 of the 138 statements were catalogue lookups (`has_table`, column lists) repeated on
  every request by the data-quality receipts and the identity report.
  `db/schema_cache.py` remembers a table found once, with its columns, per engine (a
  weak reference, so a reused engine id is never mistaken). A missing table is never
  remembered; the schema only grows through a migration, which restarts the service.
- The identity report groups every ENTSOG flow and capacity row by the operator key inside
  its JSON metadata (0.35-0.7 s at this size, growing with the store). It is now reused
  while the data it reads is unchanged (`application/identity_resolution.cached_identity_report`):
  keyed by a cheap data version (row count and newest receipt of each identifier table and
  of `source_entity_mappings`), invalidated in the process by `record_identities` (the ENTSOG reference read, releasing a
  quarantined identifier), and bounded by a 60 s TTL for an in-place change those counters
  cannot see (a provider revising a row's operator key). An ingest that adds rows, or a new
  mapping, is therefore listed at the next read; an approval does not change identities.

`/api/physical/capacity` is left unbounded, deliberately. In volume mode it loads every
capacity row in the window and resolves overlapping validity ranges across rows
(`capacity_resolution.resolve_capacity`): the latest-received range of a series cuts the
others, including ranges that publish energy and no volume. Filtering the energy-only
rows in SQL, as `/flows` now does, could therefore change which value is served for a
period, so it is not a provably equivalent change. A bounded read needs the resolution to
move into SQL (or a resolved-capacity projection maintained at ingestion); until then the
read is 2-3 s at five weeks of ENTSOG capacity.

## Methodology rules

- Always record environment, row counts, concurrency, warm/cold state, duration,
  version, and git SHA.
- Report p50/p95/p99, not only mean.
- Re-run with the documented harness after material query/index changes.

## Portfolio and risk reads at trading-house scale (2026-11-01)

Measured in-process on SQLite with 300 supply contracts, 5,000 filled trades (one third
ETRM), 400 days of month-ahead closes and 24 curve months for six hubs, 40 credit lines and
12 mandates:

| Read | Time |
|---|---|
| `GET /api/portfolio/position-ladder?months=24` | 187 ms |
| `GET /api/portfolio/credit-exposure` | 228 ms |
| `GET /api/portfolio/mandate-usage` | 210 ms |

Legs are split by calendar month, not by day, so the work grows with legs × months held.
Mark-to-market now shares the ladder's month split instead of building a one-leg ladder per
leg (207 → 187 ms). About 40 % of the remaining time is loading trades through the ORM;
that is the next lever if books grow tenfold.
