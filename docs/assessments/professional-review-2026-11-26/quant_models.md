# Quant and model review: are the numbers right and defensible?

Reviewers (personas): (1) a quant analyst on a gas/power desk, (2) an independent model validator (MRM),
(3) a structurer pricing storage, swing, capacity and LNG optionality, (4) a product controller doing IPV.
Code reviewed: `/home/user/EurogasNexus-merge/src/eurogas_nexus` (domain/, application/, optimization/).
Checks were run read-only with small Python scripts in the scratchpad (no database).

## 1. Verdict in five sentences

The arithmetic building blocks are careful: unit conversion, the DST-aware gas day, the forward-curve
bootstrap, capacity-tariff-to-€/MWh conversion, the LNG cargo chain and the resource-pool solver are correct
in the cases I tested, and they are better documented than most in-house spreadsheets. The risk and valuation
layer is a set of indicators, not a risk system. Historical VaR runs on a single rolling price series per hub
that mixes products, MtM is undiscounted and converted at spot FX, there is no P&L attribution, and credit
covers current exposure only. Nothing values optionality: there is no storage extrinsic value, no swing/ToP
valuation, no options, no volatilities or correlations, and no hourly power shaping. That is the core of a
structurer's and a quant's job, so personas 1 and 3 would keep their Python/Excel models and use this
product for the fundamentals, cargo netbacks, tariff lookups and the position ladder. Persona 2 (MRM) and
persona 4 (product control) would block any figure here from being used as an official mark, VaR or P&L,
mainly because of three concrete errors (section 3), the absence of model governance (every method note is
`"drafted; awaiting risk review"`) and the fact that ladder, VaR and MtM are not stored, so yesterday's
numbers cannot be reproduced.

## 2. Per persona

### Quant analyst (gas/power desk)
**Daily job:** refresh curves and fundamentals, run the balance model, update the spread and seasonal
models, explain the overnight P&L and risk moves, and answer the structurer's and the traders' questions.
**What works:** the units authority (`domain/market/units.py`: 1 MWh = 34.1214 th = 3.41214 MMBtu, FX always
explicit; I checked 100 p/th at 0.85 GBP/EUR = 40.14 €/MWh), the gas-day calendar (23/24/25 h verified for
27/28 Mar and 30 Oct 2027), the curve bootstrap weighted by hours, the spread lab with roll handling and
next-close execution, and the forward balance with its own backtest MAE.
**Gaps (must):** a curve built from quotes taken at the same time; returns computed per contract (constant
maturity or per-contract) for VaR; a vol surface and correlations; a weather-driven daily balance (today the
D+1..D+14 balance assumes *normal weather*, `forward_balance.py:17-20`, while the ECMWF demand model sits
unused in `domain/research/weather_demand.py`). **Should:** daily curve shaping (weekday/weekend, within the
month), discounting, and EOD snapshots. **Redundant:** the "strategy lab" backtest (see 3.4) duplicates the
spread lab and is less correct.
**Organisation:** one "Curves & Risk factors" workspace (curve, its quotes and their timestamps, return
series, vols), separate from the trader's screens.

### Independent model validator (MRM)
**Daily job:** keep the model inventory, validate new and changed models, monitor VaR backtesting exceptions,
and sign off limitations. **What works:** method notes carry includes/excludes (`domain/risk/method_notes.py`);
the backtest engine is versioned (`backtest-engine/1`, `/2`); opportunity valuations are frozen and
replayable (`application/valuation_snapshot.py` `freeze_snapshot`/`ReplayReader`); and there is a code
fingerprint (`application/calculation_manifest.py`). **Gaps (must):** a model inventory with owner, tier,
approval status and validation date for VaR, MtM, curve, credit and the cargo model; VaR backtesting
(hypothetical P&L against VaR, Kupiec/traffic-light); persisted EOD ladder/VaR/MtM with their inputs;
challenger models; and a change log tying a model version to the numbers it produced. None of these exist
(`docs/` has no model-risk document; `REVIEW_STATUS = "drafted; awaiting risk review"`, `method_notes.py:23`).
**Organisation:** a "Model register" admin page that lists each engine, its version, its notes and its
validation evidence. A new page is justified here (AGENTS rule 9) because MRM needs it to sign off.

