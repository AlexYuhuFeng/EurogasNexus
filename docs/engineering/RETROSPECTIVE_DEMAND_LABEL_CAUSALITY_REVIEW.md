# Retrospective demand-label causality review

Status: research/architecture review only, 2026-10-30. This file is the only
change proposed here. It makes no implementation, schema, API, source-activation,
default-read or model-promotion change. Root owns acceptance; none is claimed.

## 1. Finding

Historical ECMWF reconstruction (RFC-0007 S4) cannot by itself enable a real
historical OOS demand model. Weather features and demand labels have separate
causality gates. The target path admits labels only by `available_at`, and
`available_at` is the actual local receipt captured now. Provider applicability
clocks are retained as ranking/provenance evidence, not substituted for receipt.
A fold at a 2025 origin therefore has zero eligible demand targets even when
archived weather is eligible. That is a label-history absence, not missing
weather.

The current pure core can still fit a *current* model at today's cutoff if enough
target/feature pairs exist. It then has no historical holdout, reports
`INSUFFICIENT_DATA`, selects the calendar baseline, and cannot produce a selected
weather prediction. On the actual persisted probe there are zero feature days and
zero paired training days, so even that current fit is refused before the fitter.

## 2. Exact current-code path

| Claim | Current evidence |
|---|---|
| `DemandTargetRow` has one availability clock | `src/eurogas_nexus/domain/research/weather_demand.py:1133-1167`: `available_at`; no provider-applicability field |
| Mapper uses receipt; quality gates stay source-faithful | `demand_target_inputs.py:495` reads `record.available_at_utc`; `:502` filters it by cutoff; `:605-643`: D+1 only `PROVISIONAL` with explicit opt-in, D+6/`None` refused, quality A=`AMENDED` refused, unsupported refused |
| Source-applicability opt-in ranks only | `demand_target_inputs.py:350-361` builds the row with `revision.available_at`; `:577-600` stores `source_order_at_utc` separately; `:1088-1089` keeps it in provenance |
| Mapper states the boundary | `demand_target_inputs.py:38-40`: source applicability "does not admit a row historically; folds still filter by actual receipt" |
| Repository read is receipt-bounded | `src/eurogas_nexus/db/repositories/demand.py:194-251`: `available_at_utc <= cutoff` at `:234` |
| Fold target resolution filters receipt | `weather_demand.py:1902-1918`: `if target.available_at <= cutoff` at `:1909`; max revision at `:1913` |
| Training filters every fold | `weather_demand.py:1955-1983`: resolve at cutoff `:1965`; skip gas days ending after cutoff `:1972-1974`; append paired rows `:1980` |
| OOS separates final truth from fold training | `weather_demand.py:2214-2301`: final truth at `validation_as_of` `:2227-2236`; fold origin `:2248-2256`; per-fold training `:2259-2265`; skip below minimum `:2266`; actual from final truth `:2275` |
| Core fit only needs training rows at cutoff | `weather_demand.py:2351-2372`: `_numpy()` `:2351`; `_prepare_training(training_cutoff)` `:2360`; refusal `:2366-2367`; folds `:2371` |
| Current fit can have zero folds | If `training_cutoff == validation_as_of`, holdout requires `start >= training_cutoff` (`:2232-2234`); zero folds gives `INSUFFICIENT_DATA` (`:2376-2388`) and selects baseline (`:2415-2419`) |
| Baseline cannot yield selected weather prediction | `predict_selected_demand` refuses weather for a selected baseline at `:2832-2837`; selection evidence is required `:2584-2603` |

