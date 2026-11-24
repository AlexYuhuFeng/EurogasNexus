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
  with their arithmetic, and the inputs with their sources. The what-if says nothing is
  stored; the hedge editor validates before the PUT. Advice only: nothing books, nominates or
  trades. The board is the landing of the `lng` composition (a trader whose book scope names an
  LNG book) and the palette finds a cargo by id, vessel or IMO. Pure logic:
  `clients/web/src/app/model/cargoBoardModel.ts`.
- Live updates: no cargo channel exists. The board re-reads on the session's `map` change
  notices for the `cargoes` and `slots` groups, and polls every minute while that stream is down.
- Import cadence: no source declares one for cargo files, so the board states its own (24 h
  for an ETRM file, 6 h for a vessel feed) and marks an import older than that as late.
- Storage: migration `0078_lng_cargo_hedges` (ADR Decision 29).

## Limits today

- Send-out runs at a flat rate; a terminal's nominated profile per day is not yet read.
- Hedges are recorded by the desk; they are not matched to ETRM trades automatically.
- A FOB cargo without a vessel in the feed (no `lng_cargo_id`) or without a plan is still
  not on the ladder; a warning says so.
- Credit exposure does not include recorded cargo hedges: they name no counterparty.
- Vessel position, heading and route are not used for the ETA; the ETA is what the import
  says.
- The screen has no Today row or What-needs-me item yet, the timeline has no crosshair or zoom,
  and a changed row's flash is neutral rather than coloured by direction.
