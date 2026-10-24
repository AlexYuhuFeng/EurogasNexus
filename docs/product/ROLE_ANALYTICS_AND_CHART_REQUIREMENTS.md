# Role-based gas desk analytics and chart requirements

Owner direction: 2026-10-24. Candidate design and acceptance requirements, not a
claim that these analytics are implemented. Complements
[business workflows](EUROPEAN_GAS_BUSINESS_WORKFLOWS.md) and
[data-to-decision mapping](DATA_TO_COMMERCIAL_DECISION_MAP.md).

## Choose the decision before the chart

| Role / question | Primary view | Useful reference lines / statistics | Preconditions |
| --- | --- | --- | --- |
| DA/within-day trader: is this product attractive and usable for our remaining obligation? | Price or bid/ask series, synchronized spread panel, delivery-period exposure | Prior comparable settlement, selected position cost, all-in break-even, explicit strategy threshold; quote age and bid/ask spread | Distinguish observation time from delivery time; executable quotes from indicative indices; show available liquidity only when supplied |
| Trader: should we change a pipeline route or LNG sale alternative? | Comparable delivered-cost/netback bars with component waterfall, sensitivity curve, capacity timeline | Break-even sale price, booked capacity and obligation limits | Common destination, delivery interval, currency and energy basis; transport, losses, regas and funding assumptions explicit |
| Portfolio manager: where is the book exposed and earning or losing? | Exposure by hub/delivery bucket, PnL time series and attribution waterfall | Approved limits, zero line, budget where defined; realized and unrealized components | Reconciled positions, marks and FX; distinguish physical quantity, financial exposure and scenario allocation |
| Researcher: what drives the market and is a strategy robust? | Seasonal price/spread curves, distribution, forecast-revision and demand/flow panels; comparable frozen backtests | Optional median and quantile bands, sample size, missing coverage, out-of-sample boundary | Comparable instruments and point-in-time inputs; calibrated weather/demand linkage before quantitative causal claims |
| Independent reviewer / risk: can this decision withstand adverse outcomes? | Stress loss matrix, exposure/limit view, loss distribution and VaR exceptions when validated | Confidence threshold, risk limit, historical stress references | Frozen portfolio and market snapshot, declared risk methodology and evidence; review permission remains authoritative |
| Administrator / data operator: can users trust this result? | Freshness/coverage timeline and affected-workflow list | Freshness target, failed/revised observations and ingestion delay | Entitlement-safe operational metadata; no automatic access to commercial analytics |

## Price and spread semantics

- Daily index or settlement: line/point chart with gaps. Do not manufacture an
  open, high, low, close or volume from one daily observation.
- OHLC candles: only supported by actual bar data or a validated aggregation of
  eligible trades, with venue session, timezone, bar interval and trade filters.
  Last trade, official close and settlement are separate fields. Volume/open
  interest need their actual source, unit and reporting frequency.
- Forward curves use delivery tenor on the x-axis; historical charts use
  observation time. Rolling front-month history discloses roll methodology and
  adjustments; it is not a single unchanged deliverable contract.
- Spreads require selected legs, sign/weights, matched delivery periods, currency,
  energy conversion and synchronized mark rules. Missing legs remain missing;
  never subtract incompatible prices or silently forward-fill stale observations.
- Median and quantiles are optional analytical references, labelled with window,
  sampling, population and coverage. Mean, VWAP and median are distinct; VWAP
  needs appropriate volume. A statistical band is not a predictive confidence band.
- Default to a small number of decision-relevant guides: zero for a spread,
  cost/break-even and a configured threshold. Technical indicators are optional
  research tools, not an unexplained default overlay or recommendation.

## Economics and risk contracts

**PnL.** Reuse existing backend-owned cumulative net indicative backtest PnL and
amount drawdown (`domain/backtest/engine.py`, `StrategyBacktestWorkspace.tsx`,
`StrategyCompareWorkspace.tsx`). Preserve the indicative/synthetic qualification.
Do not relabel a backtest as realized account performance. Actual portfolio PnL
requires position and cash reconciliation, valuation time, currency, fees and
realized/unrealized conventions. Attribution must reconcile to the total within
declared tolerance; missing periods must not become zero returns. Percentage
returns and percentage drawdown require a meaningful capital/NAV denominator.

**Margin.** Use explicit labels for commercial unit margin, total contribution,
initial margin, variation margin and collateral liquidity. These are different
quantities. Guarantee/collateral cash is not automatically an expense; funding
costs are distinct. Clearing-margin calculations require the applicable agreement
or clearing methodology, eligible offsets and dated inputs. A flat percentage
estimate must remain a labelled scenario, never an authoritative margin call.

**VaR / expected shortfall.** No decorative risk KPI. Before enabling, define
portfolio scope, mark snapshot, currency, horizon, confidence, method, lookback,
factor mapping, missing/stale handling and model version. Account for hub/tenor/FX
basis, correlations and nonlinear exposures as applicable. Validate loss signs,
diversification, scenario revaluation and exception backtests. Do not sum desk
VaRs or assume square-root-of-time scaling without justified model assumptions.
VaR is neither a maximum loss nor a substitute for pipeline outage, basis blowout,
LNG delay, liquidity and collateral stress scenarios. Insufficient input coverage
must yield an unavailable/qualified result, never a green zero-risk badge.

## Shared interaction and acceptance

Charts inherit the selected book/case, hub, product, delivery interval and snapshot;
changing display range cannot silently change the valuation basis. Crosshair,
zoom/reset, legend and table alternatives must work with Windows/Linux keyboard
navigation. Units, timezone, source, as-of time, freshness and synthetic status
remain visible. No color-only meaning; missing data and unavailable permissions
must be distinguishable. Selections may attach versioned evidence to a case, not
mutate a frozen run. Shared client behavior applies to Web and Tauri.

Implementation order: inventory existing results and retain validated charts;
improve typed price/spread selection and guides; connect portfolio exposure and
economic attribution; introduce missing risk/margin engines only as separately
validated capabilities. Prefer existing backend API/SDK result contracts over
client-side financial calculations. Each capability requires deterministic
numerical examples, bad/missing/stale-data behavior, role access checks and an
actual workflow test. This document does not certify current industry compliance
or claim a completed VaR, clearing-margin or live portfolio-PnL implementation.
