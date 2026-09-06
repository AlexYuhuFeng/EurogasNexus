# Backtest Engine Specification — CR-04

Status: accepted CR-04 architecture. This document owns the backtest engine
contract: temporal data semantics, as-of evidence selection, economics,
decision events, metrics, experiments, determinism, and persistence.

## 1. Scope

CR-04 delivers the backend engine and experiment infrastructure that answers:

> What would this exact frozen strategy version have done over this historical
> period using only information available at each simulated decision time,
> under these explicit economic assumptions?

In scope:

- temporally safe historical evidence selection (as-of joins);
- gas-day decision clock using the canonical DST-aware CAM calendar;
- explicit economic/fill-price/missing-data policies;
- decision events, hypothetical exposure state, gross vs net indicative PnL;
- backend metric aggregation with correct drawdown;
- lightweight `backtest_experiments`, `backtest_decision_events`,
  `backtest_series`, `backtest_attribution` persistence;
- reproducibility through CR-03 manifests plus a pinned
  `backtest-engine/1` version.

Out of scope: Strategy Builder UX, polished result UI, advanced comparison,
parameter optimizer, full walk-forward, shadow scheduler, execution, order
routing, nomination submission.

## 2. Current backtest audit (pre-implementation)

Repository audit results:

- `src/eurogas_nexus/domain/research/backtest.py` — legacy endpoint
  `/api/research/backtest` computes win rate / Sharpe approximation /
  percentage drawdown from client-supplied `{"pnl_eur": ...}` trade records.
  No as-of data access, no frozen strategy version, no cost model. Marked as
  **legacy research path**; it is not upgraded and must not be presented as
  scientifically equivalent to CR-04.
- `src/eurogas_nexus/domain/strategy_lab/evaluation.py` — the only current
  strategy rule engine: component scoring -> OCM/day-ahead split -> paper
  targets -> expected margin `PnL`. It accepts client-supplied
  `price_observations` already selected by the caller; it is temporally
  agnostic by design. CR-04 wraps this rule engine behind an as-of evidence
  provider and never sends future observations into it.
- `src/eurogas_nexus/domain/market_intelligence/normalized_view.py` and
  `scan_and_persist_intraday_opportunities` — live-view code that selects
  **latest** FX/quote rows. These remain live UI/scan paths and are not used
  by the historical engine.
- `src/eurogas_nexus/domain/strategy_lab/run_orchestration.py` — CR-03
  professional `EVALUATION` path. It persists immutable manifests. CR-04
  extends this contract rather than creating `strategy_runs_v2`.
- Temporal fields present today:
  - `market_observations`: `observed_at_utc`, `period_start_utc`,
    `period_end_utc`; **no** `received_at_utc` / `available_at_utc` /
    `ingested_at_utc`.
  - `market_quotes`: `observed_at_utc` and `received_at_utc`.
  - `fx_observations`: `observed_at_utc`; no receipt timestamp.
  - `raw_archive`: `received_at_utc` exists for archived payloads but is not
    joined to normalized observations.
  - `cost_observations`: effective windows + `created_at_utc`.
- Cost assumptions today: strategy evaluation uses
  `all_in_cost_gbp_mwh + balancing_allowance_gbp_mwh`; no transaction cost,
  slippage, broker fee, tariff or capacity cost is modeled in strategy-lab.
  CR-04 makes every friction explicit.
- Duplicated simulation surfaces: legacy research backtest, strategy-lab
  evaluation, and intraday opportunity scan coexist intentionally. CR-04 is
  the only historical-engine path.

## 3. Terminology

- **Observation time** (`observed_at_utc`) — when the source states the value
  is effective.
- **Availability time** — when the value could have been known by the
  strategy. Stored explicitly when `received_at_utc` exists; otherwise
  policy-derived and classified.
- **Ingestion time** — when Eurogas Nexus received/stored the row. Not
  available on normalized market/FX rows today.
- **Delivery period** — the gas/product period the observation applies to
  (`period_start_utc`, `period_end_utc` or quote delivery window).
- **Decision time T** — one simulated evaluation timestamp.
- **Run cutoff** — maximum information time allowed for a decision. Per-event
  cutoff equals T; the run manifest records the whole period and per-event
  boundaries.