### Structurer (storage, swing/ToP, capacity, LNG optionality)
**Daily job:** price a storage lease, a swing or take-or-pay supply deal, a capacity booking or a DES/FOB
cargo with diversion and cancellation rights, and produce intrinsic value, extrinsic value, Greeks and a
hedge. **What works:** the LNG chain (`domain/lng/cargo_economics.py`) is a correct deterministic
netback, with lifting cost (fee sunk under ToP), terminal ranking and a delivered-versus-netback check that
reconciles. The storage spread opportunity (`domain/opportunities/storage.py`) uses bid/ask, fuel and
financing like a desk sheet does. The storage DP (`optimization/storage.py`) gives the correct intrinsic
value on a monthly price strip. **Gaps (must):** storage extrinsic value (rolling intrinsic, spread-option,
or LSMC on a spot-forward model), ratchets (explicitly "not modelled", `opportunities/storage.py:23`),
swing/ToP valuation with ACQ, DCQ, make-up and carry-forward (none: `optimization/contract.py` is a
single-day greedy), volatilities, correlations, option Greeks, and the time value of cancellation and
diversion options on US FOB cargoes. **Organisation:** a "Deal pricer" workspace with one template per
structure (storage, swing, capacity, cargo), each showing intrinsic value, extrinsic value, Greeks and the
delta hedge by tenor, which then feeds the position ladder.

