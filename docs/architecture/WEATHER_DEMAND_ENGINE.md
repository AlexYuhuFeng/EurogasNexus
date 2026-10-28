# Weather-to-demand engine (pure research core)

Status: implemented domain slice; unvalidated numerically and not production-promoted.

This slice is the adapter-neutral core for RFC-0003 phase C. It does not fetch
ECMWF data, read storage, write storage, expose API/UI code, schedule work or
assemble a European aggregate. A later adapter can supply immutable forecast
vintages from the existing weather/research foundations.

## Weather features

`src/eurogas_nexus/domain/research/weather_demand.py` exposes frozen:

- `ForecastTemperatureInterval` with location, valid UTC start/end, mean
  temperature, `issued_at`, `available_at`, provider/model/run, source ref and a
  required `temporal_method` tag.
- `RealizedTemperatureInterval`, a distinct type with no forecast-vintage field
  and the same required `temporal_method` provenance.
- `TemperatureDerivationMethod`, with explicit `PROVIDER_INTERVAL_MEAN` and
  `EXPLICIT_DERIVED_HOLD` values. This module does not convert an instant to a
  held mean; a future adapter that does so must label the result
  `EXPLICIT_DERIVED_HOLD` and cannot present it as a provider interval mean.
- `RegionLocationWeight` using exact `Decimal` weights. Weights must be
  non-negative, unique by location and sum exactly to one. No population data is
  invented.
- `DegreeDayPolicy` with explicit heating/cooling bases, maximum gap and minimum
  covered fraction. There is no implicit 15.5 °C base, interpolation,
  extrapolation or weather-climatology fill.
