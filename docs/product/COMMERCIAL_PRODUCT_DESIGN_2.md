# Eurogas Nexus — Commercial product design basis 2 ("Opportunities first")

Status: Accepted; decisions L1–L7 taken as recommended. Supersedes `docs/product/ROLE_FIRST_REDESIGN.md` where they conflict (sections 3.2 Today/Prices, 3.3 Deals, 3.5 Research, WP-07/09/13/14/15/17/18); the role registry, the situational strip, the device strategy, the information rules I1–I14 and WP-01…06, 08, 10–12, 16, 19, 20 stand. Suggested location: `docs/product/COMMERCIAL_PRODUCT_DESIGN_2.md`.

Basis: branch `integrate` at `0e75b43`, read from source and docs. I did not run the application or fetch any external source. Every tariff, rate, price and distance in the worked examples is **illustrative** (chosen to be realistic, not read from a publication); every statement about an operator's publication practice that is not already encoded in the repository is marked "to verify" and must pass the AGENTS rule 18 terms check (`docs/legal/`) before ingestion.

## 0. What the code says that drives this design

| Finding | Evidence | Consequence |
|---|---|---|
| Deals → Evaluate is a result viewer with no way to state a question. It shows route rows, four tiles formatted with a hard-coded `GBP …/MWh`, one editable financing rate and blocker codes. | `clients/web/src/components/ScenarioWorkspace.tsx` (`moneyPerMwh`, `SCENARIO_EDITABLE_DRAFT_INPUTS`, `net_margin_gbp_mwh`) | The owner's "I have no idea what this is" is structural, not a copy problem. The page is removed; its engines become the workbench behind an opportunity. Currency baked into field names must go. |
| The only user-facing JSON uploads are the desk replay and the contract import. | `components/decision/DeskReplayPanel.tsx` line 94 (`accept="application/json,.json"`, heading key `desk_replay.how` = "What this needs"); `components/ContractWorkbench.tsx` line 352 (`.pdf,.json,.txt`) | Desk replay leaves the commercial UI. Contract import keeps PDF only in the UI. |
| An opportunity engine already exists, for intraday hub spreads only, with three states (`ACTIONABLE_REVIEW`, `WATCH`, `BLOCKED`), executable quote sides, fail-closed access. | `src/eurogas_nexus/domain/market_intelligence/opportunity_engine.py` | The state model and fail-closed discipline are kept and generalised; this is an extension, not a new idea. |
| Route pricing walks proven adjacency and prices exit, pipeline and entry legs from the tariff register; a missing tariff is "missing", never zero. | `domain/route_cost/market_area_graph.py`, `route_adjacency.py`, `ingestion/entsog_tariffs.py` (`per_mwh_at_full_load`) | Locational opportunities can be computed honestly today. |
| Regulated terminal tariffs are already parsed for Fluxys LNG (Zeebrugge), Elengy (Montoir, Fos Cavaou, Fos Tonkin) and DET auctions, with URL and SHA-256. The firm's terms sit in one row per terminal. | `ingestion/lng_terminal_tariffs.py`; `db/models/risk_controls.py` (`LngTerminalTermsRecord`); `api/routes/public/risk.py` (`/api/portfolio/lng-terminal-terms`, `/api/portfolio/lng-cargo-bid`) | The cargo model has a real foundation. Missing: versioned public register separate from the firm's terms, more operators, freight, FOB, origin comparison. |
| The cargo bid sheet prices DES only: boil-off and charter apply to "extra sailing days versus the reference terminal"; there is no origin, no voyage, no FOB. | `domain/portfolio/lng_bid.py` (`_bid`, `extra_sailing_days`) | Cannot answer the owner's US FOB question. Section C adds the upstream half and reuses this for the downstream half. |
| The LNG economics sandbox is EUR-only, converts nothing and takes every number as text. | `domain/research/lng_cargo_economics.py` ("EUR-only initial scope; no FX conversion"), `components/LngEconomicsPanel.tsx` (1,189 lines) | Removed from the UI. |
| Henry Hub is the daily spot series only. | `ingestion/eia.py` (`HENRY_HUB_SPOT_SERIES = "RNGWHHD"`) | No HH forward is held. Section C states what fills it. |
| Spread analysis refuses legs in different units; the leg catalogue is a flat list of every (hub, tenor, source). | `api/routes/public/spread_lab.py` line 177 ("legs are quoted in different units"), `list_spread_series` | Exactly the owner's two Research complaints. Fixed by normalisation and a hierarchical catalogue (section D). |
| Units have one authority and FX is always explicit; ECB fixings and SONIA/€STR/SOFR fixings are modelled. | `domain/ontology/quantity.py`, `domain/market/units.py` (`convert_price`), `domain/market/fx_fixings.py`, `domain/market/interest_rates.py` | Forward FX by covered-interest parity needs no new data. |
| Two chart systems: the `Chart` primitive (uPlot; table and CSV built in) and a hand-rolled SVG `StrategyLineChart` with a categorical axis and only first/last labels. | `components/ui/charts/Chart.tsx`; `components/strategy/StrategyLabCharts.tsx` | One chart system. |
| "NBP–TTF spread by delivery month" is drawn as bars; the storage chart is 120 days against one prior year, NW Europe only. | `components/PriceCharts.tsx` (`style: "bar"`), `components/TodayScreen.tsx` (`StorageSeasonChart`), `application/desk_today.py` (`STORAGE_CHART_DAYS = 120`) | Section E and F replace both. |
| The report standard says the platform holds about 14 months of history. | `docs/product/REPORT_EDITORIAL_STANDARD.md` ("the platform holds about 14 months") | A five-year band needs a storage history backfill first (GIE AGSI publishes history back to 2011; to verify in the connector). |
| The filter strip (gas day, delivery product, hub) is mounted on every Desk task inside the context strip. | `components/MarketCockpit.tsx` (`MarketContextStrip` with `tradingContextControlsFor`), `components/TradingContextControls.tsx` | Removed from Today (section E). |
| Network takes about forty props of pool, route and strategy results. | `components/MarketCockpit.tsx` → `NetworkWorkspace` | Client-side composition of commercial results; replaced by server-assembled reads (section J). |

---

## A. Verdict from first principles

### A.1 The test
A commercial gas desk makes six kinds of decision. A feature stays only if it changes one of them and its number can be checked against the screen or a published document. A feature that exists to show a capability is removed.

### A.2 What the product must do superbly (seven jobs)

| # | Job | Decision it serves | Where | What "superb" means |
|---|---|---|---|---|
| 1 | Tell me what changed and whether it touches us | Trade, cover or wait | Desk → Today, the strip | One read; prices at my hubs, my position, events sized against my book; nothing I must configure. |
| 2 | Show the curve and the spreads in comparable terms | Which product, which side | Desk → Prices | Native quotes; every spread in one stated unit with forward FX; term structure readable. |
| 3 | Show the physical system on the map with my book on it | Where the constraint is, what it touches | Desk → Network (**the map stays**) | Outages, flows, capacity, and my contracts, cargoes and the hubs my deals could reach. |
| 4 | Find what I could do with my book, and prove the arithmetic | Move gas, store, re-route, sell down, land a cargo, hedge | Deals → Opportunities | Ranked claims with legs, tariffs, FX, units, as-of, assumptions, checks; one click to adjust; one click to a case. |
| 5 | Price a cargo across origins, terms and terminals | Bid, lift, divert, choose a terminal | Opportunity workbench (cargo) and Research → Cargo & netback | FOB → freight → DES → regas → entry → hub, each input sourced or marked as an assumption. |
| 6 | Keep the book, limits and decisions honest | Size, approve, evidence | Book (as in basis 1), Deals → Contracts, Deals → Review | Contracts in; position, limits and credit out; four-eyes decisions. |
| 7 | Let an analyst answer a market question fast and publish it | View, brief, report | Research (Spreads, Fundamentals, Cargo & netback, Reports), Ask | Normalised series, history bands, export, reports from the same facts. |

### A.3 What is removed (summary; full list in section I)
- Deals → **Evaluate**, **Optimise**, **Routes & netback** as pages. Their engines survive behind the opportunity workbench.
- Research → **Strategies** (Design, Backtest, Compare, Shadow), **Data** (dataset builder, feature and target registries, catalogues), **Assistant** (agents workspace).
- Desk → Today filter strip; Desk → Prices converter, product strip, storage trajectory, NBP–TTF bar chart.
- LNG economics sandbox, desk replay upload, capacity billing calculator as a standing panel, financing rate helper as a panel.
- Every catalogue, registry and plumbing strip on commercial pages (already decided in basis 1; now deleted rather than folded).

### A.4 Navigation after the change (17 tasks → 11)

| Mode | Tasks | Change |
|---|---|---|
| Desk | Today · Prices · Network | Unchanged set. |
| Deals | **Opportunities** · Contracts · Review | 5 → 3. |
| Book | Position · Limits · Delivery · Planning | As basis 1 (Nominations + Storage merged). |
| Research | **Spreads** · **Fundamentals** · **Cargo & netback** · Reports | Strategies, Data, Assistant removed. |

Ask (the answer bar, `clients/web/src/app/answer/*`, `POST /api/analysis/ask`) is the narrative layer everywhere, not a page. With three or four tasks per mode, the "More" overflow of basis 1 (D6) is no longer needed for most roles.

---

## B. Deals: opportunities, not tools

### B.1 Answer to the owner's question
Traders do not open an optimiser and then look for a question. They hold a book and ask "what should I do with it today". So the product evaluates continuously and advises; the tools become what you open **from** an opportunity to check and adjust it. An opportunity is a claim for human review. It is never an order, a nomination or an instruction (AGENTS rule 8).

### B.2 The opportunity object