The REST parser defaults `available_at_utc` to local receipt
(`src/eurogas_nexus/ingestion/national_gas_rest.py:258-260`), persists it separately
from the provider clocks (`:583-585`; `src/eurogas_nexus/db/models/demand.py:77-79`),
and append-or-verify preserves the first receipt (`db/repositories/demand.py:1-5,79-153`).
Tests pin the distinction: `tests/unit/test_demand_target_inputs.py:459-480`
(earlier cutoff empty), `:513-531` (`source_order_at_utc` separate;
`row.available_at == RECEIVED`), and
`tests/unit/test_weather_demand_runtime.py:982-1064` (all revisions forwarded,
basis `ACTUAL_RECEIPT_AVAILABLE_AT`).

## 3. Actual REST evidence already recorded

| Record | Actual result |
|---|---|
| `docs/data/NATIONAL_GAS_REST_OPERATIONS.md:25-29` | Two-day PUBOB637 dry run returned 17 revisions; persistence inserted 17, replay inserted 0/17; provider upper bound is separate from receipt and does not authorise historical OOS |
| `docs/engineering/RFC-0003-ECMWF-DEMAND-VERTICAL.md:130-151` | `latestValue=N` 17 rows, `Y` 5 rows over 5 gas days; each Y row matched the unique maximum `applicableAt`; all three clocks agreed for every N row; source applicability is not first-publication proof and grants no historical admission |
| `docs/engineering/ARCHITECTURE_V2_EXECUTION_STATE.md:65-72` | Read-only two-database probe: 3 ECMWF / 17 National Gas source rows; 4 target revisions admitted; 2 weather observations; 0 feature days and 0 training pairs; `INSUFFICIENT_REAL_HISTORY`, no model |

These are different probes: 17 is a source-row count, 4 is the admitted count in
the second probe, and 0 is the eligible training-pair count. Admitted D+1 quality
is `PROVISIONAL`, not `ACTUAL`; `latestValue=Y` is not a first-publication clock.

## 4. Probe status and deterministic mechanics

Probe: **NOT RUN**. The process launcher failed before Python started:

```text
CreateFileW failed (Win32 5): C:\Users\qqshu\AppData\Local\Temp\dsh-acl-locks\50fd8c0a8ec2bb2a.lock
```

The same failure occurred for `pwsh`, background execution and glob/ripgrep;
no stdout, exit code, database access, network access or temp script existed. The
sandbox escalation channel was unavailable. Counts below are
`DERIVED_FROM_CURRENT_SOURCE`, not execution output; metrics are not claimed.

Synthetic setup: 10 gas days `2025-01-01..2025-01-10`; complete realized features
available at each gas-day end; `training_cutoff=2025-01-06T00:00Z`;
`validation_as_of=2026-10-30T12:00Z`; minimum 1 training row, 1 fold.

| Scenario | Derived result |
|---|---|
| A: target `available_at = 2026-10-30T12:00Z` | `_resolve_targets(training_cutoff)=0`; `_prepare_training=0`; `_resolve_targets(validation)=10`; 5 holdout days; **0 folds**, coverage 0.0, metrics `None`; every fold skips because training has 0 targets |
| A: `fit_weather_demand_model` | With NumPy: `WeatherDemandInputError: no training rows were available at training_cutoff`. With NumPy absent, `_numpy()` at `:2351` raises `MissingNumpyError` first. Branch not executed |
| B: control, target `available_at` = gas-day end | `_prepare_training=4`; 5 holdout days; **5 folds**, coverage 1.0; fold training counts `[5,6,7,8,9]`; numeric MAE/RMSE/bias not run/not derived |
| C: today's cutoff, `training_cutoff=validation_as_of=2026-10-30T12:00Z` | `_prepare_training=10`; **0 folds** because no gas day starts at/after cutoff; with NumPy, baseline and candidate can be fitted, but selection is `INSUFFICIENT_DATA` and selected model is baseline; no OOS, no selected weather model |

A shows zero folds come from zero historically available targets, not missing
weather. B is a synthetic control proving folds occur only with earlier receipts,
not that they existed. C is a current fit with insufficient evaluation, not OOS.

## 5. No-leakage options

### A. Prospective accumulating history (default; no backfill)

