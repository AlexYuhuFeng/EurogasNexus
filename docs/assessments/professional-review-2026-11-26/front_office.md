# Front-office review: Eurogas Nexus 1.0.0-beta

Reviewers (composite): a prompt/curve trader (TTF/NBP/THE plus locational spreads), an LNG trader/cargo operator, an originator (supply, storage, capacity), a fundamentals analyst, and a power trader looking at extending the product. Each of us has used Trayport Joule, ICE/EEX screens, Endur/Allegro, Kpler, LSEG/Montel/ICIS and the desk's own Python/Excel.

Evidence: newest tree `/home/user/EurogasNexus-merge`. Demo walked as `test_trader` on 2026-11-26 (Today, Prices/ladder, Network, Cargoes, Opportunities, Contracts, Position, Fundamentals, LNG netback, Reports, answer bar). The demo dropped out three times during the walk ("sandbox service disconnected"), so some pages were judged from the existing screenshots in `scratchpad/review/test_trader/`. The account's language is set to Chinese, and I did not change it.

## 1. Verdict

1. As it stands, none of us would use it as our primary screen. Prices, curve and position come from Trayport, the ETRM and our spreadsheets, and here they arrive by CSV import or are simulated.
2. Several of us would adopt it as a second screen for three things no vendor gives us together:
   - "What this outage or flow means for our book": REMIT outages, flows and contracts drawn on one map.
   - A physical gas-day view per hub: the imbalance, the nomination deadline and what happens if we do nothing.
   - Auditable LNG netback and route economics, where every input says where it came from.
3. Analysts would use the fundamentals pages only once there is a year or more of history and weather is added. Today storage history starts on 12 Oct 2026, and there is no weather page.
4. Originators get the least value. Storage, swing and capacity valuation (intrinsic/extrinsic, options) does not exist, and the contract taxonomy itself marks storage and terminal capacity as "deferred".
5. Adoption is blocked by the following:
   - No licensed real-time price connector and no settlement-curve history.
   - Valuation is linear only: no volatility or options.
   - The trader's pages are cluttered with alarms, operations and evidence.
   - The default AI provider is not acceptable to compliance.
   - The demo is unstable.

## 2. Per persona

### 2.1 Prompt/curve trader (TTF/NBP/THE, locational spreads)

**The job in a day:**
- Before 08:00: overnight UMMs, the Norwegian nomination, the weather run, the DA and WE marks.
- During the session: quote and hit WD/DA/BOM/front-month and spreads (TTF–NBP, TTF–THE, Q1/Q2, Win/Sum).
- Watch the book's delta by month and its intraday P&L, and roll at expiry.
- End of day: settlements versus our marks, P&L explain, a note to the desk head.

**What works:**
- The ladder (products down, hubs across, Bid Vol | Bid | Offer | Offer Vol) uses screen names (WD, DA, WE, Q1-27, Cal-27, Sum-27) and native p/th for NBP (`MarketLadder.tsx`, `marketLadderModel.ts`). Real and simulated quotes never compete for best price.
- The hub board: bid/offer, mid, last, change versus the previous close, spread to TTF, ECB FX shown beside it.
- The forward-curve builder is correct where it matters. Months are weighted by delivery hours, the 23/25-hour DST gas days are handled, and the strip is repriced with a 0.5 % tolerance flag (`domain/market/forward_curve.py`).
- On Today, "NBP–TTF Dec-26 +0.304 €/MWh · transport 1.880 · net −1.576 · not profitable" is exactly the one-line arbitrage check a spread trader wants.
- The answer-bar conversion "100 p/th in EUR/MWh" returned 40.7517 €/MWh with the ECB EURGBP 0.8373 rate and its date. That is quick and properly sourced.

**Gaps:**
- Must-have:
  - A direct real-time feed from Trayport/ICE/EEX. Today it is a CSV of the trader's own screen export (`ingestion/licensed_quote_import.py`).
  - A daily settlement curve per hub and product, with history (previous close, a week ago, curve change by month).
    - The demo curve panel says "only one close held: no previous close or week-ago curve to compare".
    - The simulated TTF curve is a perfect sinusoid (screenshot `desk-prices.png`): fine as a mock, useless for testing.
  - Position as delta by tenor bucket in MW (continental) and th/d (NBP), not only MWh per month.
  - P&L explain: new deals versus curve move versus time decay, by hub and month.
  - Tenor-aware VaR. The project's own review says VaR nets a hub across delivery months, so a calendar-spread book looks flat (`docs/product/STRATEGIC_REVIEW_2026-11.md` §3).
