# 10 Programme state

Read this first when picking the programme up. Updated in the same commit as the work it
describes.

**Last updated:** 2026-11-24
**Branch:** `innovation/continuous-commercial-intelligence` (pushed; no pull request opened,
nothing merged, no tag, no release package)
**Baseline:** `main@6d21b898661d6466418b3aaeab505a7bc4fb4013`
**Schema head on the branch:** `0078_lng_cargo_hedges` (LNG-1)

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
| M7 to M11, M13 | Planned ([05](05_IMPLEMENTATION_ROADMAP.md)) |
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
| (this commit) | F1 audit blockers: gas-day status, scheduled tracks, segregation of duties, audited partial updates, feed plausibility |

## What M5 built

`src/eurogas_nexus/application/market_event_capture.py` reads the stored settlements, FX
fixings and REMIT messages and publishes what changed. It runs after every scheduler cycle
over a 4-day window, and inside `import_settlements.py` and `import_fx_fixings.py` in the
importer's own transaction. Held content writes nothing, so re-reading is safe. The
consumer widens a EUR fixing to the stored cross pairs that contain its other currency.
`run_due` (CP-13) now deletes pending classes by condition in the store, so a change noted
while it runs is no longer lost (R4).

## Continuation plan (Q1, F1, then M7)

1. **Q1.** Review every surface against [11](11_COMMERCIAL_QUALITY_STANDARD.md) per role in a
   real browser (clicks, hover, chart interaction, keyboard), checking each figure against
   its source; record findings in [13](13_PERSONA_AND_PRACTICE_REVIEW.md).
2. **F1 (built).** Gas-day status answers; daily tracks are scheduled; segregation of
   duties; audited partial updates; feed plausibility and licensed-label grants. Left:
   four-eyes on limits with P-17, and the S1/S2 findings of the hands-on review.
3. **Desk polish from the UI review.** Stale vs live styling, prices above the fold,
   directional value flash, instrument search in the palette, consistent units, number
   formatting, transitions, sign-in and installer.
4. **Data.** Public tariff pickup with quarantine and versions; label simulated LNG terms;
   news and events with citation checks ([13](13_PERSONA_AND_PRACTICE_REVIEW.md)).
5. **M7.** New-engine opportunities to alerts and the stream; deploy the listen worker.

The research behind 13 is in the session workspace and summarised there; nothing in it is
needed to build.

## Operating the outbox

```bash
python scripts/ops/market_events.py status
python scripts/ops/market_events.py staleness
python scripts/ops/market_events.py capture --since 2026-11-01T00:00:00Z --commit
python scripts/ops/market_events.py drain --commit
python scripts/ops/market_events.py replay opportunities --since 2026-11-24T00:00:00Z --commit
python scripts/ops/market_events.py listen --interval 30   # PostgreSQL only
```

Without `--commit`, `capture`, `drain` and `replay` roll back, so they can be tried safely.

## Open questions for the user

- Access for M12: an ENTSO-E API token, an Oracle Cloud tenancy and an Aiven PostgreSQL
  service. Nothing in M5b to M11 needs them.
- Whether to open a draft pull request for review (none opened).