| Part | Content | Rule |
|---|---|---|
| Claim | One sentence built from fields: "Move 10,000 MWh/d TTF → THE in Jan-27: +0.23 EUR/MWh after exit and entry, EUR 71,300." | Template per type; never model-written. |
| Arithmetic | Ordered legs: each a row with label, quantity, price or rate, unit, currency, source, as-of, and the running subtotal. FX and unit conversions are their own rows. | The rows must sum to the headline; a unit test per type checks it. |
| Assumptions | Each assumption with its value, who set it (public source, firm's assumption set, this user), and its date. | An assumption is never shown as data. |
| Falsifiers | What would make it untrue, as testable statements: "spread below 0.97 EUR/MWh", "no firm capacity at Oude Statenzijl for Jan-27", "THE entry tariff for 2027 published higher". | At least one per opportunity. |
| Sensitivity | Breakeven on the main driver; value change per unit move of the two largest drivers; value at the low and high of each assumption's stated range. | Computed, not narrated. |
| Checks | Capacity (available at each point; capacity we hold), limit (mandate headroom after the action), credit (counterparty line, where a counterparty is implied), physical (open outages on the path), contract (flexibility actually allows it). Each: pass, fail, not assessed, with the figure. | "Not assessed" is a state, never a pass. |
| Data quality | Per input: **sourced** (licensed or public, named), **firm's mark** (entered by the customer), **indicative** (settlement or mid, not executable), **derived** (computed, method named), **assumption**, **simulated**, **missing**. Overall grade = the weakest input on the value path. | Drives state and ranking (B.5). |
| Timing | Valid from evaluation until expiry (product expiry, booking deadline, gas day end, tariff period end). | Expired opportunities leave the list. |
| Next step | "Open as a case" (creates a decision case with the frozen arithmetic as evidence), "Adjust" (workbench), "Dismiss" (with a reason; hides this key for this user until it materially changes), "Watch". | No other action exists. |

### B.3 Opportunity types

| Type | Claim | Inputs | Core formula (per MWh unless stated) | Feasible today? |
|---|---|---|---|---|
| **L · Locational spread** | Buy at hub A, sell at hub B, same delivery period, along a proven path | Marks or quotes at A and B; path from `MarketAreaGraph`; exit, pipeline, entry tariffs for the period and capacity product; fuel/shrinkage where published; FX forward if currencies differ | `net = P_B·fx − P_A − Σ tariff_leg·m(product) − fuel% · P_A − cost_of_carry` | **Yes**, with prices the customer is entitled to or its own marks; tariffs from the `entsog-tariffs` source. Without prices: blocked, says which mark is missing. |
| **C · Unused capacity** | Capacity we hold on A→B is worth more than leaving it idle | As L, but tariff for held capacity is sunk; only variable charges count | `net = P_B·fx − P_A − variable charges` | **Yes** where the capacity book (`CapacityContractBook`, `/api/…capacity contracts`) holds bookings. |
| **T · Time spread vs storage** | Inject in period 1, withdraw in period 2 | Curve months; storage we hold (capacity, injection and withdrawal rates, variable fees, fuel); financing rate; entry/exit to storage | `net = P_2·DF − P_1 − inj − wd − fuel%·P_1 − P_1·r·Δt` (capacity fee sunk if held, else added) | **Yes for held storage** entered in the book. For storage not held: indicative only, with a user-entered or published storage tariff. Rate-dependent limits (ratchets) are not modelled (open item 3 of `STRATEGIC_REVIEW_2026-11.md`): the check reads "not assessed". |
| **R · Re-route a flexible volume** | Deliver contract volume X at point B instead of A | Contract flexibility (delivery-point options, swing), sale options, route costs | The resource-pool optimiser (`domain/route_cost/resource_pool.py`) run with and without the alternative; `Δ margin` | **Yes** where contracts carry the flexibility fields. This is what Optimise becomes. |
| **S · Sell down vs hold** | Residual at hub H on gas day D: sell DA or within-day rather than cash out | Daily balance residual, DA price, the desk's short premium and long discount | `value = residual · (P_DA − cashout_price)`; split from `domain/portfolio/sell_down.py` | **Yes** (`/api/portfolio/daily-balance`). |
| **G · Hedge gap vs policy** | Cover for contract K in month M is outside its approved band | Hedge bands (`DealHedgeApprovalsPanel`), cover by month | `gap = band_edge − cover%`, volume = gap · exposure | **Yes, needs no market data.** Ranked in the "must act" lane. |
| **D · LNG terminal choice / diversion** | Cargo is worth more at terminal X than at the planned terminal | Section C | Section C | **Yes for regulated terminals with ingested tariffs** (Zeebrugge, Montoir, Fos). Others need the firm's terms. Diversion needs freight: the firm's assumption or a licensed assessment. |
| **A · Origin arbitrage (FOB lift)** | A US FOB cargo landed in NW Europe clears the hub by X | Section C | Section C | **Partly**: HH spot is held; HH forward, freight and FOB markers need an entitlement or assumptions (C.3). Shown as "indicative" until then. |
| **E · Event exposure** | Outage at point P reduces our supply by X MWh/d for N days; cover costs Y | REMIT event, site → contracts (`application/map_situation.py`), balance, curve | `exposure = affected MWh/d · days · (P_cover − P_contract)` | **Yes**; this is idea 1 of the strategic review. Appears on the strip as urgent and in the list as "must act". |

Not built now (need data the product does not hold or models not validated): storage extrinsic value, swing option value, weather-driven directional calls, cross-commodity (spark spread) trades. A fundamentals model output is never turned into a price opportunity (rule 17).

### B.4 Worked examples (illustrative figures)

**L · TTF → THE, Jan-27, 10,000 MWh/d**

| Leg | Value | Unit | Source class |
|---|---|---|---|
| Sell THE Jan-27 | 31.20 | EUR/MWh | sourced (customer's licensed quotes), bid side |
| Buy TTF Jan-27 | −30.00 | EUR/MWh | sourced, offer side |
| Gross spread | 1.20 | EUR/MWh | |
| Exit NL at Oude Statenzijl, monthly firm: 0.0101 EUR/(kWh/h)/d ÷ 24 × 1000 | −0.421 | EUR/MWh | sourced (ENTSOG tariff, gas year 2026/27), full load |
| Entry THE at the same point: 0.0132 EUR/(kWh/h)/d ÷ 24 × 1000 | −0.550 | EUR/MWh | sourced |
| **Net** | **0.229** | EUR/MWh | |
| Volume 10,000 × 31 days | 310,000 | MWh | |
| **Value** | **EUR 71,000** | | |

Breakeven spread 0.971 EUR/MWh. Sensitivity: ±0.10 EUR/MWh on the spread = ±EUR 31,000. Falsifiers: spread below 0.97; no firm monthly capacity offered at the point; load factor below 100 % (at 80 % the tariff per MWh rises to 1.214 and the net is −0.01). Checks: capacity available 38 GWh/d (pass); mandate headroom after +310 GWh at THE (pass, 61 % used); outage on path (none). State: actionable for review.

The load-factor falsifier is not decoration: capacity is paid on booked kWh/h whether it flows or not, so the default assumption (100 % load, the conversion in `per_mwh_at_full_load`) must be shown and adjustable.

**T · Summer-27 into Winter-27, storage not held (indicative)**

Win-27 31.50 − Sum-27 28.00 = 3.50 gross. Less capacity 2.20 (user-entered), injection and withdrawal 0.35, fuel 1 % × 28.00 = 0.28, financing 28.00 × 3.0 % × 0.5 y = 0.42, storage entry/exit 0.20 → costs 3.45, **net 0.05 EUR/MWh**. Below the minimum margin (B.6): state "watch", not listed among actionable. This is the false-positive control doing its job.

**G · Hedge gap**: contract "Norsk-2027", Q1-27, cover 42 % against an approved band of 60–80 %: gap 18 points = 54,000 MWh. No margin; the claim is "below the approved band by 54,000 MWh; band approved 12 Sep by the risk committee". Next step: open a case.

### B.5 States and ranking

States (the existing three, with their meaning made visible):

| State | Condition | Shown as |
|---|---|---|
| Actionable for review | Net margin ≥ threshold, every value-path input sourced or firm's mark and fresh, no failed check | Main list |
| Watch | Complete inputs but margin under threshold; or one value-path input indicative, derived beyond its tolerance or an assumption; or a check "not assessed" | Folded group "Watching (n)" |
| Blocked | A value-path input missing, a check failed, or path not proven | Folded group "Cannot evaluate (n)" with the single missing thing and its fix |

Two lanes, never mixed:
1. **Must act** (obligation or risk): G, E, S near gas-day end, expiring booking deadlines. Ordered by time to deadline, then size.
2. **Could act** (margin): L, C, T, R, D, A. Ordered by `score = value_in_reporting_currency × quality_weight × persistence_weight`, ties by earliest expiry.

| Factor | Values (proposed defaults; organisation settings) |
|---|---|
| quality_weight | all sourced/firm's mark 1.0; one indicative 0.6; any assumption on the value path 0.4; simulated: ranked only among simulated |
| persistence_weight | seen in 1 evaluation 0.5; 2 consecutive 1.0 |
| value | net margin × executable volume, where executable volume = min(position or flexibility available, capacity available, limit headroom, quote depth when known) |

The list shows at most 7 per lane; the rest are counted. The ranking reason is one line on each row ("ranked 2nd: EUR 71k, all inputs sourced, expires in 9 days").

### B.6 False-positive control

| Control | Rule (default) |
|---|---|
| Minimum margin after costs | `max(0.10 EUR/MWh, half bid–offer of both legs when quotes are held, 10 % of total route cost)` |
| Minimum value | EUR 10,000 (organisation setting) |
| Executable sides | With quotes: buy at offer, sell at bid (as the existing engine does). With settlements or marks only: input class "indicative", state at most "watch" unless the firm's setting accepts marks as actionable. |
| Staleness | DA/within-day price: same gas day. Forward: last settlement no older than 1 business day. FX and rates: 1 business day. Tariff: must be in force for the delivery period; an "indicative" publication downgrades to "watch". Outage and capacity: within 60 minutes when a live feed is connected, else the publication day, stated. Terminal tariff: in force for the arrival month. |
| Persistence | New only after two consecutive evaluations; removed after two consecutive failures (hysteresis). |
| Deduplication | Key = (type, legs, delivery period, book). A material change (value ±20 % or state change) updates the same record with a version. |
| Simulated inputs | A simulated price is never mixed into a real opportunity. On the demo desk every opportunity carries the simulated mark and the banner; on a real desk simulated-only opportunities are not produced. |
| Unproven path | No direct pricing between market areas without a crossing (existing rule in `route_adjacency.py`). |
| Suppression | A dismissed key stays hidden for that user until a material change. Dismissal reasons are counted per type and reported monthly to tune thresholds. |
| Precision feedback | Each opportunity opened as a case and its case outcome is the measure: precision per type = accepted ÷ opened. Shown in Admin, not on the desk. |

### B.7 The page

**Deals → Opportunities, desktop, populated**

```
Opportunities                          as of 09:42 · next evaluation on new data      [New evaluation ▾]
-----------------------------------------------------------------------------------------------------
MUST ACT (2)
 ! Hedge below band · Norsk-2027 · Q1-27     −54,000 MWh vs 60–80 %        due: committee 20 Nov   >
 ! Outage · Easington · our supply −24,000 MWh/d × 3 d   cover cost ~EUR 86k   since 07:10          >
COULD ACT (4)
 1 TTF → THE · Jan-27 · 10,000 MWh/d     +0.23 EUR/MWh   EUR 71k   sourced      expires 9 d        >
 2 Zeebrugge instead of Montoir · cargo LNG-114 · Dec    +0.41 EUR/MWh  EUR 448k  1 assumption      >
 ...
Watching (5) ▸        Cannot evaluate (3) ▸
```

Selecting a row opens the detail beside the list (sheet on phone): claim, arithmetic table, assumptions, falsifiers, sensitivity, checks, data quality, map thumbnail of the path ("Show on map" opens Network with the path selected), and the three actions. One primary action: **Open as a case**.

**Adjust = the workbench.** A side panel with the same arithmetic made editable: volume, period, capacity product (day, month, quarter, year), load factor, the route's crossing (when several proven paths exist), assumption values, the sale or purchase side. Every edit recomputes server-side and shows the delta against the system's version. "Save as my evaluation" stores a user evaluation linked to the opportunity. This is where the existing engines run:

| Existing engine | Becomes |
|---|---|
| Route cost what-if (`RouteCostWhatIfPanel`, `domain/route_cost/route_cost_service.py`) | Workbench for L and C |
| Resource pool and route optimiser (`resource_pool.py`, `route_optimizer.py`) | Workbench for R; the optimiser's allocation is the opportunity's arithmetic, binding constraints stated as sentences |
| Cargo bid sheet (`domain/portfolio/lng_bid.py`) | Downstream half of the workbench for D and A |
| Sell-down (`domain/portfolio/sell_down.py`) | Workbench for S (also on Book → Delivery) |
| Capacity billing (`domain/research/capacity_billing.py`) | A disclosure inside the tariff leg ("how this tariff becomes EUR/MWh") |
| Financing (`domain/economics/financing.py`) | The financing row of T and of cargo cash timing |

**New evaluation** (the only entry that does not start from a system opportunity): a menu of four typed forms — Location spread, Storage / time spread, Cargo, Portfolio allocation. Each form has at most six required fields with defaults from the book and context, an example button ("Fill with the demo example"), and produces the same opportunity object marked "your evaluation". No JSON anywhere.

**Empty on day one** (no book, no prices):

```
Opportunities
Nothing can be evaluated yet. The product looks for ways to earn or save money with your book.
It needs three things:
 1 Your book        0 contracts, 0 positions      [Add a contract]  [Import trades from the ETRM]
 2 Prices           no licensed quotes or marks   [Enter marks]  (administrator: connect a price feed)
 3 Published costs  transport tariffs: 412 held · terminal tariffs: 4 terminals     ready
What it will find: location spreads net of tariffs · storage spreads · re-routing · sell-down ·
terminal choice for cargoes · hedge gaps.                      [See it working on the demo desk]
```

Each line turns into a tick as it is satisfied; with the book but no prices the hedge-gap and event-exposure types already work and appear. "Enter marks" opens a small grid (hub × month, native unit) stored as the firm's marks, class "firm's mark".

### B.8 What happens to today's Deals tasks

| Today | Verdict | Detail |
|---|---|---|
| Evaluate (`ScenarioWorkspace.tsx`, the scenario branch of `DecisionWorkspace.tsx`) | **Remove** | Replaced by Opportunities and the workbench. `task=scenario` redirects to Opportunities. |
| Optimise (optimise branch of `DecisionWorkspace.tsx`) | **Remove as a page**; engine kept | Type R; "Portfolio allocation" under New evaluation. `task=optimize` redirects. |
| Routes & netback (routes branch of `PortfolioWorkspace.tsx`: `RouteCostWhatIfPanel`, `CapacityBillingPanel`, `LngCargoBidPanel`, `TariffPublicationsPanel`) | **Remove as a page** | Route what-if and cargo bid become workbench forms. Tariff publications move to Admin → Connectors (coverage) and to the Inspector of a tariff leg. Capacity billing becomes the tariff-leg disclosure. |
| Contracts (`ContractWorkbench.tsx` etc.) | **Keep**, slim as basis 1 | The source of the book. PDF intake stays; JSON and text import leave the UI. `FinancingRateHelper` leaves; `LngEconomicsPanel` is deleted. Capacity bookings and storage held are entered here (a contract kind), because the engine reads them. |
| Review (`DecisionCasePanel`, `DecisionPackPanel`, `ReviewWorkspace`) | **Keep** | Receives cases opened from opportunities with the frozen arithmetic as evidence. `DayBoardPanel` goes to Book → Planning only. |

Resulting tasks: **Opportunities · Contracts · Review**. Registry changes: originator lands on Opportunities (cargo types first); trader's place 3 becomes Deals → Opportunities; risk and desk head keep Review.

---

## C. LNG cargo economics

### C.1 The chain, one model for every origin and delivery term

All per-unit results are per MMBtu **delivered at the ship's rail at discharge** unless stated; the model computes in energy and money totals and divides at the end, so denominators are never mixed (the existing rule in `lng_cargo_economics.py`).

```
Q_load                         energy loaded (MMBtu)
Q_del  = Q_load × (1 − bor_laden × d_laden) − heel_delta          delivered at discharge
FOB cost  = P_FOB × Q_load                                        (FOB purchase), or
            (a × HH_month + b) × Q_load                           (HH-linked formula)
Freight   = hire × (d_laden + d_ballast + d_port)                 charter
          + fuel_ballast × d_ballast × P_fuel                     fuel not covered by boil-off
          + canal + port_load + port_discharge
          + insurance% × cargo value
DES-equivalent cost = (FOB cost + Freight) / Q_del
Regas side (existing lng_bid arithmetic, per MWh unloaded):
  sent_out = Q_del × (1 − gas_in_kind%)
  netback at ship's rail = [ sent_out × (P_hub(arrival month) − entry_tariff)
                             − regas charge(cargo, product) − other ] / Q_del
Margin = netback at ship's rail − DES-equivalent cost
```

A DES cargo skips the first half: its cost is the DES price. A FOB cargo with our own shipping uses the full chain. A cargo "already near the Netherlands" is a DES or ex-ship offer with `d_laden` of one or two days. All three land in the same comparison table because all three end as **margin against the hub at the arrival month**, per MMBtu delivered and in total.

### C.2 Each input

| Input | Definition | Open source the product can ingest (rule 18 check each) | Licensed, via the customer's entitlement | Default when missing | How shown |
|---|---|---|---|---|---|
| HH price, loading month | NYMEX HH futures for the pricing month of the SPA (usually the month of loading; final settlement) | EIA Henry Hub spot (`RNGWHHD`, held). EIA also publishes futures contracts 1–4 as daily series (`RNGC1`–`RNGC4`; **to verify** series and terms) | NYMEX/CME settlements through the customer's vendor | Spot used as a flat proxy: class "indicative", state at most "watch" | "HH Dec-26 3.50 USD/MMBtu · EIA futures contract 1" or "spot proxy" |
| FOB formula | `a × HH + b`; US tolling convention a = 1.15, b = liquefaction fee | None (contract term) | FOB assessments (e.g. Gulf Coast markers) | The firm's assumption set; shipped example a = 1.15, b = 2.50 USD/MMBtu marked "example, not a market value" | Two results side by side: **full cost** (a·HH + b) and **lifting cost** (a·HH only; the fee is sunk for an offtaker with a take-or-pay SPA). The lifting cost is the one that decides whether to lift or cancel. |
| Cargo energy | Loaded MMBtu | — | — | From ship capacity × fill × energy density: 174,000 m³ × 98.5 % × 22.2 MMBtu/m³ ≈ 3.80 TBtu, every factor an assumption | Editable; MWh and m³ shown as secondary |
| Route distance | Nautical miles, load port → discharge port, by routing (direct, Suez, Panama, Cape) | A product-authored route table (distances are facts; computed once from an openly licensed sea-route source or measured on the product's own map geometry; **to decide in the package**, editable by the customer) | Vendor distance tables | Blocked for that route: "no distance for Corpus Christi → Świnoujście; enter it" | "4,900 nm · product route table v1" |
| Speed, days | `d = nm ÷ (speed × 24)`; default 17 kn laden and ballast; port days 1 + 1 | — | — | Assumption set | "12.0 days laden at 17 kn" |
| Charter rate | USD/day, by vessel class | None reliable under open terms (**assumption**: broker weekly reports are not licensed for redistribution) | Freight assessments (Atlantic and Pacific round-voyage rates) | The firm's assumption; if none, freight is "missing" and the result is blocked for FOB cargoes | "45,000 USD/d · your assumption, set 3 Nov by A. Trader" |
| Ballast | Round voyage (ballast days = laden days) by default; one-way or positioning bonus as options | — | The assessment's basis | Round voyage | Stated in the freight row |
| Boil-off | % of cargo per day laden; default 0.10 %/d (modern two-stroke 0.07–0.10; steam 0.12–0.15) | — | — | Assumption set per vessel class | Row "boil-off 1.2 % · 45,600 MMBtu" |
| Fuel | Laden: boil-off covers propulsion (no extra cost; already in Q_del). Ballast: `fuel_ballast` MMBtu/d valued at the cargo's FOB cost | — | Bunker assessments | Assumption (2,000 MMBtu/d) | Own row |
| Canal | Panama, Suez tolls per transit | Canal authorities' published toll schedules (**to verify** terms; values change) | — | Zero when the route has no canal; otherwise the firm's entry; "missing" if routed via a canal with no figure | Own row with the schedule's date |
| Port costs | Per call, load and discharge | Terminal and port tariff documents where published | — | Assumption | Own row |
| Insurance | % of cargo value; default 0.05 % | — | — | Assumption | Own row |
| Regas tariff and slot | Per terminal and product (C.4) | Operators' regulated tariff publications (C.4) | — | For exempt or negotiated terminals: the firm's terms (`LngTerminalTermsRecord`); if none, that terminal is left out with the reason | "Fluxys LNG slot, Dec-26 indexed · CREG tariff · PDF link" |
| Gas in kind / fuel retention | % of cargo retained | Same documents | — | As above | Own row |
| Entry into the grid | Entry tariff at the terminal's entry point, EUR/MWh at stated load factor | ENTSOG tariffs for the terminal's entry point (`entsog-tariffs` source) | — | "missing", never zero | Row with the point name |
| Slots available, send-out | Capacity and utilisation | GIE ALSI (held: send-out, inventory, declared capacity per terminal); operators' primary and secondary slot notices (**to verify**) | — | Check "not assessed" | In checks, not in price |
| Use-it-or-lose-it terms | Notice period, release rules, secondary market | Terminal access codes (text; structured fields in C.4) | — | "not recorded" | Shown under the terminal; a failed check when arrival is inside the UIOLI notice period and no slot is held |
| Hub forward, arrival month | TTF, NBP, ZTP, PEG, THE month containing the discharge window | — (public exchange settlement files only where their terms allow) | The customer's licensed quotes; or the firm's marks | Blocked: "no ZTP mark for Jan-27" | With bid side when held |
| FX | Forward for the arrival month (D.5) | ECB reference rates + benchmark rates (held) | Licensed forward points | — | "EUR/USD Jan-27 1.1600 · derived (interest parity)" |
| Vessel position | Where a cargo is | — | AIS / vessel feed through the customer | The cargo's declared ETA | Map only; never a price input |

Assumptions live in **assumption sets** (C.5): a named, versioned set owned by the firm ("LNG desk standard, v7"), with a per-evaluation override. Every assumption row in the arithmetic carries a small "A" mark and its owner and date on hover; a result with assumptions on the value path says so in its headline ("3 assumptions").

### C.3 Worked example (illustrative): US Gulf FOB, lifted December, discharged January

Inputs: HH Dec-26 3.50 USD/MMBtu; formula 115 % HH + 2.50; Q_load 3,800,000 MMBtu; Sabine Pass → Rotterdam 4,900 nm at 17 kn = 12.0 days laden, 12.0 ballast, 2 port days; hire 45,000 USD/d; boil-off 0.10 %/d; ballast fuel 2,000 MMBtu/d; ports 2 × 150,000 USD; insurance 0.05 %; EUR/USD Jan-27 forward 1.1600; 1 MWh = 3.41214 MMBtu.

| Step | Calculation | Result |
|---|---|---|
| FOB price | 1.15 × 3.50 + 2.50 | 6.525 USD/MMBtu |
| FOB cost | 6.525 × 3,800,000 | 24,795,000 USD |
| Boil-off | 3,800,000 × 0.10 % × 12.0 | 45,600 MMBtu |
| Delivered | 3,800,000 − 45,600 | 3,754,400 MMBtu (1,100,306 MWh) |
| Hire | 45,000 × 26 days | 1,170,000 USD |
| Ballast fuel | 2,000 × 12 × 6.525 | 156,600 USD |
| Ports | 2 × 150,000 | 300,000 USD |
| Insurance | 0.05 % × 24,795,000 | 12,400 USD |
| Freight total | | 1,639,000 USD = 0.437 USD/MMBtu delivered |
| **DES-equivalent cost** | (24,795,000 + 1,639,000) ÷ 3,754,400 | **7.041 USD/MMBtu** = 24.024 USD/MWh = **20.71 EUR/MWh** |
| of which boil-off effect | 24,795,000 ÷ 3,754,400 − 6.525 | 0.079 USD/MMBtu |

Downstream, three terminals (tariff figures illustrative; class shown):

| Terminal → hub | Hub Jan-27 | Gas in kind | Entry | Regas + slot | Netback at ship's rail | Margin vs 20.71 | In USD/MMBtu | Total |
|---|---|---|---|---|---|---|---|---|
| Gate → TTF | 30.00 EUR/MWh | 0.5 % | 0.45 (ENTSOG) | 0.95 (**firm's terms**, negotiated terminal) | (30.00 − 0.45) × 0.995 − 0.95 = **28.45** | **7.74 EUR/MWh** | 2.63 | 8.52 m EUR |
| Zeebrugge → ZTP | 29.70 | 1.0 % | 0.30 (ENTSOG) | 0.62 (regulated, indexed) | (29.70 − 0.30) × 0.99 − 0.62 = **28.49** | **7.78** | 2.64 | 8.56 m EUR |
| Montoir → PEG | 29.10 | 0.6 % | 0.25 (ENTSOG) | 0.78 (regulated, standard cargo class) | (29.10 − 0.25) × 0.994 − 0.78 = **27.90** | **7.19** | 2.44 | 7.91 m EUR |

Range if arrival slips a month either side (existing `_neighbours` logic) is shown beside each margin. Zeebrugge ranks first by 0.04 EUR/MWh, which is inside the uncertainty of the Gate figure being the firm's own term: the table says "difference within assumption range", and does not declare a winner.

**Comparison with a cargo already near the Netherlands.** DES offer at TTF Dec-26 − 0.40 EUR/MWh with TTF Dec-26 at 30.40: DES price 30.00 EUR/MWh (= 10.20 USD/MMBtu at 1.1600). Netback at Gate for December: (30.40 − 0.45) × 0.995 − 0.95 = 28.85. Margin −1.15 EUR/MWh. So the table reads:

| Cargo | Term | Arrives | Cost at ship's rail | Best terminal | Netback | Margin | Inputs |
|---|---|---|---|---|---|---|---|
| US Gulf, lift 18 Dec | FOB, own shipping | Jan-27 | 20.71 EUR/MWh | Zeebrugge | 28.49 | +7.78 (lifting-cost basis: +10.3) | 3 assumptions (hire, boil-off, ballast fuel); HH futures public; hubs sourced |
| Offered DES ARA | DES | Dec-26 | 30.00 EUR/MWh | Gate | 28.85 | −1.15 | hubs sourced; Gate terms firm's |

The honest reading printed under it: the US cargo's margin is the liquefaction-to-hub arbitrage and exists whether or not we own the cargo; the DES offer is priced by the market close to its netback, so the decision there is whether our regas position (a held slot, a cheaper terminal) beats the market's. If we hold a slot at Gate (capacity fee sunk, variable 0.10), the DES cargo's netback becomes (30.40 − 0.45) × 0.995 − 0.10 = 29.70 and the margin −0.30: still negative, so the maximum bid is TTF − 0.70. That is the existing "max bid" output, now with a reason.

### C.4 "Henry Hub versus TTF at the same delivery point"

Two views of one number, both produced by the chain above and shown together in Research → Cargo & netback and in the Spreads explorer as a **delivered spread**:

| View | Formula | Example |
|---|---|---|
| **At NW Europe (delivered)**: what US gas costs at TTF | `(a·HH + b + freight + boil-off effect) → EUR/MWh at forward FX, ÷ (1 − gas in kind), + regas + entry` versus TTF same arrival month | 20.71 ÷ 0.995 + 0.95 + 0.45 = 22.21 EUR/MWh at the TTF virtual point, against TTF 30.00: **arb +7.79 EUR/MWh (2.65 USD/MMBtu)** |
| **At the US Gulf (netback)**: what TTF is worth FOB | `TTF → USD/MMBtu, less regas, entry, gas in kind, freight, boil-off` versus `a·HH + b` | 30.00 EUR/MWh = 10.199 USD/MMBtu; less 0.476 (regas, entry, gas in kind) less 0.437 freight less boil-off 1.2 % = **9.17 USD/MMBtu FOB netback** against FOB cost 6.525: +2.65; against lifting cost 4.025: +5.15 |

As a time series this is the "US arb" line an analyst follows: HH and TTF are held daily; freight and fees come from the assumption set (a constant, so labelled "at today's freight assumption") or from a licensed freight series when connected. The chart states which.

### C.5 Data model and ingestion for regulated terminal tariffs

Keep `LngTerminalTermsRecord` as **the firm's terms** (what we pay under our contracts). Add a **public register** beside it, versioned, never overwritten:

`lng_terminal_tariff` (new table)

| Column | Meaning |
|---|---|
| `tariff_id`, `terminal_id`, `operator`, `country`, `hub`, `entry_point_key` | Identity; the ENTSOG point the terminal sends out through (joins to the tariff register and the graph) |
| `regime` | regulated, regulated_indexed, auction, negotiated, exempt (existing vocabulary) |
| `service` | bundled slot, unloading, storage, send-out, additional storage, additional send-out, truck loading, reload |
| `product` | term, annual, spot, prompt (e.g. Elengy SMART SPOT), auction period |
| `charge_basis` | per cargo, per cargo class, per MWh unloaded, per MWh/d send-out capacity, percent in kind |
| `amount`, `currency`, `unit`, `by_cargo_class` (JSON) | The figure(s) |
| `indexation` | none, CPI-monthly (Fluxys), annual update |
| `valid_from`, `valid_to`, `period_label` | Applicability |
| `slot_days`, `sendout_days`, `included_storage` | What a slot contains |
| `uioli_notice_days`, `uioli_rule`, `secondary_market` | Use-it-or-lose-it: structured where the code states a notice period; otherwise a 25-word quotation and the document link (the existing `MAX_QUOTATION_WORDS` rule) |
| `excludes` | What the figure does not include (port fees, entry tariff, gas in kind) — existing `TerminalCost.excludes` |
| `source_url`, `source_sha256`, `retrieved_at_utc`, `document_title` | Provenance |
| `review_status` | candidate → reviewed (existing `FactReviewStatus`); only reviewed rows price an actionable opportunity; candidate rows price "indicative" |
| `reviewed_by`, `reviewed_at_utc` | Four-eyes on data |

Resolution order when pricing a terminal: (1) the firm's terms for that terminal and capacity basis; (2) the reviewed public tariff in force for the arrival month and cargo class; (3) candidate public tariff (indicative); (4) left out with the reason.

Ingestion: one connector `lng-terminal-tariffs` in the source registry, a parser per operator, monthly schedule plus change detection by hash (the existing `compare_lng_terminal_source_bytes` pattern), each new document creating candidate rows and one Admin attention item "Fluxys LNG tariff changed: review 3 values". Order of operators:

| Wave | Terminals | Regime | State |
|---|---|---|---|
| 0 (exists) | Zeebrugge (Fluxys LNG); Montoir, Fos Cavaou, Fos Tonkin (Elengy); Brunsbüttel, Wilhelmshaven (DET auction averages) | regulated / auction | Parsers in `ingestion/lng_terminal_tariffs.py`; needs the register and review flow |
| 1 | Spanish terminals (regulated access tolls set by the national regulator; hub PVB), Świnoujście (regulated), Klaipėda (regulated), Revithoussa (regulated), Italian terminals (regulated; hub PSV), Sines (regulated), Krk (regulated) | regulated | **To verify per operator**: document format, update cycle, terms of reuse |
| 2 (no public price; firm's terms only) | Gate, Dunkerque, Isle of Grain, South Hook, Dragon, Eemshaven | exempt / negotiated | Shown as "enter your terms"; capacity and send-out still from GIE ALSI |

NW Europe hubs (TTF, NBP, ZTP, PEG, THE) are the first release; wave 1 is listed so the model does not need changing later. **Assumption to confirm with the owner's market knowledge:** which wave 2 terminals publish list prices for short-term or secondary capacity today; where they do, they move to wave 1.

`freight_route` (new table): `route_id`, `load_port`, `discharge_port`, `routing` (direct, suez, panama, cape), `distance_nm`, `canal`, `source`, `version`. Shipped with about 40 routes (US Gulf, US East, Qatar, Nigeria, Algeria, Norway (Hammerfest), Trinidad × the NW Europe terminals), editable in Admin.

---

## D. Research

### D.1 Verdict
Today's Research is a strategy-lifecycle platform (design, freeze, backtest, compare, shadow), a dataset builder and an agents console. An analyst on a gas desk spends the day on four things: relative value, fundamentals against history, arbitrage arithmetic, and writing it up. Research is rebuilt as exactly those four.

### D.2 The four workbenches

**1 · Spreads (relative value)**

| | |
|---|---|
| Job | "Is this spread unusual, and is it wide enough to pay after costs?" (A3, T7) |
| Inputs | Two to four legs, each picked hub → product kind → tenor; weights; display unit; history window |
| Instrument picker | Level 1: hub (TTF, NBP, THE, PEG, ZTP, PSV, …, HH), my hubs first. Level 2: product kind as tabs (Spot/DA · Month · Quarter · Season · Year · Rolling: M+1, M+2, Q+1, Win, Sum). Level 3: the tenors of that kind as a short list. A search box takes desk shorthand ("ttf jan27", "nbp m+1", "the-ttf q1") using the existing product grammar (`domain/market/products.py`: `_MONTH_CODE`, `_RELATIVE`). Presets on top: NBP–TTF, THE–TTF, PEG–TTF, ZTP–TTF, Sum–Win, Q1–Q2, HH–TTF delivered. Series with fewer than 30 observations are greyed with the count. Source is not a level: the best entitled source is chosen, changeable under "Source". |
| Normalisation | Automatic: each leg converted to the display unit (default: the unit of the first leg; choice EUR/MWh, p/th, USD/MMBtu) with the FX of D.5. A line under the formula always states it: "NBP converted p/th → EUR/MWh at EUR/GBP forward for Jan-27 0.8726, derived". A toggle "spot FX" exists for comparison. |
| Outputs | Spread level now; percentile and z-score in the window; mean, ±1σ and ±2σ band; half-life; **route cost overlay** when the legs are two hubs with a proven path (horizontal lines at +cost A→B and −cost B→A: outside the lines, moving gas pays); seasonal view (this year against prior years by day of year) |
| Default view | NBP–TTF front month for a user with both hubs, else the user's first focus hub against TTF; history 1 year; chart on top, four figures beside it. Opens populated; no "Run" needed for the default. |
| Rule test | One fold, "Would a simple rule have paid?": the existing z-score and threshold rules (`domain/research/spread_analysis.py`), result as three figures and a cumulative line. No strategy objects, no freezing. |
| Flows to | "Open as an evaluation" (pre-fills a location or time-spread workbench in Deals); "Add to report" (the chart and its fact enter a report draft); CSV |

**2 · Fundamentals**

| | |
|---|---|
| Job | "Where is the system against normal, by country, and what moved?" (A1, A2) |
| Tabs inside the task | Storage · LNG · Flows · Balance · Gas for power |
| Storage | Europe aggregate and one panel per country (small multiples, shared axis): fill % on a gas-year axis with the 5-year range band, 5-year mean, last year, this year, the regulatory target; table beside: fill %, vs last year (points), vs 5-year mean (points), day change (GWh/d), stock (TWh), implied days to target at the 7-day rate. Toggle % / TWh. Country pair difference (e.g. DE − NL fill) as a derived series for regional spread work. |
| LNG | Send-out by country and terminal (stacked area by country; terminal table with utilisation = send-out ÷ declared capacity), inventory, against the same band logic |
| Flows | Norway by landing point, interconnector flows (IUK, BBL, the big IPs), against 7-day and prior-year |
| Balance | NW Europe supply stack against the supply call (existing `NweBalancePanel` data), with the revision since yesterday attributed when versions exist |
| Default view | Storage, Europe + the user's focus countries first |
| Flows to | "Add to report"; "Ask about this" (the answer bar with the series in context); CSV; a surprise beyond its band raises the analyst's strip item (basis 1, 5.2) |

**3 · Cargo & netback**

| | |
|---|---|
| Job | "What does a cargo from X on terms Y net at each terminal, and how does the arb evolve?" (O1, the owner's HH–TTF question) |
| Inputs | Origin and term (FOB formula, FOB price, DES price), load or arrival window, cargo size, vessel class, assumption set; terminals to compare |
| Outputs | The comparison table of C.3 (cargo × terminal), the waterfall for one row (FOB → boil-off → freight → DES → regas → entry → hub), the delivered-spread time series of C.4, sensitivity (hire, HH, hub, FX) |
| Default view | The demo or last-used cargo against the NW Europe terminals with tariffs held; opens populated |
| Difference from Deals | Same engine and component. In Research it is hypothetical (no book, no checks); in Deals it starts from a cargo in the book and adds slot, limit and credit checks. |
| Flows to | "Open as an evaluation" in Deals; "Add to report"; CSV |

**4 · Reports** — unchanged (`ReportsWorkspace.tsx`, `application/reports/`). It gains "exhibits added from Research" as an input to an asked report.

**Ask** stays the answer bar and copilot. **Export**: every chart and table has CSV (the `Chart` primitive already does); a "Download data" action on each workbench exports the normalised series with their conversion metadata (unit, FX rate, method, as-of) as columns. The Python SDK remains for quants.

### D.3 What leaves Research

| Today | Verdict |
|---|---|
| Strategies → Spread (`SpreadLabWorkspace.tsx`) | Rebuilt as Spreads (new component on the `Chart` primitive) |
| Strategies → Design, Backtest, Compare (`StrategyDesignWorkspace`, `StrategyBacktestWorkspace`, `StrategyCompareWorkspace`, `StrategyNavigator`, `StrategyIdentityHeader`, `StrategySharing`) | Removed from the product. Deferred: add back only if an analyst asks for frozen, reproducible strategies. |
| Strategies → Shadow (`StrategyShadowShell`, `StrategyShadowRunDetail`, `StrategyShadowRunSections`) | Removed. Scheduled jobs stop. |
| Data (`ResearchDataWorkspace.tsx`: datasets, features, targets; `DataProductCatalogue`, `ResearchCapabilityCatalogue`) | Removed. Export on every view replaces it. |
| Assistant (`AgentsWorkspace.tsx`, `agents/AgentArtifactChain`, `agents/AgentReviewGate`) | Removed from navigation. Ask remains. |
| `LngEconomicsPanel.tsx` (was to move here in basis 1) | Deleted; replaced by Cargo & netback. |
| `NativeCapacityContextPanel.tsx` (was to move here) | Moves to Admin → Connectors instead. |

### D.4 Analyst composition
Landing Desk → Today (fundamentals first); shortlist Today · Research → Spreads · Research → Fundamentals · Research → Reports.

### D.5 Forward FX, precisely

Purpose: convert a price for delivery period T quoted in currency X into currency Y at the rate at which that cash flow could be hedged today.

1. **Spot** `S(X/Y)` = the latest ECB euro reference rates held (`domain/market/fx_fixings.py`), crossed through EUR for non-EUR pairs. Named with its date.
2. **Rates** `r_X`, `r_Y` = the latest held overnight benchmark fixing per currency (`DEFAULT_BENCHMARK_FOR_CURRENCY`: SONIA, €STR, SOFR), each on its own day count (GBP act/365; EUR and USD act/360).
3. **Forward** to the value date `t` = midpoint of the delivery period (for a month: its 15th; for DA: spot is used, no forward):
   `F(X/Y, t) = S × (1 + r_Y · τ_Y) / (1 + r_X · τ_X)` for `t` ≤ 1 year, with `S` quoted as units of Y per unit of X; compounded annually beyond one year.
4. **Label**: always "derived (interest parity from <benchmarks>, flat rate)". Class **derived**.
5. **Stated limitation and tolerance**: a flat overnight fixing is not a term curve and ignores the cross-currency basis. Tolerance attached to the conversion: 0.1 % of the rate for `t` ≤ 3 months, 0.3 % to 12 months, 1 % beyond; the tolerance is carried into the spread as an uncertainty (30 EUR/MWh × 0.3 % = 0.09 EUR/MWh). An opportunity whose net margin is smaller than its FX tolerance is "watch". Beyond 24 months the conversion is refused unless licensed forwards are present.
6. **Licensed forwards** (forward points or outright forwards through the customer's entitlement) take precedence when present; label "sourced (<vendor>)", no tolerance.
7. **Never silent**: the rate, its date, the method and the value date are on the conversion row or one hover away; the export carries them as columns.

Example (illustrative): TTF Jan-27 30.00 EUR/MWh; NBP Jan-27 78.00 p/th. NBP in GBP/MWh = 0.78 × 34.1214 = 26.615. Spot EUR/GBP 0.8700 → 30.592 EUR/MWh, spread +0.59. Forward: SONIA 3.75 %, €STR 1.90 %, 60 days: F = 0.8700 × (1 + 0.0375 × 60/365) ÷ (1 + 0.0190 × 60/360) = 0.8726 → 30.501 EUR/MWh, **spread +0.50 EUR/MWh**. The 0.09 difference is the size of many NBP–TTF trades' edge; at Cal-28 the difference is about 0.9 EUR/MWh. This is why spot conversion is wrong for forwards.

---

## E. Desk → Today

### E.1 Principles
No filter strip: Today is about today. The gas day is the current one; the products are day-ahead and front month (plus a personal watchlist of up to three tenors); the hubs are **my hubs** (derived from the book and overridable in Settings, basis 1 gap G12). Nothing on the page is empty furniture: a section with nothing to say is one sentence, not a panel.

### E.2 Trader composition (desktop)

| Row | Content | Rules |
|---|---|---|
| Header line | "Tuesday 17 Nov · GD 17 Nov · front month Dec-26" · freshness as one word · "Morning brief" | No controls. |
| **1 · My market** | Per focus hub (up to 4): DA and front month in the native unit with day change and a 30-day sparkline; then the spreads that matter to the book (e.g. NBP–TTF, THE–TTF) in one unit with forward FX and "vs route cost" (in/out of the money as a word) | First thing on the page (D1 of basis 1). Source on hover; simulated mark where simulated. |
| **2 · My book** | Net position today and front month by hub (signed, native volume unit); day P&L change (book currency; secondary line in the reporting currency per section G); tightest limit (% used) | Hidden without `portfolio.read`. |
| **3 · What needs me** | One merged, ranked list of at most 5: must-act opportunities, unplanned outages touching the book or focus hubs (size, effect on us), limit alerts, then the top "could act" opportunity. Each row links to its object. | When nothing qualifies: one sentence in the header of row 4, "Nothing new since yesterday 17:30: no unplanned outages at your hubs, no alerts." The row is then absent. Never two empty panels. |
| **4 · Fundamentals** | Left: storage. Europe aggregate as the lead chart (gas-year axis, range band, mean, last year, this year, target), then small multiples for the focus countries + the next largest (up to 8), each with its headline: "DE 71.4 % · −6.2 vs 5-yr · −0.31/d". "All countries" opens Research → Fundamentals. Right: supply call today vs 7-day average with the stack sparkline; LNG send-out vs yesterday. | For the trader the country multiples are open (the owner's point: regional spreads come from country storage); the balance and gas-for-power charts are not on Today (they live in Research → Fundamentals). |

Removed from Today: the context/filter strip; the separate alerts and outages panels; `NweBalancePanel` and `GasForPowerPanel` as full charts; the 120-day storage chart; the source-approval notice (basis 1).

### E.3 Other roles (through `roleComposition.ts`: `todayRows` gains the new keys `market`, `book`, `needs_me`, `fundamentals`, plus per-row variants)

| Role | Order and variant |
|---|---|
| Analyst | Fundamentals (full: Europe + all country multiples, balance figure, LNG) → market → needs me (fundamentals surprises first) → book (if permitted) |
| Desk head | Book (P&L by hub, position, breaches count, decisions waiting) → needs me → market (two hubs) → fundamentals as three figures |
| Risk | Limits (top 5, not only the tightest; G2) → needs me (breaches, cases due) → book → market as figures |
| Originator | Needs me (my cases, cargo opportunities) → market (hub forwards for the arrival months of open cargoes) → fundamentals: LNG first |
| Operations | Needs me (shortfalls, outages at delivery points, windows) → book (residual by day) → market as figures |
| Finance, compliance | Do not land on Today. |

### E.4 Phone
Five elements: strip · my market (two hubs, DA and front month) · my position and tightest limit · what needs me (3) · storage Europe as headline + sparkline (tap for the chart). Country multiples become a two-column list of headline numbers.

### E.5 Server
`GET /api/desk/today` (`application/desk_today.py`) gains: `market.spreads` (normalised, with route cost), `needs_me` (merged and ranked server-side, using the opportunity store), `fundamentals.storage.countries[]` with band statistics. `STORAGE_CHART_DAYS` goes; the storage read returns the gas-year series and band per entity.

---

## F. Chart and figure standard (in-app)

Adapted from `docs/product/REPORT_EDITORIAL_STANDARD.md` (exhibits: declarative title, unit line, source, direct end labels, context in grey, forecasts dashed, zero baseline for bars, "n prior years held" stated).

### F.1 Which chart for which data

| Data | Chart | Never |
|---|---|---|
| A level over time (price, flow, fill) | Line on a true time axis; context series in grey | Categorical axis; area under a price |
| A spread over time | Line with a zero line; mean and ±1σ/±2σ band; cost thresholds as horizontal rules | Bars |
| **Term structure** (price by delivery month today) | Line with a marker per delivery month (step where products are quarters/seasons); ghost curves for prior close and one week ago; one unit | Bars |
| **Spread by delivery month** | Top: both curves in one unit; bottom, aligned: the spread as a line with markers, zero line, cost band, ghost of a week ago. Or a table when fewer than 6 months are held. | "A lot of pillars" |
| Seasonality against history | Gas-year (Oct–Sep) or calendar-year axis: range band (min–max), mean line, last year thin, this year bold, target marker | A 120-day window with one comparison line |
| Supply stack against demand | Stacked area (daily, > 14 points) or stacked bars (≤ 14 points), at most four tones ordered by size + "Other"; the demand or call line on top | More than five stack members |
| Change between two states (cargo waterfall, P&L attribution, balance revision) | Waterfall, horizontal on phone | Pie |
| Distribution (where today sits in history) | Percentile strip in the figure (a 0–100 bar with a marker) or a histogram with today marked | A z-score alone without the window |
| Comparison across entities at one time (terminals, countries) | Sorted horizontal bars or a dot plot with the comparison as a second mark | Unsorted vertical bars |
| Part of a series in a table row | Sparkline (30 points), no axis, last value as the number beside it | Sparkline without the number |

### F.2 Rules

| Aspect | Rule |
|---|---|
| Title | Says the finding or the measure ("NBP over TTF, front month"), not the mechanism. Unit beside the title and on the axis. One axis, one unit; two units means two aligned panels, never a dual axis. |
| Labels | Direct end labels instead of a legend when ≤ 4 series; one number of decimals per axis; date ticks on calendar boundaries (month starts; gas-day starts); delivery months as "Jan-27". |
| History bands | < 1 full prior year held: no band; the subtitle says "history from <date>". ≥ 1 and < 5 prior years: prior year(s) as thin grey lines, labelled "1 prior year held". ≥ 5: min–max band and mean of the last five complete years, labelled "5-yr range 2021–2025"; last year remains a thin line. The band is never drawn from fewer years than its label says. |
| Targets and thresholds | Thin neutral rule with a direct label ("target 90 %"; "route cost 0.97"). |
| Simulated, forecast, derived | Simulated: dashed, badge on the chart, "simulated" in tooltip and export (existing `Chart` behaviour). Forecast: dashed from its start. Derived conversion: stated in the note line. |
| Hover readout | A crosshair with every series' value and unit at that x, the comparison ("−6.2 vs 5-yr mean") and the as-of; never leaves the plot (existing). Keyboard stepping stays. |
| Compare | A "Compare" control adds one series of the same unit (another hub, another year); a different unit is refused with the offer to convert. |
| Small multiples | Shared y scale by default (comparability), stated; "independent scales" as a toggle; each panel carries its headline number; ordered by the user's focus then by size; at most 8 before "all". |
| Table and CSV | Every chart offers the table view and CSV of exactly what is plotted, with unit and conversion columns (existing). |
| Height | Lead 260 px, standard 200, multiple 120, sparkline 14–20. |
| Phone | A chart is its headline number + sparkline; tap opens the full chart in a sheet with the crosshair on touch-and-drag; small multiples become a list; no hover-only information. |
| Colour | Token series palette; this year = accent; history = greys; positive/negative only for signed P&L. |

### F.3 Every existing in-app chart and its replacement

| # | Chart today (file) | Problem | Replacement |
|---|---|---|---|
| 1 | Forward curve, one hub (`PriceCharts.tsx`, id `forward-curve`) | One hub at a time; no reference to yesterday; hubs in different units cannot be compared | Term-structure chart: up to 3 hubs in a chosen unit (native by default for one hub; EUR/MWh with forward FX for several), ghost of prior close and week ago, quarter and season products as steps |
| 2 | NBP–TTF spread by delivery month, **bars** (`PriceCharts.tsx`, id `nbp-ttf-spread`) | Bars for a spread; fixed pair; spot FX | Two-panel "spread by delivery month" (F.1) for a selectable pair, forward FX, route-cost band |
| 3 | Board sparkline (`MarketTerminal.tsx`) | — | Keep; add the last value's change in the title text |
| 4 | Storage season, NW Europe, 120 days vs one prior year (`TodayScreen.tsx`, `StorageSeasonChart`) | Region only; short window; history unreadable | Seasonal band chart, Europe lead + country small multiples (E.2) |
| 5 | Storage and supply-call sparklines (`TodayScreen.tsx`) | — | Keep, with the comparison number beside each |
| 6 | NW Europe balance: stacked bars + call line (`NweBalancePanel.tsx`) | Acceptable form; lives on Today as a full chart | Moves to Research → Fundamentals → Balance; stacked area beyond 14 days; forecast dashed; revision attribution as a waterfall when versions exist |
| 7 | Delivery: nominated bars + allocated step (`DeliveryPerformancePanel.tsx`) | Acceptable | Keep (Book, outside this scope); add the shortfall as a signed line beneath |
| 8 | Spread, z-score, cumulative P&L (`SpreadLabWorkspace.tsx` via `StrategyLabCharts.tsx`) | Hand-rolled SVG, categorical axis, first/last labels only, three stacked panels, no hover readout | One spread chart on the `Chart` primitive with mean and σ bands and the percentile strip (z-score panel dropped: the bands show it); rule P&L in the fold |
| 9 | Backtest equity and drawdown (`StrategyBacktestWorkspace.tsx`) | — | Removed with the page |
| 10 | Compare runs (`StrategyCompareWorkspace.tsx`) | — | Removed |
| 11 | Shadow drift SVG (`StrategyShadowRunSections.tsx`) | — | Removed |
| 12 | Report exhibits (`application/reports/charts.py`: line, step, stacked, bar, sankey, sparkline) | The standard | Keep; add the band and the term-structure forms so reports and the app draw the same thing |
| 13 | Gas for power (`GasForPowerPanel.tsx`, figures only) | On Today | Moves to Research → Fundamentals |
| New | — | — | Cargo waterfall; terminal comparison dot plot; percentile strip; delivered-spread line |

`StrategyLabCharts.tsx` and `strategyChartGeometry.ts` are deleted once #8 is replaced.

### F.4 The other trader-desk furniture on Prices (`TraderDeskPanel.tsx`)

| Element | Verdict | Reason |
|---|---|---|
| Price converter | **Remove** | The answer bar converts ("78 p/th in eur/mwh jan27"), and display preferences (G) put the converted value on hover everywhere. A standing form duplicates both. |
| Product strip (delivery windows) | **Remove** as a panel | The delivery window of a tenor is shown on hover of the tenor header on the board and in the picker. |
| Storage-target trajectory | **Move** to the storage chart as the target marker and "days to target" figure | One number, one place. |
| Quotes by source, reference index evidence | Inspector (basis 1) | — |
| Intraday decision feed | **Merge** into Opportunities (type L intraday) with one line on Prices linking there | One opportunity surface. |

Prices is then: the hub × tenor board, the term-structure chart, the spread-by-delivery-month chart.

---

## G. Display rules

| # | Rule |
|---|---|
| G1 **Native first where you trade** | Prices, quotes, the board, order-like quantities and contract terms are always shown in the instrument's native unit and currency (TTF EUR/MWh; NBP p/th; HH USD/MMBtu). The primary figure is never replaced by a preference. |
| G2 **Preferences** (personal, with organisation default; existing three-tier settings in `domain/settings/preferences.py`) | `reporting_currency` (EUR, GBP, USD, CNY, …: any currency in the ECB table); `energy_unit` (MWh, therm, MMBtu, GJ; volume in m³ only with a stated calorific value: Sm³ needs the reference conditions and a GCV, default the ontology's desk GCV, shown); `price_basis` for comparisons (EUR/MWh, p/th, USD/MMBtu). |
| G3 **Secondary value** | On hover/focus (tap on phone) every native figure shows the converted value, the rate, its date and method: "30.00 EUR/MWh · 10.20 USD/MMBtu at EUR/USD 1.1600 (ECB 16 Nov; forward Jan-27, derived)". In reporting contexts (P&L totals, limits, the desk-head Today, reports) the secondary value is a visible second line when the reporting currency differs from the book currency. |
| G4 **Aggregates** | A total across currencies or units is only ever shown converted, in the reporting currency, with the conversion line under it. Per-row values stay native. (The backend already refuses to add GBP and EUR without FX.) |
| G5 **Which rate** | Spot/DA and realised values: the ECB reference rate of the value date. Forward values: the forward of D.5 for the delivery period. Historical P&L: the rate of the snapshot date, never today's. "Live rate" in the owner's sense: the latest held rate, with its date; the product does not hold intraday FX unless a licensed feed is connected, and says so. |
| G6 **Never silent** | No converted number without a reachable rate, date and method. Exports carry them as columns. |
| G7 **Where conversion is forbidden** | Contract terms as signed (price formula, currency, volume unit); limits and credit lines (shown and tested in the currency they were approved in; a converted view is secondary only); tariff publications (as published); decision-case evidence once frozen; anything simulated into a non-simulated total. Conversions never write back. |
| G8 **Gas day and time** | Gas day shown as "GD 17 Nov" (06:00–06:00 CET/CEST for continental hubs; 05:00–05:00 UK time for NBP, the same instant), boundaries on hover in market time. Clock times in the user's zone (office zone, overridable), market zone on hover; deadlines as time to go + clock time. No ISO strings or "UTC" on commercial pages (I2). A daily value for NBP and TTF on "the same gas day" is the same physical day. |
| G9 **Simulated** | The `sim` mark on every simulated figure, dashed in charts, a banner on a simulated board, a dagger in reports; a simulated input makes every figure computed from it simulated; simulated opportunities exist only on the demo desk; no simulated price is ever class "sourced" or "firm's mark". |
| G10 **Units in figures** | I1 stands: every figure carries its unit; MW and th/d for position, GWh/d for flows, TWh and % for storage, with the preferred energy unit as the secondary. |

Implementation note: conversion is server-side through one service (J.3) so that the client never holds a factor; the client `Figure` wrapper (WP-03) asks for `{native, converted[], conversion}`.

---

## H. Guidance without a manual

### H.1 The page contract (every commercial task)

| Element | Rule |
|---|---|
| Purpose line | One sentence under the title, in the user's terms, naming the decision: "Ways to earn or save money with your book, checked against published tariffs and your limits." Always visible, muted, never more than 110 characters. |
| What it needs | Shown **only when something is missing**, as a checklist of at most three items with the state and the one control that fixes each (B.7). When everything is present it is absent. |
| Example | A "See an example" control that loads the demo case into the same view, clearly marked simulated, with "Clear example". On the demo desk the page opens with it. |
| Empty state | One sentence: why it is empty, and one next action (I5). An empty state for a missing permission names who can grant it. For a missing licence: "Needs a price feed; your administrator connects it" — never a prompt to buy inside the product. |
| Progressive disclosure | Default view answers the job's question; "Adjust" reveals inputs; "How this is calculated" opens the arithmetic with sources; the Inspector holds ids, exact times, methods. Three levels, never more. |
| First-use hints | At most three dismissible callouts per page, anchored to real controls, shown once per user (preference), replayable from the page's "?" (`PanelHelp`). |
| Vocabulary | Desk words (netback, slot, entry, gas in kind), each with the glossary hover (`GlossaryWiki`, answer bar). No engine names, no codes (I3). |
| Result explains itself | Every computed number has "Why?" (`WhyButton`): the arithmetic rows, not prose from a model. |

### H.2 Purpose lines

| Task | Purpose line |
|---|---|
| Desk → Today | What changed since yesterday and what it means for your book. |
| Desk → Prices | The curve at every hub, and the spreads between them in one unit. |
| Desk → Network | The gas system now: outages, flows and capacity, with your deals on it. |
| Deals → Opportunities | Ways to earn or save money with your book, with the arithmetic shown. |
| Deals → Contracts | Your supply, sales, capacity and storage contracts: the book everything else reads. |
| Deals → Review | Decisions waiting for approval, and the record of those taken. |
| Research → Spreads | How one price trades against another, and whether today is unusual. |
| Research → Fundamentals | Storage, LNG, flows and the balance against their own history, by country. |
| Research → Cargo & netback | What a cargo from any origin is worth at each terminal. |
| Research → Reports | Market reports written from the data held. |

### H.3 JSON upload is removed as a user entry

| Today | Replacement |
|---|---|
| Desk replay JSON (`DeskReplayPanel.tsx`) | Removed from the UI. The look-back it served is the outage's detail: "what was our exposure then", computed from stored state. The JSON entry stays an API for support. |
| Contract import JSON and staged text (`ContractWorkbench.tsx`) | The UI accepts PDF (OCR intake, with page references) and the form. Bulk import is the ETRM connector (Admin) or CSV with a downloadable template. JSON stays on the API. |
| LNG economics text-in sandbox | The cargo form (C, D.2). |
| Nomination and dispatch period entry by identifier (`decision.nomination.blocker.*`, `decision.dispatch.blocker.*`: "every period needs an identifier") | Book → Planning forms pre-filled from the book and windows; identifiers generated. |

---

## I. Removal list

### I.1 Delete now (client code; routes redirect per the existing redirect table in `modeNavigation.ts`)

| Item | Paths |
|---|---|
| Deals → Evaluate | `clients/web/src/components/ScenarioWorkspace.tsx`; scenario branch of `DecisionWorkspace.tsx`; `app/model/scenarioInputProvenance.ts`, `scenarioRouteEconomics.ts`; `app/strategyScenario.ts` |
| Deals → Optimise page | optimise branch of `DecisionWorkspace.tsx`; `decision/DecisionActionStatus.tsx` |
| Deals → Routes & netback page | routes branch of `PortfolioWorkspace.tsx`; `RouteCostWhatIfPanel.tsx`, `LngCargoBidPanel.tsx`, `CapacityBillingPanel.tsx` (logic re-homed in the workbench, files deleted after) |
| Desk replay | `decision/DeskReplayPanel.tsx` |
| LNG economics sandbox | `LngEconomicsPanel.tsx`; UI client of `/api/research/lng-economics-only` |
| Financing rate helper panel | `FinancingRateHelper.tsx` |
| Research → Strategies (Design, Backtest, Compare, Shadow) | `components/strategy/` except what Spreads reuses (nothing after CP-16): `StrategyLabWorkspace.tsx`, `StrategyDesignWorkspace.tsx`, `StrategyBacktestWorkspace.tsx`, `StrategyCompareWorkspace.tsx`, `StrategyShadowShell.tsx`, `StrategyShadowRunDetail.tsx`, `StrategyShadowRunSections.tsx`, `StrategyNavigator.tsx`, `StrategyIdentityHeader.tsx`, `StrategySharing.tsx`, `StrategyLabCharts.tsx`, `strategyChartGeometry.ts`, `SpreadLabWorkspace.tsx`, `strategy-lab.css` |
| Research → Data | `ResearchDataWorkspace.tsx`, `DataProductCatalogue.tsx`, `ResearchCapabilityCatalogue.tsx` |
| Research → Assistant | `AgentsWorkspace.tsx`, `components/agents/AgentArtifactChain.tsx`, `agents/AgentReviewGate.tsx` |
| Today filter strip | `TradingContextControls.tsx` mount in `MarketCockpit.tsx` (`tradingContextControlsFor`); the component itself deleted once Book → Delivery has its own day picker |
| Prices furniture | `TraderDeskPanel.tsx`; the bar spread in `PriceCharts.tsx`; `IntradayDecisionFeed.tsx` (merged into Opportunities) |
| Network decision rail | `ResourcePoolPathOverlay.tsx` as a standing overlay, the decision rail and `CommercialWarningList` on Network; the ~40 pool/strategy props of `NetworkWorkspace` (paths are drawn only for a selected opportunity) |
| Book overview residue | scenario strip and resource register in `PortfolioWorkspace.tsx` (overview branch) |
| Context strips | `MarketContextStrip.tsx`, `PortfolioContextStrip.tsx`, `ReviewContextStrip.tsx`, `ProjectionContextStrip.tsx` on commercial pages (basis 1 said "one conditional word"; now: the status chip only) |
| Screen-order observations | fold in `MarketPositioningWorkspace.tsx` (P&L snapshots stay) |

### I.2 Moves to Admin or Inspector

| Item | Destination |
|---|---|
| `TariffPublicationsPanel.tsx` | Admin → Connectors → Coverage (transport and terminal tariffs: held, in force, overdue, awaiting review) |
| `ReferenceNetworkCatalogue.tsx`, `NativeCapacityContextPanel.tsx`, `CapacityContractBook.tsx` (as a register) | Admin → Connectors → Infrastructure; capacity bookings are entered as contracts |
| `SourceApprovalNotice`, endpoint banner, pipeline alerts | Admin (basis 1 WP-08) |
| Quotes by source, `ReferenceIndexEvidence.tsx`, run ids, fingerprints, engine and commit identity | Inspector |
| Assumption sets, terminal tariff review, freight route table, opportunity thresholds and precision | Admin → new "Commercial settings" section inside Runtime or Connectors (no new page) |
| Agent capability catalogue, research capability catalogue | Deleted from the UI (not moved): declarations, no job |

### I.3 Deferred: "add back if proven" (backend kept, dormant; no UI, no scheduled jobs)

The strategy laboratory (registry, decision-time backtest, tracks and shadow runtime) is not
deferred: the owner approved removing it with its backend and tables (migration
`0099_remove_strategy_laboratory`); profit is fixed at decision time, so its "backtest" proved
no outcome. The spread laboratory and research datasets stay.

| Capability | Backend kept | Re-entry condition |
|---|---|---|
| Dataset builder, feature and target registry | `domain/research/datasets.py`, `features.py`, `targets.py`, `application/research_registry.py` | A quant team at a customer; until then the SDK and CSV |
| Agents workspace | `application/agents/`, `domain/agents/` | A shown desk use beyond Ask |
| Capacity billing calculator as a tool | `domain/research/capacity_billing.py` | If the tariff-leg disclosure proves insufficient |
| Desk replay | `domain/portfolio/desk_replay.py` | As the outage look-back, without upload |

The backend APIs for deferred items are unregistered from the public router profile where the route-registration mechanism allows (`api/route_registration.py`, `route_profiles.py`), so the attack and maintenance surface shrinks with the UI (decision L4).

---

## J. Architecture consequences

### J.1 Does the architecture hold?
**Yes.** FastAPI, PostgreSQL/Alembic, the job runner, the projections, the permission model and the React client all stand (rules 4–6). No new service, queue or datastore. Three changes of principle are needed, none of infrastructure:

1. **Server-assembled reads for commercial pages.** Today's pattern for Deals and Network composes results in the client (`useAppController`, `workspaceDerivedData.ts`, forty props into `NetworkWorkspace`). Opportunities, the workbench and Today read one server-assembled object each, as `GET /api/desk/today` already does. The client renders; it does not compute commercial results.
2. **Money and units are typed end to end.** Field names with a currency in them (`net_margin_gbp_mwh`, `net_pnl_gbp_per_day`) and the hard-coded `GBP` in `ScenarioWorkspace.tsx` cannot carry a multi-hub book. Opportunity arithmetic uses `{value, unit, currency}` (the ontology's `Money`/`PriceUnit`, `domain/ontology/currency.py`, `quantity.py`). The resource-pool result needs the same treatment where it feeds type R; until then type R is offered only for single-currency pools.
3. **One valuation snapshot per evaluation.** Every evaluator reads the curve, FX, rates, tariffs and book through a `valuation_snapshot` (ids and as-of of each input set), so two screens never value a month differently (idea 4 of the strategic review) and a case's evidence can be replayed.

### J.2 The opportunity engine

| Aspect | Design |
|---|---|
| Shape | An application service `application/opportunities/` with one pure evaluator per type under `domain/opportunities/` (inputs → `Opportunity`), the existing intraday engine becoming the type-L intraday evaluator. Deterministic; no model. |
| Triggering now | The existing job runner (`application/jobs.py`): a full evaluation after each scheduled ingestion that changes an input class (prices, tariffs, outages, book import), debounced to at most one run per 5 minutes; plus on write of a contract, mark, assumption set or limit; plus on demand for the workbench (synchronous, single opportunity). |
| Triggering with M4 | When the event outbox and impact propagation land, evaluators subscribe by input dependency: each opportunity record stores the keys it read (`hub:TTF:2027-01`, `tariff:ITP-00005:EXIT:2026/27`, `outage:<event>`, `contract:<id>`); an outbox event carrying a key re-evaluates only the opportunities and candidate generators that depend on it. The dependency keys are stored from the first release so M4 needs no remodelling. Outbox in PostgreSQL with `LISTEN/NOTIFY`, as the strategic review requires. |
| Candidate generation | Bounded: locational = hub pairs with a proven path of ≤ 3 crossings × delivery periods held (DA, months to M+6, next two quarters and seasons) where the book has a position, flexibility or held capacity at either end, plus all direct neighbours of focus hubs ("adjacent hub" in the owner's map request). Order of 10²–10³ candidates per run; no solver except type R. |
| Storage | PostgreSQL. Current opportunities plus versions; retained 90 days after expiry, longer when linked to a case. |
| Scope and permissions | Evaluated per book scope; a user sees opportunities only for books they can read (the `alert_scope.py` rule). New permission `opportunity.read` (granted with `portfolio.read`); opening a case uses the existing case permission. No new authority through composition. |
| Insider wall | Inputs classified public / internal. An internal operational fact (own unpublished outage, own nomination) may produce type E for operations but never a margin opportunity (L, T, D, A) before publication. Enforced in the evaluator by input classification; tested. |
| Failure | An evaluator that fails produces no opportunity and one admin alert; the desk never sees an error panel, only "last evaluated 09:42". |

### J.3 Data model additions

| Table | Key fields |
|---|---|
| `opportunity` | id, key (dedupe), type, lane, state, book scope, claim fields, value (amount, currency), net margin (value, unit), executable volume, delivery period, quality grade, score, first seen, last evaluated, expires, version, snapshot id, simulated |
| `opportunity_leg` | opportunity id, order, label key, quantity, rate, unit, currency, input class, source ref, as-of, subtotal |
| `opportunity_check` | kind, result, figure, reference |
| `opportunity_dependency` | opportunity id, input key |
| `opportunity_user_state` | user, opportunity key, dismissed/watching, reason, at-version |
| `evaluation` | a user's adjusted copy: base opportunity, overrides, result, author |
| `assumption_set` / `assumption_value` | set id, name, version, owner, effective; key (e.g. `lng.hire_usd_day.174k`), value, unit, range low/high, note |
| `valuation_snapshot` | id, as-of, curve version, FX date, rates date, tariff register version, terminal tariff version, book version |
| `firm_mark` | hub, period, value, unit, author, at (the customer's own marks) |
| `lng_terminal_tariff` | section C.5 |
| `freight_route` | section C.5 |
| preferences | `display.reporting_currency`, `display.energy_unit`, `display.price_basis`, `desk.focus_hubs`, `desk.watch_tenors` |
| storage history | backfill rows in the existing storage observations (no schema change) plus a materialised band statistic per entity and day of gas year |

### J.4 APIs

| Endpoint | Purpose |
|---|---|
| `GET /api/opportunities` | The list for the caller (lanes, groups, counts, readiness checklist for the empty state) |
| `GET /api/opportunities/{id}` | Detail: legs, assumptions, falsifiers, sensitivity, checks, quality |
| `POST /api/opportunities/evaluate` | Workbench: a typed request (location, time, cargo, allocation) → the same object, not stored unless saved |
| `POST /api/opportunities/{id}/case` | Open a decision case with the frozen arithmetic |
| `PUT /api/opportunities/{key}/state` | Dismiss or watch (per user) |
| `GET/PUT /api/assumption-sets…` | Sets and values (write: desk lead permission; audited) |
| `GET/PUT /api/market/firm-marks` | The customer's marks |
| `GET /api/market/instruments` | Hierarchical catalogue hub → kind → tenors, with observation counts and entitlement |
| `POST /api/market/normalise` | Series or values → target unit with conversion metadata (replaces the client-side refusal in `spread_lab.py`) |
| `GET /api/market/fx-forward` | Pair, value date → rate, method, inputs, tolerance |
| `POST /api/lng/cargo-economics` | Section C chain; supersedes `/api/portfolio/lng-cargo-bid` (kept as an alias for one release) |
| `GET /api/lng/terminal-tariffs`, review endpoints | The public register and its review |
| `GET /api/lng/freight-routes` | The route table |
| `GET /api/fundamentals/storage` | Entities (Europe, countries) with gas-year series, band, comparisons |
| `GET /api/desk/today` | Extended per E.5 |
| `GET /api/portfolio/map-situation` | Extended for the map (below) |

### J.5 The map's "Our book" view
The map stays and gains what the owner asked. `application/map_situation.py` returns three relevance classes for network objects:

| Class | Contains | Drawn |
|---|---|---|
| **Ours** | Delivery points, hubs, terminals, storage sites and booked capacity of active contracts; expected cargoes with ETA and terminal; held slots | Full emphasis |
| **Reachable** | Every interconnection point and pipeline on a proven path from an "ours" hub to a neighbouring hub (≤ 2 crossings), with its tariff and available capacity | Medium emphasis |
| **Opportunity** | The legs of any actionable opportunity (path highlighted, the margin as a label on the far hub); a watch-state opportunity as a thin outline | Pops out; selecting it opens the opportunity |

Everything else dims to the base map in this view. Outages intersecting any of the three classes are marked "touches our book". Client: `app/mapBook.ts`, `MapBookPanel.tsx`, `app/routeEmphasis.ts`.

---

## K. Implementation plan

### K.0 The reliability gate (applies to every package that puts a number on a page)
Nothing ships as a page or panel unless all four hold, and the package's pull request shows them:

1. **Golden cases**: a hand-computed worked example per calculation (spreadsheet-reproducible, checked in as a fixture with the arithmetic in the test's docstring), matching the engine to the stated rounding. The examples in this document become the first fixtures.
2. **Reconciliation**: the legs sum to the headline for every object the engine produces in the demo and public-data runs (property test).
3. **Demo end to end**: the browser sweep opens the page on the demo desk, reads the headline figure from the DOM (`data-figure`) and compares it with the API's value and the golden case.
4. **Real public data end to end**: the same view on a store filled only from public sources (ENTSOG tariffs, GIE AGSI/ALSI, ECB, benchmark rates, EIA, operator tariff documents captured as fixtures with their hashes): every figure is either a verified number traceable to the publication, or an explicit "missing/needs entitlement" state. No simulated value appears. A reviewer signs the comparison of three figures against the source documents.

A package failing 4 ships its engine but not its page.

### K.1 Work packages (prefix CP; each sized for one implementer)

| CP | Scope | Main files | Depends | Acceptance |
|---|---|---|---|---|
| **01 Normalisation and forward FX** | `fx_forward` (D.5), series/value normalisation service, tolerance; `/api/market/fx-forward`, `/api/market/normalise` | new `domain/market/fx_forward.py`, `application/market_normalisation.py`; `domain/market/units.py`, `interest_rates.py`, `fx_fixings.py`; `api/routes/public/market.py` | — | Golden: the NBP/TTF example to 3 dp; day counts per currency; refusal beyond 24 months without licensed forwards; licensed forward overrides; metadata present on every result |
| **02 Instrument catalogue and picker** | Hierarchical catalogue endpoint; `InstrumentPicker` (hub → kind → tenor, search grammar, presets) | `api/routes/public/spread_lab.py` (catalogue), new `components/ui/InstrumentPicker.tsx`, `app/model/instrumentPicker.ts` | — | Unit: "ttf jan27", "nbp m+1" resolve; ≤ 12 items visible per level on the demo store; keyboard complete; 390 px usable |
| **03 Chart standard** | Extend `Chart`: band, ghost series, end labels, reference rules, seasonal (gas-year) axis, two aligned panels, small-multiples wrapper, percentile strip, waterfall; touch readout | `components/ui/charts/Chart.tsx`, `chartModel.ts`, `charts.css`; new `SmallMultiples.tsx`, `Waterfall.tsx`; `application/reports/charts.py` (band, term structure) | — | Unit on the model per F.2 (band label never exceeds years held); visual checks in the sweep; axe clean |
| **04 Storage history and fundamentals read** | Backfill AGSI history to ≥ 5 complete years per country (terms check first); band statistics; `/api/fundamentals/storage` | `ingestion/gie_facilities.py` / storage ingestion, `api/routes/public/storage.py`, `fundamentals.py`, new `application/fundamentals_storage.py` | terms check | Public-data gate: three countries' fill on three dates match AGSI; band from exactly the labelled years; missing country stated |
| **05 Display preferences** | Preference keys; `Figure` secondary value; aggregate conversion line; forbidden-conversion list enforced | `domain/settings/preferences.py`, `components/PreferencesPanels.tsx`, `components/ui/KeyFigure.tsx`, `app/format/*` | 01 | Unit: G7 objects never convert; hover shows rate, date, method; export columns present |
| **06 Guidance kit** | `PageIntro` (purpose line), readiness checklist, example loader, first-use hints; purpose lines for all tasks | new `components/ui/PageIntro.tsx`, `ReadinessChecklist.tsx`; `components/ui/EmptyState.tsx`; i18n | — | Sweep: every commercial task has `[data-purpose]`; empty states meet I5; no `type=file` accepting JSON on commercial pages |
| **07 Assumption sets, firm marks, valuation snapshot** | Tables, APIs, audit, the snapshot reader used by all evaluators | new `db/models/commercial_assumptions.py`, migration; `application/valuation_snapshot.py`; `api/routes/public/market.py`, new `assumptions.py` | — | Role access tests; a snapshot replays to identical figures; firm marks never class "sourced" |
| **08 Opportunity core** | Domain model, store, ranking, states, false-positive controls, dedupe/persistence, dependency keys, list/detail/state/case APIs, permission | new `domain/opportunities/`, `application/opportunities/`, `db/models/opportunities.py`, `api/routes/public/opportunities.py`; `security/authorization.py`; generalise `domain/market_intelligence/opportunity_engine.py` | 07 | Property: legs reconcile; thresholds, staleness and hysteresis each unit-tested; scope test (no cross-book leak); simulated never mixes |
| **09 Evaluators I** | L (locational, forward and intraday), C (held capacity), G (hedge gap), S (sell-down), E (event exposure) | `domain/opportunities/{locational,capacity,hedge_gap,sell_down,event}.py`; readers over `route_cost`, `limits_service`, `daily_balance`, `map_situation` | 01, 08 | Golden: the TTF→THE example incl. the 80 % load-factor falsifier; reliability gate 1–4 |
| **10 Evaluators II** | T (storage), R (re-route through the resource pool, single currency first) | `domain/opportunities/{storage,reroute}.py`; `domain/route_cost/resource_pool.py` (typed money on the result) | 08 | Golden: the Sum/Win example lands in "watch"; R equals the optimiser's Δ margin |
| **11 Terminal tariff register** | Table, resolution order, review flow, connector with change detection, wave 0 operators wired; Admin review UI | `ingestion/lng_terminal_tariffs.py`, new `db/models/lng_terminal_tariff.py`, `api/routes/public/lng.py`, `components/SourceCenter.tsx` (coverage/review) | — | Public-data gate: captured Fluxys and Elengy documents reproduce the registered values; a changed hash raises one attention item; candidate rows price "indicative" only |
| **12 Voyage and cargo model** | `freight_route` table and shipped routes; voyage model; FOB formula; the full chain; `/api/lng/cargo-economics`; evaluators D and A | new `domain/lng/voyage.py`, `domain/lng/cargo_economics.py` (composing `domain/portfolio/lng_bid.py`), `ingestion/eia.py` (futures series, after terms check) | 01, 07, 11 | Golden: section C.3 to the cent; DES and FOB cargoes land in one table; missing hire → blocked with the reason; lifting vs full cost both shown |
| **13 Evaluation scheduling** | Job-runner triggers and debounce; on-write triggers; the outbox subscription seam (interface only until M4) | `application/jobs.py`, `application/opportunities/schedule.py` | 08 | A price import leads to a re-evaluation within the debounce; a failing evaluator raises an admin alert only |
| **14 Deals page** | Opportunities list, detail, empty state, navigation change to three tasks, redirects, registry update, case hand-off; delete Evaluate/Optimise/Routes pages | `app/navigation/modeNavigation.ts`, `app/experience/roleComposition.ts`, new `components/opportunities/*`, `DecisionWorkspace.tsx`, `PortfolioWorkspace.tsx`, `DecisionCasePanel.tsx` | 06, 08, 09 | Old deep links land on Opportunities; one primary action; day-one empty state on an empty store; a case opened carries the frozen legs; I4, I5 |
| **15 Workbench** | Adjust panel and the four typed forms (location, storage, cargo, allocation); save as evaluation | `components/opportunities/Workbench*.tsx` | 10, 12, 14 | Editing volume/product/load factor recomputes and shows the delta; no JSON; tablet usable |
| **16 Research → Spreads** | New workbench on the picker, normalisation and chart standard; rule test fold; flows to Deals and Reports; delete the strategy client | new `components/research/SpreadsWorkbench.tsx`; `api/routes/public/spread_lab.py` (accept mixed units via normalisation); delete `components/strategy/*` | 01, 02, 03 | NBP–TTF runs with mixed units and states the FX; route-cost overlay equals the route engine; opens populated |
| **17 Research → Fundamentals** | Storage, LNG, flows, balance, gas-for-power tabs | new `components/research/FundamentalsWorkbench.tsx`; `NweBalancePanel.tsx`, `GasForPowerPanel.tsx` re-homed | 03, 04 | Country multiples with correct bands; export carries units |
| **18 Research → Cargo & netback; Research clean-up** | The study view; delivered-spread series; remove Data and Assistant; Reports "add exhibit" | new `components/research/CargoStudy.tsx`; delete `ResearchDataWorkspace.tsx`, `AgentsWorkspace.tsx`, `LngEconomicsPanel.tsx` | 12, 16 | HH–TTF both views agree to rounding; removed pages redirect |
| **19 Today** | Composition E; server read extended; filter strip removed | `components/TodayScreen.tsx`, `today.css`, `MarketCockpit.tsx`, `application/desk_today.py`, `app/experience/roleComposition.ts` | 03, 04, 05, 08 | Per demo identity the row order matches E.3; no empty panel; no context controls; phone ≤ 5 elements |
| **20 Prices** | Board + term structure + spread by delivery month; remove `TraderDeskPanel`, bars, feed | `components/PriceCharts.tsx`, `MarketTerminal.tsx`, delete `TraderDeskPanel.tsx`, `IntradayDecisionFeed.tsx` | 01, 03 | No bar-series spread; spread uses forward FX and names it; existing board tests pass |
| **21 Map "Our book"** | Three relevance classes; opportunity paths; outage "touches our book"; remove the decision rail and pool props | `application/map_situation.py`, `app/mapBook.ts`, `MapBookPanel.tsx`, `app/routeEmphasis.ts`, `NetworkWorkspace.tsx` | 08, 09 | Demo: a contract's hub, its reachable IPs and one opportunity path are emphasised; selecting the path opens the opportunity |
| **22 Sweep, gates, documents** | Delete dormant client code and i18n keys; unregister deferred routes; extend the browser sweep with number checks; update manuals, `UX_REFERENCE.md`, this document's status | `scripts/uat/browser_workflow_smoke.mjs`, `clients/web/src/i18n/*.json`, `api/route_profiles.py`, `docs/` | all | Sweep green in EN and ZH at four viewports for five identities; i18n parity; no orphaned keys |

### K.2 Order and parallelism

| Wave | Packages | Parallel? |
|---|---|---|
| 1 Foundations | CP-01, 02, 03, 04, 06, 07, 11 | Yes: no shared files (01 and 07 touch `market.py` routes: append-only, agree the order) |
| 2 Engines | CP-05 (after 01); CP-08 (after 07) → CP-09, CP-10 in parallel; CP-12 (after 01, 07, 11) | Three tracks |
| 3 Pages | CP-14 (after 08, 09) → CP-15; CP-16 → CP-18; CP-17; CP-19; CP-20; CP-13 | Five tracks; `roleComposition.ts` and `modeNavigation.ts` are edited by CP-14 first, then CP-19 and CP-16–18 append |
| 4 | CP-21; CP-22 | Serial |

Shared-file rules of basis 1 stand (i18n key prefixes per package; only the gate packages edit the browser sweep).

A sensible first release for owner testing is wave 1 + CP-08, 09, 14, 16, 19, 20: opportunities for location, hedge gap, sell-down and events; Spreads; the new Today and Prices. The cargo model (CP-11, 12, 15, 18) is the second release.

### K.3 Earlier packages (basis 1)

| WP | Status | Note |
|---|---|---|
| WP-01–06 | Kept | Gates, registry, formatting, strip. The strip gains opportunity items (must-act lane). |
| WP-07 Today by role | **Superseded** by CP-19 | |
| WP-08 Plumbing off the desk | Kept, strengthened | Context strips are removed, not reduced to a word. |
| WP-09 Prices slimming | **Superseded** by CP-20 | Product strip removed rather than folded; charts replaced. |
| WP-10 Network slimming | Changed | Capacity book goes to Admin and to contracts (not Routes); decision rail removed (CP-21). |
| WP-11 Book: Position, Limits | Kept | |
| WP-12 Book: Delivery, Planning | Kept | Delivery gets its own day picker (the shared context strip is gone). |
| WP-13 Deals: Evaluate, Routes, Review | **Superseded** by CP-14/15 | Only the Review slimming survives, inside CP-14. |
| WP-14 Contracts | Changed | Slimming kept; LNG sandbox deleted, not moved; JSON/text import leaves the UI; capacity and storage as contract kinds. |
| WP-15 Research slimming | **Superseded** by CP-16–18 | |
| WP-16 Settings/Admin split | Kept | Receives commercial settings (assumptions, tariff review, thresholds). |
| WP-17 Task-row shortlist | Changed | Modes now have 3–4 tasks; "More" needed only where a role's shortlist crosses modes. |
| WP-18 Phone views | Changed | Trader phone landing per E.4; "continue on desktop" wrappers only for contract entry and the workbench. |
| WP-19, WP-20 | Kept | WP-20(a) price-move alert and (c) Today figures are now inputs to the opportunity lanes. |

---

## L. Decisions for the owner

| # | Decision | Recommendation |
|---|---|---|
| L1 | **Delete the strategy lifecycle, dataset builder and agents console from the product now**, keeping only their backends dormant. | Yes. They are the largest part of "I have this feature"; none serves a daily desk decision; the simple rule test inside Spreads covers the analyst's real question. Re-entry conditions are in I.3. |
| L2 | **May the firm's own marks make an opportunity "actionable"**, or only executable licensed quotes? | Marks → "indicative" by default, with an organisation setting to accept them. A desk without a connected feed still gets ranked opportunities, honestly labelled; nothing reads as a market price. |
| L3 | **Freight and FOB without a licence**: ship the cargo model with the firm's assumption sets (hire, boil-off, fees) and an example formula, or wait for a licensed assessment. | Ship with assumption sets, marked on every row and in the headline, blocked where the firm has entered nothing. A cargo desk always has a view on hire; the product should do the arithmetic properly around it. |
| L4 | **Henry Hub forward**: use the public futures series for the first four months (after the terms check) and require the customer's NYMEX entitlement beyond, or spot as a proxy. | Futures 1–4 where terms allow; beyond that, entitlement or the firm's marks; spot proxy only as "indicative". |
| L5 | **Default thresholds**: minimum margin 0.10 EUR/MWh, minimum value EUR 10,000, at most 7 per lane, two-evaluation persistence. | Accept as defaults; organisation-tunable; review after one month of the dismissal and case-outcome statistics. |
| L6 | **Terminal coverage order**: NW Europe hubs first (Zeebrugge, Montoir, Fos, German auctions; Gate, Dunkerque, Grain and the Welsh terminals as "your terms"), then Iberia, Italy, the Baltic and Poland. | Yes; and the owner's knowledge of which exempt terminals publish list prices decides which move into the public wave. |
| L7 | **Reporting currency scope**: any ECB-listed currency (including CNY) for reporting views, with native always primary on trading views. | Yes; conversion at the ECB reference rate of the value date, forward by interest parity only for EUR, GBP and USD (the currencies with held benchmarks), spot with a stated limitation for others. |

---

### Critical Files for Implementation
- /home/user/EurogasNexus-int/src/eurogas_nexus/domain/market_intelligence/opportunity_engine.py (existing three-state opportunity engine to generalise into the opportunity core)
- /home/user/EurogasNexus-int/src/eurogas_nexus/domain/route_cost/market_area_graph.py (proven-path pricing with exit/pipeline/entry legs; with `route_adjacency.py` and `/home/user/EurogasNexus-int/src/eurogas_nexus/ingestion/entsog_tariffs.py`)
- /home/user/EurogasNexus-int/src/eurogas_nexus/domain/portfolio/lng_bid.py (downstream cargo arithmetic to compose; with `/home/user/EurogasNexus-int/src/eurogas_nexus/ingestion/lng_terminal_tariffs.py` and `/home/user/EurogasNexus-int/src/eurogas_nexus/api/routes/public/risk.py`)
- /home/user/EurogasNexus-int/src/eurogas_nexus/domain/market/units.py (unit and price conversion authority; forward FX builds on `fx_fixings.py` and `interest_rates.py` beside it)
- /home/user/EurogasNexus-int/clients/web/src/app/navigation/modeNavigation.ts (task set and redirects; with `/home/user/EurogasNexus-int/clients/web/src/app/experience/roleComposition.ts`)
- /home/user/EurogasNexus-int/clients/web/src/components/ui/charts/Chart.tsx (the one chart primitive to extend; replaces `/home/user/EurogasNexus-int/clients/web/src/components/strategy/StrategyLabCharts.tsx` and the bar spread in `/home/user/EurogasNexus-int/clients/web/src/components/PriceCharts.tsx`)
- /home/user/EurogasNexus-int/src/eurogas_nexus/application/desk_today.py (server-assembled Today read to extend; client in `/home/user/EurogasNexus-int/clients/web/src/components/TodayScreen.tsx` and `/home/user/EurogasNexus-int/clients/web/src/components/MarketCockpit.tsx`)
- /home/user/EurogasNexus-int/src/eurogas_nexus/api/routes/public/spread_lab.py (flat series catalogue and the mixed-unit refusal to replace)