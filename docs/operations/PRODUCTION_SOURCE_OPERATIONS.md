# Production Source Operations Runbook

Chinese companion: [PRODUCTION_SOURCE_OPERATIONS-CN.md](PRODUCTION_SOURCE_OPERATIONS-CN.md)

## Scope

R33 adds production-shaped controls around public-source ingestion. Providers
are still called only by backend scripts/connectors; clients never call a
provider directly.

## Retry policy

`src/eurogas_nexus/application/source_operations.py` owns bounded exponential
retry policies:

| Source | Retry max | First backoff | Freshness SLA |
|---|---|---|---|
| ENTSOG | 3 | 30s | 60 min |
| GIE | 3 | 60s | 360 min |
| ECB | 3 | 300s | 1440 min |
| NationalGasNTS / BBL / IUK | 2 | 60s | 43200 min |
| Weather | 3 | 60s | 360 min |

Unknown sources use a safe default (3 retries, 30s backoff, 24h SLA).

## CR-09 scheduler

```bash
python scripts/ops/run_dataops_scheduler.py --interval-seconds 60 --scan-limit 10 --run-limit 10 \
  --entsog-lookback-gas-days 7
```

`src-entsog` needs an ENTSOG window (`--entsog-lookback-gas-days`, or `--entsog-from/--to`);
without one it is blocked as a configuration error and the other sources still run.

**Read bounds.** Each public-source run is given bounds that make a complete read, in one
table (`_SOURCE_BOUNDS` in `scripts/ops/run_dataops_scheduler.py`); the ingestor's own
default of 20 records is a sample size, never a scheduled read.

| Source | Bounds | Why |
|---|---|---|
| `src-entsog` | `--limit 50000 --entsog-page-size 1000 --entsog-max-pages 50` | a 7-day unscoped flow read is about 6,800 records (7 pages), capacity about 12,200 (15 pages, 4 indicators); 50 x 1,000 is the transport's hard cap |
| `src-entsog` reference | re-read at most every 24 h (`--entsog-reference-max-age-hours 24`) | 789 points and 1,283 operator directions change rarely; `operatorpointdirections` pages at 400 rows (3 KB a row; 1,000 rows exceed the 2 MB response limit) |
| `src-gie` | `--limit 30 --gie-country nwe` | newest 30 gas days of the Europe total and the north-west Europe countries GIE publishes (revisions seen up to 4 days back); history is a separate back-fill |

An ENTSOG query that stops at its bound before the provider's data is exhausted fails the
attempt as `QUALITY_REJECTED entsog_read_bound_reached` (not retried: the same bound would
be hit again); it is never reported complete. A skipped reference refresh is reported as
`status: skipped_fresh`, not as a read.

The ENTSOG reference network is updated in place: rows are upserted under their stable
ids, and a point the provider no longer publishes is retired (`data_quality =
'retired_by_provider'`, `retired_at_utc` in its metadata), never deleted, because flows,
access points, edges and mappings reference it. Listings of the current network leave
retired rows out; reading one by id still returns it.

The scheduler reconciles the typed backend-owned source registry into
`source_runtime_states`, claims due sources with PostgreSQL SKIP LOCKED and a
partial unique `(source_id, scheduled_for_utc) WHERE trigger_type='SCHEDULED'`
index, then executes QUEUED `ingestion_runs` with failure-category-aware retry
and circuit breaking. It is restart-safe and multi-process safe.

## Legacy worker

```bash
python scripts/ops/run_public_ingestion_worker.py \
  --source entsog --source gie \
  --limit 10000 \
  --interval-seconds 3600 \
  --retry-max 3 \
  --retry-backoff-seconds 30
```

Each interval runs `ingest_public_sources.py` under the retry policy. A failed
iteration is logged and supervision continues; `ingestion_runs` remains the
source of truth for per-run evidence.

## Freshness SLA

`evaluate_source_sla(source_system, last_success_at_utc)` returns `live`,
`stale`, or `unknown` using the table above. Source Center continues to render
`freshness_status` per source.

## Remaining production work

- Deployment scheduler ownership (systemd/Kubernetes/Windows task) is not in
  this repository.
- Licensed commercial providers remain gated on credentials, entitlement, and
  live certification evidence; CR-09 never fabricates connectivity.
