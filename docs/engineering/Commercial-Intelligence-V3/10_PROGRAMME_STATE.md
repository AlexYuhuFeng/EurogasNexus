# 10 Programme state

Read this first when picking the programme up. Updated in the same commit as the work it
describes.

**Last updated:** 2026-11-25
**Branch:** `innovation/continuous-commercial-intelligence` (pushed; no pull request opened,
nothing merged, no tag, no release package)
**Baseline:** `main@6d21b898661d6466418b3aaeab505a7bc4fb4013`
**Schema head on the branch:** `0086_lng_disruption` (LNG-3: seven expand-only tables, ADR Decision 36), on `0084_news_items` (NEWS-1: tables `news_items`, `news_source_polls`), on `0085_sched1_nomination_matching` (SCHED-1: matching columns on `gas_day_nomination_events`), on `0083_tar1_tariff_book` (TAR-1: tables `tariff_versions`, `capacity_notices`), on `0082_data1_integration` (DATA-1: `market_events.writer_txid`, table `erp_references`), on `0081_change_requests` (P-17), on `0080_lng_eta_basis` (LNG-2), on `0079_licensed_data_use` (GOV-1, P6)

## Where the programme stands

| Milestone | State |
| --- | --- |
| M1 Baseline | Done: [01](01_CURRENT_STATE_AUDIT.md), test results in [09](09_VALIDATION_EVIDENCE.md) |
| M2 Audit and gap matrix | Done: [01](01_CURRENT_STATE_AUDIT.md), [02](02_CAPABILITY_GAP_MATRIX.md) |
| M3 Design documents | Done: [03](03_TARGET_ARCHITECTURE.md) to [08](08_DECISION_LOG.md) |
| M4 Market events and outbox | Built and tested; acceptance A1 to A14 met ([06](06_ACCEPTANCE_CRITERIA.md)) |
| M5 Settlement, FX and REMIT events; the CP-13 race | Built and tested; acceptance B1 to B11 met ([06](06_ACCEPTANCE_CRITERIA.md)) |
| M5b Contract, hedge-band and assumption events | Built and tested; C1 to C6 met |
| M6 Feed, dead-letter and lag alerts | Built and tested; D1 to D4 met |
| LNG-1 Cargo in transit | Built and tested; E1 to E9 met ([12](12_LNG_CARGO_IN_TRANSIT.md)) |
| Q1 Quality standard and hands-on review | In progress ([11](11_COMMERCIAL_QUALITY_STANDARD.md)) |
| F1 Audit blockers | Built and tested; F1-1 to F1-7 met ([06](06_ACCEPTANCE_CRITERIA.md)) |
| DOC Documentation and SDK | Built and tested; DOC-1 to DOC-6 met |
| QA-1 Persona round 1 fixes | Built and tested; F1-8 to F1-10 met, review rows in [13](13_PERSONA_AND_PRACTICE_REVIEW.md) |
| P-11 Book-scoped opportunity evaluation | Built and tested |
| AIR-1 AI by role and improvement loop | Design done ([14](14_AI_ROLES_PERSONALISATION_AND_IMPROVEMENT_LOOP.md)); AIR-1 and AIR-2 met |
| 16 Competitive and design study | Done ([16](16_COMPETITIVE_STUDY.md)) |
| P-08 One price resolver | Built and tested |
| M7 Live pipeline | Built and tested; M7-1 to M7-9 met, M7-10 (legacy engine removal) blocked by its dependents (R19); design and budgets in [15](15_LIVE_PIPELINE_AND_LATENCY_BUDGET.md) |
| LNG-2 A cargo change reaches each role | Built and tested; LNG2-1 to LNG2-5 met ([06](06_ACCEPTANCE_CRITERIA.md)); who hears what in [12](12_LNG_CARGO_IN_TRANSIT.md); commit to every role's notification measured in [15](15_LIVE_PIPELINE_AND_LATENCY_BUDGET.md) section 8 |
| GOV-1 Audit with the change, AI controls, licensed-data use | Built and tested; GOV1-1 to GOV1-6 met ([06](06_ACCEPTANCE_CRITERIA.md)); maker-checker (P-17) built and tested, P17-1 to P17-9 met (migration `0081_change_requests`, ADR Decision 32); effective-dated changes not yet built |
| DATA-1 Data integration | Built and tested; DATA1-1 (as-of reads), DATA1-2 (change feed), DATA1-3 (Power Query reads) and DATA1-4 (ETRM and ERP import contracts) met ([06](06_ACCEPTANCE_CRITERIA.md)) |
| TAR-1 Public tariffs and capacity windows | Built and tested; TAR1-1 to TAR1-6 met ([06](06_ACCEPTANCE_CRITERIA.md)); ENTSOG is the only machine-readable publisher reachable, every other TSO, LNG and storage publisher is in the [registry](../../data/TARIFF_PUBLISHER_REGISTRY.md) as manual or parsed (terms not reviewed or restrictive); migration `0083_tar1_tariff_book`, ADR Decision 34 |
| MAP-1 The map | Built and tested; MAP1-1 to MAP1-6 met ([06](06_ACCEPTANCE_CRITERIA.md)): terminals and storage from ENTSOG published capacity with GIE inventory labelled by scope, carriers with reported and labelled estimated positions and ETA basis, flows with a direction only where the operator's side is known and a gas-day scrubber, 2D/3D with reduced motion. Not yet: frame rate measured in a browser, page-to-page transitions |
| SCHED-1 Nominations: why trades, confirmations and nominations disagree | Built and tested; SCHED1-1 to SCHED1-8 met ([06](06_ACCEPTANCE_CRITERIA.md)): per gas day, hub and counterparty traded, confirmed, nominated and TSO-matched quantities; eleven break kinds explained with their arithmetic and next step, ordered by cut-off and MWh at risk with an indicative cash-out; alerts in `nomination`, withdrawn when fixed; Today's Reconciliation row and What needs me; demo case R1. Read only, nothing sent. Not yet: shipper-code reference data (codes come from the scheduling file), a TSO confirmation feed (imported, not received) |
| NEWS-1 News and events in the analysis | Built and tested; NEWS1-1 to NEWS1-11 met ([06](06_ACCEPTANCE_CRITERIA.md)): a source registry with quoted terms (REMIT messages held, GOV.UK DESNZ feed polled; the Commission, EUR-Lex and ACER terms read, feed addresses not yet recorded; licensed and forbidden sources excluded), deterministic tags, a link from an item to a held outage that re-evaluates opportunities, role routing with dedupe and cooldown, the AI use `news_note` with a sentence-by-sentence grounding check and its evaluation set, three additive reads and the Desk → Today panel |
| LNG-3 A disruption re-optimises the portfolio | Built and tested; LNG3-1 to LNG3-8 met ([06](06_ACCEPTANCE_CRITERIA.md)); design, sources and limits in [17](17_LNG_PORTFOLIO_DISRUPTION_OPTIMISATION.md); migration `0086_lng_disruption`, ADR Decision 36; latency in [15](15_LIVE_PIPELINE_AND_LATENCY_BUDGET.md) sections 2 and 8 |
| CODEX-1 The Codex assessments on agents and big data | Reviewed and the valid, contained proposals built; CODEX1-1 to CODEX1-6 met ([06](06_ACCEPTANCE_CRITERIA.md)); verdicts and the list for the owner in [18](18_CODEX_ASSESSMENT_REVIEW.md); no route, migration or ADR; data sizing in doc 19 |
| CAP-1 Data capacity and infrastructure | Report done ([19](19_DATA_CAPACITY_AND_INFRASTRUCTURE.md)): sizes, rates and a staged recommendation for 15 years; recommendation only, nothing adopted; proposed ADRs ADR-P1 to ADR-P7 await the owner. Read-only measurement script `scripts/capacity/measure_db.py` (not shipped) |
| UX-1, UX-2, LOOP-1, M8 to M11, M13 | Planned, in the order of [05](05_IMPLEMENTATION_ROADMAP.md) |
| M12 Hosted pilot | Dropped by the user on 2026-11-24 (deployment later, outside this programme) |

