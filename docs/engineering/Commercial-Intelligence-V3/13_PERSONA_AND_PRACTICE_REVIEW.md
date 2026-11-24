# 13 Persona and practice review

What the programme learned on 2026-11-24 from role-playing the platform's users, from how
professional gas and LNG desks and systematic trading firms work, and from reviews of
latency, ontology, integration, UI, documentation, tariffs, news and the map. Each finding
is scored against [11_COMMERCIAL_QUALITY_STANDARD.md](11_COMMERCIAL_QUALITY_STANDARD.md) and
carries its fix and status. The hands-on browser review per role (Q1) adds its findings here.

## Practice the platform should follow

From desk practice at European utilities and traders, LNG portfolio players, and the public
engineering talks of Jane Street, HRT and similar firms:

1. Freshness on every number with source-specific thresholds; stale treated as live is the
   classic failure (A2).
2. The gas-day clock is the spine of the day: D-1 nomination, re-nomination cycles,
   settlement windows, weather model runs.
3. Indicative intraday marks are kept apart from official end-of-day marks (A4, B3).
4. A daily P&L explain by factor (flat price, basis, freight, FX, time spread).
5. The LNG cargo is one linked object from voyage to hedge. **Done in LNG-1** ([12](12_LNG_CARGO_IN_TRANSIT.md)).
6. Optionality views (rolling intrinsic, deltas) for cargo and storage options, not only
   static netbacks.
7. Basis risk shown next to any hub hedge (DES NWE against TTF, JKM against TTF).
8. "Too good to be true" checks route an edge to review, not to a recommendation.
9. Low-noise, symptom-based alerts with acknowledgement and escalation. **Partly done in M6.**
10. A strategy lifecycle with sign-off: research, backtest, shadow, advisory.
11. Every change to limits, curves, assumptions and models audited with a "what changed" diff.
12. A suspend switch per strategy or desk, and limit checks that gate recommendations.
13. Independent reconciliation against the ETRM and TSO data.
14. The ETRM stays the system of record, the terminal the price source; no execution here.
15. Summary first, drill down second; users use about a fifth of the features.
16. A first-class event calendar: REMIT messages, holidays, model runs, slot releases.
17. Shift hand-over: open items, position against nomination, acknowledged alert log.

## Latency

Decision support needs seconds, not milliseconds (decision in [08](08_DECISION_LOG.md)).
Measured on PostgreSQL with the demo desk: publishing a price event 9.8 ms, the targeted
re-evaluation 158 ms (p95 229 ms), a full evaluation 6.5 s (1,937 SQL statements), a listen
worker from commit to processed 0.81 s. End to end today a change waits for the 60 s
scheduler tick and up to 5 min of debounce, and the Opportunities page never refreshes by
itself. Fixes: push opportunity changes to the page, deploy the listen worker, prefetch the
repeated price queries, remove the 1,000-event drain cap (M7).

## Findings by severity

