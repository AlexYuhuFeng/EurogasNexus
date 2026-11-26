# 12 LNG cargo in transit (LNG-1)

A desk that has bought a US cargo for Europe manages one chain, not separate screens. Before
LNG-1 the platform kept only a cargo's latest ETA, with nothing linking it to the slot, the
send-out, the hub months or the hedges, so a schedule change showed up nowhere it mattered.

```
ETA -> berth (slot window) -> boil-off -> gas in kind -> delivered energy
    -> send-out by gas day -> hub exposure by delivery month -> hedge cover -> what to do
```

## How the plan is built

| Step | Rule | Source of the input |
| --- | --- | --- |
| Berth | On time if the ETA is inside the slot window; waiting at anchor until it opens if early; missed if after it closes (no send-out assumed); no slot if none is linked | ETA from the ETRM or vessel feed import; slot from `regas_slots` |
| Boil-off | Loaded energy x rate x days from loading to berth (waiting boils off too) | Contract terms (`boil_off_pct_per_day`), else the approved assumption `lng.boil_off`, else the desk standard 0.10 %/day, named as such |
| Gas in kind | Terminal's retention share of the energy at berth; 0 with no berth (missed or no slot: nothing is unloaded, nothing is delivered, and `energy_at_eta_mwh` is what stays aboard) | Terminal terms |
| Send-out | From berth at the slot's send-out rate until the delivered energy is gone, cut at 06:00 CET gas-day boundaries. Today's "My gas day" and checklist take this send-out for a slot holding a firm cargo (`basis` `cargo_plan`); a slot without a cargo is spread over its window and labelled as an assumption | Slot |
| Hub months | Send-out summed by hub and delivery month; the hub comes from the terminal | Terminal register, else the identity resolver |
| Hedge cover | Recorded legs per hub and month (short is negative); net = physical + hedge | `lng_cargo_hedges` |
| Last trading day | Two UK business days before the month (ICE Endex TTF rule) | Calendar; holidays passed in |
| Demurrage | Berth delay beyond laytime x daily rate | Request (what-if) or charter terms |

## Suggestions

Advice for a person; nothing is traded, nominated or booked.

| Kind | When |
| --- | --- |
| `roll` | A short hedge sits in a month the gas left; one roll from that month to the month it moved to, due at the close of whichever of the two months stops trading first (the target month when the cargo arrives earlier); never into a month that has stopped trading (QA-L-02) |
| `sell` / `buy_back` | Physical longer or shorter than the hedge in a month that still trades |
| `short_notice` | The month has stopped trading: close the gap in balance-of-month or day-ahead |
| `find_slot` | The ETA misses the window; the hedges have no gas behind them |
| `demurrage` | Berth delay past laytime |
| `deadline` | The next trading deadline that affects the cargo |

## What a change does

Each change to a firm cargo's plan inputs (ETA, departure, energy, slot, hedge set) publishes
a `cargo.changed` market event (`cargo:<id>`) through the outbox. The payload holds the
inputs, not the plan, so the plan before can be rebuilt; vessel position fixes are left out
because they are not plan changes. `GET /api/lng/cargoes/{id}/plan` compares the current plan
with the one before and says in one line what moved, for example "The new ETA misses the slot
window." or "212,400 MWh of send-out moves into TTF 2027-01."

An import (`scripts/ops/import_lng_positions.py`, `application/lng_positions_import.py`)
updates a stored cargo or slot only in the fields its file supplies: a column it leaves out or
a blank cell keeps the stored value, so a vessel feed without `book_id` never takes a cargo
out of its book, and a cargo moves book only when a file names another book. The import
publishes the cargo events in its own transaction and lists an ETA that overrides an ETA
another source set (QA-L-04).

## What to do about it (LNG-3, built)