These fields are never interchangeable.

## 4. Architecture

```text
BacktestRequest
    -> frozen StrategyVersion
    -> DecisionClock (canonical gas day + explicit UTC clock time)
    -> HistoricalEvidenceProvider (batch load, then as-of filter per T)
    -> StrategyEvaluator (existing strategy-lab rule engine)
    -> EconomicModel (explicit cost components + as-of FX)
    -> DecisionEvent / ExposureState / Attribution
    -> MetricAggregation
    -> CR-03 StrategyRun + Manifest + Snapshot
    -> experiment_id link
```

Separations enforced:

- data access lives in `db/repositories/backtest.py`;
- temporal/as-of rules live in `domain/backtest/temporal.py`;
- strategy rules remain in `domain/strategy_lab/evaluation.py`;
- economics/metrics live in `domain/backtest/engine.py`;
- persistence of immutable run rows uses CR-03 `strategy_runs`.

## 5. Temporal data model

Policy:

| Row | Availability field | Integrity class |
|---|---|---|
| `market_quotes` | `received_at_utc` | `VERIFIED` |
| `market_observations` real-time/broker sources (`ICE_OCM*`, `Trayport*`) | `observed_at_utc` (source semantics: screen mark is contemporaneous) | `APPROXIMATE` |
| `market_observations` daily assessments (`ICIS*`, `SAP`, `EEX*`, `ECB`) | `observed_at_utc` (publication time unknown) | `APPROXIMATE` |
| any row without `observed_at_utc` | none | `INSUFFICIENT` |

`TEMPORAL_PROVENANCE_APPROXIMATE` is always a visible warning. A strategy
whose result would be misleading without exact availability timing is
BLOCKED only if the selected missing-data policy is `FAIL` and required
series are absent; otherwise the run remains visible with the approximate
classification. No availability timestamps are invented.

## 6. As-of rules

For simulated decision time T:

- price observations are eligible when
  `availability_time(observation) <= T`;
- FX rates are eligible under the same rule;
- cost observations are eligible when
  `effective_from_utc <= T <= effective_to_utc` (inclusive) and the newest
  `created_at_utc` among eligible rows wins;
- delivery/tenor filters come from the frozen component (`hubs`, `tenors`,
  `price_basis`) and from the observation/quote delivery window.

The engine never uses `latest`, `max(observed_at)` over the whole period, or
today's live snapshot inside a historical decision. Repository queries load
the whole eligible window once (batch), then the domain filters per decision
time.

## 7. Gas-day handling

The decision clock uses `domain/market/gas_day.py` with
`EU-CAM-UTC-2025`. Backtest-specific gas-day code is forbidden. Decision
timestamps are explicit UTC clock times; the recorded `gas_day_start_utc` /
`gas_day_end_utc` come from the shared calendar, so 23/25-hour DST gas days
are correct. Tests cover normal CET, normal CEST, spring-forward, and
fall-back.

## 8. Data snapshot / evidence

CR-03 `strategy_data_snapshots` remains the immutable logical evidence
reference. A backtest snapshot records:

- source systems, observation refs, FX refs, resource refs, cost refs;
- row counts by table/source;
- eligible time range (`period_start` / `period_end`);
- `data_cutoff_utc` (maximum decision time);
- `quality_state`:
  `VERIFIED` (all rows have explicit receipt time),
  `APPROXIMATE` (policy-derived availability), or
  `MIXED`/`INSUFFICIENT`;
- temporal-integrity status and warnings.

Rows are referenced, not duplicated. Normalized observation rows are treated
as append-style; if a future retention/update path ever mutates rows, that
path must add immutable row hashes before CR-04 runs may claim full
reproducibility on top of it.

## 9. Economic assumptions

`BacktestEconomicAssumptions` is stored in the run manifest. Default cost
treatments:

