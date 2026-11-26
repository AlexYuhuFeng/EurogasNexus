# DRAFT ADR: Database standby, continuous backup, object storage and retention by data class

**Status:** DRAFT, awaiting owner review (2026-11-26). Proposed in
[ARCHITECTURE_V3_PLAN.md](../ARCHITECTURE_V3_PLAN.md) section 3.2. On acceptance it is appended
to [ARCHITECTURE_DECISION_RECORD.md](../ARCHITECTURE_DECISION_RECORD.md) as the next decision.
It amends Decision 24 (retention) and Decision 22 (it brings the standby forward from "on
measured trigger" to "required for production"); it adds no new database.

**Context.** The only backup is a logical dump taken by hand (`docs/operations/BACKUP_RESTORE.md`),
so up to a day of decisions, approvals and audit can be lost (recovery point 24 hours,
`DISASTER_RECOVERY.md`); the 30-minute recovery time has been measured only on dumps of a few
hundred kilobytes. There is no standby (`deploy/runtime/compose.yaml` runs one
`postgres:16-alpine`). The raw source-page archive is about 91 % of database growth (about
107 MB a day today, 3.2 GB a day with hourly flows; capacity study section 1.4), mostly the same
page stored again. `application/retention.py` deletes quotes after 30 days and observations
after 90, which would destroy the settlement and curve history that risk, compliance and the
five-year backfill need. Five reviews (technology, operations, security, middle office, quant)
name these as blockers or majors. Recovery is a control requirement of every trading firm's
IT risk function, so it needs no further measured need under AGENTS.md rule 5.

**Decision.**

1. Production runs PostgreSQL 16 as a **primary with a hot standby** (streaming replication),
   with automatic or one-command failover: Patroni (MIT) on self-managed servers, or the
   customer's managed PostgreSQL with high availability. A pilot runs the same pair.
2. **Continuous backup with pgBackRest (MIT)**: the write-ahead log shipped continuously to
   object storage; weekly full and daily differential backups; encryption at rest; recovery to
   any minute. Targets: recovery point 5 minutes or better, recovery time under 1 hour. The
   existing restore drill runs quarterly on a store of realistic size and records the measured
   times.
3. **Object storage** (any S3-compatible store with write-once retention: the customer's own,
   a cloud bucket or a provider) is part of the supported topology. MinIO is not shipped (AGPL,
   rule 18). Buckets: `backups` (base backups and WAL), `archive` (raw pages), `audit`
   (write-once daily audit exports with their signed digest), `history` (Parquet cold tier,
   when its trigger is met), `reports` (rendered report artefacts).
4. **Raw archive**: each distinct page is stored once, keyed by its digest and request; the
   parsed JSON is not stored (it is reproducible); pages older than four weeks move to the
   `archive` bucket compressed, with their digests kept in the database.
5. **Retention by data class**, configured per class, raised but never lowered below the floor
   by configuration, run by the product's own scheduler, archive before delete:
   trades and deal versions, closes, settlements, curves, decisions and audit at least 7 years;
   observations kept (hot 2 to 3 years, then Parquet); intraday quotes thinned to one-minute bars
   after 90 days; raw pages per the source's terms. The current 30-day and 90-day deletions are
   withdrawn.
6. **Database roles** (with the security remediation): migration owner, application (no DDL,
   insert-only on audit), read-only reporting, audit reader. The replica and backup tools use
   their own roles.
7. Monthly partitions and the Parquet cold tier keep Decision 24's triggers (50 million rows,
   or before the five-year backfill). TimescaleDB (Decision 39) stays optional and off.

**Alternatives.** (a) Nightly dumps plus a manual restore: fails a firm's recovery expectations
and loses a day. (b) Storage-level snapshots of a single server: no protection from logical
corruption to a point in time, and vendor-specific. (c) Logical replication to a second server:
more moving parts than physical streaming, no gain for one database. (d) Barman instead of
pgBackRest: equivalent; pgBackRest chosen for parallel, delta restore and native S3 support.
(e) A managed cloud database only: supported where the customer is on that cloud, but the
product must also run on-premises.

**Consequences.** Two database servers instead of one, and object storage, from the pilot on
(estimated 600 to 900 EUR a month rented for the pilot set). Operations gain a quarterly restore
drill and replication-lag monitoring. Retention changes stop the only destructive path to
history. The restore drill must also restore TimescaleDB hypertables where that option is on
(already enforced).

**Migration.** No application change for steps 1 to 3: deploy the standby, configure
pgBackRest, run a drill. Step 4 is an expand-only migration (digest columns, a `stored_in`
location) plus an offload job, with a replay test that rebuilds parsed observations from
archived files. Step 5 replaces `application/retention.py` with a policy table and a scheduled
job; the old script is removed. Step 6 is in the security remediation.

**Tests that make it observable.** A drill test that restores to a chosen minute and compares
row counts and the audit hash chain; a replay test from archived pages; a retention test that
proves settlements older than 90 days survive a retention run; a CI check that the compose and
deployment templates contain the standby and backup services.
