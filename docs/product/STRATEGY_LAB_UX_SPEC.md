# Strategy Lab UX Specification — CR-05

Status: accepted CR-05 architecture. This document owns the Strategy Lab
information architecture, workflow, component boundaries, validation, state,
density, comparison semantics, and Shadow shell.

## 1. Audit of legacy Strategy UX

Current `StrategyShadowRunTerminal` is a 800+ line monitor-centric terminal with
four legacy views (`monitor`, `economics`, `risk`, `runs`). Audit defects:

- workflow is fragmented: no Design/Backtest/Compare workflow, run history is a
  sub-panel, and version identity is buried;
- strategy identity is not persisted/editable; the hard-coded
  `nbp-sap-icis-ocm-window` scenario is assembled client-side;
- hidden assumptions: risk overrides and bar selection are local strings; no
  cost/fill/missing-data policy is visible;
- client-side calculations: price-basis classification, stale detection, pool
  cost, PnL curves and per-contract attribution are derived in React rather
  than consuming backend contracts;
- oversized/undersized information: six-column run table cannot compare
  professional runs; KPI/curves are synthesized from current live tape;
- charts have no persisted series, axes provenance, crosshair or empty state;
- duplicated controls: risk inputs coexist with bar selector and scenario
  evaluation, with no structured validation summary;
- ambiguous terminology: "shadow run", "paper PnL" and live-monitor labels mix;
- loading/error states are generic; frozen/read-only semantics are not shown;
- keyboard/ARIA behavior is partial and custom;
- no experiment grouping, no comparison semantics, no truthful Shadow shell.

## 2. Workflow and information architecture

Strategy Lab remains ONE primary workspace with local tasks:

- `DESIGN`
- `BACKTEST`
- `COMPARE`
- `SHADOW`

Deep link: `?workspace=strategy&task=<design|backtest|compare|shadow>`.
Invalid/missing task falls back to `design`. Trader context and selection query
keys remain in the same URL and are not overwritten by task navigation.

## 3. Persistent identity header

A compact `StrategyIdentityHeader` is shared by all tasks:

- strategy name + `strategy_id`;
- selected version `v{n}` and state `DRAFT`/`FROZEN`/`RETIRED`;
- lifecycle state, hypothesis (truncated with title), creator/last modified;
- hub/product/resource summary from frozen definition;
- active trader context;
- current selected run where applicable.

Actions use research language only: `New Strategy`, `Create New Version`,
`Freeze Version`, `Fork Version`, `Run Backtest`. Execution vocabulary is
forbidden.

## 4. Left strategy navigator

`StrategyNavigator` loads persisted strategies from `GET /api/strategies`,
search/filter client-side, shows lifecycle status and current version. Version
list loads lazily from `GET /api/strategies/{id}/versions`; selecting a version
never resets trader context.

## 5. DESIGN task

A structured editor, not JSON:

- **Hypothesis** — name, description, market thesis, objective;
- **Components** — rows for currently executable component types
  (`OCM_VS_DAY_AHEAD`, `MEAN_REVERSION`, `BEST_BUCKETS`, `SCORING`,
  `WEIGHTED_COMBINATION`). `OCM_VS_DAY_AHEAD` exposes day-ahead/intraday price
  names, hubs, tenors, bar minutes, thresholds and weight. Unsupported future
  component types are shown but marked unavailable;
- **Parameters** — typed parameter definitions with value/unit/range and
  sensitivity/optimization eligibility; correct input controls;
- **Risk controls** — hard blocks vs limits with visible distinction;
- **Economic assumptions** — fill-price policy, transaction cost, slippage,
  broker fee, tariff, balancing allowance, FX and missing-data policy with
  `KNOWN_COST`/`MODELED_COST`/`EXCLUDED`/`UNAVAILABLE` states;
- **Data requirements** — hubs, products, source classes, max age, FX,
  resource/capacity/tariff requirements.

`DRAFT` is editable. `FROZEN` is read-only; editing offers `Create New Version`
(`Based on v3 → Draft v4`), never unlock.

Validation is continuous and surfaced in a summary rail with BLOCKER/WARNING
badges near the affected section.

