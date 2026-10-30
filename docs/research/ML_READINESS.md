# ML Readiness Report (CR-14 / P13)

## Purpose

Make future forecasting work possible without shipping training
infrastructure in this milestone. CR-14 delivers a leakage-safe, versioned,
provenance-complete, semantically unambiguous multivariate European-energy
dataset foundation.

## Ready now

| Capability | Where |
|---|---|
| Versioned energy ontology and canonical entities | `domain/research/ontology.py`, `energy-ontology/v1` |
| Point-in-time source mappings | `canonical_entities`, `source_entity_mappings` |
| observed/available/ingested temporal semantics | `domain/research/temporal.py` |
| Forecast vintages and actual/forecast/assessment/simulated kinds | `forecast_observations`, `ObservationKind` |
| Versioned feature registry with dependency closure | `domain/research/features.py`, `feature_definitions` |
| Versioned target registry and target-never-feature gate | `domain/research/targets.py`, `target_definitions` |
| Bounded resampling (no unlimited ffill) | `domain/research/resampling.py` |
| Declarative DatasetSpec and immutable snapshots | `domain/research/datasets.py`, `dataset_snapshots` |
| Leakage validation with blockers/warnings | `domain/research/leakage.py` |
| Time-based splits with embargo/gap | `DatasetSplit` |
| Quality report and content hashing | `DatasetBuildResult.as_metadata()` |
| Parquet/CSV export with entitlement gate | `domain/research/export.py` |
| Lineage and reproducibility | snapshot metadata + dependency tables |
| Typed agent capability contracts (MCP-free) | `domain/research/capabilities.py` |
| Catalog/build/quality/export APIs | `/api/research/*` |

## Deliberately not ready

- No model training, no GPU, no training jobs.
- No MCP adapter; capability contracts are transport-neutral and become the
  input to CR-15 (`Agent-Native Capability Layer`).
- No direct DB exposure to agents: agents call typed capabilities, never SQL.
- No execution/order/nomination semantics.

## Known limitations

- UAT price feeds are simulated; the representative snapshot uses
  `EXPLORATORY` mode and labels simulated targets explicitly.
- Runtime feature computers currently cover builtin spread/route-margin
  transforms; new transforms require a versioned `transformation` reference
  and tests.
- Official historical availability timestamps must be certified by sources
  before production `STRICT` datasets can be claimed.

## Next milestone

CR-15 / P14 is complete (see `docs/agents/`). Next: CR-16 / P15 Energy
Forecast Benchmark, unless CR-15 reveals a material defect first.

## Assessment: training datasets for gas and power forecasting (2026-10-30)

### Is the expectation valid?

Yes, for **fundamental, daily-to-seasonal forecasting**, and that is where it pays.
European gas and power desks forecast LDZ and industrial demand, gas-for-power burn,
storage injection and withdrawal, LNG send-out, cross-border flows and the spreads
these drive (NBP–TTF, THE–TTF, TTF–JKM, clean spark spreads). Weather explains most of
the day-to-day variance in demand, and gas-for-power burn links gas to power prices,
wind and solar output. The hard part of those models is not the estimator; it is a
history that shows **what was known at each forecast time**: weather forecast
vintages instead of later actuals, flows before their revisions, and prices with
their real publication times. Most in-house datasets get this wrong and their
backtests look better than live performance. A product that produces point-in-time,
licence-aware, reproducible datasets solves the expensive part.

It is **not** a meaningful source for the work HFT and market-making firms (Jane
Street, Hudson River Trading and similar) do in these markets. Their edge is order-book
microstructure: tick-by-tick ICE Endex/EEX/Trayport depth, queue position and latency.
That needs a dedicated capture stack and exchange licences for derived use, not a
research product, so it is out of scope by design. What those firms and energy
majors share with this product is the discipline: point-in-time data, embargoed
walk-forward evaluation and reproducible snapshots.

In a trading house the user is a **quantitative analyst or data scientist** on the
fundamentals or quant team. Here that is an ANALYST role with the
`QUANT_RESEARCHER` job function; data operators keep the sources current, and the
dataset build/export routes stay behind the GOVERNED floor and the export
entitlement gate.

### What the product provides

| Need | Status |
|---|---|
| Point-in-time selection (`available_at ≤ cutoff`), forecast vintages | Ready |
| Target registry; a target can never be a feature; leakage validator | Ready |
| Bounded resampling (no unlimited forward fill) | Ready |
| Lags, changes, rolling mean/std, linear combinations, each as of its own cutoff | Ready (2026-10-30) |
| Walk-forward folds with an embargo (`walk_forward_folds`) | Ready (2026-10-30) |
| Immutable snapshots, content hash, lineage, quality report | Ready |
| Parquet/CSV export with the entitlement gate | Ready |
| Python SDK for notebooks | Ready |

### Gaps, in priority order

1. **Coverage of drivers.** The catalogue has price series, weather and a few
   features. A useful demand or spread model also needs power prices and
   generation (ENTSO-E day-ahead prices, load, wind and solar), storage (AGSI),
   flows (ENTSOG), LNG send-out (ALSI), and calendar effects (holidays, gas-day,
   weekends). Each needs an ingestor that records publication time.
2. **Source certification for STRICT mode.** Until a source's historical
   `available_at` is certified, its datasets are EXPLORATORY.
3. **Licensing of exported features.** Exchange settlement prices and broker data
   are usually licensed for display; derived-data or non-display use in models needs
   the customer's own licence. The export gate enforces the row policy; the licence
   itself sits with the customer (see `docs/legal/DATA_SOURCE_TERMS.md`).
4. **Bulk and scheduled builds.** Builds are bounded per request (250k origins).
   Multi-year hourly datasets for many entities should run as scheduled jobs that
   write Parquet to object storage.
5. **Forecasts back into the platform.** Models are trained outside (notebooks,
   MLflow or similar). Their outputs should come back as `FORECAST` vintages so they
   enter later datasets and shadow evaluation like any other source. Training
   infrastructure stays out of scope.
