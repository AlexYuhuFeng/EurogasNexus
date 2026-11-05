# Strategic review, November 2026: an external proposal against the plan

An external review of Eurogas Nexus (a ChatGPT conversation of 4 November 2026, read at
main `8de5aa62`, 0.7.0) proposed where the product should go next. This document checks it
against the project's rules (`AGENTS.md`) and Architecture V2
(`docs/engineering/Architecture-V2/`), says what is best practice and what is not, records
what was verified in the code and fixed, and adds the desk's own view.

## 1. What was proposed

1. **Weather-driven demand.** Keep the audited ridge model; first finish the historical
   evidence (archived ECMWF vintages, demand labels: RFC-0007/0008), map GB weather by LDZ
   (as Xoserve's composite weather variable does), add wind, solar and thermal inertia,
   then benchmark GAM, gradient boosting and autoregressive challengers at a fixed decision
   time (13:00 London, D+1 to D+5) against National Gas's own day-ahead forecast, with
   calibrated intervals and ECMWF ensembles.
2. **Whole platform.** Numerical correctness first (forward-curve weighting and quote
   reconciliation, currency and gap handling in mark-to-market and VaR), then tenor-aware
   risk, storage deliverability and intrinsic/extrinsic value, multi-period optimisation,
   a closed NWE balance, gas-for-power dispatch, regime-aware backtests.
3. **A continuous, adaptive system.** A "market state" (per market, gas day and as-of
   time, separating observed, reported, estimated, forecast, scenario and simulated
   values); forecasting as a lifecycle (versioned forecasts, champion/challenger, drift);
   adaptive data (open data runs everything, licensed data improves it, nothing stops
   without it); forecast-revision attribution; value-of-information studies.
4. **Dual speed.** Trading reacts in minutes, so add an event layer: REMIT, news and price
   moves normalised into events with four timestamps (event, published, received,
   evaluated), a fast path on precomputed sensitivities, "has the market already moved",
   and a hard wall against trading on non-public information.

## 2. Coherence with the plan

| Proposal | Verdict | Why |
|---|---|---|
| Keep FastAPI / React / Tauri / PostgreSQL, no rewrite | Coherent | Rules 4 and 6 |
| Numerical correctness before new models | Coherent, done in part (section 3) | Bounded, deterministic, upstream of every figure |
| Market state as the core | Coherent **as a PostgreSQL read model**, not a service | Architecture V2 Wave 5 (application projections, active context). The map's `/api/portfolio/map-situation` is already a first slice: one read of outages, flows, contracts, cargoes and slots per as-of time |
| Forecast lifecycle, champion/challenger | Coherent | Mirrors what Strategy Lab already does for strategies (versions, frozen runs, shadow runtime). A model registry is a table and a job, not a platform |
| MLflow model registry | **Not without an ADR** | Rule 5: a new datastore/service needs a reviewed ADR and a measured need. PostgreSQL rows plus object storage for artefacts (already in `07_DATA_PLATFORM.md`) cover it |
| "Market Event Bus" | Coherent **only as PostgreSQL** (outbox + the existing job runner, `LISTEN/NOTIFY` for wake-ups) | Rule 5 forbids Kafka/service mesh without an ADR; event volumes here are thousands a day, not millions |
| Adaptive data, graceful degradation | Coherent | Matches the licence register, source center and the rule that a missing figure is shown as missing, never zero. Rule 18 holds: open data must be licensed for commercial use (Open-Meteo's free tier is not; ECMWF open data is CC BY 4.0) |
| Distilling a "student" model from licensed data | Research only | Rule 18: vendor terms often forbid derived models; it needs the customer's licence, case by case |
| Fundamentals to price | Coherent with a caveat | No model output may read as a market price (rule 17). Study balance surprise against price moves; never publish a "forecast price" next to the hub board |
| Event-driven alerts | Coherent | Decision support only (rule 8); nothing changes a position or sends an order |
| Insider-information wall | Coherent and essential | REMIT/MAR: internal operational data (own outages, own nominations) must not drive trading research before publication. Today it is enforced by roles and book scopes; it needs an explicit data classification |
| New workbenches (balance, outlook, revisions, implications) | Coherent **as tasks inside Market**, not new pages | Rule 9; the five primaries stay |
| Seconds-level reaction | Partly out of scope | ACER's IIP refreshes daily; minute-level needs the customer's own REMIT platform feeds and licensed prices. The product is not a news terminal and should not compete with one on latency |

Overall: the proposal is coherent with the plan and mostly best practice. Its two real
risks are architectural (an event bus and a model registry that would bring new
infrastructure) and product focus (section 4).

## 3. Verified in the code, and fixed

Four of the review's concrete code findings were checked and were correct. Fixed on
2026-11-05 with tests:

| Finding | Fix |
|---|---|
| The forward curve weighted months by gas days. A flat-MW product delivers per hour, and the gas days with the summer-time change have 23 and 25 hours | Months now weigh by delivery hours (`gas_day_hours`, 06:00 CET gas day, Europe/Brussels rules). Q1-27 is 744 + 672 + 743 = 2,159 hours |
| A quarter whose months were all quoted was skipped silently, even when the months did not average to it | The strip is repriced, and a difference over 0.5 % is reported ("Q1-27 quoted 37.000 but its months average 40.000") |
| `mark_to_market` and `historical_var` used a rate of 1 for every hub when no FX table was passed, so GBP and EUR could be added | Without FX, valuing hubs in two currencies is refused |
| VaR paired consecutive *available* dates, so a ten-day data gap counted as a one-day move | A pair more than four days apart (a weekend plus a holiday) is not a scenario |

Still open, in order of desk impact:

1. **Tenor-aware risk.** VaR nets a hub across all delivery months; a long winter against
   a short summer looks flat. It needs closes per hub and tenor (front month, quarter,
   season) and the ladder's months mapped onto them.
2. **Netting sets.** Credit exposure nets every leg with a counterparty, as an EFET
   agreement with close-out netting allows. A credit line needs an explicit "netting
   agreement in place" flag (and the legal entity), and sums positive exposures when it
   is off.
3. **Storage deliverability.** Withdrawal and injection rates that depend on inventory
   (ratchets), then intrinsic plus extrinsic value by rolling intrinsic over price
   scenarios.
4. **Demand-forecast evidence** (RFC-0007/0008 to completion, LDZ weights, the 13:00 D-1
   benchmark against National Gas), before any new model family.

## 4. Where the desk's view differs

- **Desk first, research second.** The users are commercial traders, analysts and risk
  staff on Trayport (rule 17). The proposal leans towards a research platform ("market
  intelligence engine"). Each step should answer a question a desk acts on that day: what
  do I nominate, what do I sell where, what is my imbalance, what changed in my book. A
  balance model a trader does not act on is not worth its maintenance.
- **Our edge is not speed, it is "what this means for us".** Montel, ICIS and Bloomberg
  will always report an outage first. What no terminal does is say, within a minute of the
  UMM: this outage is at Easington, where our Langeled contract lands 24,000 MWh/d; the
  site is 11 % down; our NBP-sold volume is exposed by X MWh/d for Y days; the NBP-TTF
  spread moved Z since publication. The pieces exist (REMIT import, sites and roles on the
  map, contracts and flows by site, the daily balance, the curve).
- **Forecast revisions over forecasts.** Agreed with the review: "the 7-day balance
  tightened 500 GWh since yesterday: +260 colder, +140 less wind, +180 Norway, -80 LNG"
  is more useful to a trader than the level. It needs only versioned forecasts, which the
  demand vertical already keeps.
- **Keep a published benchmark in view.** A demand forecast that does not beat National
  Gas's free 13:00 day-ahead forecast at the same decision time has no desk value; that is
  the acceptance test, not MAE in isolation.

## 5. Ideas beyond the review

1. **Book impact of an outage** (the edge above): REMIT event to site to our contracts,
   flows, slots and positions, with MWh/d, days and value at the current spread, by email
   to the desk (the customer's channel), deduplicated by event version. Minutes, using the
   customer's REMIT platform feed; the daily IIP is the fallback.
2. **"Since you last looked" briefing** per person: what moved in prices, the balance
   forecast (with attribution), outages and the book since their last session. One card on
   the Market overview and the morning email, not a new page.
3. **Within-day imbalance projection.** The daily balance plus measured allocations
   through the day gives the expected end-of-day imbalance and the cost of closing it on
   the OCM or within-day versus cash-out, which is the decision a GB trader makes every
   afternoon.
4. **One curve everywhere.** Positions already mark on the curve; LNG bids, storage, route
   netbacks and backtests should read the same versioned curve snapshot, so two screens
   never value one month differently.
5. **Data tier on every figure.** Provenance on demand already names the source; add which
   capability tier (open, customer, licensed) produced a figure and what the next tier
   would add, so "buy this data" becomes a measured decision (the review's
   value-of-information idea, made visible).
6. **Wall view.** Done 2026-11-05: the live map full screen, refreshing, with entry flow
   and regas in progress and an explicit stale state.

## 6. Recommended sequence

Bounded packages, each with its own acceptance test (rule 10):

| # | Package | Accepted when |
|---|---|---|
| 1 | Numerical correctness (done above), then tenor-aware VaR and netting sets | Reference cases: a calendar-spread book shows risk; a line without netting sums positive exposures |
| 2 | Outage-to-book impact, emailed | A replayed UMM for Easington produces the right site, contracts, MWh/d and value within one minute of import |
| 3 | Forecast versions and revision attribution for the NWE balance | Any stored as-of can be replayed; the attribution sums to the change |
| 4 | Demand evidence and the 13:00 D-1 benchmark | Multi-season fixed-origin results against National Gas's forecast, published with intervals |
| 5 | Within-day imbalance projection | Matches a day's allocations replayed hour by hour |
| 6 | Storage deliverability and extrinsic value | Ratchet constraints honoured; rolling intrinsic converges on reference cases |

Each stays decision support: nothing changes a position, nominates or sends an order
(rule 8), and nothing introduces new infrastructure without an ADR (rule 5).