| Cost component | Default treatment | Meaning |
|---|---|---|
| `TRANSACTION_COST` | `UNAVAILABLE` | never silently zero |
| `SLIPPAGE` | `UNAVAILABLE` | never silently zero |
| `BROKER_EXCHANGE_FEE` | `UNAVAILABLE` | never silently zero |
| `TRANSPORT_TARIFF` | `EXCLUDED` | current OCM/DA strategy has no route transport |
| `CAPACITY_COST` | `UNAVAILABLE` | visible warning when strategy would require it |
| `BALANCING_ALLOWANCE` | `RESOURCE_DEFINED` | already embedded in resource all-in cost |
| `STORAGE_COST` | `EXCLUDED` | not applicable to current component |
| `FX_CONVERSION` | `AS_OF_REQUIRED` | historical rate eligible at T |

Treatments are one of `KNOWN_COST`, `MODELED_COST`, `EXCLUDED`,
`UNAVAILABLE`, `RESOURCE_DEFINED`. A component with an amount participates in
modeled costs only when treatment is `KNOWN_COST` or `MODELED_COST`.
`UNAVAILABLE` emits `COST_UNAVAILABLE:<code>` and is not subtracted.

## 10. Fill-price policy

Supported `fill_price_policy`: `MID`, `BID`, `ASK`, `LAST`, `ASSESSMENT`,
`NEXT_ELIGIBLE`. `market_observations` map source rows to `price_type`
(`ASSESSMENT`, `EXCHANGE_REFERENCE`, `BROKER_SCREEN`, `INSTANT`);
`market_quotes` map `MID`/`BID`/`ASK`/`LAST` to their explicit fields. The
policy is stored in assumptions. No order-book execution is simulated.

## 11. Missing-data policy

Supported policies:

- `FAIL` — any required price series absent at T blocks that decision;
- `SKIP_DECISION` — decision is recorded as `SKIPPED`, not a normal result;
- `CARRY_FORWARD_WITH_MAX_AGE` — last eligible value is reused only within
  `carry_forward_max_age_seconds`, with source and
  `CARRY_FORWARD_USED:<series>` visible on the event;
- `USE_APPROVED_FALLBACK_SOURCE` — an explicit `fallback_sources` map is
  required; lineage is preserved in `evidence_refs`.

Unrestricted forward fill is not implemented.

## 12. Decision-event model

`BacktestDecisionEvent` records per evaluation:

- `decision_time_utc`, `gas_day`, `gas_day_start_utc`, `gas_day_end_utc`;
- `strategy_version_id`, `run_id`, `experiment_id`;
- eligible evidence refs (`price`, `fx`, `resource`, `cost`);
- frozen parameter values;
- weighted score, day-ahead/intraday averages, spread;
- allocation targets (candidate action + quantity + reference price +
  expected margin);
- `gross_indicative_pnl_gbp`, modeled cost trace,
  `net_indicative_pnl_gbp`, `cumulative_net_indicative_pnl_gbp`,
  `ending_exposure_mwh_per_day`;
- outcome: `COMPLETED`, `COMPLETED_WITH_WARNINGS`, `BLOCKED`, or `SKIPPED`;
- machine-readable `missing_inputs` and `warnings`.

Events are normalized rows (`backtest_decision_events`) plus an API projection.

## 13. Hypothetical exposure state

The current strategy emits a full portfolio allocation target per decision,
not an incremental position. Exposure state is therefore the latest
allocation target quantity, carried forward when a decision is skipped and
reset to zero when blocked. Future incremental strategies must add explicit
inventory semantics; CR-04 does not pretend this state is trade capture.

## 14. PnL model

For each non-blocked decision with allocation targets:

- `gross_indicative_pnl_gbp` = existing strategy-lab expected margin *
  target quantity (before modeled frictions);
- `modeled_costs_gbp` = sum over `KNOWN_COST`/`MODELED_COST` components,
  converted to GBP/MWh with as-of FX and multiplied by target quantity;
- `net_indicative_pnl_gbp` = gross - modeled costs;
- cumulative net series and drawdown use net indicative PnL.

Labels are `gross_indicative_*` / `net_indicative_*`; never settled
financial truth.

## 15. Result metrics

Always emitted where meaningful:

- `evaluation_count`, `candidate_decision_count`, `blocked_decision_count`,
  `skipped_decision_count`;
- `data_coverage` (completed or completed-with-warnings / evaluation count);
- `gross_indicative_pnl_gbp`, `modeled_costs_gbp`,
  `net_indicative_pnl_gbp`;
