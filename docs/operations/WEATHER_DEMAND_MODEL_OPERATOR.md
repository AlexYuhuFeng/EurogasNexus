# Weather-demand model operator entrypoint

`scripts/ops/fit_weather_demand.py` is a bounded, trusted-operator command for the
existing read-only weather-demand runtime. It is deliberately separate from the
public SDK-backed `cli/main.py` and adds no API, SDK, route, schema, registry,
source-activation or dependency change. It does not replace the runtime, the
frozen fitter or the public CLI.

The command accepts one explicit local JSON request, builds the immutable
`WeatherDemandRuntimeRequest` from the actual nested domain types, and calls
`run_weather_demand_runtime` on a PostgreSQL session. It is an operator/research
surface, not a customer forecast product.

## Trust and credential boundary

- Only a trusted operator may run it. The caller remains responsible for source
  authorization, entitlement and activation; the command grants none of them.
- The database location comes only from the existing environment resolver, in
  this precedence order: `RUNTIME_STORE_DATABASE_URL`, `DATABASE_URL`,
  `EUROGAS_NEXUS_DB_DSN`.
- There is no `--database-url` option. Database credentials are never accepted on
  the command line and are never written to output.
- PostgreSQL is required. A SQLite or other dialect session is refused before the
  runtime is called.

## Command

```powershell
$env:RUNTIME_STORE_DATABASE_URL = "postgresql+pg8000://operator@example.test/eurogas"
python scripts/ops/fit_weather_demand.py --request-json C:\operator\weather-request.json
```

The input must be a local regular file of at most **1 MiB**. The request hash is
derived only from the explicit request content, so repeating the same file gives
the same request hash. File paths and modification times are not hashed.

## Request contract

The root object requires `schema` with the exact value
`weather-demand-operator-request/v1`, plus:

| Root key | Meaning |
| --- | --- |
| `model_policy` | Complete frozen model policy; no timing, base, weight, region or threshold defaults are invented. |
| `degree_day_policy` | Explicit degree-day bases, gap, coverage fraction and method version. |
| `bridge_configs` | One explicit bridge per requested gas day; each inherits the model's `expected_feature_policy`. |
| `point_bindings` | Explicit point/series/entity/location/region bindings. |
| `provider_item_id` | Explicit National Gas source item. |
| `source_format` | `CSV` or `REST`; the two are not merged. |
| `target_gas_day_from`, `target_gas_day_to` | Inclusive calendar-date window. |
| `allow_provisional_targets` | Explicit bool; never defaulted. |
| `regional_weighting_evidence_ref` | Operator-declared provenance reference; not a review or accuracy proof. |
| `target_revision_order_policy` | Optional additive policy key: `DERIVED_RECEIPT_ORDER` (default) or `DERIVED_REST_APPLICABILITY_ORDER_V1` (explicit REST-only opt-in). |
| `work_budget` | Optional existing query bounds: `target_read_limit`, `forecast_read_limit`. |

The parser rejects, before any database session is opened:

- duplicate JSON keys at any object level;
- unknown root or nested fields;
- missing root policies or a missing `expected_feature_policy`;
- `NaN`, `Infinity` and non-finite numeric results;
- naive or date-only timestamps where an aware instant is required;
- booleans used as integer counts or work bounds;
- invalid enum values, dates, decimals or negative/duplicate selection values;
- `validation_basis: SYNTHETIC_NOT_REAL`;
- an unknown revision-order policy, or the REST applicability-order opt-in with a
  non-`REST` `source_format`;
- request files above 1 MiB or non-UTF-8 files.

Location weights are exact JSON **strings** parsed as `Decimal`, not binary
floats. They must sum exactly to one and match the explicit point bindings. There
is no default region, base, weight, timestamp, cutoff or minimum threshold.

### Optional revision-order policy

Omitting `target_revision_order_policy` preserves the existing
`DERIVED_RECEIPT_ORDER` behaviour: admitted target revisions are ranked by their
actual receipt availability within each gas day, and competing publications with
the same receipt still refuse with `AMBIGUOUS_RECEIPT_TIE`.

`DERIVED_REST_APPLICABILITY_ORDER_V1` is an explicit, non-default opt-in. It is
valid only with `"source_format": "REST"`, and only when the persisted fixed
National Gas REST identity and provenance are complete, the three offset-bearing
provider clocks agree as one UTC instant, and that instant is not after actual
receipt. It ranks revisions by that single provider applicability instant,
independently of receipt order. It is **not** a provider revision number, first
publication time, or historical-admission claim. Actual availability remains the
receipt-based `available_at`; each model fold still filters by actual receipt.

