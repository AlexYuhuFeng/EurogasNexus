# 05 Implementation roadmap

Vertical slices, each shippable and tested on its own, in priority order. M1 to M3 are the
Phase 0 work (baseline, audit, these documents). Status is kept in
[10_PROGRAMME_STATE.md](10_PROGRAMME_STATE.md).

| Milestone | Slice | Capabilities | Needs access? | Status |
| --- | --- | --- | --- | --- |
| M1 | Baseline: branch, SHA, ancestry, test results | all | No | Done |
| M2 | Capability audit and gap matrix | all | No | Done |
| M3 | Target architecture, domain design, criteria, risks, decisions | all | No | Done |
| M4 | Canonical market events, PostgreSQL outbox, targeted re-evaluation, replay, staleness, timeline | 1, 7, 10 | No | **Built, tested** |
| M5 | Settlements, FX fixings and REMIT messages publish events through change capture (scheduler window, importers in their own transaction); FX reaches cross pairs; the CP-13 lost-change race fixed | 1, 2, 7 | No (public sources and fixtures) | **Built, tested** |
| M5b | Contract, hedge-band and assumption edits publish `contract.changed` / `assumption.changed` (digests only, captured from the store at save time); a return to earlier content is a revision | 1, 7 | No | **Built, tested** |
| M6 | Stale feeds, dead letters and outbox lag raise monitoring alerts (one per condition, cleared when it recovers); source freshness ages with the clock | 10 | No | **Built, tested** |
| LNG-1 | A cargo in transit as one plan: ETA, slot window, boil-off, gas in kind, send-out by gas day, hub months, recorded hedges, roll and short-notice suggestions, what-if; `cargo.changed` events; SDK and web transport ([12](12_LNG_CARGO_IN_TRANSIT.md)) | 5, 7 | No | **Built, tested** |
| Q1 | Commercial quality standard ([11](11_COMMERCIAL_QUALITY_STANDARD.md)) and a hands-on review of every surface against it, per role, in a real browser | all | No | In progress |
| F1 | Audit blockers from the persona review: gas-day status 500, unscheduled strategy tracking, credit-line partial update and four-eyes, tick validation, segregation of duties | 7, 10 | No | Built (four-eyes moves to the reference-data approval work) |
| QA-1 | Hands-on persona round 1 fixes: trader (market first with a gas-day strip, change vs close, stale rows), scheduler, risk (credit lines, marks age, implausible marks, segregation warning), LNG (roll due date, cargoes on the ladder, imports keep the book, cargo board), personal API keys | all | No | **Built, tested** |
| AIR-1 | AI by role, personal workspaces and the improvement loop: design ([14](14_AI_ROLES_PERSONALISATION_AND_IMPROVEMENT_LOOP.md)); in-product feedback | 8, 12 | No | Design done; feedback capture built |
| P-08 | One price resolver: every screen reads the same price, kind, source and age for a hub and month | 1, 7 | No | **Built, tested** |
| P-11 | Opportunities value each book with its own assumption set and its gas-day balance | 7 | No | **Built, tested** |
| M7 | Live pipeline ([15](15_LIVE_PIPELINE_AND_LATENCY_BUDGET.md)): the listen worker is the default trigger (no drain cap, one-minute debounce, sweep lock); new-engine opportunities to alerts routed to an owner with escalation, notified once under a row lock; `/api/stream/opportunities` pushes open, withdrawn and evaluated, and the Opportunities page follows it with its age shown; latency measured before and after. Retiring the legacy intraday engine is blocked by its dependents (R19) | 7, 10 | No | **Built, tested** (M7-1 to M7-9; M7-10 blocked) |
| LNG-2 | A cargo change reaches each role: rebuilt plan, hedge roll proposal, slot and nomination consequences, exposure, material escalation; ETA basis and confidence | 5, 7 | No | Next (needs M7 routing) |
| GOV-1 | Governance: audit written with the change, entitlement usage and export decisions, maker-checker on limits and reference data (P-17) with figure provenance; AI controls stage 2 (AI-use register, switch per feature, prompt and model versions on audit rows, tool allowlists per role, evaluation gate) | 8, 10 | No | Next |
| UX-1 | Client polish from the design study (R1 to R12): focus in high contrast, colour-blind palette, directional change, one number formatter, icons, dark surfaces, motion tokens, density, settings split, desktop plugins and menu; installer and sign-in; freshness shown on every figure | 9 | No | Next |
| DATA-1 | Price revisions readable as known at a time; a change feed over market events; Power Query refreshable reads; ETRM and ERP import contracts | 1, 2 | No | After P-08 |
| TAR-1 | Public tariffs from TSOs, LNG terminals and storage operators, versioned indicative and final, slot windows, auction notices | 1, 5 | No (public sources) | After UX-1 |
| MAP-1 | The map: terminals and storage from published capacity, LNG carriers with tracks and ETAs, animated flows, page transitions; real or labelled data only | 5, 9 | No | After LNG-2 |
| NEWS-1 | News, policy and geopolitical events into analysis, cited and grounded under GOV-1's AI controls | 8 | No (public sources) | After GOV-1 |
| SCHED-1 | Nominations: explain mismatches between trades, confirmations and nominations (read only; nothing sent) | 5 | No | After LNG-2 |
| UX-2 | Personal workspaces from a governed component catalogue, "make me a view", command palette finds instruments, cargoes and vessels | 9, 12 | No | After UX-1 and GOV-1 |
| LOOP-1 | Improvement loop tooling: feedback lifecycle and thread with the requester, change specification template, repository map, triage | 12 | No | After UX-2 |
| M8 | Take-or-pay: ACQ, make-up, carry-forward and shortfall exposure on contracts, with events on change | 5 | No | Planned |
| M9 | Outcome ledger: recommendation -> decision -> trade reference -> realised value; one P&L definition | 12 | No (client trade data stays in the installation) | Planned, ADR first |
| M10 | Ontology consolidation; counterparty concept | 2 | No | Planned |
| M11 | Forecast ranges: NumPy in the runtime lock (ADR, licence review), quantile output, CRPS | 4 | No | Planned |
| M12 | Hosted pilot on Oracle Cloud with Aiven PostgreSQL; ENTSO-E with a token | 11, 1 | **Yes** (ENTSO-E token, Oracle Cloud, Aiven) | Dropped from this programme: the user will deploy later |
| M13 | Engineering discipline and optimiser consolidation: enforced module boundaries, one kernel each for LNG economics, P&L and freshness, one flow kernel, bounded storage DP, hedge optimiser | 3, 6 | No | Ongoing, optimiser later |