When a cargo is late or a pipeline supply is curtailed, the plan sheet's **Options** section
lists what the desk could do across the whole book (wait, borrow in tank, buy send-out or
storage, divert, swap with another cargo; cover a pipeline shortfall from a cargo), each
valued against the plan under ETA and price scenarios, with the Pareto frontier, the options
a firm obligation or a storage or diversion right rules out, and a default by the desk's
stated preference. A person chooses; the choice is recorded and nothing is booked. Design,
sources and the worked example: [17](17_LNG_PORTFOLIO_DISRUPTION_OPTIMISATION.md).
LNG-4 lists every option with its consequences instead of ruling breaches out, values each at
its full cost, and shows the cargo's demurrage in the contract's currency at a chosen FX fix
([17](17_LNG_PORTFOLIO_DISRUPTION_OPTIMISATION.md) section 9).

## Who hears about a change (LNG-2, built)

A cargo change matters to several people for different reasons. The `cargo_roles` outbox
consumer (`application/lng_cargo_alerts.py`) takes each `cargo.changed` revision, rebuilds the
plan from the event's inputs, compares it with the plan each role last heard about, and
derives one message per role (`domain/lng/consequences.py`, pure). Taking the owner's example,
a cargo due at Gate in three days, hedged forward month by month, reported four days late by
the vessel feed (an AIS ETA, low confidence):

| Role (job function) | Channel category | What it receives |
| --- | --- | --- |
| Trader (TRADER) | `cargo` | "Hedges no longer match Aurora (SAB-0420): buy 383,333 MWh TTF 2026-11 at short notice; sell 379,373 MWh TTF 2026-12", each with "physical + hedge = net" per month, the due time (Dec before it stops trading) and "nothing is traded". Critical when a month has already stopped trading or the first action is due within a day |
| Scheduler (OPERATIONS) | `nomination` | "Renominate 10 gas day(s)": berth before and after, send-out by gas day before and after, and for each day the nomination or renomination cut-off it hits (`gas_day.cutoffs_for`). "Slot missed" when the new ETA misses the window. Critical when a cut-off has passed or falls within three hours |
| Risk (RISK_MANAGER) | `limits` | Net exposure by hub month before and after, and each mandate over the book re-checked with the limits screen's own rule ("LNG desk 98 % watch → 126 % breach"). Critical on a new breach |
| Desk head (MANAGEMENT) | `desk_head` | Only when material: the largest change in net by month, or the hedge actions in total, at or above `lng.material_change_mwh` (an approved commercial assumption; else a desk standard of 100,000 MWh, said so), a slot newly missed, or a mandate newly breached. The message lists the reasons |

Every message ends with how current its inputs are: "ETA from KPLER (the ETA declared in
AIS, low confidence), stored …; slot gate-1 from ETRM, …; hedges recorded by lng.trader, …;
plan rebuilt … from cargo.changed revision 2". An AIS or low-confidence ETA asks the reader
to confirm it before acting.

- **Dedupe and cooldown.** A message is keyed on its digest: the same content is not sent
  twice. A changed message for the same role waits 30 minutes after the last one unless its
  severity rises or it names a new item (a new month, gas day or mandate).
- **Withdrawal.** When a later change makes a role's message moot (the ETA corrected back,
  the cargo delivered or taken out of the book), the alert is resolved and the role is told
  "Withdrawn: …" with the reason (the screens show it in English or Chinese).
- **Where it shows.** Each role's channel; Today's "What needs me" (the reader's own roles
  only, critical first); the cargo board's "Who must act" column (the reader's roles marked);
  the plan sheet's "Who has been told" (open messages, and those withdrawn in the last day).
- **Any change.** The chain is the same for a departure, energy, slot or hedge change:
  `cargo.changed` carries all plan inputs. A change that moves nothing a role acts on tells no
  one; the first recording of a cargo tells no one.

Nothing in this chain trades, nominates or books; proposals wait for the trader. Criteria:
LNG2-1 to LNG2-5 in [06](06_ACCEPTANCE_CRITERIA.md). Routing: [15](15_LIVE_PIPELINE_AND_LATENCY_BUDGET.md)
section 5.

## What the ETA rests on (lesson P3)

An import may give `eta_basis` (master_notice, ais_declared, feed_estimate, schedule, manual;
`nor`, `ais` and the like are accepted) and `eta_confidence` (high, medium, low). The cargo
keeps them with the source that set the ETA and when (`eta_source`, `eta_recorded_at_utc`,
migration `0080_lng_eta_basis`). A new ETA without them reads "basis not stated, confidence
not stated"; the old basis never carries over. The plan's ETA input, the board, the plan sheet
and every role message say it in words.

