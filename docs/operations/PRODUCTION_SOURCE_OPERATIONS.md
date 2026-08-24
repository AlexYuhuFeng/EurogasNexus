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

## Worker

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
  `provider_certifications` live validation.
