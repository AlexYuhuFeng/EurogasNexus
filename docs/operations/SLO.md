# Service Level Objectives (Preview)

Preview-grade objectives for the Eurogas Nexus runtime. These are the numbers
the operator-facing checks (health, pipeline-health, load smoke, freshness)
map to; production SLOs with error budgets are part of the release-gate
milestone and are not claimed yet.

## Objectives

| Objective | Target | Evidence (automated) |
|---|---|---|
| API availability (process up) | 99% per day | `/api/health` returns 200; CI `Import API` step |
| API latency, read endpoints | p95 ≤ 500 ms (in-process baseline) | `scripts/ops/load_smoke.py` in CI (threshold 1000 ms on shared runners) |
| API error rate, smoke paths | ≤ 5% of requests | `load_smoke.py` error-rate threshold |
| Runtime DB reachable when configured | 100% of health polls | `/api/runtime/db` + `/api/runtime/pipeline-health` |
| Data freshness honesty | 100% of sources evaluated | Source Center `freshness_status` (live/stale/unknown) — never silent `active` for stale data |
| Audit completeness | 100% of policy decisions recorded when DB available | `audit_events` write/readback in `test_postgres_backed_smoke.py` |
| Ingestion run bookkeeping | 100% of runs (success/failure/blocked) recorded | `ingest_public_sources.py` failed-run paths + `ingestion_runs` |

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