```json
{
  "source_format": "REST",
  "target_revision_order_policy": "DERIVED_REST_APPLICABILITY_ORDER_V1"
}
```

The request schema stays `weather-demand-operator-request/v1`: the key is
additive and optional, so existing request files remain valid. A non-default
policy is bound into the runtime request hash and target source lineage; the
default policy is omitted from the hash so legacy hashes are unchanged.

## PostgreSQL and session guarantees

After parsing and building the immutable request, the command:

1. obtains the session factory through the existing `get_session_factory()` with
   no database-URL argument;
2. requires the bound dialect to be `postgresql`;
3. forces `autoflush` off;
4. executes `SET TRANSACTION READ ONLY` before the actual runtime;
5. calls the existing runtime on that session;
6. always attempts `rollback()` and `close()`; it never calls `commit()`.

No network fetch occurs inside the command. No model, prediction, coefficient,
registry entry or source state is persisted.

## Exit codes and statuses

| Exit | Meaning | Typical status |
| --- | --- | --- |
| `0` | The runtime returned `READY` with an actual fitted research result. | `READY` |
| `1` | Typed source/history/dependency refusal. | `INSUFFICIENT_REAL_HISTORY`, `NUMPY_NOT_INSTALLED`, `SOURCE_AMBIGUITY`, `SOURCE_REFUSED` |
| `2` | Malformed request, missing/non-PostgreSQL database, database failure or unexpected internal failure. | `REQUEST_INVALID`, `DATABASE_ERROR`, `INTERNAL_ERROR` |

A source ambiguity returns its explicit typed code (for example
`AMBIGUOUS_RECEIPT_TIE`); it is not converted into an empty-history success.
Counts are `null` when the failure occurred before a complete runtime result, so
no count is fabricated after a pre-query error.

## Stable summary

The command writes exactly one JSON object to stdout. It never prints a traceback,
raw provider text, exception message, credential or database URL. The summary
contains:

- `schema`, `status`, `research_only`, `research_label` and
  `production_promotion` (`NOT_PROMOTED`);
- `request_hash` and a `hashes` object with request, feature-policy, baseline,
  candidate, selected-model and model-selection hashes;
- `counts` for admitted target revisions, distinct target days, feature days, raw
  forecast rows, paired training days, selected vintages, omissions and
  diagnostics;
- `source_evidence` with the immutable target revision/source IDs, forecast
  observation IDs, feature/degree-day source references, selected vintage IDs,
  training cutoff, validation cutoff, validation basis, the chosen
  `target_revision_order_policy` next to `target_availability_basis`, and exact
  regional-weighting evidence reference/basis;
- `source_basis` with the declared source item/format, validation basis, chosen
  `target_revision_order_policy`, `target_availability_basis` and weighting
  provenance;
- `missing_inputs` with stable diagnostic/omission codes and gas days only;
- `model`, only for an actual `READY` result: selection status, selected model
  kind and use status, native unit, target scope/region/version, training-row
  count and baseline/candidate presence — never coefficients or predictions;
- `database` with the required dialect, whether the read-only transaction was
  requested and `commit_issued: false`;
- `error`, or `null` on success.

## NumPy, history and weight limitations

This command does **not** install, deploy, certify or add NumPy to the delivered
dependencies. If the frozen fitter cannot import NumPy, the result is
`NUMPY_NOT_INSTALLED` and exit code `1`; no alternative solver or baseline is
substituted.

The command also does not establish that regional weights, historical coverage,
source provenance or the declared validation basis are reviewed or accurate.
Those are operator inputs/claims. A `READY` result is research mechanics from the
rows visible in PostgreSQL, not a promotion, customer forecast, accuracy claim or
evidence that the weighting/history is accepted.

## Synthetic full request example

> **Clearly synthetic.** The location, point, series, entity, model version,
> weighting reference and dates below are placeholders. This is **not** a real
> regional weighting, provider mapping, historical calibration or accuracy claim.
> Do not copy the identifiers into production source configuration. The declared
> `GENUINE_FORECAST_VINTAGE_OOS` label is an operator declaration, not verified
> evidence.

