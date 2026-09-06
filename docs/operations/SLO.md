# Service Level Objectives (Preview)

Preview-grade objectives for the Eurogas Nexus runtime. These are engineering objectives for the current single-organization
deployment model, based on the CR-11 baseline. They are not contractual SLAs.

## Objectives

| Objective | Target | Evidence (automated) |
|---|---|---|
| API liveness (process up) | process alive | `/api/health/live` never depends on PostgreSQL/providers |
| API readiness | mandatory deps only | `/api/health/ready` fails when PostgreSQL/schema unavailable |
| Interactive API p50/p95/p99 | ≤100/1500/2500 ms | `scripts/ops/performance_baseline.py`; CI load smoke p95 ≤1000ms |
| API error rate, smoke paths | ≤ 5% of requests | `load_smoke.py` error-rate threshold |
| Runtime DB reachable when configured | 100% of health polls | `/api/runtime/db` + `/api/runtime/pipeline-health` |
| Data freshness honesty | 100% of sources evaluated | Source Center backend-owned `freshness_state` (fresh/late/stale/missing/not_expected/unknown/restricted) — never silent `active` for stale data |
| Audit completeness | 100% of policy decisions recorded when DB available | `audit_events` write/readback in `test_postgres_backed_smoke.py` |
| Ingestion run bookkeeping | 100% of runs recorded with structured counts/category | `ingestion_runs` + `ingestion_run_issues` + `/api/runtime/source-operations` |

## Measurement

- Latency/error: run `python scripts/ops/load_smoke.py` (in-process ASGI, no
  server). CI runs it with `--p95-threshold-ms 1000`.
- DB-backed checks: `tests/integration/test_postgres_backed_smoke.py` against
  the configured store (`scripts/ci/run_postgres_ci.sh` on PostgreSQL 16).
- Freshness: Source Center `freshness_status` per source, driven by
  `domain/monitoring/freshness.py`.

## Non-goals

- Error budgets and burn-rate alerts (production milestone).
- Multi-tenant capacity planning and load modeling (requires a real deployment).
- Performance regressions between releases are caught by the load-smoke step,
  but the threshold is a smoke baseline, not a capacity guarantee.
