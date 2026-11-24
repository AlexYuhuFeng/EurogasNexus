# 10 Programme state

Read this first when picking the programme up. Updated in the same commit as the work it
describes.

**Last updated:** 2026-11-24
**Branch:** `innovation/continuous-commercial-intelligence` (pushed; no pull request opened,
nothing merged, no tag, no release package)
**Baseline:** `main@6d21b898661d6466418b3aaeab505a7bc4fb4013`
**Schema head on the branch:** `0077_market_event_outbox`

## Where the programme stands

| Milestone | State |
| --- | --- |
| M1 Baseline | Done: [01](01_CURRENT_STATE_AUDIT.md), test results in [09](09_VALIDATION_EVIDENCE.md) |
| M2 Audit and gap matrix | Done: [01](01_CURRENT_STATE_AUDIT.md), [02](02_CAPABILITY_GAP_MATRIX.md) |
| M3 Design documents | Done: [03](03_TARGET_ARCHITECTURE.md) to [08](08_DECISION_LOG.md) |
| M4 Market events and outbox | Built and tested; acceptance A1 to A14 met ([06](06_ACCEPTANCE_CRITERIA.md)) |
| M5 Price, FX, outage, contract and assumption events | Next |
| M6 to M11, M13 | Planned ([05](05_IMPLEMENTATION_ROADMAP.md)) |
| M12 Hosted pilot | Blocked: ENTSO-E token, Oracle Cloud and Aiven access not set up |

## Commits on the branch

| Commit | Milestone |
| --- | --- |
| `7cddbe0` | M4 canonical market event model |
| `7fc4438` | M4 outbox tables, migration 0077 |
| `fdf6a53` | M4 outbox delivery, targeted re-evaluation, producers, operations CLI |
| `429f51a` | M4 ontology-review entry for `PublishKind` (caught by the full suite) |
| (this commit) | M1 to M4 documents, ADR Decision 28, execution state |

## Continuation plan (M5)

1. **Prices.** In the observation upsert path for settlement prices, compare the stored
   value with the incoming one; when it changed (or is new), publish `price.updated` with
   subject and dependency key `hub:<HUB>:<period label>`, market time the trade date,
   published time from the source where it gives one, and the run id as correlation. No
   event for an unchanged value. Same for FX (`fx:<BASE><QUOTE>:<value date>`).
2. **Outages.** The REMIT ingestion publishes `outage.published` with `identity` set to the
   message id and subject `outage:<message id>`, so a moved start time is a revision, not a
   new event.
3. **Desk edits.** Contract and assumption-set changes publish `contract.changed` and
   `assumption.changed` with their keys, next to the existing `note_input_changed` calls.
4. **Retire `run_due`'s race.** Once these producers publish, make the CP-13 full
   evaluation lock its pending rows (`FOR UPDATE`) or read the outbox instead.
5. Tests: one integration test per producer on fixtures (no network), plus a PostgreSQL
   test that a correction re-runs only the dependent evaluator.

Start by reading `src/eurogas_nexus/application/market_events.py` (publish, the consumer)
and the producers already wired: `publish_firm_marks` and `ingestion_events`.

## Operating the outbox

```bash
python scripts/ops/market_events.py status
python scripts/ops/market_events.py staleness
python scripts/ops/market_events.py drain --commit
python scripts/ops/market_events.py replay opportunities --since 2026-11-24T00:00:00Z --commit
python scripts/ops/market_events.py listen --interval 30   # PostgreSQL only
```

Without `--commit`, `drain` and `replay` roll back, so they can be tried safely.

## Open questions for the user

- Access for M12: an ENTSO-E API token, an Oracle Cloud tenancy and an Aiven PostgreSQL
  service. Nothing in M5 to M11 needs them.
- Whether to open a draft pull request for review (none opened).
