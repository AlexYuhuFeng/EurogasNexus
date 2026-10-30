# RFC-0008: Retrospective demand-label availability

- Status: **Accepted staged research architecture by root**, 2026-10-30. Implementation and acceptance evidence remain pending.
- Scope: architecture/design only. This file is the only proposed change; no code,
  schema, API, dependency, source-activation or default-read change.
- Owner: root integrator. Reviewers: architecture, data governance/source owner, model validation.
- Goal: allow an explicit research caller to test a reconstructed demand-label clock without
  rewriting actual receipt, publication identity, quality or the default model path.

## Summary

Propose one opt-in, research-only `DemandTargetLabelBasis` value,
`RETROSPECTIVE_PROVIDER_APPLICABILITY_RESEARCH`, orthogonal to weather
`ValidationBasis` and separate from revision ranking. Default remains
`ACTUAL_RECEIPT`; `DemandTargetRow.available_at` remains the actual receipt.
Eligibility is reconstructed only under an explicit policy using the already-persisted
strict National Gas REST identity, raw/UTC source clocks, hashes and provenance.
It is not first-publication truth, prospective OOS, genuine OOS or production evidence.

## Problem

The 2026-10-30 causality review and root 40-day addendum show that historical ECMWF
reconstruction cannot enable a historical demand OOS model by itself. Today every fold
filters targets by `available_at <= fold_origin`, and `available_at` is the receipt
captured now. Historical labels therefore do not exist at 2025 origins: capture-now
receipts refuse at a historical cutoff, while a capture-time fit has zero folds,
`INSUFFICIENT_DATA` and selects the calendar baseline. Weather and demand-label
causality are separate gates.

The mapper already retains the strict REST source-applicability instant as ranking
provenance, but explicitly does not admit it historically. This RFC proposes a narrow
research basis for that existing evidence. It changes no default result and grants no
acceptance.

## Current seams and exact evidence

| Claim | Current code |
|---|---|
| One receipt clock on the row; weather basis is separate | `src/eurogas_nexus/domain/research/weather_demand.py:120-126,1133-1167,1170-1216` |
| Folds filter receipt; final truth is receipt-selected | `weather_demand.py:1902-1918,1955-1983,2214-2301` |
| Model hash binds revision IDs but not label clocks | `weather_demand.py:2014-2039,2138-2176` |
| Mapper validates REST clocks and keeps all revisions | `src/eurogas_nexus/application/research/demand_target_inputs.py:242-387,452-602,704-951` |
| D+1 provisional requires opt-in; A amended and D+6 unknown are refused | `demand_target_inputs.py:605-643` |
| Read is receipt-bounded; runtime evidence is separate | `src/eurogas_nexus/db/repositories/demand.py:194-251`; `src/eurogas_nexus/application/research/weather_demand_runtime.py:757-795,1100-1172,1220-1246` |
| Operator summary reports a fixed receipt basis | `scripts/ops/fit_weather_demand.py:888-965` |

Actual 17-row REST evidence is recorded in RFC-0003’s 2026-10-30 extension and the
review’s evidence section: all three clocks agreed; `latestValue=Y` is not first
publication. The root probe is `.local-runtime/delivery-20261030-label-causality/report.json`
(ignored), not provider-history evidence.

## Decision

**D1 — Orthogonal label basis.** Add `DemandTargetLabelBasis` with
`ACTUAL_RECEIPT` (default) and `RETROSPECTIVE_PROVIDER_APPLICABILITY_RESEARCH` (opt-in).
Do not add either to `ValidationBasis`, do not relabel RFC-0007 archive weather, and do
not treat one basis as convertible to the other. A result may carry both only as distinct
fields.

**D2 — Row and policy DTOs.** Keep `DemandTargetRow.available_at` as the immutable actual
receipt and `revision` as the derived integer rank (never a provider revision number).
Add `label_at: datetime | None = None` and `label_basis: DemandTargetLabelBasis =
ACTUAL_RECEIPT` to the row and equivalent immutable fields to `DemandTargetProvenance`.
Add `target_label_basis: DemandTargetLabelBasis = ACTUAL_RECEIPT` to
`DemandModelPolicy`, plus a deterministic `target_label_policy_hash` property. For the
default basis the effective clock is exactly `available_at`; for the opt-in basis it is
the required `label_at`.

