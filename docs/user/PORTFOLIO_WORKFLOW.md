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
| Net / hedged | Net flat-price exposure (`price_exposure_mwh`) and the share of the physical price exposure offset by trades. A contract priced at a hub index keeps its volume in Physical, and its price exposure is on the index (`index_mwh`), so a contract on its own hub's index adds no exposure and needs no hedge; `net_mwh` stays the net volume |
| Mark | Monthly hub curve price and its basis (quoted, derived from a quarter, season or year, balance of month), from one snapshot of quotes per hub (one as-of, settlements first, then the hub's main source, each quote within its tenor's staleness limit). A month no quote prices is not available and its leg-months are not valued; no day-ahead or other product fills it |
| Summary | Physical/financial/net position, hedge measures, mark-to-market and historical price VaR |

Contract prices retain their recorded currency. Position composition converts them to the
hub currency with available ECB reference rates; a missing conversion is reported with
its valuation exception. Reporting-currency roll-ups likewise depend on the required FX.
Inspect unvalued legs, FX warnings and mark methods before reconciling totals.

The displayed one-day 95% historical VaR describes price moves on the represented open
price exposure. Each hub's series is one product from one source (month-ahead, or
day-ahead where no month-ahead history is held, which the read says); a missing day is a
gap, a contract roll is not a scenario, and with fewer than 250 one-day changes the read
says "not enough history" instead of a number. Mark-to-market is a present value: each
month at the forward FX for its delivery month, discounted to its payment date (the 20th
of the month after) at the reporting currency's overnight benchmark. Volume, basis, shape
and credit exposures need their corresponding reviews.
Use the selected book scope and the firm's reconciled position record for the comparison.

See [Risk and finance](../guides/RISK_AND_FINANCE.md) for controls and review records.
