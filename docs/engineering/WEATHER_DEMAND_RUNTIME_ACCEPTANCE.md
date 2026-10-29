# Weather-demand runtime PostgreSQL acceptance

## Scope

`tests/integration/test_weather_demand_runtime_postgres.py` is a new, opt-in
PostgreSQL acceptance module for the read-only weather-demand runtime
composition. It owns one uniquely named disposable schema per test, creates only
the existing National Gas demand-target and `forecast_observations` tables in
that schema, and drops only that schema afterwards. It does not use Alembic
migrations as a substitute for table creation, and it adds no production table,
migration, requirement or runtime code.

The module reuses the established `EUROGAS_NEXUS_TEST_POSTGRES_URL` /
`RUNTIME_STORE_DATABASE_URL` opt-in pattern. Without a PostgreSQL URL all five
tests are skipped.

## What the tests exercise

1. **Actual fitted core from persisted ORM rows.** Twenty-one synthetic gas days
   are persisted as real `NationalGasActualDemandRecord` revisions, including a
   later revision that is genuinely unavailable at the training cutoff and at the
   earliest OOS fold. Real `ForecastObservationRecord` rows carry the authentic
   `ecmwf-open-data-forecast-observation/v3` provenance required by the existing
   projection. The test calls `run_weather_demand_runtime` without mocking the
   repositories, projection, bridge, degree-day solver or fitter, then asserts
   native `MSCM`, research-only/no-promotion output, all admitted target revision
   ids, raw forecast observation ids, selected vintage ids, feature source refs,
   model/selection hashes and the later revision's absence from training evidence.
2. **Actual SQL origin exclusion.** An eligible forecast run and a later-issued,
   later-received run for the same day are both persisted. Runtime evidence and
   the raw read count contain only the eligible run; the later observations never
   reach the projection.
3. **Missing weather history without NumPy.** Two real target rows, one CSV and
   one REST copy, are read in separate explicit requests. Each returns typed
   `INSUFFICIENT_REAL_HISTORY`, preserves its own source representation and does
   not mix the other format. With no forecast feature row the path stops before
   the optional fitter, so it is independent of NumPy.
4. **No caller autoflush.** A persisted target, a pending same-table caller write
   and a `before_flush` listener prove the runtime's target and forecast reads do
   not flush the pending row. Database count, transaction identity, session state
   and pending/persistent state are retained.
5. **Overflow is surfaced.** A target read limit below the actual row count raises
   the repository's typed `DEMAND_TARGET_READ_OVERFLOW`; no partial model result
   is returned and the rows remain intact.

## NumPy conditions

The fitted-core case needs the separately reviewed optional NumPy dependency and
is skipped when `numpy` is not importable. Expected collection is five tests:

- NumPy present: five tests execute.
- NumPy absent: four tests execute and the fitted-core test is skipped.

The other four cases deliberately avoid reaching the fitter, so they do not
silently convert a missing NumPy dependency into a green fitted-model claim.

## Fixture and limitation facts

- All source values are explicitly synthetic mechanics fixtures. They are not
  provider history, an accuracy result, a validation of regional weighting, or
  evidence that a production source is activated.
- The forecast rows preserve the real persistence provenance contract, but they
  are not authentic captured ECMWF files or receipts.
- The mechanics fixture uses twenty-one gas days with nine three-hourly forecast
  instants per day. The fitting policy separately requires at least eight paired
  training days; forecast instant count is not training-day count.
- The target rows are provisional D+1 revisions admitted only because the
  request explicitly allows provisional targets. No D+6, amended-quality or
  unit-conversion claim is made.
- Root registered this module in `scripts/ci/run_postgres_ci.sh`. A standalone
  actual PostgreSQL run with NumPy executed all five cases successfully. Hosted
  dependency locks still omit NumPy, so a skipped fitted-core case is not evidence
  that the delivered runtime can fit a model.
- The tests cover database/runtime composition mechanics only. API, SDK, Web,
  scheduler, portfolio consumption, historical coverage, provider rights and
  model accuracy remain out of scope.
