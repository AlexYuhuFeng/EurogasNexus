# 17 LNG portfolio disruption optimisation (LNG-3)

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

Architecture: ADR Decision 36. Code:

- `domain/lng/disruption.py`: the engine (pure; no I/O and no clock).
- `application/lng_disruption.py`: loads the book, serves the reads, records the choice and
  runs the outbox consumer.
- `api/routes/public/lng.py`: the routes.
- `clients/web/src/components/CargoOptionsPanel.tsx`: the panel.

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

- **USD demurrage.** Demurrage held only in USD, from the master agreement, is not converted.
  Waiting is then costed at boil-off only, and a warning says so. Converting it needs an
  FX-fixing rule.
- **Pipeline outages.** A pipeline curtailment is entered on `pipeline_supplies`, or asked as
  a what-if. A REMIT outage message is not yet linked to the supply it curtails.
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
  A person always chooses.