## In the position ladder

A firm cargo (book set, not on a ballast voyage) is on the position ladder and every read
built on it (Today's book, the desk brief, mandate usage, VaR): its plan's send-out by gas day
is physical at the terminal's hub, the hedges recorded on it are financial over their delivery
month, both with `reference` `cargo:<id>` and volume only. Each ladder row names its cargoes
(`cargoes`). A DES cargo contract on the ladder that names the cargo keeps the physical (the
plan's send-out is not added again), and a hedge whose reference is a booked trade on the
ladder is that trade. The gas day keeps the send-out on the slot's line and does not add
recorded hedges, which are not booked trades (QA-L-03, QA-R-26).

## Interfaces

- API: `GET /api/lng/cargoes/plans`, `GET /api/lng/cargoes/{cargo_id}/plan`,
  `POST /api/lng/cargoes/{cargo_id}/plan/what-if` (stores nothing),
  `PUT /api/lng/cargoes/{cargo_id}/hedges` (PORTFOLIO_WRITE, audited). See
  [the contract policy](../../architecture/API_CONTRACT_EVOLUTION_POLICY.md).
- Python SDK: `eurogas_nexus_sdk.lng_cargo_plan` (`fetch_cargo_plans`, `fetch_cargo_plan`,
  `try_cargo_eta`, `record_cargo_hedges`).
- Web client transport: `api.cargoPlans`, `api.cargoPlan`, `api.cargoPlanWhatIf`,
  `api.saveCargoHedges`.
- Screen (QA-L-05): Desk → Cargoes (`?workspace=market&task=cargoes`, `&cargo=<id>` opens one
  plan). The board lists the book's cargoes, missed and no-slot rows pinned first, then by the
  next action's due time; a strip above sums the open hub months, the next futures expiry and
  what needs action today. Each cell's hover names its source, unit and as-of. Keys: ↑ ↓,
  Enter (plan), `w` (what-if), `h` (hedges). The plan sheet shows the header, what changed, a
  timeline, the energy waterfall (with its table and CSV), send-out by gas day coloured by
  delivery month, the hub × month grid with the recorded hedge legs, suggestions by due time
  with their arithmetic, and the inputs with their sources. Since LNG-2 the ETA cell says what
  the ETA rests on, a "Who must act" column shows one chip per open role message, and the plan
  sheet has "Who has been told". The what-if says nothing is
  stored; the hedge editor validates before the PUT. Advice only: nothing books, nominates or
  trades. The board is the landing of the `lng` composition (a trader whose book scope names an
  LNG book) and the palette finds a cargo by id, vessel or IMO. Pure logic:
  `clients/web/src/app/model/cargoBoardModel.ts`.
- Live updates: no cargo channel exists. The board re-reads on the session's `map` change
  notices for the `cargoes` and `slots` groups, and polls every minute while that stream is down.
- Import cadence: no source declares one for cargo files, so the board states its own (24 h
  for an ETRM file, 6 h for a vessel feed) and marks an import older than that as late.
- Storage: migrations `0078_lng_cargo_hedges` (ADR Decision 29) and `0080_lng_eta_basis`
  (ETA basis and confidence, LNG-2).

## Limits today

- Send-out runs at a flat rate; a terminal's nominated profile per day is not yet read.
- Hedges are recorded by the desk; they are not matched to ETRM trades automatically.
- A FOB cargo without a vessel in the feed (no `lng_cargo_id`) or without a plan is still
  not on the ladder; a warning says so.
- Credit exposure does not include recorded cargo hedges: they name no counterparty.
- Vessel position, heading and route are not used for the ETA; the ETA is what the import
  says, with the basis and confidence the import states.
- Role messages go to channels by category, not to a named person on duty; escalation is
  stated in the message, not timed (15 section 5).
- The mandate re-check reads the whole ladder, about 0.1 s on the test desk; it grows with
  the book.
- The timeline has no crosshair or zoom,
  and a changed row's flash is neutral rather than coloured by direction.
