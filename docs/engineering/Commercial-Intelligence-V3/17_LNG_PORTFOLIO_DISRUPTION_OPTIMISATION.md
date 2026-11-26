# 17 LNG portfolio disruption optimisation (LNG-3, LNG-4)

LNG-1 builds one cargo's plan ([12](12_LNG_CARGO_IN_TRANSIT.md)), and LNG-2 tells each role
when that plan changes. LNG-3 answers the desk's next question: **what should we do about
it?** A late cargo, or a curtailed pipeline supply, can be handled in several ways. Each way
has its own cost, value, flexibility and risk, and some of them move cargoes that were
running to plan. The engine lists the options, values each one against the plan as it stood
before the disruption, discards the options that break a hard constraint, marks the Pareto
frontier and names a default. A person then chooses.

**Decision support only (AGENTS.md rule 8).** The engine proposes and values options. A human
chooses. Choosing records the choice in an audited row. Nothing is booked, borrowed, bought,
traded, nominated or sent. **No AI is used.** The engine is plain Python: deterministic, with
no solver, no randomness and no model call. GOV-1's AI controls therefore do not apply, and
there is no entry in the AI-use register.

LNG-4 (section 9) turns the single default into options with their consequences, values each
one at its full cost, adds substitute supply from across the portfolio, reads demurrage from the
contract in its own currency, and links REMIT outages to the pipeline supply they curtail.

Architecture: ADR Decisions 36 and 37. Code:

- `domain/lng/disruption.py`: the engine (pure; no I/O and no clock).
- `application/lng_disruption.py`: loads the book, serves the reads, records the choice and
  runs the outbox consumer.
- `api/routes/public/lng.py`: the routes.
- `clients/web/src/components/CargoOptionsPanel.tsx`: the panel.
- LNG-4: `application/lng_demurrage.py` (demurrage by contract and the one FX function
  `_fx_rate`), `application/lng_substitutes.py` (substitute supply and the one transport-cost
  function `_transport_cost`), `application/pipeline_outages.py` (REMIT links and the override).

## 1 Sources read, and what each changed

All of these are public pages, read in November 2026, and nothing was sent to them. Fluxys,
Elengy and DET terms do not allow their figures to be reused, so **no tariff or capacity
figure from any terminal is stored in the product**. Every price, offer and slot term in the
tests and the demo is the desk's own entry and is labelled illustrative.

