# RFC-0003: ECMWF weather to regional gas demand

Status: Accepted architecture and staged implementation,2026-10-28.
Root architecture/integration review under the autonomous execution policy.
No model accuracy, production source activation or customer acceptance is claimed.

## Problem and result

The owner requires public ECMWF forecasts to be consumed in demand/supply models,
not merely collected or displayed. Weather currently has a mock connector and
empty API. Implement real forecast acquisition, immutable vintages, explicit
degree-day features, regional actual targets, point-in-time fitting/comparison,
labelled predictions and existing research/portfolio consumers. Market prices
use official public Data-page downloads when no API subscription is supplied.

## Reviewed evidence

ECMWF official Open Data documentation and the AWS Open Data Registry identify
no-key public forecast access under CC-BY4.0 and ECMWF terms. Root fetched the
official directory and observed forecast dates20261024-20261027. Root also
fetched the official ECMWF-managed AWS replica listing, which includes prefixes
starting20230118. Existence of old prefixes does not prove usable field history:
inspect each object's model/grid/index/time metadata and report actual coverage.

- https://www.ecmwf.int/en/forecasts/datasets/open-data-0
- https://data.ecmwf.int/forecasts/
- https://registry.opendata.aws/ecmwf-forecasts/
- https://www.nationalgas.com/our-businesses/operational-data/gas-data-portal
- https://data.nationalgas.com/Files/How%20to%20work%20with%20Gas%20operational%20data%20in%20Excel%20using%20PowerQuery.pdf

National Gas documents public demand/supply/weather downloads and a CSV query
endpoint. It is the first target candidate, subject to actual catalogue/series/
unit/gas-day validation; an ENTSOG flow is not silently renamed total demand.

## Decisions

1. Add dataset-specific ECMWF public identity and preserve existing generic
   licensed Weather semantics. Existing authentication, operator stop, rate limits
   and source validation apply. No credentials, cookies or arbitrary URLs.
2. Acquire official indices and bounded GRIB2 byte ranges from data.ecmwf.int or
   the ECMWF-managed AWS bucket named in the official registry. Preserve origin,
   request/index/message hashes, model/cycle/grid/parameter and attribution.
   No whole-global-field download when the selected indexed message suffices.
3. Decode authentic GRIB2 using ECMWF ecCodes; no invented JSON weather feed.
   Dependency selection is ecCodes Python2.50 with a Python3.11-compatible NumPy
   line2.3, subject to pinned universal closure, license-text and CVE verification
   before adding it to delivered requirements. Isolated decoder experiments are
   approved. No new service/datastore; existing worker/API/artifact stack remains.
4. Reuse ForecastObservationRecord for forecast temperatures and derived features,
   SeriesDefinitionRecord, SourceEntityMapping and governed dataset artifacts.
   The proposal's parallel weather_points/forecast_observations storage is not
   accepted without a measured need. Add only missing immutable run, regional
   policy, actual-target and fitted-model evidence structures; keep schema phases
   additive and bounded rather than installing eight speculative tables at once.
5. Preserve issued, valid interval, provider availability evidence, receipt and
   ingestion times separately. A future-valid forecast IS permitted as a feature
   when it was issued and demonstrably available at the prediction origin.
   Later-issued or later-available vintages are excluded. Archive reconstructed
   availability must name its evidence/basis and is never called historical local
   receipt. Missing historical coverage is a visible limitation, never fabricated.
6. Explicit region/grid bindings, weights, gas-day calendar, degree-day bases,
   units, hold/coverage rules and method versions are required. Forecast grid
   cells are not observing stations. Daily-mean HDD/CDD and integrated heating/
   cooling degree-hours are distinct named feature definitions; do not silently
   interchange them or award zero to incomplete days. DST23/25h is tested.
7. Native demand units remain native until an evidenced conversion exists.
   In particular, mcm is not converted to MWh with an assumed calorific value.
   Preserve actual/estimated/forecast/allocation/nomination flags and revisions.
8. Fit a seasonal/calendar baseline and weather/calendar candidate with frozen
   training cutoffs and rolling out-of-sample folds. Score error and intervals on
   real targets, compare against baseline and retain the measured winner.
   Synthetic data proves mechanics only. Realized-weather calibration and genuine
   forecast-vintage validation are different claims. No universal accuracy claim,
   unmeasured promotion or guessed weather-to-demand/supply coefficient.
9. ENTSOG/GIE supply, storage and LNG become compatible contemporaneously available
   conditionals, with explicit coverage. Regional outputs never become an invented
   pan-European total. Predictions are model output, not observed physical facts.
10. Use existing weather/research APIs, typed SDK and existing task workspaces.
    Bind predictions to portfolio/scenario and strategy inputs with exact run and
    vintage references, units and uncertainty. No decorative unused data/page.
    No trade execution, nomination, settlement or authority from a persona.

## Delivery phases and proof

A. Official transport/index/range and authentic decoder; root captures real data.
B. Immutable persistence and explicit features, plus actual target ingestion.
C. Dataset/model/OOS evidence and labelled predictions consumed by research.
D. Portfolio/scenario consumption, scheduler and typed API/SDK/Web workflows.
E. Same-commit full tests, real-provider/PG and installed Windows/Linux evidence.

Each phase preserves the whole vertical objective. A parser, schema or green
fixture suite alone cannot close it. Tests cover range/hash/size/time mismatches,
missing/partial coverage, DST, vintage leakage, revised targets, model freezing,
baseline comparison, unauthorized reads and actual consumer result changes.

## Alternatives, risks and rollback

Reject a mock or third-party JSON proxy as ECMWF evidence, global15.5C defaults,
forecast-as-observed writes, future-valid-feature prohibition, missing-to-zero,
training on synthetic targets, unvalidated superiority and duplicate speculative
storage. Preserve existing APIs and legacy data; new source can be disabled and
new consumers invalidated without destroying history. Root reviews each bounded
migration/numerical implementation. Separate legal/customer reviews are not
claimed by this technical architecture decision.