- Should-have:
  - Spreads as first-class instruments on the board, with their own bid/offer: TTF–THE, NBP–TTF, Q1/Q2, Win/Sum, DA–WE.
  - Exchange holiday calendars for the DA/WE/BOM roll.
  - Intraday charts from ticks.
  - A BOM row: the ladder showed WD, DA, WE, MA but no BOM.
- Nice:
  - The ladder sorts Jan-27, Q1-27, Cal-27, Feb-27 by start date, mixing months, quarters and years. Screens group them in blocks (months, quarters, seasons, years). This is minor but jars on every glance.
  - NBP volumes (733 to 4,396) carry no visible unit and do not look like th/d clip sizes.

**Redundant or remove:**
- The 6-hub board and the 6-hub ladder show the same prices. Keep the ladder as the default for traders and the board as an option.
- Remove from the trader's view the nomination checklist (seven rows of sent/confirmed/renominated status pickers, a scheduling job) and the 30-row evidence dumps with tariff URLs and contract IDs on Position (`book-position.png`).
- The credit-limit banner ("Rhinmark 458 %/507 %") never goes away. Together with 65–66 open alerts, this teaches the trader to ignore the strip.

**How to organise it:**
- Landing page: ladder plus spread strip plus my delta by month.
- Second tab: Today's physical position per hub, with the scheduling detail on demand.
- Third tab: the map.
- Everything else one Ctrl-K away.

### 2.2 LNG trader / cargo operator

**The job in a day:**
- Decide where to deliver each open or flexible cargo, Europe versus Asia (JKM–TTF less the freight difference), and when to divert.
- Manage the ADP, slot use and berth windows, boil-off, heel and demurrage.
- Hedge the price exposure at loading and at discharge.
- Watch the fleet on Kpler/AIS.

**What works:**
- The cargo chain is rigorous: FOB a×HH+b, voyage days, boil-off, charter, ballast, canal, port, insurance, regas, gas-in-kind, netback by terminal (`domain/lng/cargo_economics.py`).
- A sensitivity table: HH ±0.10, hire ±5k/d, NBP ±1, FX ±1 %.
- Every one of the 10 assumptions is labelled with its class and source.
- "Full cost versus lifting cost" (the sunk fee under a take-or-pay contract) is the right distinction.
- Disruption and demurrage logic exists (`domain/lng/disruption.py`).

**Gaps:**
- Must-have:
  - A second destination basin. Only European terminals are compared (`research-cargo.png`: Thames → NBP, Rotterdam → TTF, Zeebrugge → ZTP). There is no JKM, so no diversion decision, and that is the core LNG arbitrage.
  - Henry Hub forwards. Henry Hub is the EIA spot, used as "an indicative proxy for Dec-26". The landed cost must use the HH forward for the loading month.
  - Freight rate indices (Spark/Baltic, licensed) and canal routing choices (Panama, Suez, Cape) with their days.
  - The fleet board. "Cargoes" was empty ("no cargoes in transit in your book"), and vessel positions come only from a CSV export (`ingestion/lng_positions.py`).
- Should-have:
  - ADP / annual programme views.
  - Slot calendars per terminal with send-out profiles.
  - A diversion "option value" (deliver here versus hold versus divert, with time).
  - Regas tariffs for all EU terminals in the register.
- Nice: a DES/FOB cargo P&L that tracks against its hedge.

**Redundant or remove:** Desk → Cargoes and Research → LNG cargo and netback are two homes for one workflow. Merge them: the cargo row opens its netback.

**How to organise it:** one LNG workspace, laid out as fleet/positions → cargo plan → netback/diversion → hedge.

### 2.3 Originator (supply, storage, capacity)

**The job in a day:**
- Price and structure GSAs: swing (min/max DCQ), take-or-pay, make-up, index formulas (TTF/oil/HH).
- Bid for storage (SBU) and capacity (PRISMA auctions).
- Run tolling and flexibility deals.
- Write credit and approval memos.

