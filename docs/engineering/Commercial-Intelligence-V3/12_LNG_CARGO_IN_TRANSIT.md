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
| Gas in kind | Terminal's retention share of the energy at berth | Terminal terms |
| Send-out | From berth at the slot's send-out rate until the delivered energy is gone, cut at 06:00 CET gas-day boundaries | Slot |
| Hub months | Send-out summed by hub and delivery month; the hub comes from the terminal | Terminal register, else the identity resolver |
| Hedge cover | Recorded legs per hub and month (short is negative); net = physical + hedge | `lng_cargo_hedges` |
| Last trading day | Two UK business days before the month (ICE Endex TTF rule) | Calendar; holidays passed in |
| Demurrage | Berth delay beyond laytime x daily rate | Request (what-if) or charter terms |

## Suggestions

Advice for a person; nothing is traded, nominated or booked.

| Kind | When |
| --- | --- |
| `roll` | A short hedge sits in a month the gas left; one roll from that month to the month it moved to, due the day the earlier month stops trading |
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

## Interfaces

- API: `GET /api/lng/cargoes/plans`, `GET /api/lng/cargoes/{cargo_id}/plan`,
  `POST /api/lng/cargoes/{cargo_id}/plan/what-if` (stores nothing),
  `PUT /api/lng/cargoes/{cargo_id}/hedges` (PORTFOLIO_WRITE, audited). See
  [the contract policy](../../architecture/API_CONTRACT_EVOLUTION_POLICY.md).
- Python SDK: `eurogas_nexus_sdk.lng_cargo_plan` (`fetch_cargo_plans`, `fetch_cargo_plan`,
  `try_cargo_eta`, `record_cargo_hedges`).
- Web client transport: `api.cargoPlans`, `api.cargoPlan`, `api.cargoPlanWhatIf`,
  `api.saveCargoHedges`. The screen follows the hands-on review (Q1).
- Storage: migration `0078_lng_cargo_hedges` (ADR Decision 29).

## Limits today

- Send-out runs at a flat rate; a terminal's nominated profile per day is not yet read.
- Hedges are recorded by the desk; they are not matched to ETRM trades automatically.
- A FOB cargo still does not appear in the position ladder; the plan is where it shows.
- Vessel position, heading and route are not used for the ETA; the ETA is what the import
  says.
