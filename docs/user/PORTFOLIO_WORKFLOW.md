# Portfolio comparison and position review

[简体中文](PORTFOLIO_WORKFLOW-CN.md) · [Trader guide](../guides/TRADER.md)

## Compare resources and routes

1. Open **Deals → Contracts** and inspect saved resources, quantity, all-in cost and access.
2. Route comparison (Routes) and the pool optimiser (Evaluate, Optimise) were removed from the
   screens (commercial design basis 2, section I); they return as **Deals → Opportunities**.
   The engines stay on the API.
3. Open **Review**, inspect assumptions and source references, and record the permitted outcome.

The allocation engine uses min-cost flow over the declared inputs and constraints.
The [data guide](DATA_STATUS_AND_PROVENANCE.md#resource-pool-financing) gives the simple-interest
cash-timing formula and explains the default rate and ACT/365F or ACT/360 conventions.

## Review the position ladder

In **Book → Limits & P&L**, use the ladder to inspect physical contracts and
filled financial trades together.

| Item | Interpretation |
| --- | --- |
| Rows | Delivery month, then hub |
| Physical | Active stored contracts over their gas-year window, with daily contract quantity and delivery hub |
| Financial | Filled screen-trade quantities allocated over their delivery gas days; buys long, sells short |
| Net / hedged | Net long/short and the share of physical position offset by trades |
| Mark | Monthly hub curve price and its derivation; latest-close flat fallback for uncovered months |
| Summary | Physical/financial/net position, hedge measures, mark-to-market and historical price VaR |

Contract prices retain their recorded currency. Position composition converts them to the
hub currency with available ECB reference rates; a missing conversion is reported with
its valuation exception. Reporting-currency roll-ups likewise depend on the required FX.
Inspect unvalued legs, FX warnings and mark methods before reconciling totals.

The displayed one-day 95% historical VaR describes price moves on the represented open
position. Volume, basis, shape and credit exposures need their corresponding reviews.
Use the selected book scope and the firm's reconciled position record for the comparison.

See [Risk and finance](../guides/RISK_AND_FINANCE.md) for controls and review records.