- `DegreeDayFeaturePolicy`, the typed immutable identity of the weather features
  a demand model may consume: region, heating/cooling bases, exact location
  weights, gas-day calendar, coverage policy and temporal derivation method.
  Region and weights are required fields with no fallback. Its `policy_hash` is
  a SHA-256 fingerprint over that structured identity (not caller free text and
  not a particular day's feature values), so it changes when the region, bases,
  exact weights, coverage thresholds, calendar or temporal method change.
  Equivalent exact `Decimal` weights hash equally after canonicalization.
- `DegreeDayRequest` with explicit gas days, prediction origin, calendar version
  and optional forecast-vintage selection. All intervals in one request must
  share the same temporal derivation method; provider means and explicitly
  derived holds cannot be mixed in one feature identity.

`compute_degree_days` reuses `domain.market.gas_day` for 23/24/25-hour UTC gas-day
boundaries. Forecast eligibility is `issued_at <= origin AND available_at <=
origin`; a future valid interval is allowed. The input may contain multiple
vintages, but the engine selects one newest available common vintage and never
fills missing coverage from an older run. Later-issued data is excluded. Mixed
forecast/realized inputs, overlapping intervals in the selected vintage and
ambiguous equally-newest vintages are refused.

The request and `DegreeDayPolicy` actually used are propagated into the result as
a `DegreeDayFeaturePolicy`. `DegreeDayResult.feature_policy_hash` therefore
identifies the real region, bases, weights, calendar, coverage and temporal
method, not a caller-supplied label. Every row from `feature_rows()` carries that
same frozen policy, with `region` and `feature_policy_hash` projections, so
downstream fitting cannot silently lose the identity.

Outputs are separately named:

| Name | Meaning |
| --- | --- |
| `DAILY_MEAN_HDD` | `max(0, heating_base - covered-period mean temperature)` |
| `DAILY_MEAN_CDD` | `max(0, covered-period mean temperature - cooling_base)` |
| `TIME_INTEGRAL_HEATING_DEGREE_DAY` | heating degrees integrated over true UTC time, divided by 24 hours |
| `TIME_INTEGRAL_COOLING_DEGREE_DAY` | cooling degrees integrated over true UTC time, divided by 24 hours |

The threshold-before-integration values can differ from the daily-mean values
when temperature crosses a base. Every gas day reports its true UTC duration and
covered fraction. If any required location is below the explicit gap/fraction
policy, all four values are `None`, never zero. Location weights are applied only
after each required location is complete.

These calculations use binary floating point. They are physically approximate,
not financial-exact arithmetic.

## Demand fitting

`fit_weather_demand_model` accepts frozen `DemandTargetRow` revisions in one
native unit and `DailyWeatherFeature` rows with independent availability and
prediction-origin evidence. It refuses mixed forecast/realized provenance and
basis mismatch. It never converts `Mscm` to `MWh`, invents a calorific value or
combines regions.

`DemandModelPolicy` requires an `expected_feature_policy` and checks that its
region and gas-day calendar agree with the model policy. Before any training or
prediction work, every supplied feature row is checked against that expected
identity: a row from another region, another base pair, another weight set or
another coverage/temporal method is refused. This covers holdout rows as well as
training rows, so a GB model cannot fit or predict with DE features and a 15.5 °C
feature policy cannot pass into an 18 °C model. Baseline and candidate models
both record the expected `feature_policy_hash`, and the canonical model hash
includes it; there is no mixed-baseline fallback.

The calendar baseline is a frozen month-mean method. The candidate uses:

- annual sine/cosine seasonality;
- Monday-reference weekday indicators;
- explicitly selected `HDD_MEAN`, `CDD_MEAN`, `HDD_INTEGRAL` and/or
  `CDD_INTEGRAL` columns.

There is no temperature-to-supply coefficient and no hidden temperature
imputation. NumPy is imported lazily inside the fitter. A missing installation
raises `MissingNumpyError` (`code="NUMPY_NOT_INSTALLED"`); this change adds no
dependency and does not edit requirements. The candidate is solved with NumPy
`lstsq`/SVD; the intercept is unpenalized and standardization is learned only
from each training fold. Rows, features and folds are bounded by policy.

Every cutoff resolves the latest target revision with `available_at <= cutoff`.
Filters run before transforms. Target truth used for final scoring may have been
published after the fold origin, but it never enters that fold's features or
training. Deterministic daily expanding folds start at the frozen training cutoff
and are compared against the same baseline predictions using MAE, RMSE and bias.
An uncertainty interval is available only from enough real held-out residuals;
otherwise no interval is returned and a reason is recorded.

Selection outcomes are `INSUFFICIENT_DATA`, `BASELINE_RETAINED` or
`CANDIDATE_SELECTED`, governed by explicit minimum fold/prediction/coverage,
relative-MAE improvement, fold-win and RMSE conditions. Even a selected candidate
is `UNVALIDATED_OOS_RESEARCH_OUTPUT` with `NOT_PROMOTED`; this core cannot promote
a model. Synthetic mechanics report `SYNTHETIC_NOT_REAL` and never claim forecast
accuracy. Genuine forecast-vintage OOS has a separate `validation_basis`.

The canonical model hash covers method/model version, kind, coefficients,
intercept, training scales/means, feature names, native unit, scope/region,
calendar, feature-policy fingerprint, training cutoff, source refs, target
revision IDs and weather vintage IDs. Coefficients and uncertainties are emitted
for the next integration stage; they are not a production forecast.

## Future prediction API

`DemandPredictionRequest` requires an explicit target gas day, prediction origin,
target scope, region, native unit and gas-day calendar, plus an optional
`DailyWeatherFeature` for a weather candidate. `predict_selected_demand` applies
the frozen `selected_model`; `predict_baseline_demand` always applies the frozen
calendar baseline and refuses weather input.

`DemandModelResult.selection_evidence` records the validation cutoff
(`validation_as_of`), selected/baseline/candidate model hashes, measured OOS
metrics, fold and residual counts, fold-win fraction, coverage and the policy
thresholds. Its deterministic `selection_hash` binds those values and the
validation cutoff; it contains no runtime execution timestamp. Both prediction
paths refuse before `validation_as_of`, even when the selected model's training
cutoff is earlier. The interval is available on the same schedule.

For a weather model, prediction accepts only an already-available
`FORECAST_VINTAGE` row whose gas day matches the target and whose feature-policy
fingerprint, region and calendar match the fitted model. Feature issue,
availability and prediction origin must be at or before the requested prediction
origin; a future valid gas day is allowed. Realized weather is refused rather
than relabelled as a forward forecast. Missing required columns are typed
refusals. The row is transformed with the frozen training means, scales, feature
names and coefficients; no refit, target lookup or weather imputation occurs.

The result carries the native unit, selected model hash, selection hash,
selection cutoff, feature refs, source ref, forecast vintage, prediction origin,
target gas day and a finite non-negative value. A negative estimate raises
`NegativeDemandEstimateError` rather than being silently clamped. An interval is
emitted only when the stored held-out residual evidence is supported; it is
labelled `EMPIRICAL_HELDOUT_RESIDUAL_RESEARCH_INTERVAL`, has
`coverage_guarantee=False` and remains `NOT_PROMOTED`. The explicit baseline path
returns a `CALENDAR_BASELINE_REFERENCE` label with no weather feature refs and no
weather residual interval.

## Validation status

Focused tests live in `tests/unit/test_weather_demand.py`. They include the
existing degree-day numerics, causal OOS checks and NumPy SVD fitting checks, plus
separate regressions for cross-region feature rejection, policy-hash sensitivity
to bases/weights/coverage/method, and a cross-policy holdout row that must fail
before prediction. This provenance revision was not executed by the implementing
worker; the root reviewer runs the isolated NumPy test command. NumPy-dependent
tests require the root-reviewed NumPy 2.3 lock to be installed. The
lazy-dependency failure test does not require NumPy.