## Consolidated requirements (2026-11-24)

The owner asked on 2026-11-24 for many additions on top of the original brief, and noted
they overlap. Each one is mapped to a single slice above so nothing is built twice.

| Requirement (brief or 2026-11-24) | Slice |
| --- | --- |
| Continuous intelligence: events, outbox, targeted re-evaluation, staleness | M4 to M6 (done), M7 |
| "Live": feeds, processing, analysis and warnings in seconds; a streaming experience per role; opportunities the minute they open and withdrawn when they close; crisis alerts to whoever is in charge | M7 (latency budget per data class first; a streaming layer only on measured need) |
| AI-assisted strategy automation one step away | M7 signals plus M9 ledger; execution stays out of scope |
| Persona role-play and rigorous human-like testing to a commercial standard | Q1, then a review round after each user-facing slice |
| LNG cargo lifecycle in transit; the delayed-cargo example | LNG-1, QA-1 (done), LNG-2 |
| Where AI belongs per role; safe, controlled, predictable AI following industry practice | AIR-1 (design done), GOV-1, NEWS-1 |
| Personal tabs, views made with AI help; feedback turned into reviewed changes | UX-2, LOOP-1 (design in 14) |
| Learn from Kpler, Bloomberg, Platts, ETRMs, Kraken | 16 maps each lesson to DATA-1, GOV-1, SCHED-1, M7, M13 |
| Premium UI, design system, motion, installer, identity | UX-1 |
| Terminals, ETRM and ERP integration | DATA-1 (import contracts, change feed, refreshable reads) |
| Latency and millisecond decisions | M7 (seconds for decision support; milliseconds belong to execution systems) |
| Ontology constraints | M10, with additions made in each slice |
| Docs and SDK to commercial standard | DOC (done), kept current by each slice |
| 3D terminals, ships, voyages, flow animation | MAP-1 |
| Real public tariffs from every publisher, indicative and final | TAR-1 |
| News, policy and geopolitics, cited, no hallucination | NEWS-1 |
| Deployment | M12, dropped; the owner deploys later |
| Branch hygiene | Main plus one development branch |

## Order and reasoning

Built so far: M4 to M6, LNG-1, F1, DOC and the first persona round (QA-1, P-11). Next:

1. **P-08 and M7 together.** Every later screen and alert depends on one price and on
   changes reaching people in seconds. M7 builds role routing, which LNG-2 needs.
2. **LNG-2.** The owner's delayed-cargo example, end to end, on M7's routing.
3. **GOV-1.** Audit with the change and AI controls come before any feature that leans
   harder on AI (NEWS-1, "make me a view").
4. **UX-1.** Polish on a stable model; two items are bugs (high-contrast focus, desktop
   capabilities claimed without their plugins).
5. **DATA-1, then TAR-1, MAP-1, SCHED-1, NEWS-1**, each on the foundations above.
6. **UX-2 and LOOP-1**, once the component catalogue and AI controls exist.
7. **M8 to M11, M13** for commercial depth and consolidation.

A persona review round follows each user-facing slice. The owner dropped M12 on
2026-11-24.

## Working rules for every slice

- One development branch: `innovation/continuous-commercial-intelligence`. Atomic commits
  naming the milestone (`M5: ...`). No merge to `main` without the owner's word, no tag, no
  release package. Work branches are local and removed once their commits are on the
  development branch.
- Expand-only migrations, `DB_SCHEMA_REVISION` and the pinned test literals bumped together.
- `scripts/ci/pre_push_check.sh` before every push; PostgreSQL tests on a real server.
- Update 09 and 10 in the same commit as the code they describe.
