# Weather-Demand Prediction Runtime

## Purpose

`application/research/weather_demand_prediction_runtime.py` is the bounded
read-only consumer between a **frozen fitted** `DemandModelResult` and one future
native-unit demand prediction. It closes the missing runtime composition for the
already-implemented pure predictor without adding a second solver, a fitting path,
a baseline fallback, an API, a scheduler, source activation or persistence.

The explicit inputs are:

- the actual frozen `DemandModelResult` (already fitted elsewhere; this module
  never fits, refits or reads actual target demand);
- one explicit gas day and one aware prediction origin;
- one `WeatherDemandBridgeConfig` for that exact day/origin;
- the explicit point bindings, degree-day policy and feature policy;
- an explicit caller-declared regional-weighting evidence reference;
- a bounded forecast read limit no greater than
  `MAX_FORECAST_READ_LIMIT` (256).

The fitted result's selection evidence must already be available at the
prediction origin. Scope, region, native unit, gas-day calendar and feature-policy
hash must all match the frozen model and the explicit weather inputs. Whether the
gas day is still in the future remains a core-owned predictor rule; this module
does not reimplement it.

## Execution Path

For a selected weather-calendar ridge model the runtime:

1. computes the single gas-day bracket from the explicit max-hold policy;
2. reads persisted ECMWF rows through the existing bounded
   `read_ecmwf_forecasts` SQL prefilter;
3. projects each persisted record with
   `project_forecast_observation_record`;
4. builds the bounded left-hold bridge with `build_weather_demand_inputs`;
5. derives degree days with `compute_degree_days_from_bundle`;
6. takes the complete `DailyWeatherFeature` rows from the actual domain result;
7. calls `predict_selected_demand` with exactly one feature row.

There is no numerical duplication and no alternative regression or degree-day
implementation. If the bridge produces no interval, the degree-day result is
incomplete, or no feature row exists, the runtime returns
`INSUFFICIENT_FORECAST_COVERAGE` with no prediction. It does not invent zero
weather and does not fall back to the calendar baseline.

The forecast read bracket is:

```text
valid_from = gas_day_start - max_hold
valid_to   = gas_day_end + max_hold + 1 microsecond
```

The extra microsecond preserves an instant exactly at the outer bracket despite
the repository's half-open validity window. One request covers exactly one gas
day; the read limit is the smaller of the explicit request limit and the bridge
row bound, and is validated before any query. Overflow is a typed refusal rather
than truncation. The repository's own `no_autoflush` scope leaves caller-pending
rows unflushed; this module never commits, flushes or rolls back caller work.

## Selected Calendar Baseline

If the frozen core already selected `CALENDAR_BASELINE`, the runtime does not read
forecast rows and does not pass a weather feature to the predictor. It calls the
same `predict_selected_demand` entry point with `weather_feature=None` and returns
the core's explicit `CALENDAR_BASELINE_REFERENCE` label. Evidence records
`consumption_basis=CALENDAR_BASELINE_REFERENCE`, `weather_consumed=False`, no
selected vintage, no forecast observation IDs and no weather-derived source refs.
This is a reference from the selected baseline, not a silent fallback from a
failed weather model.

## Evidence and Labels

`WeatherDemandPredictionRequest`, `WeatherDemandPredictionResult`,
`WeatherDemandPredictionEvidence` and the diagnostics are immutable dataclasses.
The request hash is deterministic and binds the selected/baseline/candidate model
hashes, selection hash and availability, model identity, feature-policy hash,
degree-day policy, bridge bounds, point bindings, declared weighting reference,
read limit and forecast evidence basis.

Evidence also retains:

- the actual selected vintage and its stable identifier;
- every forecast observation ID read by the bounded query;
- feature and degree-day source refs, plus the model's source, target-revision and
  training-vintage identities;
- the feature-policy hash, selected/candidate/baseline model hashes and selection
  hash;
- the native target unit (`MSCM`) and the core prediction/selection hashes.

`regional_weighting_evidence_basis` is always
`CALLER_DECLARED_PROVENANCE_NOT_REVIEWED`. This module does not review, validate or
endorse regional weights.

Every result is research-only, `NOT_PROMOTED`, and explicitly carries
`prospective_accuracy_claim=False` and `gb_representative_claim=False`. It is not
a provider-history model, an accuracy result, a GB-representative forecast or a
customer-facing production claim.

## Genuine Receipt Basis Only

`ForecastEvidenceBasis.GENUINE_RECEIPT_AVAILABILITY` is the only implemented
evidence basis. The staged S4 archive/reanalysis basis is **not implemented** here:
there is no archive read, no archive fallback and no reconstruction claim. A
caller naming an unsupported basis receives the typed
`WeatherDemandPredictionArchiveBasisError`.

## Typed Refusals

The module defines stable typed errors with safe messages:

- `WeatherDemandPredictionValidationError` for invalid explicit requests, model
  identity, policy, calendar, limits or binding mismatches;
- `WeatherDemandPredictionArchiveBasisError` for the unimplemented archive basis;
- `WeatherDemandPredictionCoreError` when the actual domain bridge, degree-day
  solver or predictor refuses (including core model/selection integrity checks);
- `WeatherDemandPredictionReadError` for a failed persisted read, with raw database
  text withheld;
- `WeatherDemandPredictionReadOverflowError` when the bounded query overflows.

Missing coverage is a result status, not an exception and not a fabricated value.

## Out of Scope

This stage adds no API, SDK, CLI, permission, source activation, scheduler,
Alembic table, persistence path, scenario policy, unit conversion or promotion
workflow. Future scenario integration must consume the returned native `MSCM`
value and apply an audited unit conversion outside this runtime.

## Validation

Focused unit coverage exercises a selected weather model, an already-selected
calendar baseline, missing bridge/degree-day coverage, late issue/receipt
exclusion, bounded read arguments, overflow and safe database errors, model and
binding mismatches, selection-time bounds, core tamper refusal, and prediction
without NumPy or a fitter. The real PostgreSQL module creates a disposable UUID
schema, commits 21 days of synthetic training mechanics, obtains the frozen model
through the existing `run_weather_demand_runtime`, persists future forecast rows,
and runs the actual repository/projection/bridge/degree-day/core-predictor path.
It also proves late-receipt SQL exclusion and that a caller-pending forecast row is
not flushed or read.

Those fixtures are synthetic mechanics only. NumPy is optional in the hosted
environment, so the fitted PostgreSQL case is skipped when it is absent; the module is registered in the scientific CI workflow where NumPy is installed
and skipping cannot satisfy the numerical gate. See
[ML readiness](../research/ML_READINESS.md).
