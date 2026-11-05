# Data, units and calculation basis

[简体中文](DATA_STATUS_AND_PROVENANCE-CN.md) · [Client guide](../guides/README.md)

Use the source, delivery period, unit and timestamp together when comparing a figure or
investigating a difference between systems.

## Identify the observation

| Information | What to check |
| --- | --- |
| Hub, point or book | The same commercial location and population are selected |
| Product and period | WD, DA, weekend, month, quarter, season or calendar delivery period |
| Unit and currency | Price, quantity, rate and reporting-currency conventions |
| Observation time | When the value or delivery period applies |
| Availability/publication time | When that information could have been known |
| Ingestion/read time | When the installation received or read it |
| Source and method | Quoted, assessed, calculated, imported or simulated |

A recent screen refresh can display an older source observation. A working live-push
connection describes delivery between application components; it does not make the
underlying price or physical observation current.

## Interpret status and missing values

| State | Interpretation | Next action |
| --- | --- | --- |
| Fresh | Within the source's configured freshness policy | Check the delivery period and source before comparison |
| Late / stale | Later than the expected refresh or outside its freshness window | Inspect the last successful run and the provider's publication schedule |
| Missing / unavailable | Required evidence is absent or could not be read | Check filters, coverage and the source result |
| Not expected | The source policy does not expect an observation for this period | Check its calendar/cadence |
| Blocked | A calculation's required input or condition is unresolved | Open the named blocker and resolve it |
| Simulated / `_Sim` | A test observation | Keep it in the test context and identify it in any exported example |

An empty successful query, a failed query and a numeric zero are different results.
After a failed read, an earlier displayed record may remain as the last successful reading;
check its timestamp and the failure notice. On a joined flow/capacity board, inspect the
status of both inputs.

## Understand source coverage

| Source type | Example | What it provides |
| --- | --- | --- |
| Public reference data | ECB | Published reference FX; not an executable currency bid/offer |
| Public physical transparency | ENTSOG | Network, flow and capacity observations for the configured scope |
| Keyed transparency data | GIE; ENTSO-E | Storage/LNG or power data with provider-specific setup |
| Licensed market data | Entitled gas quotes/settlements; WMR/BFIX exports | The selected licensed dataset, subject to the firm's permitted use |
| Operator records | Contracts, trade imports, tariffs | Information supplied or maintained for the installation |
| Test data | Simulation sources | Examples and test scenarios |

A catalogue entry identifies a source; it does not establish that its connector is running.
For ENTSOG, absence of an API key requirement does not remove the query-scope and
certification steps. [Source setup](../guides/ADMIN_AND_OPERATIONS.md) explains commissioning.

## Read prices and conversions

NBP prices commonly use **p/th**; continental hub prices commonly use **EUR/MWh**.
**MWh** is energy, **MW** is a rate, and **MWh/d** is a daily energy quantity/rate convention.
A quoted currency amount, an annual percentage rate and a daily cash result are separate
measures.

A hub spread requires a common delivery period, price basis, currency and unit.
For illustration, two comparable mid-prices of EUR 30/MWh and EUR 29/MWh differ by
EUR 1/MWh. This arithmetic example is not a market observation.

Inspect the selected FX source, value date and any averaging window. ECB reference rates,
WM/Reuters fixings and Bloomberg BFIX are different benchmarks.
[FX fixings](../operations/FX_FIXINGS.md) describes their identifiers and import routes.
A volume-weighted reference index, including EEX TTF NGP reference observations, has a
different interpretation from an executable bid/offer.

## Use the gas-day calendar

The current `EU-CAM-UTC-2025` calendar starts the gas day at 06:00 Central European local
time: 05:00 UTC in winter and 04:00 UTC during daylight saving. Clock-change gas days
can contain 23 or 25 delivery hours. Retain the calendar identifier with a dated analysis;
historical records can reference an earlier frozen calendar.

A delivery-day label is not necessarily a midnight-to-midnight UTC period.
Use the displayed period boundaries when reconciling hourly rates or daily volumes.

## Calculation basis

| Result | Basis to inspect |
| --- | --- |
| Monthly curve | Quoted months first; longer products allocate residual value using delivery-hour weights |
| Position marks | Curve method per month; the position view may use a labelled latest-close flat fallback for uncovered months |
| Indicative VaR | Historical price moves on the represented position, with the displayed horizon, confidence and history |
| Resource-pool allocation | Saved resources and sale options, prices/costs, capacity and access constraints; inspect each contract rate and any scenario-default fallback |
| Resource-pool early-cash value | Simple-interest receipt-timing credit using the resource rate/day count and effective payment lags |
| Backtest | Frozen strategy/run identity, data coverage, availability cutoffs and costs |
| Research dataset | Registered features/targets, observation types, forecast vintages and point-in-time availability rules |

Check exceptions alongside totals: unvalued legs, missing FX, flat marks, inconsistent
quotes and excluded observations affect interpretation. Reconcile model scope with the
desk's question rather than treating one risk statistic as a complete risk assessment.

## Resource-pool financing

For each allocation, use the resource's recorded annual financing rate; a missing rate
uses the scenario default. The result identifies the rate and its source.
The early-cash credit per MWh is:

```text
eligible_days = max(upstream_payment_lag_days - effective_sale_cash_lag_days, 0)
base_cost = contract_cost + variable_cost + fuel_loss_cost
early_cash_credit = round(base_cost * (annual_rate_pct / 100) * eligible_days / year_days, 4)
```

The effective sale-cash lag uses the resource override when recorded, otherwise the sale
option's declared lag. Both payment lags must be known. A non-positive timing advantage
produces zero early-cash credit; assess any other funding cash costs separately.

The resource model defaults to simple interest on ACT/365F; explicit resource requests
also support ACT/360. Saved-contract composition currently leaves the day count at the
resource default. Inspect the result's applied rate, source and day count. A recorded
0% rate is distinct from a missing rate.

The [cash valuation reference](../architecture/CASH_VALUATION_CAPABILITY.md) describes the
separate dated cash-flow engine and its adapters.

## Retain evidence

Keep the saved case/run/snapshot identifier, relevant source references, input period,
assumptions, warnings and permitted exports with the desk's review record.
For an unexpected number, use the [support workflow](../guides/SUPPORT_AND_UPDATES.md)
and provide a reproducible comparison on the same basis.
