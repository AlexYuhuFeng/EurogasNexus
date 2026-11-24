# 08 Decision log

Programme decisions, newest first. Architecture-level decisions also go to
[the ADR](../../architecture/ARCHITECTURE_DECISION_RECORD.md).

| Date | Decision | Why | Alternatives rejected |
| --- | --- | --- | --- |
| 2026-11-24 | M5 captures changes from the stored rows, not inside each writer | Writers mix Core upserts and ORM merges; reading the store catches all of them, including manual importers, and the outbox already makes a re-read free of writes | ORM flush hooks (miss Core upserts); a hook in every writer (easy to forget the next one) |
| 2026-11-24 | A settlement's identity is hub, period, venue and trade day; its observation instant orders figures | A same-day correction is a revision; an earlier print found late cannot overwrite a later one | Market time alone (a re-observation becomes a new event); hashing the row id (an id change looks like news) |
| 2026-11-24 | A EUR fixing reaches stored cross pairs in the consumer | Opportunities store the conversion pair (`fx:GBPUSD`); fixings arrive per EUR leg | Fan out at publish time (couples the producer to the consumer's keys) |
| 2026-11-24 | `run_due` deletes pending classes by condition in the store | Removes the lost-change race without a lock held across the evaluation | Row lock for the whole evaluation (blocks every writer for minutes) |
| 2026-11-24 | The first consumer re-evaluates only evaluators whose stored opportunities depend on the event's keys; discovery of new opportunities stays with the CP-13 debounced full run | Targeted re-runs are cheap and exact for known exposure; a new opportunity needs the full scan anyway | Full evaluation on every event (too costly at price frequency); event-specific evaluators (duplicates the engine) |
| 2026-11-24 | Firm marks publish a digest, not the value | Marks are desk-private; consumers need to know that something changed and re-read it under their own permissions | Value in payload (leaks through replay and logs) |
| 2026-11-24 | A new revision supersedes the previous revision's undelivered rows | No consumer should spend effort on a corrected figure | Deliver every revision (wasted work, confusing alerts) |
| 2026-11-24 | Publication and ingestion time are outside identity and content | A re-download of the same figure must be a duplicate, not a revision | Hash the whole row (every poll becomes a revision) |
| 2026-11-24 | PostgreSQL transactional outbox; `LISTEN/NOTIFY` only as wake-up; no broker (ADR Decision 28) | Atomic with the data it describes, no new datastore (rule 5), replay is a query | Kafka or Redis streams (new infrastructure, dual-write problem); NOTIFY alone (lossy) |
| 2026-11-24 | M4 (events and outbox) is the first slice | Unblocks capabilities 1, 7, 10 and later 12; needs no credentials; hooks already in code | Take-or-pay (valuable but isolated); hosted pilot (blocked on access) |
| 2026-11-24 | Baseline is `main@6d21b89`; programme branch `innovation/continuous-commercial-intelligence` | Only maintained line; no release or architecture branch on the remote | Branch from a release candidate tag (behind `main`) |
