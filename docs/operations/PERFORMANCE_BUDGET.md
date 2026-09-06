# Performance Budget — CR-11

Targets are based on the measured baseline in `PERFORMANCE_BASELINE.md`.
"Hard regression threshold" is a broad smoke guard, not a fragile
microbenchmark.

| Metric | Baseline | Target | Hard regression threshold | Measurement |
|---|---|---|---|---|
| Interactive API p50 | 20.9ms | ≤ 100ms | ≤ 250ms | `scripts/ops/performance_baseline.py` |
| Interactive API p95 | 1182.8ms | ≤ 1500ms | ≤ 2500ms | same harness |
| Interactive API p99 | 1978.0ms | ≤ 2500ms | ≤ 4000ms | same harness |
| Error rate, representative paths | 0% | ≤ 1% | ≤ 5% | same harness / load smoke |
| CI in-process load smoke p95 | measured per CI | ≤ 1000ms | fails above 1000ms | `scripts/ops/load_smoke.py` |
| Source Center payload | included in API p95 | ≤ 2000ms | ≤ 3500ms | `/api/sources` timing |
| Runtime source-operations payload | included in API p95 | ≤ 2000ms | ≤ 3500ms | `/api/runtime/source-operations` |
| Web production bundle | ~460KB JS main bundle | ≤ 1MB JS main bundle | fail build review above 2MB | Vite build |
| Desktop cargo check / build | passes CI | pass | pass | CI desktop job |
| Dataops scheduler scan (24 sources) | 11.8ms | ≤ 100ms | ≤ 500ms | `scripts/ops/dataops_benchmark.py` |
| Backtest throughput | recorded per engine benchmark | no universal budget | no broad gate | `scripts/ops/backtest_benchmark.py` |

## Non-goals

- No p95 budgets below the measured p50.
- No contractual SLAs.
- No active-active multi-region latency claims.
- No distributed cache/queue introduced to chase these numbers.