| ID | Sev | Standard | Finding | Fix | Status |
| --- | --- | --- | --- | --- | --- |
| P-01 | S1 | B7, F4 | One reviewer can save a credit line with a shorter contract list and clear a breach in one call | Partial update with before/after audit (done); four-eyes with P-17 | Partly done (F1) |
| P-02 | S1 | B7, F4 | ANALYST plus REVIEWER on one person can approve their own work; the own-mandate check compares an id with a free-text label | Segregation of duties; own mandate under any name | **Done in F1** |
| P-03 | S1 | A7 | Prices 100x, negative or in the future are accepted into strategies and the prompt panel; any operator key can label quotes as a licensed feed | Plausibility bands per hub, refuse future times, bind source label to the key's entitlement | **Done in F1** |
| P-04 | S1 | F1 | `POST /api/desk/gas-day/status` always returns 500 | Give the route a permission with a role | **Done in F1** |
| P-05 | S1 | F1 | Daily strategy tracks are evaluated once and never again (`run_due` not scheduled) | Schedule it | **Done in F1** |
| P-06 | S1 | A3 | Demo LNG terminal terms are priced as the firm's contract terms | Carry the simulated label end to end | Tariff pickup |
| P-07 | S1 | A5 | `GBP/th` read as pence by one unit module and pounds by another (100x) | One strict unit authority | M10 |
| P-08 | S2 | A1, A4 | Three prices for TTF Dec-26 at one instant; a stale quote beats a fresh settlement | Freshest entitled source within each class's maximum age | Next after F1 |
| P-09 | S2 | B3 | Four LNG economics implementations rank the same cargo's terminals differently | One LNG economics kernel | Planned |
| P-10 | S2 | B5, B6 | The opportunity stream and monitoring read the legacy table | M7 | M7 |
| P-11 | S2 | B1 | Book-owned assumption sets are ignored by the firm-wide evaluation; sell-down always "cannot evaluate" | Evaluate per book or key by zone | Planned |
| P-12 | S2 | B1 | Hedge-gap alerts run past the band's validity (37 items, 26 outside it) | Respect `valid_until` | Planned |
| P-13 | S2 | A1 | An own cargo's feed ETA contradicts its contract window unchecked | **Done in LNG-1** (contract warning on the plan) | Done |
| P-14 | S2 | B1 | A FOB cargo is invisible in the position ladder | Plan shows it (LNG-1); ladder leg next | Partly done |
| P-15 | S2 | B1 | The HH pricing month has no effect (no HH forward held) | HH, JKM forward connectors under the customer's licence | Needs data licence |
| P-16 | S2 | D5 | ETRM import truncates ids to 64 characters, has no snapshot mode, hard-deletes; screen fills and ETRM trades are double counted | Integration layer with snapshot semantics | Planned |
| P-17 | S2 | B7 | LNG terminal terms and freight routes change with no second approval | Four-eyes with effective dates | Planned |
| P-18 | S2 | C1, A2 | No price above the fold on the trader's landing; stale and live look the same | Desk polish | Next |
| P-19 | S2 | C6 | The value flash has no direction and fires on tenor switches | Directional flash on value change only | Next |
| P-20 | S2 | A4, C2 | Units and decimals differ between screens ("GBp/th" and "p/th"; 3 and 2 dp) | One formatter per measure | Next |
| P-21 | S2 | C5 | The command palette finds pages only, not instruments | Instrument search | Next |
| P-22 | S2 | D1, E2 | The SDK cannot be used from its docs: no install or auth steps, both examples fail with 503 | Rewritten SDK docs, verified examples | DOC |
| P-23 | S2 | E2 | The README's develop path fails at its second command (database URL driver) | Rewritten README; driverless URLs use the runtime driver | DOC |
| P-24 | S3 | C12 | Installer images are 1x and blur at high DPI; no signing; sign-in has no autofocus | Installer and sign-in polish | Next |

## Hands-on review by role (Q1)

Three reviewers signed in as each role in a real browser on 2026-11-24 (commit `877b355`,
before F1), clicked, hovered, used the keyboard and checked figures against the store. On-time
cargo plans matched hand calculations to 0.1 MWh; the credit exposure reconciled to the store;
the draft SDK docs took a new quant to a first result verbatim. The S1 findings and their state:

| ID | Role | Finding | State |
| --- | --- | --- | --- |
| QA-T-01 | Trader | "Mid" is the last price, not (bid+ask)/2 | Fixed: mid only from two sides, Last its own column, one-sided quotes marked; the backtest pool no longer stores a last print as a mid |
| QA-T-02, QA-L-22 | Trader, LNG | Up to three prices for one month across screens; the demo curve has no drift | Demo drift fixed; one price resolver next (with P-08) |
| QA-T-03 | Trader | No change against the close; prices below the fold on the landing | Change vs close fixed (quotes carry the close, kind, day and source). Fixed: My market is first for traders, under a strip with the next cut-off, overdue steps and open imbalances (owner, 2026-11-24) |
| QA-T-04, QA-R-07 | Trader, risk | Stale rows look live; old marks raise no stale alert; the feeds panel and Today disagree | Board rows fixed (age, cadence, freshness state, stale legs). Risk rows, the marks alert and one freshness contract next |
| QA-T-05, QA-R-05 | All | Implausible, future and wrongly labelled ticks accepted | Ticks fixed in F1; firm marks and the "Updated" stamp next |
| QA-T-06, QA-R-08 | Scheduler | The status write failed for all and the scheduler could not record | Fixed (F1, F1-8) |
| QA-T-07 | Scheduler | Two daily balances with hard-coded rates | Fixed: one gas-day definition; the approved cash-out set or rates labelled as entered |
| QA-T-08 | Scheduler | The nomination step's deadline uses the wrong cut-off | Fixed |
| QA-T-09 | Scheduler | An outage is ignored in the gas-day balance | Fixed: supply capped by a REMIT outage at its source, named on the line |
| QA-L-01 | LNG | The gas-day card and the cargo plan give different send-out | Fixed: a slot with a firm cargo takes the plan's send-out; QA-L-06 energy balance fixed too |
| QA-L-02 | LNG | A backward roll is due after the target month stops trading | Next |
| QA-L-03, QA-R-26 | Desk head, risk | Firm cargoes and their hedges are missing from the ladder | Next |
| QA-L-04 | LNG | A vessel-feed import clears a cargo's book link | Next |
| QA-L-05 | LNG | No cargo screen | Next (cargo board) |
| QA-R-01 | Risk | The credit-line form sends empty links; the breach and its alert vanish | Fixed (F1-10): the form reads the whole line, unlinking all is confirmed, a cleared breach waits for acknowledgement. Maker-checker on increases waits for P-17 |
| QA-R-02 | Admin | An admin can mint a key for another person and act as them | Fixed (F1-9): people issue their own keys in Settings; admins issue for services only |
| QA-R-03, QA-R-04 | Admin, risk | Trader+risk users and own mandates by name | Fixed in F1 (segregation, all names compared); a warning at user creation is next |
| QA-R-06 | All | One spread gets opposite verdicts on Today and the Spreads board | Fixed: one direction rule (`spread_direction`), Today shows the flow and net. Both screens still choose their route separately (S2) |

The full reports, screenshots and scripts are kept in the session workspace; the S2 and S3
findings are worked through after the S1s.

## Data the platform should add, and how

- **Public tariffs.** The LNG tariff register is well built but ships empty. Regulated
  terminals publish slot tariffs (Zeebrugge's auction notices start at the regulated slot
  tariff); Gate, Grain, Dunkerque and others publish none. TSOs publish entry and exit
  tariffs yearly, indicative then final (National Gas: indicative on 29 May 2026, final on
  31 July, effective 1 October). Plan: a publisher registry with release windows and licence
  notes; conditional fetch and hashing where terms allow automated fetching; per-publisher
  parsers; quarantine with an alert on a parse failure; versioned rows with effective dates
  and indicative or final status; review; `tariff.changed` events keyed by operator, point
  and gas year so only affected results recompute. Sources whose terms forbid automated
  fetching are transcribed by a person with the source quoted.
- **News and events.** No news connector exists. Usable without a licence: EIA, the
  European Commission, the EU Official Journal, the US Federal Register, sanctions lists,
  maritime advisories (UK Open Government Licence), REMIT messages (already ingested);
  GDELT for links only. Licensed services (Platts, Argus, ICIS, LSEG, Bloomberg, Kpler) only
  under the customer's licence. Every extracted fact quotes its source span, entities must
  exist in the ontology, one source stays unverified until a second or a person confirms
  it, and a threat is never treated as a closure. Confirmed events drive what-ifs (LNG
  supply loss, Cape reroute) that a person accepts before they touch the book.
- **Map.** Terminal tanks, jetties and ships in 3D with MapLibre's built-in extrusions (no new
  dependency), from a register where every figure carries its source and whether it is
  published or estimated; ship positions only from the feed with their age, a projected
  position drawn as an estimate, and moving flow lines only where a measured flow exists.

## What already works well

The market event outbox and the targeted re-evaluation; the hub resolver that refuses
rather than guesses; the token system and calm visual design; four-eyes on assumption sets;
the reviewed public-path registry and contract tests; the tariff register's document hashes
and review flow.