**What works:**
- Contract records with GSA, upstream tender (DCQ 136,000–204,000), LNG MSPA/cargo, index terms and payment terms.
- PDF intake by OCR.
- Route/tariff cost from ENTSOG tariffs.
- The storage seasonal-spread and held-capacity opportunities.
- Early-cash value from SONIA/€STR/SOFR.

**Gaps:**
- Must-have:
  - Option valuation. There is no volatility surface, no Black-76/Kirk, and no Monte Carlo or least-squares (LSM) model for swing, storage or spread options. `grep intrinsic|extrinsic` over `src/` finds nothing. The contract taxonomy marks STORAGE_CAPACITY and LNG_TERMINAL_CAPACITY as "deferred" (`docs/product/CONTRACT_TYPES.md` §2).
  - Storage valuation with ratchets.
  - Capacity valuation (spread option on entry/exit).
  - Deal-pricing output: a price build-up (index + shape + swing premium + credit + cost) the originator can quote.
- Should-have:
  - Oil-indexed formulas (Brent 6-0-1, JCC) priced off a forward curve.
  - The PRISMA auction calendar wired into deal screening. `domain/tariffs/auction_calendar.py` exists.
  - Counterparty credit cost (CVA-lite) in the pricing.
- Nice: approval workflow templates. The decision-case review exists and is reusable.

**Redundant or remove:** the "Opportunities" lists for an originator. They are trader-flavoured (sell-down, hedge gap) and show raw codes: "Cannot evaluate: balancing.long_discount not held".

**How to organise it:** a deal workbench of term sheet → valuation → risk/credit → approval pack, reusing Contracts and Review.

### 2.4 Market analyst (fundamentals)

**The job in a day:**
- The morning balance: Norway nominations and UMMs, LNG send-out, storage, demand versus weather normal, power-sector burn.
- Revisions since yesterday.
- A seasonal storage trajectory.
- A note to the desk.

**What works:**
- GIE AGSI storage by country against the 90 % target trajectory.
- NWE supply/demand (11,824 GWh/d, 7-day average).
- LNG send-out with day-on-day change.
- REMIT IIP outages (65 shown, sorted by GWh/d) on a real pipeline map. The basemap is SciGRID_gas, CC BY 4.0, which permits commercial use.
- Every figure carries provenance, and CSV export is everywhere.
- A report builder with sections, an internal/external audience switch and units.

**Gaps:**
- Must-have:
  - History. Storage shows "History from 12 Oct 2026: no complete prior year held", and year-on-year and 5-year comparisons are all "–". AGSI history back to 2011 is free and should be backfilled. This is an operations job, not a feature.
  - Weather. There is no weather tab (the tabs are Storage, LNG, Pipeline flows, Balance, Gas for power). HDD/CDD routes return empty "until a runtime source is ingested" (`api/routes/public/weather.py`).
  - Demand versus normal by country.
- Should-have:
  - Forecast versions with attribution of the revision ("tightened 500 GWh: +260 colder…"). This is already proposed in `STRATEGIC_REVIEW_2026-11.md` §4.
  - Norwegian nominations (Gassco) as a series.
  - An imbalance forecast for NBP within the day.
- Nice: an export to the analyst's notebook. The SDK/MCP exist, and they should be documented as the analyst's path.

**Redundant or remove:** the storage block on the trader's Today page duplicates Fundamentals. Show one line on Today and link to the full view.

### 2.5 Power trader (extension test)

**What exists:**
- `domain/power/gas_for_power.py`: clean spark and dark spreads, the fuel-switch price, residual load.
- ENTSO-E A44 (day-ahead prices), A65 (load) and A75 (generation) parsing with publication-time stamps (`ingestion/entsoe_transparency.py`).
- `GET /api/market/gas-for-power` by bidding zone.

This is a sound analytics seed: it uses the GCV emission factor and refuses missing inputs instead of filling them.

**What power would require:** these are architectural, not page-level.
- Hourly and 15-minute granularity throughout. The gas-day (06:00 CET) is the atomic period across the data model, positions and nominations.
- Power products: base, peak and off-peak blocks, EPEX DA/ID, XBID continuous.
- Cross-border capacity: JAO auctions, flow-based market coupling.
- Licensed EEX power and EUA curves.
- Plant and asset models (tolling and dispatch with ramp and start costs).
- Intraday latency of seconds to minutes.

**Verdict:** keep power as a gas-for-power fundamentals view inside gas research (spark spreads explain gas burn). Do not claim to be a power trading tool without an ADR on time granularity.