**D3 — Evidence prerequisite.** The opt-in exists only for `source_format="REST"` with
the existing `DERIVED_REST_APPLICABILITY_ORDER_V1` policy and complete persisted evidence:
fixed API URL, series/hash identity, all raw/offset-bearing source clocks and their
wall-clock copies, three-clock single-UTC-instant consensus, raw hash, receipt/availability/
ingestion identity, and source instant not after receipt. `label_at` is that consensus
instant. CSV, missing provenance, disagreeing clocks, malformed/naive clocks, future
clocks or changed replay are typed refusals. No fallback to the maximum clock, receipt,
lexical order or provider revision number. This is a distinct label basis/hash, not a
ranking field; reusing the existing evidence path avoids duplicating clock validation.

**D4 — Analysis-as-of and fold selection.** The analysis cutoff (`validation_as_of`) first
filters actual receipts: `available_at <= analysis_as_of`. The existing repository query
already performs exactly this bound; it is reused. For each fold origin, the core selects
the latest revision by the chosen effective clock/derived rank among all revisions whose
effective label clock is `<= fold_origin`. It never chooses a global latest revision, never
drops earlier revisions, and refuses equal effective clocks for competing publications.
Default `ACTUAL_RECEIPT` selection is byte-for-byte the current `_resolve_targets` behaviour.

**D5 — Evaluation truth.** After the actual-receipt gate, final evaluation truth is selected
separately at the analysis cutoff using the same effective-clock order, labelled
`FINAL_KNOWN_AT_ANALYSIS_AS_OF`, and records the target revision ID, actual receipt, label
clock and basis for every gas day. This truth is for scoring only; it is never training input
and never makes an earlier fold retroactively available.

**D6 — Quality is unchanged.** D+1 remains `PROVISIONAL` and requires explicit permission;
quality `A` remains `AMENDED` and is not relabelled `ACTUAL`; D+6/unknown provisionality
remains refused; blank remains missing, not zero. Label timing cannot promote quality.

**D7 — Evidence propagation and hashes.** Only nondefault runs add keys. The nondefault
request, model and selection identities bind `target_label_basis`,
`target_label_policy_hash`, per-fold training revision IDs with their actual receipts and
effective clocks, final-truth revision IDs/basis, and the analysis cutoff. `DemandPrediction`
carries the basis and policy hash plus its model/selection references. Fit, predict, runtime,
operator and any snapshot/portfolio admission MUST carry all four (basis, policy hash,
actual receipt, derived clock) or refuse; no silent defaulting or uplift. Default keys are
omitted and default request/model/selection hashes are byte-identical.

**D8 — No infrastructure.** No table, column, migration, service, cache, dependency,
public API, SDK route, source activation, network fetch or write is introduced. The
runtime remains read-only.

## Assumptions and non-claims

The consensus provider applicability instant is an observed provider clock, not proof of
first publication, public readability, continuous availability, local receipt or market
availability. The path assumes persisted official-key evidence is faithful; changed bytes,
timestamps or identities are rejected on replay. It cannot support a prospective,
genuine-vintage, leakage-free, production, accuracy or customer claim. A research result
under this basis must retain the label forever and remains `NOT_PROMOTED`.

## Staged implementation and exact paths

| Stage | Exact paths and bounded change |
|---|---|
| 1. Pure DTO/selector | `src/eurogas_nexus/domain/research/weather_demand.py`: enum, row/policy fields, effective-clock selector, final-truth selector, prediction/evidence fields, conditional hash payloads. Tests: `tests/unit/test_weather_demand.py`. |
| 2. Mapper/runtime opt-in | `src/eurogas_nexus/application/research/demand_target_inputs.py`: optional basis argument, prerequisite checks, label fields/provenance. `src/eurogas_nexus/application/research/weather_demand_runtime.py`: request/evidence/result propagation and conditional request hash. `scripts/ops/fit_weather_demand.py`: optional model-policy input and evidence-based summary. Tests: `tests/unit/test_demand_target_inputs.py`, `tests/unit/test_weather_demand_runtime.py`. |
| 3. PG causal tests | Reuse `src/eurogas_nexus/db/repositories/demand.py` unchanged. Extend `tests/integration/test_weather_demand_runtime_postgres.py`; add `tests/integration/test_demand_target_label_clock_postgres.py` for persisted-capture-now, late-receipt, analysis-cutoff and replay cases. |
| 4. Prediction/evidence consumer | `src/eurogas_nexus/domain/research/weather_demand.py` `predict_selected_demand`/`predict_baseline_demand` and `DemandPrediction`; `scripts/ops/fit_weather_demand.py`; evidence/snapshot/portfolio admission. No current `DemandModelResult` snapshot/portfolio consumer exists, so the future adapter MUST consume this evidence DTO or refuse; it is not added here. |

