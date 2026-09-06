# Performance Baseline — CR-11

Methodology is recorded with every number. These are engineering baselines,
not contractual SLAs.

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

## Methodology rules

- Always record environment, row counts, concurrency, warm/cold state, duration,
  version, and git SHA.
- Report p50/p95/p99, not only mean.
- Re-run with the documented harness after material query/index changes.
