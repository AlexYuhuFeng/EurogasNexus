# Weather-demand runtime gap audit — 2026-10-29

Status: read-only architectural audit. No implementation, dependency, registry or schema change.
Authority: accepted RFC-0003 and the execution-state checkpoints below. Repository code wins for what exists;
RFC-0003 wins for direction. The generated vertical plan and untracked proposals are not authority.

## Verdict

The pure model, the persisted-ECMWF projection bridge, forecast/target persistence and degree-day API/SDK
exist, but **no runtime path joins persisted forecasts and persisted actual demand to `fit_weather_demand_model`
or `predict_selected_demand`**. `fit_weather_demand_model` is also unusable in the delivered environment:
NumPy is absent from runtime dependencies and the all-extras lock. Current acceptance data is far too short
and too London-specific to fit a genuine forecast-vintage model. A truthful next slice can wire the path and
report insufficiency; it cannot yet produce a defensible regional forecast or accuracy claim.

Accepted checkpoints: RFC-0003 (2026-10-28, staged implementation; Decisions 4–10, phases C–D); execution
state 2026-10-29 “staged weather feature and demand inference implementation” (47 focused tests, NumPy isolated
only), 2026-10-29 “REST demand persistence verified”, and 2026-10-29 “governed weather API/SDK”. The snapshot
service’s claim that “no weather ingestion path exists” is now stale (`application/data_platform_snapshots.py`
`_weather_demand_assumptions`, around line 276).

## Implemented, with evidence

| Concern | Existing evidence | Limit |
| --- | --- | --- |
| Pure weather/degree-day core | `domain/research/weather_demand.py`: `compute_degree_days`, `DegreeDayResult.feature_rows()` (line 806), `DailyWeatherFeature` (686), explicit region weights, DST gas-day calendar, null on incomplete coverage | No I/O, no runtime composition |
| Pure demand model | same file: `DemandTargetRow` (1133), `DemandModelPolicy` (1170), `fit_weather_demand_model` (2336), `predict_selected_demand` (2778), selection-evidence cutoff/refusal, frozen coefficients, native unit preserved | NumPy required for fit; no persistence |
| Persisted-ECMWF bridge | `application/research/weather_demand_inputs.py`: `ForecastPointBinding` (127), `build_weather_demand_inputs`, `compute_degree_days_from_bundle`, `project_forecast_observation_record`; one newest eligible vintage per origin; left-hold labelled; missing stays missing | Produces degree-day results only; no demand-target mapping or model call |
| ECMWF read adapter | `db/repositories/ecmwf_forecast_reads.py::read_ecmwf_forecasts` (96); issue/availability ≤ origin; source/model/quality/unit pinned; 256-row and 32-day caps | Per-call bound; no historical archive loader |
| Actual-target persistence | `db/models/demand.py::NationalGasActualDemandRecord` (27): GB_NTS, native `mscm`, D+1/D+6, CSV/REST separated, receipt availability, blank flag; `db/repositories/demand.py::list_demand_rows` (127) | Read is bounded but not point-in-time and returns ORM rows, not `DemandTargetRow` |
| Source fidelity | `ingestion/national_gas_demand.py`: `QUALITY_LABELS` maps A→AMENDED, not Actual; D+1 `is_provisional=True`; D+6 `is_provisional=None` | No reviewed mapping into `DemandTargetQuality` |
| Degree-day API/SDK | `api/routes/public/weather.py` GET forecasts (102), POST degree-days (155), identity/entitlement/certification; `packages/python-sdk/src/eurogas_nexus_sdk/weather_degree_days.py`; Web panel recorded in the 2026-10-29 checkpoint | No model-fit/predict route, SDK model or page |
| Dataset builder | `domain/research/datasets.py`: `FeatureComputer` (324), `build_dataset(... feature_computers=...)` (630), `_compute_builtin_feature` | Computers receive one latest scalar per series and empty context; no weather/weighted-interval computer is registered |
| Frozen result envelope | `db/models/data_platform.py::AnalysisSnapshotRecord`: `weather_demand_assumptions_json` (51), `model_calculation_versions_json` (53); existing snapshot service/API | No producer of a fitted model result; weather field hardcoded UNAVAILABLE |
| Portfolio/scenario | `application/projections/scenario_context.py` lineage is route candidates/tariffs/contracts (67); `portfolio_snapshot.py` has no demand slice; `application/resource_pool.py` consumes contracts/candidates/tariffs/market/FX only | No demand-model reference or consumer contract |