## Commits on the branch

| Commit | Milestone |
| --- | --- |
| `7cddbe0` | M4 canonical market event model |
| `7fc4438` | M4 outbox tables, migration 0077 |
| `fdf6a53` | M4 outbox delivery, targeted re-evaluation, producers, operations CLI |
| `429f51a` | M4 ontology-review entry for `PublishKind` (caught by the full suite) |
| `b6f5326` | M1 to M4 documents, ADR Decision 28, execution state |
| `003da36` | M5 the scheduled evaluation keeps a change noted while it runs |
| `135ddf9` | M5 settlements, FX fixings and REMIT messages publish market events |
| `ae5fb6a` | M5 documents, evidence and state |
| `6dd2f8e` | Outbox: a return to earlier content is a revision |
| `f7a6875` | M5b contract, hedge band and assumption edits publish events |
| `224e17d` | M6 stale feeds and the outbox raise monitoring alerts |
| `877b355` | LNG-1 cargo in transit as one plan (migration 0078) |
| `dcbb498` | M5b, M6, LNG-1 documents; quality standard; research synthesis |
| `0d3d6e1` | F1 audit blockers: gas-day status, scheduled tracks, segregation of duties, audited partial updates, feed plausibility |
| `7a2b9de` | DOC README, docs index and SDK docs rewritten with verified examples; typed SDK errors; driverless database URLs |
| (F1-8 commit) | F1-8 scheduling role: a scheduler records nomination status (ADR Decision 30) |
| `8db91e5` | M7(a) listen worker is the default trigger; drain without event cap; one-minute debounce |
| `5411893` | M7(b) new-engine opportunities become alerts, routed to their owner, notified once |
| `e2e92f5` | M7(c) `/api/stream/opportunities` serves the opportunity engine; the page follows it live |
| (this commit) | M7 documents (15), latency measurement, legacy retirement blockers |
| `5cd947d` | LNG-2 an ETA carries its basis, confidence, source and time (migration 0080) |
| `4ff3f62` | LNG-2 mandate usage helpers shared by the limits screen and the cargo check |
| `4ad0103` | LNG-2 a cargo change reaches the trader, scheduler, risk and desk head |
| `dec1e4a` | LNG-2 web: who must act on a cargo change, and what its ETA rests on |
| (this commit) | LNG-2 documents and evidence |
| `6a5b5c4` | LNG-3 deterministic disruption optimiser for LNG cargoes and pipeline supply (`wip/lng3`) |
| `41e30da` | LNG-3 migration 0086 and ADR Decision 36 |
| `a9483e2` | LNG-3 re-optimise on events, three reads and a choose action, demo planted case D1 |
| `c88ab8f` | LNG-3 owner scenario through the store on SQLite and PostgreSQL; demo D1 planted test |
| `b1ecc82` | LNG-3 web Options section with a Choose that only records |
| (this commit) | LNG-3 documents and evidence |
| `93acaab` | CODEX-1 capability runtime controls from the Codex agentisation review |
| `892ca1d` | CODEX-1 versioned market change wire contract for a later transport |
| `1a3095e` | CODEX-1 documents (18) and evidence |
| `93fb109` | CAP-1 read-only measurement of table sizes and row counts |
| (this commit) | CAP-1 data capacity and infrastructure report (19), decision log and state |