Keep the receipt-only rule and wait for labels to accrue. Each fold uses only
targets whose actual receipt was at or before the fold origin, preserving
historical revisions and per-fold selection. This is the only option that can
support genuine prospective OOS. It produces no historical OOS today; RFC-0007
archive weather alone remains insufficient and has its own non-genuine basis.

### B. Explicit retrospective provider-applicability label basis

Use a separate opt-in label-time basis from the already-persisted provider
applicability clock, without changing `available_at`, receipt, publication
identity or quality. It could give historical folds labels, but it is **not
automatically accepted** and **not first-publication truth**: applicability can
precede actual publication or local receipt, so it may be optimistic and cannot
be called genuine OOS or no-leakage proof. Equal source instants remain ambiguous;
no lexical fallback, maximum-of-disagreeing-clocks fallback, CSV inference or
provider revision-number claim. D+1 remains `PROVISIONAL`; quality A remains
`AMENDED`; D+6 remains unresolved. This needs an explicit RFC and must retain all
revisions plus per-fold selection.

### C. Final-restated labels, retrospective evaluation only

`_run_oos` already scores fold predictions against the latest target revision
available at `validation_as_of` while training against the fold cutoff. That
separation is useful but not recorded as a distinct target-label basis. A narrow
option can make it explicit: training stays receipt-bounded; final-restated labels
are only evaluation truth; every fold records the final target revision ID and
basis. This is retrospective final-label scoring, never "vintage OOS" and not
missing training history. Using final labels for training is a separate,
explicitly retrospective calibration claim; it must not be called per-fold OOS or
silently choose a global latest revision for earlier folds.

## 6. If root wants an opt-in: minimum seam

| Seam | Minimum change, if accepted |
|---|---|
| Target model | Separate `target_label_basis` (default `ACTUAL_RECEIPT`) and `evaluation_claim`; do not overload `available_at` |
| Mapper/provenance | Carry explicit label time/basis from the chosen policy; retain `available_at`, `source_order_at_utc`, source clock method and all revisions |
| Repository | Separate bounded read mode only if label time is not persisted; no default SQL change, DB write or schema change unless separately decided |
| `_resolve_targets` | Selector by label basis; default `available_at <= cutoff`; still max revision per gas day |
| `_prepare_training` / `_run_oos` | Training selector separate from evaluation-truth selector; record per-fold and final-truth target revision IDs; no global latest in training |
| Policy/result | Add target-label basis and analysis-as-of to `DemandModelPolicy` and `FittedDemandModel`; keep weather `ValidationBasis` orthogonal |
| Evidence/hash | `target_label_policy_hash`, per-fold target IDs/bases and final-truth IDs in model/selection/request hashes; default hashes byte-identical |
| Runtime/operator | Default basis stays `ACTUAL_RECEIPT_AVAILABLE_AT`; nondefault basis in request hash; `READY` must not imply OOS sufficiency |
| Archive | RFC-0007 weather basis stays separate; no archive basis may be relabelled genuine or rewrite target labels |

Proposed basis/status labels: `ACTUAL_RECEIPT` (default),
`RETROSPECTIVE_PROVIDER_APPLICABILITY_RESEARCH` (not publication proof) and
`RETROSPECTIVE_FINAL_LABEL_SCORING` (evaluation only). Add typed diagnostics for
unsupported basis, absent/ambiguous labels and attempted mixture. Do not add an
`ACTUAL` path for D+1 provisional, quality A or D+6.

Default invariants: `available_at` remains actual receipt; default request,
model and selection hashes unchanged; all historical revisions stay present;
per-fold selection deterministic; ambiguous ties refuse; blank is not zero; native
MSCM unchanged; runtime read-only; no source activation, promotion, network fetch
or DB write; no weather prediction before `validation_as_of`; no selected weather
prediction while selection is insufficient.