## Missing or broken

1. **Target adapter.** Nothing converts `NationalGasActualDemandRecord` to `DemandTargetRow` with an
   `available_at` cutoff, explicit CSV-or-REST selection, stable revision ordering, native value parsing,
   and an honest quality mapping. `list_demand_rows` returns every revision up to a limit and does not filter
   by availability.
2. **Historical feature builder.** The bridge selects one vintage for one requested window/origin. Model
   training needs, for each gas day, the vintage that was available at that day’s forecast origin; no service
   loops origins, pairs days with targets, or emits `DegreeDayResult.feature_rows()` for training.
3. **Runtime composition/entrypoint.** No application service or CLI/API calls fit/predict with persisted
   rows. `api/routes/public/weather.py` ends at degree days; no weather route imports the model functions,
   and no runtime fit/predict endpoint was found.
4. **Persisted frozen model/result.** No ORM table, repository, artifact convention or API was found that
   stores a `DemandModelResult`, selection evidence or prediction. The AnalysisSnapshot JSON columns are a
   possible later envelope, not a current producer.
5. **NumPy delivery.** `pyproject.toml` runtime dependencies contain no NumPy; optional `research` contains
   only `pyarrow`. `requirements.lock` is generated with `--all-extras` and has no NumPy stanza (the sorted
   lock moves from `markupsafe` to `packaging`). `weather_demand.py` therefore raises `MissingNumpyError`
   in the delivered environment; default CI skips fitting. Isolated NumPy 2.3.5 evidence is not delivery.
6. **Real history.** Repository ECMWF coverage is the 2026-10-29/00 run at London only (a handful of rows);
   National Gas evidence is 17 recent revisions. The forecast read cap is 32 days/256 rows. This cannot
   cover the multi-season target lookback or generate enough out-of-sample vintages for selection.
7. **Regional representativeness.** A single London grid point is not GB_NTS demand weather. RFC-0003
   requires explicit region bindings and weights; no reviewed GB weighting exists. A London-only weight
   must not be labelled `GB_NTS` or used to claim regional accuracy.
8. **Stale snapshot claim.** `_weather_demand_assumptions` still reports `WEATHER_SOURCE_NOT_CONFIGURED`,
   contradicting persisted forecasts and demand. It must not be used as current evidence; correcting it
   belongs with the first persisted-result slice, not this audit.

## Smallest next implementation vertical (C1)

**Objective:** one operator-invoked, read-only runtime composition that reads actual persisted ECMWF and
National Gas rows, applies point-in-time selection, builds weather features per gas day, checks explicit
readiness gates, and calls the real model only when the gates pass. It returns typed JSON and persists
nothing. It does not add a public API, SDK/Web surface, page, table or dependency.

**Why this is smallest:** it reuses the accepted core, bridge and read adapters, adds no schema, and
exposes the true data gap before RFC-0003 phase D. A public route now would also require
same-commit SDK/Web/OpenAPI work (RFC-0004) and would make an unvalidated model look consumable.