### Product controller (IPV)
**Daily job:** source independent marks, compare them with the desk's marks, set reserves (bid/offer,
liquidity, model), explain P&L and sign off. **What works:** price resolution has an explicit, documented
precedence (`domain/market/price_resolution.py`): an in-date market price beats a firm mark, which beats a
derived price. Every mark carries its method (quoted/derived/flat/front) and its as-of. Simulated prices
are kept out of marks. **Gaps (must):** an official EOD close (the curve is "latest quote in 10 days",
3.2), a bid/ask-aware close with bid/offer reserves, IPV variance reports (desk mark against an independent
source per tenor, with thresholds), P&L attribution (new deals / curve move / time decay / FX / carry), and
discounted MtM. P&L today is imported, not computed (`method_notes.py` `pnl_snapshot`: "not recomputed
here"). **Organisation:** a "Close & IPV" workspace for finance, not the trader's Today page.

## 3. Engines, method, correctness (WRONG = bug or wrong formula)

### 3.1 VaR (position ladder): WRONG, in three ways
Method (`domain/portfolio/position_ladder.py:340-385`): 1-day 95 % historical simulation. The net MWh per
hub, summed over *all* months in the horizon, is multiplied by each day's change in one close series per
hub. Days are equally weighted, over up to 400 calendar days, with at least 20 scenarios required.

- **WRONG 1: day-ahead and month-ahead mixed in one return series.** `application/position_inputs.py:654-660`
  builds `closes[hub][day]` from the month-ahead close, *else the day-ahead close for that day*. The return
  is then taken across the seam. Minimal example: MA flat at 30 every day, with the DA (35) used on 1 day in
  10 where MA is missing. `historical_var({"NBP":372000}, ...)` returns **1,860,000** with zero true price
  movement (scratch check). The same happens wherever DA history is longer than licensed MA history: VaR
  then runs on day-ahead volatility applied to a 12-month strip, and jumps at the seam.
- **WRONG 2: roll jumps in the return series.** The month-ahead series is a *rolling* product.
  `daily_rows` carries `period_start_utc`, but the VaR ignores it, so each roll's front/second-month spread
  is booked as a one-day price move. (The spread lab handles rolls correctly,
  `research/spread_analysis.py:363`, so the fix exists in the code base.) In a synthetic example with
  ±4 €/MWh autumn/spring rolls, VaR rose 5 %. On TTF, real Oct→Nov or Mar→Apr rolls of several €/MWh fall
  exactly in the tail.
- **WRONG 3: index-priced contracts treated as flat-price exposure.** Floating contracts lose only their
  *price* (`position_inputs.py:563-569`); their volume stays in `net_mwh`, in `hedge_ratio`
  (`position_ladder.py:103-108`) and in VaR. A TTF-MA-indexed purchase has no flat-price risk. The ladder
  shows it as a 31,000 MWh long that is "0 % hedged" (checked), and a trader who "hedges" it by selling
  futures creates the open short the ladder then reports as flat. The hedge-band check
  (`risk/limits.py` `_check_hedge_policy`, `opportunities/hedge_gap.py`) inherits the error. The fix is to
  carry the index exposure (basis and averaging-period risk) as a separate leg, not as flat price.
- Simple but documented: there is a single price factor per hub, so the Samuelson effect (back months move
  less than the front) is ignored and long-dated books are overstated. VaR is refused when a hub has offsetting months.
  `min_observations = 20`: with 20–39 scenarios the "95 %" VaR is the single worst day (index
  `floor(0.05n)-1 = 0`). There is no holding-period scaling, no stressed VaR, no expected shortfall and no
  VaR backtest. Several sources for the same hub/day overwrite each other in arrival order.
- Tests: `tests/unit/test_position_ladder.py` has 10 tests, 3 on VaR, and no golden case for mixed tenors or rolls.

### 3.2 Forward curve and marks: method correct, inputs not
`domain/market/forward_curve.py`: months as quoted. Longer products are bootstrapped shortest-first, and
the residual is spread over the open months **weighted by delivery hours** (Q1 = 744/672/743 h). There is
an optional seasonal shape and no extrapolation. A product fully covered by shorter quotes is checked and
flagged at 0.5 %. I verified Jan 32 / Q1 30 → Feb = Mar = 28.948 exactly. This is the right first-pass
method.
- **Asynchronous quotes (WRONG for a mark).** `curve_quotes` (`application/position_inputs.py:52-140`) keeps
  the *latest quote per window over 10 days* (`CURVE_QUOTE_LOOKBACK_DAYS = 10`), across sources, and
  ignores price type (bid/ask/last/settlement). A today's Jan and a nine-day-old Q1 produce Feb/Mar
  residuals that are just the price move between the two timestamps. The only guard is the ±50 %
  "far from product" warning. An IPV close needs one snapshot time, and settlement or a bid/ask mid.
- Missing months are filled **flat at the hub's latest close** (`position_inputs.py:667-678`), and that close
  can be a day-ahead price (3.1). So a winter month can be marked at a summer DA price. The method says
  "flat", but product control would not accept it.
- Product dates come from `period_start_utc.date()` (UTC). A product stored with a CET-midnight start
  (`…-12-31T23:00Z`) shifts by a day. That is right only if every connector stores gas-day boundaries.
- Missing: no arbitrage-free construction (no smoothing/max-smoothness spline, no bid/ask bounds), no
  daily shaping (weekday/weekend, BOM/WE), no cascading of seasons → quarters → months as exchange
  products cascade, and no price-type weighting.

### 3.3 MtM, discounting, FX, P&L
MtM = Σ (mark − price) × MWh × spot ECB FX (`position_ladder.py:301-337`). It is **undiscounted**, and
forward FX is ignored although `domain/market/fx_forward.py` (CIP from SONIA/€STR/SOFR) exists and is used
only by opportunity snapshots. At about 2–3 % rates, a 24-month book is overstated by about 2–5 % at the
long end. GBP/EUR at spot rather than forward is a few tenths of a percent per year. No payment-date
convention (EFET 20th of M+1). P&L: `pnl_snapshot` is imported, not computed. The Today read's "day P&L" is
net 12-month position × change between the last two closes (`method_notes.py:152`), so it inherits 3.1
WRONG 1/2. There is no P&L attribution and no realised/unrealised split computed in-house.
`domain/economics/financing.py` is simple interest (ACT/365F, ACT/360), which is correct as far as it goes.

### 3.4 Strategy-lab backtest: not a backtest (WRONG as labelled)
`domain/strategy_lab/evaluation.py:338-347` and `backtest/engine.py:466-476`: paper P&L = Σ
(reference price *at the decision time* − weighted resource cost) × target quantity. P&L is therefore known
at the moment of decision, so no market outcome is realised. Every allocation that passes the minimum-margin
filter is a "hit", and drawdown and hit ratio are almost meaningless. The as-of evidence selection is
careful (no look-ahead in *inputs*), but the P&L definition makes look-ahead irrelevant: there is no
"future" in it. The component score is capped at a hard-coded 5 GBP/MWh (`evaluation.py:402`). Everything
is in GBP, including continental desks. **Remove it or relabel it "decision-time margin replay".**

### 3.5 Spread lab: mostly right; two flaws
`domain/research/spread_analysis.py`: z-score/threshold rules with next-close execution (no look-ahead),
roll exclusion for contracts longer than 2 days, energy-weighted P&L, costs on position change, AR(1)
half-life, and a 30 % out-of-sample tail. Good.
- **WRONG (DA legs):** a day-ahead series is a new delivery every day (`ROLL_EXCLUDE_MIN_DAYS = 2`, comment
  "re-traded every close"), yet (a) the P&L credited is DA(t) − DA(t−1), which is not a tradable P&L
  because a DA bought at t−1 delivers on day t and is settled against within-day/cash-out, not against
  DA(t), and (b) costs are charged only when the signal changes, although a DA position pays bid/offer on
  both legs every day. Net: DA spread backtests overstate P&L and understate costs.
- Simple: in-sample z-score parameters, no parameter-search penalty or deflated Sharpe, Sharpe on money P&L
  × √252, no survivorship issue (fixed hubs).

### 3.6 Units, calorific value, gas day: correct
Factors match IT-BTU. `volume_to_mwh` requires an explicit GCV, but there is **no reference-condition
conversion** (GB 15/15 °C against EU 25/0 °C differ by about 5 %; the 11.0 kWh/m³ desk default is
EU-basis). There is no GCV↔NCV helper, and `power/gas_for_power.py:mwh_th_to_mcm` defaults to GCV 11.0,
against the module's own "never a default" rule. The spark/dark spreads are correct *if* η is quoted on the
GCV basis (EF 0.184 t/MWh GCV is consistent). The UI must say so, because desks quote η on the LHV basis
(55–60 %) and a 50 %-LHV input understates gas cost by about 10 %. `fuel_switch_gas_price` ignores the
emission factors passed by the caller and uses the module constants (minor).

### 3.7 Route cost and tariffs: correct conversion, wrong default for prompt arbitrage
`route_cost/tariff_units.py` is right (golden 7.06 €/(kWh/h)/a → 0.8059 €/MWh) and handles y/q/m/d/h
periods, kWh/h against kWh/d capacity and load factor. However, Spreads/Today price every route on **firm
yearly capacity at 100 % LF** (`application/spreads_board.py:101-111`, product `"ANNUAL"`). For a DA or MA
spread that is not the marginal cost. The marginal cost is the daily/monthly reserve price with its NC TAR
multiplier and seasonal factor (typically ×1.0–3.0), or zero if the capacity is already booked (sunk).
TAR-2 booking layers exist; the default should follow the tenor of the spread. **Missing:** flow-based
commodity charges and fuel gas / gas-in-kind on pipeline legs (no such term in `route_tariff_cost.py`),
interruptible pricing with a probability of interruption, auction premia above reserve, and 23/25-hour
days in hourly products (24 h assumed).

### 3.8 LNG cargo economics: correct deterministic netback
Formulas check out: q_del = q_load(1 − bor·d_laden) − heel; delivered×sent_out = margin×q_del reconciles;
the FOB netback converts properly. 11 golden tests exist. Simplifications: ballast fuel is valued at the FOB
price; a canal is charged once on round voyages (Panama/Suez ballast is paid again); there is no time value
between FOB payment and sale proceeds; no forced-BOG/fuel-oil split; and laytime/demurrage terms such as
"half rate weather" are text only, with 36 h assumed when none is recorded (`application/lng_demurrage.py:491`).
A latent inconsistency: `option.other_total` is deducted in `netback()` but not in `delivered`
(`cargo_economics.py:445` against `:488`). It is unused today. **Missing optionality:** HH-linked
cancellation as a spread option (TTF/JKM − 1.15·HH − fee), destination/diversion optionality, and arrival-
month uncertainty. `margin_low/high` uses only the neighbouring months' prices, which is not a distribution.

### 3.9 Storage: intrinsic only
`optimization/storage.py`: a deterministic DP on an inventory grid gives the correct intrinsic value. My
checks: 500 MWh / 12 periods takes 0.85 s; with step 30 and 100 MWh, grid snapping works. Problems:
**O(N²·T) with the default `inventory_step_mwh = 1.0`** (`api/routes/public/optimization.py:295`). A real
1 TWh facility has 10⁶ levels, so the computation is impossible, and the sandbox `periods` list is
unbounded, which allows a CPU denial of service. Each state also copies its whole decision path. No
ratchets, no discounting, no bid/ask, no rolling intrinsic, no extrinsic value. **A desk would value storage in its own LSMC or
spread-option model and use this only as a sanity check on intrinsic value.**

### 3.10 Swing / take-or-pay: missing
`optimization/contract.py` is a one-day greedy: the minimum take is placed first, and if demand is too low
the result is "infeasible". Real ToP is annual (ACQ), with make-up, carry-forward and a payment for shortfall
(take-or-pay), so the right answer is "take less and pay". Nothing values swing rights. `kinds.py` holds
min/max DCQ only as tolerances.

### 3.11 Network optimisers
- `optimize_resource_pool` uses a proper min-cost circulation with lower bounds (`optimization/circulation.py`). I
  checked an access-constrained case where greedy would give 10: the solver gives the optimum 19, and a
  loss-making minimum take is honoured (−10, "optimal"). Correct.
- `optimize_network_flow` (successive shortest paths with Bellman–Ford) is correct for its stated
  objective. However, a *mandatory* demand is not enforced: it only routes non-negative margins. A
  feasible-but-loss-making obligation is returned as **`infeasible`** with 0 served (scratch: supply at 30,
  tariff 2, required demand at 31 → "infeasible"). The portfolio network passes `optional=True`, so this is
  latent, but the status conflates "unprofitable" with "infeasible". All are single-period: no linepack,
  storage coupling or intertemporal constraints, and field names are hard-wired to GBP.

### 3.12 Credit exposure
Current exposure = netted replacement (floored at 0) + receivables (last 50 days of sales) − collateral
(`domain/risk/limits.py:189-250`). It is clearly documented. It is conservative where EFET would net
payables. There is **no PFE** (no simulation, no add-on), no wrong-way risk, no CSA/margin thresholds, and
index-priced sales (the most common receivable) are "unvalued", which makes the line "incomplete" exactly
where exposure is largest.

### 3.13 Stress / shocks, hedge planner
Tenor shock = net MWh × the user-entered shock per hub-month (`position_ladder.py:211-256`). It is correct
and honest about unshocked months, but there are no historical scenarios (2021–22, the Freeport outage,
Norwegian outages), no correlated multi-hub shocks, no vol shocks and no reverse stress. The hedge "planner"
is a volume-band check (`opportunities/hedge_gap.py`): no minimum-variance or cross-hedge ratios, no
proxy-hedge basis, and it inherits 3.1 WRONG 3.

### 3.14 Balance forecast, weather, ML tooling
Forward balance: seasonal normal plus a 14-day anomaly (daily), and monthly a + b·HDD at the 30-year normal,
with a range from backtest MAE. It is honest and validated against its own history, but it is
**not weather-forecast-driven**, a single linear HDD term (no gas-for-power or price elasticity), and has no
skill score against a persistence or climatology benchmark in the product. The research weather module
(ridge regression with expanding folds, point-in-time vintages, `application/nwe_model_validation.py`) is
methodologically sound but is not wired into the desk balance. ML dataset tooling (`research/leakage.py`,
`resampling.py`: no global ffill, bounded carry-forward, `available_at`) is good practice.

## 4. What the desk would still do in Excel/Python, and what is missing entirely

Kept outside: storage and swing valuation (LSMC / spread options / rolling intrinsic with ratchets), option
pricing (Black-76 with smile, Asian/averaging, spread options via Kirk or Margrabe), vol and correlation
estimation, daily curve shaping and arbitrage-free construction from broker and exchange quotes, PFE, VaR
backtesting, P&L attribution, IPV variance reports and reserves, and the official EOD curve.
Missing entirely: **power** (hourly/15-min shaping, peak/base, spark/dark *spread options*, PPA valuation
with capture and profile risk, cross-border capacity/FTR valuation, cascading of power products), **options**
(no Black-76, vega, gamma), **correlation** (no matrix, no multi-factor model), **cascading** of
Cal → seasons → quarters → months as positions, **constant-maturity/per-contract return series**, and
**model governance artefacts**.

## 5. Structural limits

1. No EOD close or COB snapshot: ladder, MtM and VaR are computed live and not persisted
   (`api/routes/public/portfolio.py:197-235`), so a past VaR or MtM cannot be recomputed. Only opportunity
   snapshots are frozen and replayable.
2. One price series per hub (`closes[hub][day]`) is the data model behind risk. A risk-factor model
   (contract × tenor bucket × price type) is an architectural change, not a page fix.
3. Positions carry volume and a fixed price, with no price-formula/index object, so index, formula and
   oil-linked exposure cannot be decomposed into deltas.
4. Currency hard-wiring (`*_gbp_mwh` in optimizers and the strategy lab) is unsuitable for continental
   books.
5. Pure-Python solvers (DP, Bellman–Ford) cannot do LSMC or multi-period network LPs at scale without a
   reviewed numerical stack (NumPy/HiGHS), which AGENTS rule 5 requires an ADR for.

## 6. Top 10 changes (priority order)

1. Fix VaR inputs: build return series per contract or constant-maturity, never splice DA into MA, pick one
   source per hub, require 250 observations, and add ES and stressed VaR. (Feature; blocker for any risk use.)
2. Treat index- and formula-priced legs as index/basis exposure, not flat price, in ladder, hedge ratio,
   hedge band and VaR. (Feature; blocker.)
3. Build the curve from a single COB snapshot of settlements or bid/ask mids, store it as the official
   curve, and stop flat-filling with day-ahead. (Feature.)
4. Persist an EOD ladder/MtM/VaR run with its inputs manifest (reuse `freeze_snapshot`). (Feature.)
5. Discount MtM (€STR/SONIA/SOFR curves) and use forward FX, which the code already has. (Config/feature.)
6. Relabel or remove the strategy-lab "backtest". Fix DA-leg P&L and daily costs in the spread lab. (Feature.)
7. Set the default route capacity product by spread tenor (DA → daily product with multiplier; booked
   capacity sunk), and add commodity charges and fuel gas. (Feature.)
8. Add a model register: owner, version, approval, validation date, VaR backtesting with exceptions and a
   traffic light. (Feature; required by MRM.)
9. Add storage extrinsic value (rolling intrinsic first, then LSMC) with ratchets, and swing/ToP valuation
   with ACQ/make-up. Cap storage DP grid size (bounded `periods`, minimum step relative to capacity).
   (Architectural, needs a numerical-stack ADR.)
10. Add P&L attribution and IPV variance reports. Add Black-76 options and Greeks, and a basic correlation
    matrix for multi-hub VaR and stress. (Feature.)
