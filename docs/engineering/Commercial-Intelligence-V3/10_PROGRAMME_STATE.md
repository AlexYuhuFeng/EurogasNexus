# 10 Programme state

Read this first when picking the programme up. Updated in the same commit as the work it
describes.

**Last updated:** 2026-11-24
**Branch:** `innovation/continuous-commercial-intelligence` (pushed; no pull request opened,
nothing merged, no tag, no release package)
**Baseline:** `main@6d21b898661d6466418b3aaeab505a7bc4fb4013`
**Schema head on the branch:** `0077_market_event_outbox` (M5 adds no migration)

## Where the programme stands

| Milestone | State |
| --- | --- |
| M1 Baseline | Done: [01](01_CURRENT_STATE_AUDIT.md), test results in [09](09_VALIDATION_EVIDENCE.md) |
| M2 Audit and gap matrix | Done: [01](01_CURRENT_STATE_AUDIT.md), [02](02_CAPABILITY_GAP_MATRIX.md) |
| M3 Design documents | Done: [03](03_TARGET_ARCHITECTURE.md) to [08](08_DECISION_LOG.md) |
| M4 Market events and outbox | Built and tested; acceptance A1 to A14 met ([06](06_ACCEPTANCE_CRITERIA.md)) |
| M5 Settlement, FX and REMIT events; the CP-13 race | Built and tested; acceptance B1 to B11 met ([06](06_ACCEPTANCE_CRITERIA.md)) |
| M5b Contract and assumption events | Next |
| M6 to M11, M13 | Planned ([05](05_IMPLEMENTATION_ROADMAP.md)) |
| M12 Hosted pilot | Blocked: ENTSO-E token, Oracle Cloud and Aiven access not set up |

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
| (this commit) | M5 documents, evidence and state |

## What M5 built

`src/eurogas_nexus/application/market_event_capture.py` reads the stored settlements, FX
fixings and REMIT messages and publishes what changed. It runs after every scheduler cycle
over a 4-day window, and inside `import_settlements.py` and `import_fx_fixings.py` in the
importer's own transaction. Held content writes nothing, so re-reading is safe. The
consumer widens a EUR fixing to the stored cross pairs that contain its other currency.
`run_due` (CP-13) now deletes pending classes by condition in the store, so a change noted
while it runs is no longer lost (R4).

## Continuation plan (M5b, then M6)

1. **Desk edits (M5b).** Contract and assumption-set changes publish `contract.changed`
   (`contract:<id>`) and `assumption.changed` (`assumption:<key>`), next to the existing
   `note_input_changed` calls in the contract and assumption services. Test that only the
   evaluators that read the key re-run.
2. **Live quotes (R14).** Measure `market_quotes` volume first; capture only if a quote-driven
   evaluator needs it sooner than the CP-13 full evaluation.
3. **New outages.** Today a new REMIT message's key is read by no stored opportunity, so it
   reaches evaluators through the CP-13 full evaluation; decide whether `outage.published`
   should trigger the outage evaluators directly.
4. **M6.** Turn `market_events.py staleness` and dead letters into monitoring alerts, and
   load-test publish and delivery.

Start with `application/market_event_capture.py` and `application/market_events.py`.

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