```json
{
  "schema": "weather-demand-operator-request/v1",
  "model_policy": {
    "target_scope": "GB_NTS_THROUGHPUT",
    "region": "GB_NTS",
    "target_unit": "MSCM",
    "gas_day_calendar": "EU-CAM-UTC-2025",
    "training_cutoff": "2026-01-10T00:00:00Z",
    "validation_as_of": "2026-01-11T00:00:00Z",
    "ridge_lambda": 1e-8,
    "model_version": "synthetic-operator-example/v1",
    "validation_basis": "GENUINE_FORECAST_VINTAGE_OOS",
    "weather_features": ["HDD_MEAN"],
    "expected_feature_policy": {
      "region": "GB_NTS",
      "heating_base_c": 15.5,
      "cooling_base_c": 22.0,
      "max_gap_minutes": 240,
      "min_covered_fraction": 1.0,
      "location_weights": [
        {"location_id": "SYNTHETIC_LOCATION", "weight": "1"}
      ],
      "gas_day_calendar": "EU-CAM-UTC-2025",
      "temporal_method": "EXPLICIT_DERIVED_HOLD",
      "method_version": "degree-day-mean-and-integral/v1"
    },
    "min_training_rows": 3,
    "min_validation_folds": 1,
    "min_validation_predictions": 1,
    "min_oos_coverage": 0.5,
    "min_relative_mae_improvement": 0.0,
    "min_fold_win_fraction": 0.5,
    "min_residuals_for_interval": 0,
    "interval_level": 0.8,
    "max_training_rows": 100,
    "max_features": 32,
    "max_folds": 5
  },
  "degree_day_policy": {
    "heating_base_c": 15.5,
    "cooling_base_c": 22.0,
    "max_gap_minutes": 240,
    "min_covered_fraction": 1.0,
    "method_version": "degree-day-mean-and-integral/v1"
  },
  "bridge_configs": [
    {
      "prediction_origin": "2025-12-31T23:00:00Z",
      "gas_days": ["2026-01-01"],
      "max_hold_minutes": 240,
      "max_rows": 100,
      "max_points": 8,
      "max_window_days": 7,
      "max_cross_product": 1000,
      "max_intervals": 1000
    },
    {
      "prediction_origin": "2025-12-31T23:00:00Z",
      "gas_days": ["2026-01-02"],
      "max_hold_minutes": 240,
      "max_rows": 100,
      "max_points": 8,
      "max_window_days": 7,
      "max_cross_product": 1000,
      "max_intervals": 1000
    },
    {
      "prediction_origin": "2025-12-31T23:00:00Z",
      "gas_days": ["2026-01-03"],
      "max_hold_minutes": 240,
      "max_rows": 100,
      "max_points": 8,
      "max_window_days": 7,
      "max_cross_product": 1000,
      "max_intervals": 1000
    }
  ],
  "point_bindings": [
    {
      "point_id": "SYNTHETIC_POINT_1",
      "series_id": "SYNTHETIC_SERIES",
      "entity_id": "SYNTHETIC_ENTITY",
      "location_id": "SYNTHETIC_LOCATION",
      "region": "GB_NTS"
    }
  ],
  "provider_item_id": "PUBOB637",
  "source_format": "REST",
  "target_gas_day_from": "2026-01-01",
  "target_gas_day_to": "2026-01-03",
  "allow_provisional_targets": false,
  "regional_weighting_evidence_ref": "operator-input://synthetic-example/not-real-regional-weighting",
  "work_budget": {
    "target_read_limit": 100,
    "forecast_read_limit": 100
  }
}
```

The example is intentionally small and will normally be
`INSUFFICIENT_REAL_HISTORY` (exit `1`) unless the database happens to contain
matching admitted target revisions and available forecast features. That is the
expected dry outcome: it proves parsing, policy identity and typed refusal, not a
model. `READY` is possible only when the actual runtime finds enough paired
point-in-time rows and NumPy is available.

## Focused verification

```powershell
python -m pytest tests/unit/test_weather_demand_operator_cli.py -q
```

The focused tests use synthetic request data and controlled session seams. They
cover actual parser behavior, repeated request hashes, pre-database refusal,
explicit/default revision-order policy compatibility, opt-in reporting, read-only
SQL before the runtime, rollback/close without commit, PostgreSQL-only
acceptance, typed ambiguity, non-ready exit `1`, and stable exit `2` failures
without secret text or traceback. This command does not add a wheel/runtime
allowlist, source activation, public route or delivery gate.