| File | Change |
| --- | --- |
| `src/eurogas_nexus/db/repositories/demand.py` | Add `read_demand_target_revisions(...)`: explicit `provider_item_id`, `source_format`, gas-day range, `available_at_utc <= cutoff`, bounded limit; return ORM rows without mutation. No CSV/REST union. |
| `src/eurogas_nexus/application/research/weather_demand_runtime.py` (new) | `build_demand_target_rows(records)`, `build_forecast_feature_history(session, request)`, `run_weather_demand_model(session, request)`. Map D+1 only to `DemandTargetQuality.PROVISIONAL`; refuse D+6 until a reviewed quality mapping exists. Skip blank values (never zero). Derive receipt-order revision ids, clearly labelled as derived, not provider revision numbers. For each gas day call `read_ecmwf_forecasts` at that day’s origin, then bridge and `DegreeDayResult.feature_rows()`. Explicit Decimal weights/region/calendar; no defaults. Reject `ValidationBasis.SYNTHETIC_NOT_REAL` at runtime. |
| `src/eurogas_nexus/cli/weather_demand.py` (new) and `src/eurogas_nexus/cli/main.py` | Register `weather-demand-fit` with explicit term/source-format/region/weights/cutoffs/policy; JSON stdout; no network, writes or promotion. Exit distinctly for `INSUFFICIENT_REAL_HISTORY` and `NUMPY_NOT_INSTALLED`. |
| `tests/research/test_weather_demand_runtime.py` (new) | SQLite rows through the real repositories: later revision excluded before availability, blank≠zero, CSV/REST not mixed, D+6 refused, missing vintage/day yields null and a typed refusal, no synthetic fallback. A minimal-policy mechanics test may exercise fit/predict only when labelled synthetic and must not assert accuracy. |
| `tests/cli/test_weather_demand_cli.py` (new) | Arg/refusal/output contract, exit codes, no DB writes, unavailable NumPy path. |
| `tests/contract/test_weather_demand_runtime_boundary.py` (new, optional) | Domain stays I/O-free; application service imports no API; no new route/schema/registry. |

**Readiness diagnostics required:** target distinct gas days, source format/term, revision count, earliest/latest
target day; forecast point/vintage count, earliest/latest issued and valid day; feature days built; paired
training days; omitted days by reason. If paired days < policy minimum, return `INSUFFICIENT_REAL_HISTORY`
with these counts and do not call fit. If NumPy is absent, return `NUMPY_NOT_INSTALLED`; never fall back.

## Acceptance evidence for C1

- Focused tests only (no full suite): the two/three new test modules plus existing weather core/bridge and
  demand repository tests; Ruff on changed files.
- A dedicated PostgreSQL run using the already-captured ECMWF and National Gas rows, with exact before/after
  row counts proving read-only behaviour. Expected result is a structured coverage refusal, not a fitted model.
  Record counts and the 32-day forecast-read vs target-lookback mismatch in the evidence note.
- If a reviewed NumPy environment is used, a gate-passing run may return a result, but it must retain
  `UNVALIDATED_OOS_RESEARCH_OUTPUT`, model/selection hashes, `validation_basis`, and no accuracy/promotion
  claim. Synthetic mechanics tests are mechanics only.
- No regional claim from one London point. `GB_NTS` can be used only with a reviewed multi-point weighting
  or a genuinely regional target; otherwise the run must use an explicitly named probe region and say so.
- No mscm→MWh conversion, no CSV/REST summation, no A=ACTUAL mapping, no threshold lowering to force a fit.

## Dependencies and root decision

NumPy delivery is a hard prerequisite for any real fit, separate from C1’s composition. Adding it requires a
reviewed optional/runtime extra, regenerated hashed lock, licence/CVE evidence and a CI job; it must not be
smuggled in through an isolated test environment. If root does not approve that dependency slice, C1 can only
deliver the readiness/refusal path, and “actual model runtime use” remains unproven.

Recommended root decision: approve C1 as a read-only composition/readiness vertical plus an explicit NumPy
delivery decision; defer public API/SDK/Web, frozen-result persistence and portfolio consumption until real
multi-vintage forecast history and reviewed regional weights exist. C1 does not close RFC-0003 phase C or D.