Focused tests: (1) receipt-now history yields zero historical training/folds;
(2) B only produces folds with synthetic historical receipts; (3) today's-cutoff
fit yields `INSUFFICIENT_DATA`, baseline and no weather prediction; (4) opt-in
basis leaves `available_at` and revision IDs unchanged; (5) per-fold earlier/later
selection and final-truth revision IDs are recorded; (6) `source_order_at_utc` is
unused by default; (7) D+1 opt-in, D+6 refusal, quality-A refusal and blank
refusal; (8) default request/model/selection hash equality and nondefault binding;
(9) operator summary reads evidence, not a hardcoded basis; (10) archive weather
and demand label bases cannot be uplifted or lost. Existing tests cover late
availability and revision isolation: `tests/unit/test_weather_demand.py:569-599`,
`tests/unit/test_demand_target_inputs.py:314-331,459-531`.

## 7. Today's cutoff and prediction feasibility

- With enough real pairs, the core can fit at `training_cutoff=validation_as_of=now`,
  report `INSUFFICIENT_DATA` and select the baseline: a current fit, not historical OOS.
- `_paired_training_days` counts receipt-eligible pairs
  (`weather_demand_runtime.py:1175-1211`); below `min_training_rows` the runtime
  returns `INSUFFICIENT_REAL_HISTORY` before fitting (`:987-1016`). The actual
  probe had 0 pairs, so no model exists.
- `READY` means a model was fitted (`:1081-1097`), not that OOS selection
  succeeded. The operator summary exposes `selection_status`
  (`scripts/ops/fit_weather_demand.py:868-885`), so `READY` is not validation.
- A selected weather prediction requires `CANDIDATE_SELECTED`, hence measured
  folds and improvement; zero folds selects the baseline and refuses weather.
- RFC-0007 S4 is explicitly not a genuine forecast vintage or first publication
  and does not alter target labels (`RFC-0007-ECMWF-ARCHIVE-AVAILABILITY.md:73-85`).
- Regional weights remain separate. Runtime uses `CALLER_DECLARED_PROVENANCE_NOT_REVIEWED`
  (`weather_demand_runtime.py:94`) and requires explicit weights. Root-reported Xoserve
  2025 review is effective 2025-10-01..2030-09-30
  (https://umbraco.xoserve.com/news/seasonal-normal-weather-review-2025/); old 2015
  station weights are not current. Xoserve was not re-fetched because DNS refused.

## 8. RFC implication and recommendation

The receipt-only path needs no new RFC. Historical training from provider
applicability or final restatements changes RFC-0003's "no historical admission"
and RFC-0007's "no uplift" boundaries, so it needs a new narrow RFC (or explicit
superseding addendum) limited to demand-label temporality; RFC-0007 must not carry
target labels. Evaluation-only final-label scoring may be a bounded RFC-0003
evidence-contract addendum, but must remain retrospective and never claim vintage OOS.

Recommendation to root: do not accept a retrospective target basis on this
evidence alone. Preserve the receipt-only default and per-fold revision history.
If a retrospective number is required, scope it as research-only, keep the two
retrospective bases distinct and require the hashes/statuses above before
implementation. A selected weather prediction remains blocked until real labels
are receipted at historical fold origins and a candidate is measurably selected.

## Root executed addendum, 2026-10-30

Root executed a separate 40-day synthetic mechanics probe using the existing
unit fixture, actual NumPy core and unchanged policy selectors. This is not the
10-day source-derived illustration above and is not provider-history evidence.
Actual result: historical-receipt control produced10 folds and selected the
weather ridge; replacing every label receipt with capture-now made the same
historical cutoff refuse with `no training rows were available at training_cutoff`.
At capture-now training/validation cutoff, the candidate fitted but there were
zero folds, `INSUFFICIENT_DATA`, and the selected model was calendar baseline.
Ignored report: `.local-runtime/delivery-20261030-label-causality/report.json`.
Root accepts the architectural finding, not a reconstructed-label policy yet.