- `cumulative_net_pnl_series`;
- `max_drawdown_gbp`, `peak_timestamp_utc`, `trough_timestamp_utc`,
  `recovery_timestamp_utc` (when recovery exists);
- `pnl_volatility_gbp` (sample standard deviation, n >= 2);
- `worst_event_pnl_gbp` / `best_event_pnl_gbp`;
- `max_exposure_mwh_per_day` / `average_exposure_mwh_per_day`;
- `hit_ratio` where denominator = candidate decisions;
- `average_margin_gbp_mwh`, `average_modeled_cost_gbp_mwh`;
- `sharpe_ratio` / `sortino_ratio` = `None` with reason
  `RISK_METRIC_NOT_APPLICABLE` because event PnL has no defined periodic
  return/capital denominator;
- `turnover` = `None` (current strategy emits full allocation targets, not
  turnover).

No metric is emitted merely because professional systems have it.

## 16. Attribution

`backtest_attribution` stores dimensions the current engine can support
without fabrication:

- `component` (allocation contribution per component score is not separated
  by the current engine, so component rows are emitted only when one
  component exists);
- `market_bucket` (`ICE_OCM` / `DAY_AHEAD`);
- `cost_component` (each modeled cost line).

CR-05 visualization can consume these rows. Hub/resource/contract dimensions
are reserved for when the evaluator exposes them.

## 17. Experiment model

`backtest_experiments` stores `experiment_id`, `strategy_id`,
`base_strategy_version_id`, `name`, `hypothesis`, `experiment_type`,
`evaluation_period_json`, `run_ids`, `status`, creator/time. CR-04 implements
`SINGLE_RUN` end-to-end. `PARAMETER_COMPARISON` and `WALK_FORWARD` are
reserved enum values; no superficial implementation.

Period concepts are explicit (`evaluation_period_json`). A full-period
optimized result is never labeled out-of-sample.

## 18. Determinism

For identical frozen version, period, schedule, assumptions, evidence pool,
engine version and seed, semantic outputs are numerically identical within
the documented rounding tolerance (see precision). The API returns the
manifest hash; tests run A/B with identical inputs and assert identical
semantic outputs and hashes. Different parameter, assumption, or evidence
content produces a different input hash.

## 19. Precision

- prices/costs: rounded to 4 decimal places at component-level economics;
- money totals: rounded to 4 decimal places at event/run boundaries;
- volumes: rounded to 4 decimal places;
- FX rates: consumed as stored floats; conversion products rounded to 4
  decimal places at the GBP/MWh boundary;
- intermediate calculations are not rounded merely for display.

Binary floats remain acceptable for current research arithmetic; decimal
fixed-point is adopted only when settlement-grade accounting is introduced.

## 20. Engine versioning

`backtest-engine/1` is stored in `strategy_runs.backtest_engine_version` and
in the manifest, separately from `application_version`. Any semantic change
to temporal selection, economics, PnL, or metrics increments the engine
version and is documented in the backlog before release.

## 21. Performance

Baseline measured against an in-memory representative pool (not DB):

- `scripts/ops/backtest_benchmark.py` measured on the local Windows dev
  environment: 30-day daily run ~0.03 s / 30 events; 365-day daily run
  ~2.33 s / 365 events (both candidate decisions = events).
- DB access loads all eligible rows in a bounded batch; no per-decision DB
  query loop is used by the engine.
- No performance target is promised. The current domain loop is O(events ×
  rows) in memory; a 1-year intraday benchmark is deferred until an
  intraday historical dataset is available.

## 22. Known limitations

- `market_observations` and `fx_observations` lack `received_at_utc`, so
  availability is approximate by declared policy; runs surface
  `TEMPORAL_PROVENANCE_APPROXIMATE`.
- Current evaluator supports only `OCM_VS_DAY_AHEAD` and sibling legacy
  component families; other component types fail closed.
- Parameter overrides are not yet applied to legacy component internals;
  SINGLE_RUN freezes the version's own parameter values.
- Walk-forward and parameter sweep are contracts only.
- No trading calendar: weekends are evaluated if evidence exists.
- Cost components supplied by the caller are recorded and shown, but are not
  independent market truth unless their source refs are persisted.
- Live migration was not performed locally (no reachable PostgreSQL service);
  Alembic head is the migration contract.