| Source | What it says (as read) | What it changed in the design |
| --- | --- | --- |
| Fluxys, [Unload, store and regas your LNG in Zeebrugge](https://www.fluxys.com/en/products-services/lng-unload-store-regas-zbb) | A standard slot bundles berthing and unloading, storage that declines linearly over about 10.3 days (40 tides), and send-out over the same period. Extra storage and send-out rights can be subscribed | The slot product is `SlotTerms`: N gas days, a send-out right R per day, and a storage right S with a `linear_decline` profile (end of slot day k: S x (N - 1 - k) / N). The two "buy" options buy extra send-out and storage |
| Fluxys, [Flexible send-out services](https://www.fluxys.com/en/products-services/lng-regasification) | Send-out comes as basic (bundled with slots, separable from D-10), additional, daily, stand-alone, and non-nominated interruptible send-out that uses other shippers' unused rights pro rata | The offer kinds `send_out` (firm) and `interruptible`. Interruptible send-out is reported per option as `interruptible_mwh` and is subtracted from the flexibility objective, because it is not firm |
| Fluxys, [Flexible storage services](https://www.fluxys.com/en/products-services/lng-flexible-lng-storage) | Basic storage comes with a slot and can be separated from D-10. Daily storage is sold up to D+60. "Gas in storage exceedings" is interruptible and charged per use | The offer kind `storage` (firm). Interruptible storage carries its own per-day price (`storage_price_eur_mwh_day`). The tank is checked against firm storage first, then interruptible |
| CEER, [Congestion management procedures at LNG terminals](https://ceer.eu/wp-content/uploads/2024/04/E10-LNG-11-03b_CMP-in-LNG_-12_Apr_2011.pdf) | Use-it-or-lose-it ex ante and ex post (for example, Spain at 80 %). Secondary markets: Belgium allows resale at or below the regulated tariff, full slots up to 20 days ahead, and unbundled services after that | A send-out right not used on its day is lost (the "wait" option loses the days before berthing). Releasing a spare slot is valued at the desk's indicative `release_value_eur_mwh` for the rights not yet nominated. That value is the desk's entry, never a tariff |
| S&P Global, [Atlantic LNG players sell regas slots amid unfavourable spreads](https://www.spglobal.com/energy/en/news-research/latest-news/lng/042326-atlantic-lng-players-sell-regas-slots-amid-unfavorable-spreads) | Holders sell prompt slots below cost on the secondary market. Spanish slots change hands without a premium over the regulated cost | The release value is indicative and can be low. A diversion that frees the held slot credits that value, and the panel says the value is indicative |
| Enagás, [LNG individual services](https://enagas.es/en/energy-transition/gas-network/logistics-services/individual) | In Spain, LNG is held in the virtual balancing tank (TVB), a delocalised service rather than storage at one terminal | A delivery obligation can be named at a terminal (LNG send-out there counts) or at a hub code (any supply at it counts). The Huelva obligation in the worked example is a firm daily delivery at the terminal |
| GIIGNL, [Notes to the MSPA template (2024)](https://giignl.org/wp-content/uploads/2024/04/Notes-to-MSPA-template-2024-CSG-1.pdf) | Allowed laytime, the daily demurrage rate and the boil-off rate are entered per cargo in the confirmation notice | Voyage terms are held per cargo (`lng_voyage_terms`), not per terminal |
| bp, [Master ex-ship LNG SPA (2019)](https://bp.com/content/dam/bp/business-sites/en/global/bp-supply-trading-and-shipping/documents/bp-master-ex-ship-lng-sale-and-purchase-agreement-2019-edition%20(3)%202.pdf) | Laytime starts at notice of readiness, as clause 7.16 sets it. Demurrage is the rate times the excess days, pro rata. Boil-off for the excess time is paid as well | Demurrage = max(0, wait hours - laytime) / 24 x daily rate. Waiting boil-off is costed at the berth month's hub price |
| WilmerHale, [Destination restrictions and diversion provisions in LNG SPAs](https://www.wilmerhale.com/-/media/files/shared_content/editorial/publications/documents/20170626-gar-destination-restrictions-and-diversion-provisions-in-lng-sale-and-purchase-agreements.pdf) | Under a DES contract the seller keeps title to the destination, and the buyer has no destination freedom unless the contract adds diversion rights. Those rights may need consent, may be capped, and may share profit | Diversion is a hard constraint. It is allowed only when the voyage terms say so. A DES cargo with no recorded right is not diverted, and a cargo with no contract held is diverted with a note that the right was not checked. Profit sharing is not modelled ([section 8](#8-limits)) |
| Lacima, [LNG shipping optimiser](https://www.lacimagroup.com/lng-shipping-optimiser) | A commercial optimiser maximises total portfolio value under vessel, contract and operational constraints, and returns optimal and near-optimal solutions ranked by value | The engine values the **whole book** for every option, not only the late cargo, and shows a ranked set rather than one answer |
| US patent 10,867,261, [Method of generating an optimised ship schedule to deliver LNG](https://patents.justia.com/patent/10867261) | A MILP model with ranked hard and soft constraints, solved by a staged heuristic with local search, and a separate re-optimisation mode | Hard constraints (firm obligations, storage, diversion rights) and soft ones (a non-firm obligation's penalty) are kept apart. Read as prior art only. No claim is implemented, and the engine does not use MILP ([section 4](#4-algorithm)) |
| Balansys, [Commercial information](https://www.balansys.eu/commercial-information/) | The BeLux end-of-day imbalance is settled in cash against the ZTP spot index with a small adjustment | Gas on a day that is already nominated is settled at a cash-out premium on the day's price (`lng.disruption.cash_out_pct`, desk standard 3 %). The engine does not reproduce Balansys's formula |
| Hennen et al., [What lies beyond the Pareto front? Decision support for multi-objective optimisation](https://arxiv.org/pdf/2311.11288) | For a few alternatives, show the values directly. A weighted scalarisation can oversimplify when preferences are unknown. Prefer interpretable presentations | The engine shows the frontier with every objective, not a single number. The default comes from a stated, configurable weighting. Each dominated option names the option that beats it and on which objectives |

**General knowledge, not taken from a source above:** in-tank borrowing between terminal users
(a title transfer in the tank, returned in kind after berthing); the futures trade cost
(0.01 EUR/MWh) and the short-notice premium for a month that has stopped trading
(0.25 EUR/MWh); that a gas day is nominated the day before; and that a later ETA moves
energy from one delivery month into the next. All of these are desk standards that the firm
replaces with approved assumptions.

## 2 Model

| Concept | Held in | Notes |
| --- | --- | --- |
| Supply | `lng_cargoes` (a cargo at sea or discharging, with its slot), `pipeline_supplies` | A cargo's energy is what LNG-1's plan lands at the ETA (boil-off and gas in kind taken off). A pipeline delivers a fixed MWh per gas day, less the curtailed days |
| Slot | `regas_slots` and `lng_slot_terms` | Without slot terms, the slot's days are energy / send-out (rounded up) and storage equals the energy, declining. The source line says so |
| Capacity offer | `lng_capacity_offers` | `borrow`, `send_out`, `storage` or `interruptible`, each with a gas-day window, a price and a cap. The basis is `quoted`, `tariff` or `indicative`. An offer is the desk's own entry |
| Obligation | `lng_delivery_obligations` | MWh per gas day at a terminal or hub, over a window. A firm obligation is hard. A non-firm one costs its penalty per MWh short |
| Voyage terms | `lng_voyage_terms` | Laytime, demurrage (EUR per day), boil-off and the diversion right. Otherwise laytime comes from the cargo contract's master agreement and boil-off from the firm's assumption, each named. Demurrage held only in USD is not converted ([section 8](#8-limits)) |
| Sailing difference | `lng_terminal_terms.extra_sailing_days` | Days added to or taken from the ETA when a cargo goes to another terminal |
| Prices | The price book (P-08) | Month prices per hub, in EUR only, for four months ahead |
| Run | `lng_disruption_runs` | One row per material change: the recommendation's timeline |
| Decision | `lng_disruption_decisions` | The option a person chose, by whom and when, and whether it was the default |

Migration `0086_lng_disruption` (with `down_revision` `0082_data1_integration`) is
expand-only. It adds only these seven tables.

### The options

For each disrupted supply, the engine builds positions and combines each with a capacity
strategy. At most 24 options are built per supply and at most 256 combinations across
supplies, and the panel says when that cap applies.

| Option | Key | What it does |
| --- | --- | --- |
| Wait | `stay+absorb` | Stay at the slot. The send-out rights of the days before berthing are lost. The tank may go above the declining storage right, using bought or interruptible storage, and what does not fit in the slot runs on interruptible send-out for up to 14 days after it |
| Borrow | `stay+borrow` | Borrow LNG in the tank for the days before berthing, send it out on those days with the slot's own rights, and return it from the cargo at berth. The planned send-out is kept |
| Buy | `stay+buy` | Buy extra firm send-out (and the storage the catch-up needs) after berthing |
| Borrow and buy | `stay+borrow_buy` | Both of the above, when one alone is not enough |
| Divert | `divert:<slot>+...` | Go to a spare slot of the book's own (with the sailing difference applied) and release the held slot |
| Swap | `swap:<cargo>+...` | Exchange terminals with another cargo of the book. This **moves a cargo that was running to plan**, so it counts in `disrupted_mwh` |
| Pipeline: absorb | `<supply>:absorb` | Re-hedge the gas that is not delivered |
| Pipeline: cover | `<supply>:cover:<cargo>` | Send a cargo's gas out earlier at the same hub, on bought send-out. This changes that cargo's schedule |

Every option also re-aligns the hedges, pays any demurrage it causes, and for a pipeline
supply does not pay for gas that is not delivered (`cost_eur_mwh`).

## 3 Objectives, constraints and the default

**Valuation.** Each option is valued against the planned landings (the disrupted cargo
arrives at its own slot start), across the whole book:

- the physical value moved between hub-months, at month prices;
- the hedge re-alignment: 0.01 EUR/MWh if the month trades, otherwise 0.25 EUR/MWh;
- cash-out on gas days already nominated: 3 % of the day's price;
- capacity fees;
- demurrage;
- waiting boil-off;
- stranded energy, at the month price less 3 EUR/MWh;
- the slot release value;
- swap costs and soft-obligation penalties.

**Scenarios.** Each option is valued under several scenarios:

- **base**: the ETA as reported;
- **early and late**: the ETA moved by the spread its confidence allows (high 0 days,
  medium 1 day, low or not stated 2 days);
- **prices up and down**: prices ±10 %.

**Objectives:**

| Objective | Sense | Meaning |
| --- | --- | --- |
| `pnl_expected` | max | P&L change against the plan, in the base scenario (EUR) |
| `pnl_worst` | max | Worst P&L change across the scenarios (EUR) |
| `cost` | min | Cash the option pays beyond the plan (EUR) |
| `flexibility_mwh` | max | Firm send-out still held spare, less interruptible capacity relied on |
| `disrupted_mwh` | min | Energy of supplies that were running to plan which the option moves |

**Hard constraints.** An option that breaks a hard constraint is listed as infeasible, with
the reason, and is never recommended or chosen (choosing one returns 409):

- **Firm delivery obligations.** An obligation is judged against the baseline, so only a
  shortfall the option *adds* counts. A shortfall the plan already had is reported as
  `short_in_plan`.
- **Storage.** The tank must fit within firm storage plus interruptible storage at the end
  of each gas day.
- **Stranding.** No energy may be stranded in the base scenario.
- **Diversion.** A diversion must be allowed by the voyage terms.
- **Slots.** A target slot must be the book's own and free.

**Pareto frontier.** An option is dominated when another feasible option is at least as good
on every objective and better on one, with tolerances of 1 EUR and 1 MWh. A dominated option
names its best dominator and the objectives it loses on.

**Default.** The default is the feasible frontier option with the highest score:

```
score = expected - risk_weight x (expected - worst)
        - moved_mwh_cost x disrupted_mwh - moved_supply_cost x supplies moved
        + flexibility_value x spare MWh
```

The weights are approved assumptions:

| Assumption | Desk standard |
| --- | --- |
| `lng.disruption.risk_weight` | 0.5 |
| `lng.disruption.moved_mwh_cost` | 0.5 EUR/MWh |
| `lng.disruption.moved_supply_cost` | 0 |
| `lng.disruption.flexibility_value` | 0 |

The panel shows the rule and where each weight came from. Ties go to the option that moves
fewer supplies, then to the option key.

## 4 Algorithm

**Enumeration with a simulation of each gas day.** The engine works through four steps:

1. For each disrupted supply, build its positions (stay, each spare slot, a swap with each
   other cargo) and the capacity strategies that apply to each.
2. Take the Cartesian product across the disrupted supplies, dropping combinations that use
   one slot twice.
3. For each combination and each scenario, simulate every slot day by day:
   - before berthing: the in-tank borrow;
   - at berth: the repayment;
   - each day: the own send-out, then cover, then bought extra send-out (the inventory above
     the rights still ahead), then interruptible send-out after the slot;
   - at the end of each day: storage overflow, into bought storage first and then
     interruptible storage.
4. Value the result against the plan, check the hard constraints, mark the frontier and pick
   the default.

**Why not MILP.** The option space is small and enumerable, so enumeration is exact for the
options it lists. Each figure traces to a line of arithmetic (`GET .../{option_id}` returns
the components and lines for every scenario). It needs no new dependency, which rule 6
requires. A solver would add a dependency and make each answer harder to explain to a
trader, for no gain at this size.

**Determinism.** The engine has no clock (`now` is passed in through the market), no
randomness and a sorted iteration order. Each option id is a hash of its key. The run's
digest is the recommended key plus the frontier keys.

**Complexity.** The work is O(options x scenarios x supplies x slot days). Options are capped
at 24 per supply and 256 combinations. On the development container:

| Case | Options | Engine time |
| --- | --- | --- |
| The owner's scenario | 6 | 12 ms |
| Three supplies disrupted with eight spare slots | 112 | 0.22 s |
| The cap | 256 | about 0.5 s, estimated at about 2 ms per option |

Beyond that, combinations are cut at the cap and the result says so (`book_options`). A
desk that routinely has more than three cargoes disrupted at once needs a smarter search
([section 8](#8-limits)).

## 5 Cadence: re-optimising on events

The outbox consumer `lng_disruption` (M4 outbox, M7 worker) re-runs each book that an event
touches. It accepts these events:

- `cargo.changed` (only the cargo's own book is re-run);
- `capacity.changed`, `tariff.changed`, `contract.changed`, `assumption.changed` and
  `outage.published` (every book that holds a cargo or a pipeline supply is re-run).

`price.updated` is not accepted. Prices are valued at every read, and a tick does not start
a run: the opportunity consumer owns ticks, and the outbox contract test pins the consumers
of `price.updated`.

**Material change.** A run row is kept when one of these changes:

- the recommendation;
- the frontier's set of keys;
- the recommended P&L, by at least `lng.disruption.material_change` (50,000 EUR).

**Who is told.** When a run is kept, the trader (category `cargo`), the scheduler
(`nomination`) and the desk head (`desk_head`) are told through the LNG-2 routes:

- **Duplicate.** A state the roles were last told about is not sent again, unless the change
  is P&L.
- **Cooldown.** Nothing more is sent within 30 minutes of the last notice, unless the
  recommendation itself changed.
- **Dedupe key.** `lng_disruption:{book}:{digest}:{change}:{role}`.

**Timeline.** The panel lists the runs: what changed, the default at the time, and whether the
roles were told. The latency budget is a row in [15](15_LIVE_PIPELINE_AND_LATENCY_BUDGET.md)
section 2, the routing rows are in section 5 and the measurement is in section 8.

## 6 Explainability

Every option shows:

- the five objectives and the range over the scenarios;
- the legs: terminal, berth, wait, send-out window, borrowed and returned, bought, fees,
  demurrage and boil-off;
- the hedge legs it implies;
- the reasons it is infeasible, or the option that dominates it and where.

The detail read (`GET /api/lng/cargoes/{id}/disruption-options/{option_id}`) adds:

- each component and arithmetic line, per scenario;
- the mandates the option moves, as delta legs over the exposure ladder, using the limits
  screen's own rule.

Every input names its source: an approved assumption or a desk standard, the price's kind and
source, the slot terms or the fallback, and the voyage terms or the master agreement. Inputs
that could not be read are listed as warnings.

## 7 API and web

| Route | Permission | What it does |
| --- | --- | --- |
| `GET /api/lng/cargoes/{cargo_id}/disruption-options` | read | The book's re-optimisation as it bears on one cargo: `disrupted`, `affected` (another supply's option moves this cargo) or `as_planned`. Returns the options, the frontier, the default, the timeline and the last choice |
| `GET /api/lng/cargoes/{cargo_id}/disruption-options/{option_id}` | read | One option in full, as described in [section 6](#6-explainability). Returns 404 when the inputs have changed and the option is gone |
| `POST /api/lng/cargoes/{cargo_id}/disruption-options/{option_id}/choose` | portfolio write, governed | Records the choice and an optional note, and writes an audit row (`lng.disruption_choice`, noting "(not the default)" where it applies). Returns 409 for an infeasible option, and 503 with no row written if the audit cannot be written. `booked` is always false |
| `GET /api/lng/disruption/frontier?book_id=...` | read | The whole book. With `curtail_supply`, `curtail_from`, `curtail_to` and `curtail_mwh_per_day` (all or none, at most 93 days) it answers a pipeline what-if and stores nothing |

The public surface grows to 296 paths and 331 operations (RELEASE_READINESS,
SECURITY_ACCEPTANCE_EVIDENCE, API_CONTRACT_EVOLUTION_POLICY in EN and CN).

In the web client, the cargo plan sheet gains an **Options** section with a **Choose** button,
which needs `portfolio.write`. It is built from `components/ui`, styled with `--ds-*` tokens
in `@layer ds-components`, and translated in EN and ZH. The section shows:

- the default first;
- then the rest of the frontier;
- then the dominated options, each with the option that beats it and where;
- then the infeasible options, each with the constraint it breaks;
- then the timeline and the warnings.

## 8 Limits

These limits are deliberate, and the owner may decide to lift any of them:

- **USD demurrage** (lifted by LNG-4, section 9.4). Demurrage is read from the contract in
  its own currency and converted at an FX fix the reader picks.
- **Pipeline outages** (lifted by LNG-4, section 9.5). A REMIT message is linked to the
  pipeline supply it curtails; a curtailment entered by hand still wins.
- **Profit sharing.** Diversion profit sharing and seller consent are not modelled. The right
  is yes or no, with a note.
- **Hedge timing.** Hedges are re-aligned at once, at the month price plus the trade cost or
  premium. Intramonth timing and liquidity are not modelled.
- **Sailing difference.** The sailing difference is in whole days (rounded) on the gas day of
  arrival.
- **Search size.** Enumeration is capped. Beyond about 3 cargoes disrupted at once with many
  spare slots, a smarter search (beam or local search, as in the patent above) would be
  needed.
- **The default is a recommendation.** It is the desk's stated preference, not a prediction.
  A person always chooses. LNG-4 replaces the single default with a recommended set
  (section 9.1).

## 9 LNG-4: options with consequences, full cost, substitute supply, demurrage, REMIT

The owner's instruction of 2026-11-25: optimisation is not a single answer. A contract may forbid
a move, a location may have no storage and no swap, an option may break a contract or move
cargoes running normally, and the trader decides. Two further instructions of the same day add
the full cost of each option (its opportunity cost) and one portfolio view (substitute supply).

### 9.1 Options, not one answer

Every option is a complete course of action and is listed, ranked by the desk's ordering
weights (`rank`; the weights only order the list). Each carries its expected P&L, worst P&L and
cost, and three flags:

- `contract_breach`: it short-delivers a firm obligation or diverts a cargo with no diversion
  right. Each breach names the contract, the counterparty, the point and the shortfall by gas
  day, and is valued at the contract's liquidated damages (`penalty_eur_mwh`, `penalty_terms`)
  where the data holds them; otherwise it says "penalty not held" and the P&L leaves it out.
  A breach option stays listed and can be chosen.
- `disrupts_normal_cargo`: it moves a cargo or supply that was running to plan; each is named
  with the MWh and why.
- `physically_possible`: false when it cannot happen (no storage right, energy with no send-out
  right, a slot the book does not hold). These are listed separately, last, with the reason,
  and cannot be chosen.

The **recommended set** names, where they differ, the best option that breaks no contract and
moves nothing (`clean`), the highest expected P&L that breaks no contract (`best_expected`), and
the best overall (`overall`), each once with a one-line reason. Ties in the ranking go to the
option with fewer breaches, then to one on the Pareto frontier. The Pareto frontier and the
dominance reasons stay as supporting detail. "Choose" records the option, its consequences and
the FX choice, and whether it was in the recommended set; nothing is booked. When the set
changes the roles are told once ("Recommended options changed"). When something is disrupted
and no option can physically happen, the notice is "No workable option: <supply>", naming what
is disrupted and why each option cannot happen; "Disruption cleared" is sent only when nothing
is disrupted any more and an earlier run had a disruption open.

### 9.2 Full cost: direct P&L and opportunity cost

Each option's P&L is its direct P&L less its opportunity cost, shown apart:

- **Direct**: the moved gas at the month marks, hedge re-alignment, capacity fees (a spot slot
  at its offer's fee), demurrage and boil-off of the cargo itself, releases, swaps, breach
  exposure where held, and substitute gas.
- **Opportunity**: the knock-on on the book's other cargoes (a cargo the option moves takes the
  berth on the day it can, so a cargo due there waits, and it draws the terminals' shared
  per-day send-out first, so a later cargo finds less left), the demurrage and boil-off of
  another user's ship due at a berth the option takes (`lng_berth_calls`, where the line-up is
  held: the hours waited beyond the laytime it has left at its own rate), the release value or
  best other use of a spare slot it uses (the slot's indicative release value, else the
  approved `lng.disruption.spare_slot_value`, else "not known" and left out), and the value of
  storage gas in the month it was to be used.

Each consequence lists which cargoes it hits and whose they are (`owner` own or third_party).
A spot slot at another terminal (a `slot` capacity offer) is valued like a held slot, so a
long-term contracted terminal is never assumed to be the better choice: which wins comes out
of the full valuation. Every arithmetic line carries `sources[]` (the price, rate and tariff it
applied) and `basis` direct|opportunity; the panel's "Breakdown" lists them.

Worked example (the store test, `tests/integration/test_lng_disruption_postgres.py`,
illustrative figures, no boil-off on the book's own cargoes):

| Option | Expected | Worst | Cost | Direct | Opportunity |
|---|---|---|---|---|---|
| ZEE-1 stays, borrows | -20,000 | -158,000 | 20,000 | -20,000 | 0 |
| ZEE-1 stays, absorbs | -279,000 | -417,000 | 79,000 | -279,000 | 0 |
| ZEE-1 diverts to Dunkerque | -362,400 | -432,400 | 247,000 | -187,000 | 175,400 |

The diversion's direct P&L is -40,000 physical, -212,000 re-hedge, -35,000 demurrage and
+100,000 release. Its opportunity cost: ZEE-1 holds the Dunkerque berth on 30 and 31 Jan, so the
carrier due on 30 Jan waits 48 h against 24 h of laytime (65,000 EUR) and boils off 2,000 MWh at
PEG 30.20 (60,400 EUR); and the spare Dunkerque slot's 1,000,000 MWh could have been released
at 0.05 (50,000 EUR). So the contracted Dunkerque slot ranks below staying and absorbing, which
a direct-cost view would not show. The swap with C (-215,000 expected, -289,500 worst) is
possible at Huelva's interruptible capacity but breaks the firm delivery to Cepsa at Huelva,
50,000 MWh short on 24 Jan, penalty not held; it is listed, flagged and can be chosen. The
recommended set is borrowing (`clean`) and the swap with B (`best_expected`).

### 9.3 Substitute supply: one portfolio view

When an option leaves a delivery obligation short, substitute supply covers it as further
options of kind `substitute`, with the same fields as every other option:

- gas the book holds upstream (a supply contract's swing: its delivery tolerance on the daily
  quantity, at the contract price converted by `_fx_rate`);
- hub gas bought at the month price plus the short-notice premium plus the transport to the
  delivery point;
- storage gas (the fee now plus the gas's value in the month it was to be used);
- each alone, and a merit-order combination, cheapest first.

Transport goes through one function, `application/lng_substitutes._transport_cost`, which
answers capacity the firm holds on the leg first (sunk, 0), then the public tariff on the
cheapest proven route (`contract_costs.transport_leg_cost`), else missing; a source whose
transport or price is not held is left out and named in the warnings, never priced at zero.
No firm storage contract type is held yet, so the application reads no storage source; the
engine takes one when it is. The owner's scenario gains a Cepsa cover option, ranked in the
same list as the breach it avoids. In the engine test's extended book, hub gas from PEG at
30.20 + 0.25 short notice + 1.20 transport = 31.65 EUR/MWh on 50,000 MWh covers it at -235,000
expected, against -215,000 for the breach with its penalty not held. Through the store, hub gas
at PVB covers it at the same P&L as the breach (the same mark and premium as the breach's hedge
buy-back) and ranks above it because it breaks nothing.

**Netback.** A route-by-route netback comparison is not added. `domain/research/netback.py`
is a single-route subtraction and `cargo_economics` computes netback per terminal hub with no
customer point, so a comparison would restate what the options already value: each option
prices its own route (the hub mark where the gas lands, the transport to the obligation, the
send-out and storage it uses) and the ranked list is that comparison.

**Carbon and electricity** are not modelled here; they are a later step in
[05](05_IMPLEMENTATION_ROADMAP.md).

### 9.4 Demurrage from the contract, in its currency

Demurrage is read from the cargo's Confirmation Notice, then its voyage terms, then the master
agreement, with the laytime and the terms, in the contract's currency. The ETRM cargo schedule
import takes the optional columns `laytime_hours`, `demurrage_rate_per_day`,
`demurrage_currency` and `demurrage_terms`. Every conversion goes through one function,
`application/lng_demurrage._fx_rate(session, from_ccy, to_ccy, as_of, context)`, which answers
the rate with its source, label and rate date, and what it tried. The reader picks the source
(ECB reference rate by default; WM/Reuters or BFIX only where the principal holds entitled
fixes, else 403; or a rate entered by hand, said so) and the rate date (empty: the latest fix on
or before the cargo's day). Rates are read from the `fx_observations` the platform holds: none is
hard-coded and none is fetched. Without a rate the demurrage shows in its own currency with a
warning, and waiting is costed at boil-off only. The demo's simulated rate is used only with demo
marks on and is labelled simulated.

Example: GATE-1's 77,000 USD/day at the ECB fix of 2027-01-19 (1.10 USD per EUR) is 70,000
EUR/day; the panel shows the 77,000 USD/day, the EUR figure, and the rate with its source and
date. In demo D1, Meridian's 76,000 USD/day converts at the simulated demo rate of 2026-12-23
(1.087) to 69,917 EUR/day, labelled simulated, and only with demo marks on.

### 9.5 REMIT outages curtail pipeline supply

A pipeline supply names the assets it depends on (`depends_on`: an EIC, an asset name, or a GIE
facility, with its share and direction). When the `lng_disruption` outbox consumer receives
`outage.published`, it links each held REMIT message to the supplies it matches, before it
re-optimises their books, so the run sees the new curtailment.

- **Matching is exact.** It uses the EIC, the normalised name, or the reviewed GIE alias table,
  and the direction must agree. There is no fuzzy match.
- **The volume.** The fraction unavailable is unavailable over technical capacity, else the
  message's GWh/d over the supply's own capacity through the asset. A gas day's curtailment is
  the daily volume x the share through the asset x the fraction x the part of the gas day the
  event covers. An open-ended message is capped at 400 days or the supply's end.
- **Versions.** There is one link per supply and message. A newer version revises it; a
  repeated or older one changes nothing. A dismissed message withdraws it, an inactive one ends
  it, and a message with no derivable volume is shown as unsized and curtails nothing. Each
  link records what matched and why.
- **Override.** A day entered by hand wins over every link. Across links on the same day the
  largest counts. `outage_mode = manual` keeps only the days entered by hand. The override is
  `PUT /api/lng/pipeline-supplies/{id}/outage-override` (audited
  `lng.pipeline_outage_override`); `GET .../outage-links` shows the links.
- **Advisory.** It stays advisory: the curtailment is the platform's reading of a published
  message, shown with its source, and nothing is nominated.

### 9.6 Web

The Options section lists every option by rank with its flags, the recommended reasons, the
expected P&L split into direct and opportunity cost, worst P&L, cost and the consequences with
their sources; "Breakdown" fetches the option and lists each cost line with its sources, direct
first. An FX picker (source, rate date, rate and its currency when entered by hand, reporting
currency) feeds every read and the choice. The cargo's demurrage shows in the contract's currency
with the rate, its source and date. The REMIT links on the book's pipeline supplies are listed
with their status and why. EN and ZH.

### 9.7 Open owner decisions

- **Berth priority.** A cargo an option moves takes the berth first on the day it can; the cargo
  already due there waits. The owner may prefer first-come order.
- **Third-party demurrage.** Another user's ship is costed at its own rate and laytime from the
  line-up where held. That is a cost to the terminal's relationship, not to the book's cash, and
  the owner may decide to show it without counting it.
- **Spare-slot value.** With no slot release value, the approved `lng.disruption.spare_slot_value`
  is used; none is set by default, so the value forgone is "not known" and left out.
- **REMIT across links.** On a day two messages curtail one supply, the largest counts, not the
  sum.