## 3. Cross-cutting gaps

| # | Missing | Why a firm needs it | Evidence | Severity | Fix size |
|---|---|---|---|---|---|
| 1 | Real-time licensed price connector (Trayport API, ICE/EEX) | Every downstream figure (P&L, spreads, opportunities, netbacks) is only as good as the price | `ingestion/licensed_quote_import.py` is a CSV of a screen export. The demo board was empty in one load ("No quotes to display. Please import your trading screen") and full of simulated quotes in the next | Blocker | Feature, plus vendor procurement |
| 2 | Settlement-curve history per hub × product × trade date | Day-on-day curve moves, P&L explain, VaR, backtests | Curve panel: "only one close held"; `TRADER_ACCEPTANCE_REVIEW.md` gap 2 | Blocker | Feature (table + ingest) |
| 3 | Volatility and option valuation (swing, storage, spread/capacity) | Originators price optionality, and risk needs vega | No vol/Black-76/LSM code; storage valuation listed as "still open" | Major | Architectural (new domain + data) |
| 4 | Tenor-bucketed delta, P&L explain and tenor-aware VaR | Desk heads and risk ask "where is my risk by month and why did P&L move" | `STRATEGIC_REVIEW_2026-11.md` §3; `book-position.png` shows MWh per month only | Major | Feature |
| 5 | Global LNG (JKM, HH forwards, freight indices, Asian destinations) | Diversion is the LNG desk's main decision | `research-cargo.png` (EU terminals only, HH spot proxy) | Major | Feature, with licensed data |
| 6 | Weather plus a full history backfill | Fundamentals without weather and year-on-year are not analysis | Fundamentals tabs; "no complete prior year held"; weather routes empty | Major | Config/ops (backfill) plus feature (weather source) |
| 7 | Alarm hygiene | 65–66 open alerts and a permanent 458–507 % credit breach banner on the trader's strip cause alert fatigue, so a real UMM gets missed | Every screenshot header | Major | Config (thresholds, routing to risk) |
| 8 | Raw codes and evidence dumps on trader pages | They break the product's own rule 3 ("plain desk language") | Opportunities: "Cannot evaluate: balancing.long_discount not held" / "ESTR fixing … is stale"; Position: 30-line evidence with contract IDs and ENTSOG URLs | Minor | Feature (UI) |
| 9 | Data model in GBP | A continental desk reports in EUR; the GBP pin leaks into data and API contracts | `normalized_view.py:49 TARGET_CURRENCY = "GBP"`; `contract_price_gbp_mwh` column | Major | Architectural (ADR + migration) |
| 10 | AI provider default | Sending book, positions and limits to a third-party LLM (DeepSeek today) breaches most trading houses' MAR/inside-information and data-residency policies | `docs/product/AI_ASSISTANCE.md` ("DeepSeek today"), `src/eurogas_nexus/llm/deepseek.py` | Blocker for the AI features | Config (self-hosted or EU-hosted endpoint) plus a compliance sign-off |
| 11 | The answer bar does not find instruments or desk questions | "TTF Q1-27", "NBP TTF spread", "Norway outage", "my NBP position" and "JKM" all returned "no matching commands" in the walk, though the guide promises price, outage and position lookups | `docs/user/ANSWER_BAR.md` §2 versus demo | Major | Feature (parser coverage, tenor and spread grammar, synonyms) |
| 12 | Alerting into the desk's channels (Teams, email, Bloomberg/Symphony chat) | Traders do not sit in a browser tab | `NotificationChannelsPanel.tsx` exists; Teams/SMTP barely referenced in the backend | Should-have | Feature |
| 13 | Demo/operational stability | Three disconnects in 30 minutes would end a pilot on day one | Walk logs | Blocker for a pilot | Operations |

## 4. Structural limits

