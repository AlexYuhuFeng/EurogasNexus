# Functional engine improvements

Status: in progress on `feature/functional-engine-improvements`; no main merge.

Chinese companion: [FUNCTIONAL_ENGINE_IMPROVEMENTS-CN.md](FUNCTIONAL_ENGINE_IMPROVEMENTS-CN.md).

## Objective

Connect data, models, economics and decisions through reproducible workflows. Each
slice has focused numerical and integration tests. Preserve the existing architecture
and review independent commits before the eventual main merge.

## F01: implemented weather scenario and baseline comparison

`POST /api/market/nwe-balance` accepts explicit balance history, optional regional HDD
history and forecast, outages and initial inventory. The existing GET retains its runtime
PostgreSQL projection. POST has the analyst/governed permission floor and does not
read provider records or persist data.

The backend fits the existing HDD/weekend regression on historical rows, passes HDD
into `forecast_balance`, and compares it with the same inputs without weather. Supply,
outages, initial inventory and capacity are identical between calculations. Output includes:

- daily methods, baseline, call and storage deltas;
- `WEATHER_COMPLETE`, `WEATHER_PARTIAL` or `BASELINE_ONLY` coverage status;
- coefficients and in-sample R-squared, labelled `SCENARIO_IN_SAMPLE_FIT`;
- engine version, input hash, replayable inputs and declared source references.

The target is `NWE_FLEXIBLE_SUPPLY_CALL`: Norway + LNG send-out + net storage withdrawal,
in GWh/day. It differs from total end-user demand and the research model's GB demand target.

### Input contract and replay

OpenAPI exposes `NweBalanceScenarioRequest`. History is consecutive, ends immediately
before the scenario, and contains 7–800 days. Weather fitting requires at least 30 matched
days and a non-singular design. Missing future HDD uses the baseline for that day.
Non-finite values, duplicate dates, out-of-horizon forecasts, negative predicted calls
and evidence declared available after the prediction origin are rejected.

Weather declares `NWE`, heating base, an approved gas-day calendar and a feature-policy
hash. Policy and availability declarations are not independently checked against provider
records. Echoed references are scenario provenance, not access grants or certification.

```python
from eurogas_nexus_sdk.fundamentals import calculate_nwe_balance_scenario

# inputs is an explicit NweBalanceScenarioRequest JSON object.
result = calculate_nwe_balance_scenario("https://nexus.example.com", inputs)
replay = calculate_nwe_balance_scenario("https://nexus.example.com", result.data["inputs"])
assert replay.data["input_hash"] == result.data["input_hash"]
```

The input hash identifies this engine version and canonical inputs; it is not a stored
analysis-snapshot ID. Retain the complete input object for replay. Weather coverage is
not predictive accuracy or model promotion. Inventory is the declared state at scenario
start. Outages retain the existing recent-flow-minus-unavailable-capacity convention.

API tests exercise the real engine: weather sensitivity, identical baseline, partial/no
weather, singular training, unavailable evidence, invalid dates/calendar/numbers, replay,
changed inputs and SDK/backend composition. No real provider accuracy claim is made.

## Delivery sequence

| Slice | Work | Acceptance | State |
| --- | --- | --- | --- |
| F01 | Weather scenario, baseline comparison, replay inputs | API and SDK reproduce weather-sensitive results | Implemented |
| F02 | Persisted ECMWF-to-NWE features | Approved weights, matching policies, certification, entitlement and bounded reads | Planned |
| F03 | Shared analysis manifest | Pin data, contracts, curves, FX, models and engine versions; replay and attribution | Planned |
| F04 | Task-level data readiness | Product/date/entity coverage, revision invalidation and targeted backfill | Planned |
| F05 | Engine consolidation | Inventory callers; compare methods and constraints; migrate with compatibility tests | Planned |
| F06 | Model operating lifecycle | Walk-forward baselines, interval calibration, frozen models, shadow evaluation and rollback | Planned |
| F07 | Joint multi-day resource/network/storage | Shared edges, inventory continuity, contract obligations, financing and reference solver checks | Planned |
| F08 | Common economics for valuation/backtest | Consistent cash flow, FX, costs, price basis and value attribution | Planned |
| F09 | Task-oriented APIs | Reuse jobs for idempotency, cancellation, progress, replay and comparison | Planned |

## Findings requiring separate bounded changes

- The legacy HDD list is a placeholder; persisted ECMWF degree days are a separate
  explicit surface. F01 does not implement an automated live weather integration.
- Regional balance and research weather demand target different quantities. F02 must
  establish the target and region mapping before reusing predictions.
- The live balance read groups UTC dates and sums source rows. Reconcile gas days,
  aggregate/facility overlap, observation revisions and country coverage.
- Outages may already affect recent flow. Validate incremental effects against a
  normal-flow reference before changing the existing subtraction convention.
- Allocation paths have different constraints and methods. Demonstrate equivalence or
  intentional differences before replacing callers; F01 changes no solver.
- Storage uses an inventory grid. Measure convergence and cost before choosing LP/MILP.

## Rollback and risks

F01 is an additive POST and SDK method, with no DB migration or client page change.
Remove this slice from the branch before adoption if its contract needs revision.
The scenario is not a promoted production model. Planned slices remain unimplemented
until their numerical, data-rights and operating acceptance criteria are met.