## What M5 built

`src/eurogas_nexus/application/market_event_capture.py` reads the stored settlements, FX
fixings and REMIT messages and publishes what changed. It runs after every scheduler cycle
over a 4-day window, and inside `import_settlements.py` and `import_fx_fixings.py` in the
importer's own transaction. Held content writes nothing, so re-reading is safe. The
consumer widens a EUR fixing to the stored cross pairs that contain its other currency.
`run_due` (CP-13) now deletes pending classes by condition in the store, so a change noted
while it runs is no longer lost (R4).

## Continuation plan

The whole programme, the original brief and every addition of 2026-11-24, is one
deduplicated plan in [05](05_IMPLEMENTATION_ROADMAP.md) ("Consolidated requirements" and
"Order and reasoning"). In short:

1. **P-08 and M7 (built).** One price everywhere; the listen worker, role-routed alerts and
   opportunities pushed when they open and when they close. Left from M7: timed escalation
   (R20), conflated quote events (R14), retiring the legacy engine (R19).
2. **LNG-2 (built).** A delayed cargo reaches the trader, scheduler, risk and, when material,
   the desk head (criteria LNG2-1 to LNG2-5 in [06](06_ACCEPTANCE_CRITERIA.md)). Left: timed
   escalation when a role does not act (R20, as for M7), routing to a named person on duty.
   **LNG-3 (built)** values what the desk could do about it across the book
   and proposes a default ([17](17_LNG_PORTFOLIO_DISRUPTION_OPTIMISATION.md)). Left for the
   owner: an FX rule for USD demurrage, linking REMIT outages to the pipeline supply they
   curtail, and the default preference weights.
3. **GOV-1.** Audit with the change, entitlement reporting, maker-checker, AI controls.
4. **UX-1.** The twelve design-study fixes, installer and sign-in.
5. **DATA-1, TAR-1, MAP-1, SCHED-1, NEWS-1 and LNG-3 (built).** Then **UX-2, LOOP-1**, M8 to M11 and M13.


A persona review round follows each user-facing slice.

## Operating the outbox

```bash
python scripts/ops/market_events.py status
python scripts/ops/market_events.py staleness
python scripts/ops/market_events.py capture --since 2026-11-01T00:00:00Z --commit
python scripts/ops/market_events.py drain --commit
python scripts/ops/market_events.py replay opportunities --since 2026-11-24T00:00:00Z --commit
python scripts/ops/market_events.py listen --interval 15   # PostgreSQL only; also runs the due sweep
python scripts/ops/measure_live_latency.py after --samples 10   # API and listen worker running
```

Without `--commit`, `capture`, `drain` and `replay` roll back, so they can be tried safely.

## Open questions for the user

- Access for M12: an ENTSO-E API token, an Oracle Cloud tenancy and an Aiven PostgreSQL
  service. Nothing in M5b to M11 needs them.
- Whether to open a draft pull request for review (none opened).
- The branch `claude/gas-trading-tool-review-08bgpo` sits on the same commit as `main`; this
  session's access cannot delete it, so the owner deletes it.