- **Integration by file, not by API.** Prices, ETRM trades, vessel positions and contracts all arrive as CSV/PDF imports.
  - Fine for a pilot.
  - For production it means minutes-to-hours latency, reconciliation breaks and no intraday.
  - The ETRM stays the book of record, which is correct, but the integration needs real adapters (Endur/Allegro APIs or the ETRM's message bus) with reconciliation counts.
- **The gas day is the atomic period.** This is excellent for gas operations (the 23/25-hour DST days are right). It is the wrong foundation for power (hourly/15-minute) and for intraday gas trading in hourly blocks. Extending to power is a data-model change.
- **Linear valuation only.** Flat quantity × price, MTM against the curve. Optionality, swing, storage and capacity need a stochastic layer: vol surfaces, correlation, simulation run as jobs off the request path. That is a new domain and data family, not a page.
- **Data licensing determines value.** The rules are right: no non-commercial feeds, customer entitlement for licensed data. But the free tier (ENTSOG, AGSI, ALSI, IIP, ENTSO-E, EIA, ECB, National Gas) covers fundamentals and nothing priced. Without the customer's Trayport/ICE/EEX/Kpler/Spark entitlements, the commercial features show simulated or empty figures. The product's value is therefore conditional on procurement.
- **Latency posture.** Polling every 10 s with SSE behind it. Daily IIP refresh for REMIT unless the customer wires its own platform feeds. This is acceptable for decision support and not competitive with Montel/ICIS/Bloomberg for news. The edge must stay at "what this means for our book".
- **Scope creep against focus.** Strategy Lab, backtests, shadow runtime, agent research, MCP, glossary wiki, a reporting engine and an admin/governance estate sit beside the desk tools. For front office, the core (ladder, physical day, map, netback) is thinner than the periphery. Every page a trader does not use costs maintenance and attention.
- **Compliance boundary.** Mixing the firm's own operational data (own outages, nominations) with research and AI needs an explicit inside-information classification (MAR Art. 7 / REMIT Art. 3). The project's own review notes it is enforced only by roles today.

## 5. Where it sits beside the incumbents

- **Complements:**
  - Trayport/ICE screens (it reads their prices and never trades).
  - The ETRM (it reads trades and gives the desk a faster, physical, map-based view of the same book).
  - Kpler (it adds the firm's own economics to vessel positions).
  - Montel/ICIS (it turns their headline into book impact).
- **Replaces:**
  - The desk's Excel netback and route-cost sheets.
  - The morning storage/LNG/flows dashboard built on public data.
  - The hand-written morning note (via the report builder).
- **Pointless duplication:** a forward-curve view without settlement history duplicates the Trayport/EEX screen and adds nothing. Charting simulated ticks has no value. A news panel will lose to any terminal.

## 6. Top 10 changes, in priority order

1. **Licensed price and settlement-curve layer.** A Trayport/ICE/EEX connector under the customer's entitlement, a stored daily settlement curve per hub × product × trade date, and prior-close comparisons everywhere. Until then, label the build "pilot".
2. **Stabilise the demo and pilot environment, and cut the noise.** Default alert thresholds per role, the credit breach routed to risk (not the trader's strip), and alerts acknowledged before they reach a trader.
3. **Book risk by tenor.** Delta by month, quarter, season and year in MW and th/d; P&L explain (new trades / curve move / roll); tenor-aware VaR.
4. **AI to a self-hosted or EU-resident model** by configuration, with a written MAR/REMIT data classification. Until then AI stays off for book data.
5. **Fundamentals history and weather.** Backfill AGSI/ALSI/ENTSOG from 2015, add HDD/CDD versus normal (ECMWF open data, CC BY 4.0), and add forecast versions with revision attribution.
6. **Global LNG.** JKM and HH forwards, freight indices, Asian/Atlantic destinations, canal choices, a diversion table; merge Desk → Cargoes with Research → LNG netback.
7. **Spreads as instruments.** TTF–NBP, TTF–THE, DA–WE, Q1/Q2, Win/Sum with bid/offer from leg quotes, history and the transport-cost net already shown on Today.
8. **Answer bar coverage.** Products ("TTF Q1-27"), spreads ("NBP-TTF Sum-27"), outages by area, positions and synonyms; it must never return "no matching commands" for a hub plus tenor.
9. **Optionality engine** (an ADR first): vol surface per hub, storage intrinsic plus rolling-intrinsic/extrinsic with ratchets, swing (LSM), capacity as a spread option. This is the originator's must-have.
10. **Trader page hygiene.** Move nomination status pickers to an operations/scheduler view, keep evidence behind disclosures (Position), turn raw evaluator codes into sentences, and group ladder rows into months / quarters / seasons / years with a BOM row.

Power: keep gas-for-power and spark spreads as fundamentals, and record an ADR stating that power trading needs a sub-daily period model before any power desk feature is built.
