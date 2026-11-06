# Functional engine improvements

F01 was merged via PR #46. F02–F09 are tracked on
`feature/functional-engine-followup`. The [Chinese guide](FUNCTIONAL_ENGINE_IMPROVEMENTS-CN.md)
covers the same workflow.

| Slice | Delivered capability |
| --- | --- |
| F01 | HDD scenarios compare the same supply call with and without weather. Inputs and results can be replayed. |
| F02 | The scenario can use runtime balance history and certified, persisted ECMWF weather. Reviewed regional point weights, forecast vintages, availability and coverage are recorded with the result. |
| F03 | Durable runs freeze the input JSON, dependency versions and numerical environment. Existing optimization and backtest paths expose the shared calculation manifest. |
| F04 | Readiness checks verify declared evidence by entity, product, unit, time window, freshness and revision. Results identify backfill windows. Revision reconciliation flags dependent runs for recomputation. |
| F05 | The engine catalog describes each solver's scope. The Phase Two resource pool and multi-day optimizer share the circulation kernel, with existing partial diagnostics preserved for infeasible resource pools. |
| F06 | Expanding-window weather validation compares a baseline, calibrates an interval on a separate partition, and freezes qualified research models for prediction and later shadow evaluation. |
| F07 | Joint optimization allocates contract supply across shared transport and storage over multiple days. It reports inventory, economic components, binding capacity and optional one-MWh capacity sensitivity. |
| F08 | Resource allocation, joint optimization and backtest funding assumptions use the same simple-interest convention with explicit actual days and day count. Scenario comparison attributes the change in value by input group. |
| F09 | The task API and CLI expose idempotent submission, progress, cancellation, restart recovery, comparison and replay through the existing Job lifecycle. |

## Run a scenario

Use a named analyst identity and a runtime database migrated through `0059_functional_runs`.
Submit a JSON file with `kind`, `inputs`, and an `idempotency_key`. The `inputs` schema is
`NweBalanceRequest` for `NWE_BALANCE`, `ReadinessRequest` for `READINESS`,
`JointRequest` for `JOINT_OPTIMIZATION`, `JointComparison` for `SCENARIO_COMPARISON`,
`WeatherRegionProfile` for `WEATHER_PROFILE`, and `ValidationRequest` for
`WEATHER_VALIDATION`. The SDK submits the same JSON.

```text
eurogas-nexus --base-url https://nexus.example.com functional submit --input run.json
eurogas-nexus --base-url https://nexus.example.com functional status --id <run-id>
eurogas-nexus --base-url https://nexus.example.com functional cancel --id <job-id>
eurogas-nexus --base-url https://nexus.example.com functional replay --id <run-id> --input replay.json
```

A replay takes a new idempotency key and uses frozen inputs. Keep the matching numerical bundle
available for reproducibility. The API returns HTTP 409 when a key is reused with a different
request or a replay requires a different bundle. Run `python scripts/ops/run_functional_worker.py`
against the same runtime database to recover queued work after a web process restart.
Completed results keep their referenced Job rows during job retention.

## Resolve weather and test models

Submit `NWE_BALANCE` with declared history and HDD values, or use `persisted_weather` with
`WeatherDegreeDayRequest` windows sharing the same policy and origin. Set
`use_runtime_history` with an empty history to resolve the current runtime aggregates at the
server read cutoff. Historical coverage must be consecutive within the requested lag. The
regional balance target is the combined call on Norwegian supply, LNG send-out and net storage
withdrawal. Current runtime history carries the aggregate coverage and gas conversion assumptions.

Submit `WEATHER_PROFILE` to freeze grid points and weights, then use `freeze-model` with the
returned run ID in `other_run_id`. An owner with the review capability can adopt the profile
using `review-model`. Reference the profile via `weather_profile_id` in the balance request.
The persisted weather path checks certification and current source access before reading data.
An open outage already reflected in recent observed flow contributes only its change against
the recent baseline. REMIT revisions are resolved as of publication and ingestion.

Use `WEATHER_VALIDATION` with historical actuals, forecast features, and fold origins that
carry their original availability times. Freeze a qualified result, run `predict`, and use
`evaluate` with the resulting prediction run ID and later actuals. Reviewer actions and retirement
are audited. The registry governs research use. Production adoption requires prospective
performance evidence on the deployment's provider data.

## Interpret optimization and readiness

The joint solver handles continuous MWh quantities, confirmed route access, shared daily
capacity, storage continuity and explicit opening and terminal values. This formulation
uses unit storage efficiency. Use the separate facility dispatch solver for storage losses.
The joint engine bounds nodes, arcs and iterations and observes the job's compute deadline.
A small capacity increase is measured by re-solving the scenario. Comparison with
`attribute: true` attributes value in a fixed order and reports infeasible intermediate cases.

Use a `READINESS` run to inspect missing intervals and the selected evidence versions. Apply
version changes with `reconcile` or through the server reconciliation function. Historical
results remain available with their original inputs and a separate stale dependency status.
Use the existing source backfill workflow for the returned intervals.

Validation includes API and authorization regression tests, independent exhaustive flow
enumeration, a comparison against SciPy HiGHS linear programming in an isolated verification
environment, and PostgreSQL migration and concurrency tests registered in CI.
The [HiGHS reference](https://docs.scipy.org/doc/scipy/reference/optimize.linprog-highs.html)
describes the independent numerical formulation.
