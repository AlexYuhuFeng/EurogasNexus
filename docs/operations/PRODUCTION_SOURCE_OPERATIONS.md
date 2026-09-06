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
python scripts/ops/run_dataops_scheduler.py   --interval-seconds 60 --scan-limit 10 --run-limit 10
```

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