Every stage is independently reviewable and reversible. Root review is required before
stage 1 and again before any schema or consumer decision.

## Required test plan (not executed)

1. **Golden preservation:** exact pre-change default request, model and selection hashes;
   default prediction evidence, row count, `available_at`, revision IDs, operator output and
   numeric results unchanged; `label_at is None` and no new keys by default.
2. **Fold causality:** capture-now receipts produce zero historical folds under the default;
   the same rows under the opt-in produce folds only where the effective label is at or
   before each origin; every revision remains available for later folds.
3. **Analysis cutoff:** a label earlier than the cutoff with actual receipt after it is
   excluded; final truth is the latest revision actually known at the cutoff, separately
   labelled with IDs, and not used for training.
4. **Clock ties:** equal consensus instants for competing publications refuse; no lexical,
   receipt or provider-number fallback.
5. **Future/naive clocks:** future source clock, future label relative to analysis, naive or
   malformed clocks refuse; no fabricated UTC.
6. **CSV opt-in:** `target_label_basis` with CSV is refused before repository reads; no CSV
   field inference.
7. **Late actual receipt:** receipt after analysis-as-of excludes the row in every mode.
   Receipt before analysis-as-of but after a historical fold can be eligible only under
   the explicit reconstruction when its provider label clock is at/before that fold;
   this is the declared historical-publication assumption, never actual-receipt OOS.
8. **Changed replay:** changed raw hash, source identity or clock for the same publication
   is a typed refusal; first receipt and label evidence are preserved.
9. **Quality boundaries:** D+1 permission required; A refused as AMENDED; D+6/unknown
   refused; blank refused; native MSCM untouched.
10. **Lost basis:** fit, predict, runtime, operator and future snapshot/portfolio hops refuse
    missing or mismatched nondefault basis; no silent `ACTUAL_RECEIPT` defaulting.

## Alternatives rejected

- **Wait for prospective receipts only:** the true genuine-OOS path and the default, but it
  yields no historical labels now; retained, not replaced.
- **Overwrite `available_at` with source applicability:** destroys actual receipt and
  first-receipt evidence; rejected.
- **Global latest or final labels in training:** look-ahead and not per-fold; rejected.
- **Use RFC-0007 archive weather as a demand-label clock:** separate causality gates;
  rejected.
- **Infer from CSV or a provider revision number:** unsupported evidence; rejected.
- **Add a label-clock table/API:** no measured need; existing provenance suffices; rejected.

## Acceptance boundary

Root accepts the staged research architecture subject to the ruling below.
Only bounded pure stage1 is authorized now. Later runtime and consumer work must
pass independent root review. No source activation, public API exposure, model
promotion, production use, genuine OOS, accuracy claim or schema change is authorized.
The index records this bounded decision, not implementation completion.

## Root ruling, 2026-10-30

Root accepts the staged research architecture and authorizes bounded pure stage1.
The findings are backed by the actual40-day mechanics probe, not provider-history
accuracy evidence. Pure code takes explicit clocks; a later runtime/operator opt-in
must cap analysis-as-of at a trusted server clock and keep actual-receipt SQL admission.
All default hashes and numeric results must match the root pre-change golden.

Stage1 must reject nondefault prediction/consumer use until complete label-evidence
propagation exists; adding fields must not allow existing prediction code to silently
drop the new basis. Metadata may carry a complete immutable label-evidence set or
a bound, resolvable frozen reference to that set; a lone self-declared basis string
cannot replace revision IDs, actual receipts and derived-clock facts. No API exposure,
quality promotion, new persistence or source activation is authorized. Runtime stage2
and downstream consumers require separate root review of stage1 evidence.

## Root staged advancement — mapper-only stage2, 2026-10-30

After independent integrity review, corrective implementation and root's58 passing
Linux/NumPy label/core/prediction tests with exact pre-change default hashes and
metrics, pure stage1 is accepted at commit ddd22a4. Root now authorizes only the
mapper portion of stage2: an explicit target-label-basis argument in the existing
National Gas target mapper, restricted to already validated REST source-applicability
ordering. Actual receipt admission, all revisions, native units and quality remain
unchanged. Defaults must retain exact rows, references and hashes. CSV, unknown
basis and receipt-ranking/nondefault combinations refuse before record iteration.

This advancement does not authorize runtime/operator wire opt-in or a consumer.
The later runtime must independently cap analysis-as-of with a trusted server clock
and preserve actual-receipt SQL admission. Existing prediction refusal remains.
Mapper mechanics tests cannot establish historical public availability or accuracy.
No new persistence, schema, source activation or API is authorized.