## 6. BACKTEST task

Modes: `CONFIGURE` and `RESULT`.

`CONFIGURE` exposes frozen version, period, gas-day calendar, schedule
(`05:00 UTC` default), explicit economic assumptions, missing-data policy,
optional experiment id, and a preflight summary before `Run Backtest`.
`Run Backtest` calls `POST /api/strategy-runs` with `run_type=BACKTEST`.

`RESULT` renders only persisted backend data:

1. run identity/provenance strip;
2. KPI strip from `backtest_metrics` (gross/net PnL, modeled costs, max DD,
   coverage, evaluations, blocked decisions; no client-side Sharpe);
3. cumulative net indicative PnL series;
4. drawdown and exposure series;
5. attribution table from `/attribution`;
6. decision-event table from `/events`;
7. right evidence rail (data integrity, source/temporal, assumptions, engine,
   warnings).

Run history is a dense table from `/api/strategy-runs` with sorting/filtering,
selection, multi-select add-to-compare, and open-result.

## 7. COMPARE task

Select 2–5 persisted runs. Runs are classified:

- `COMPARABLE`;
- `COMPARABLE WITH CAVEATS` — different period/engine/assumptions/quality;
- `NOT MEANINGFULLY COMPARABLE` — different strategy/currency/product.

Views:

- parameter/assumption matrix highlighting differences only;
- KPI table with absolute differences (no relative percentage for zero-base);
- cumulative net PnL and drawdown small-multiples/overlay with identical axes;
- data-quality matrix (temporal integrity, coverage, warnings, fallbacks);
- attribution comparison when backend rows exist, otherwise an honest empty
  state.

Higher PnL is never styled as "better".

## 8. SHADOW shell (CR-05)

No production shadow scheduler exists. The task shows a truthful
`SHADOW_MONITORING_NOT_CONFIGURED` state with prerequisites (CR-06 scheduler,
pause/resume, freshness blocking, drift). Existing persisted legacy strategy
runs remain visible in Backtest/Run History and are labelled legacy; no
simulated live alerts are emitted.

## 9. State ownership

`StrategyLabWorkspace` owns task selection and URL persistence. Data is fetched
through the existing API client, never calculated in React. Suggested
boundaries are implemented in one folder with focused components; no new
global store is introduced unless a second surface needs the same state.

## 10. Review and Market/Network handoffs

- `Open in Decision Review` sets selection context `run`, `strategy` and
  `version` ids then opens the review workspace.
- `Show market context` opens Market with the strategy's first hub.
- `Open in Scenario` preserves trader context and resource selection.

No large result payloads are serialized into navigation state.

## 11. Visual density and responsive behavior

- Desktop-first: 1440×900, 1920×1080, 2560×1440.
- 12–13px dense body, tabular numerals, 8px spacing grid, hairline borders,
  low radius, restrained elevation.
- 1920: navigator | primary content | evidence rail.
- 1440: rails collapse below a width breakpoint into local panels; no forced
  page horizontal scroll; tables scroll locally.
- No gradients, glassmorphism, marketing cards, glowing indicators, consumer
  KPI tiles or illustrative charts.

## 12. Loading, empty and error states

- DESIGN: no strategy exists / none selected / draft / frozen / blocked.
- BACKTEST: no runs / running / blocked / completed-with-warnings.
- COMPARE: fewer than two runs / incompatible / no series / no attribution.
- SHADOW: not configured / future capability.
- All states include a concrete next action.

## 13. Accessibility and i18n

- shared `WorkspaceTabs` with correct `tablist`/`tab`/`tabpanel`, arrow/Home/End
  movement and visible focus;
- charts have accessible summaries, no color-only status, table semantics,
  keyboard-removable comparison selections;
- all new strings exist in en-US and zh-CN with professional gas-trading
  terminology, not literal translations;
- status is always text + badge, never color alone.

## 14. Charting

CR-05 uses simple SVG charts built from persisted backend series only:
cumulative net indicative PnL, drawdown, exposure, and compare overlays.
No chart library is added. Lines break at missing series (blocked/skipped
events remain visible as gaps), axes show currency/units/gas-day timestamps,
and empty series render an honest empty state.
