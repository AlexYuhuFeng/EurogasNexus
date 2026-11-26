# Disaster recovery

For operators and the firm's IT risk function. Engineering targets, not contractual guarantees.
The topology and backups are described in [BACKUP_RESTORE.md](BACKUP_RESTORE.md); decision record
[2026-11-26-standby-backup-object-storage-retention](../architecture/decisions/2026-11-26-standby-backup-object-storage-retention.md).

## Targets

| Asset | Recovery point (data you can lose) | Recovery time | How | Evidence |
| --- | --- | --- | --- | --- |
| Database, primary server lost | none for changes the standby had received (streaming, usually under a second behind); otherwise at most the last minute | minutes: fence and promote is one command | hot standby, `deploy/ha/failover.sh` | `ha_drill.py failover` (below) |
| Database, data damaged by mistake | back to any chosen minute | under 1 hour (target); measure quarterly at ≥ 50 GB | pgBackRest point-in-time restore | `ha_drill.py pitr`, [BACKUP_RESTORE.md](BACKUP_RESTORE.md#measured-results) |
| Both database servers lost | at most about 1 minute (`archive_timeout` 60 s) | restore time of the store on new servers | restore from object storage | as above |
| Object storage lost | none (the database is intact); backups restart | take a new full backup | a second bucket or site | `pgbackrest check` |
| Application server | none (state is in the database) | ≤ 5 minutes | `restart: unless-stopped`, redeploy the image | readiness 200 |
| Scheduler jobs | none; stale rows recovered | next scheduler scan | `scripts/ops/recover_stale_jobs.py` | heartbeat |
| Single-machine demo (daily dump) | up to 24 hours | ≤ 30 minutes at demo size | `pg_dump` / `pg_restore` | `backup_restore_drill.py` |

## How the application behaves during a database failure

You do not need to restart the application after a failover, if it lists both database servers:

- Every process (API and workers) waits for the database at start-up, retrying with backoff for
  `EUROGAS_NEXUS_DB_STARTUP_WAIT_SECONDS` (60 in the shipped stacks), instead of crashing.
- While the database is unreachable, `GET /api/health/ready` answers **503**
  `runtime_db_unavailable`. Put this endpoint behind the firm's load balancer and monitoring.
  Liveness (`/api/health/live`) stays 200: the process is fine, its database is not.
- A request that meets the outage gets **503 with a retry code**, never a 500, and never a silent
  success. Users see "the database could not be reached; nothing was saved; retry shortly".
- If the connection is lost during the very moment of saving, the user is told that the change
  **may or may not have been saved** (`runtime_db_commit_unconfirmed`) and to check before trying
  again. Writes are never repeated automatically, because a repeat could save something twice.
- With `EUROGAS_NEXUS_DB_FAILOVER_HOSTS` set, each new connection tries the configured servers in
  order and uses only one that accepts writes; a standby, or a fenced former primary, is skipped.
  After a promotion the application reaches the new primary on its next connection (measured:
  2.3 seconds from the crash to readiness 200 on the drill machine, the failover script itself
  1.4 seconds).
- Readiness also fails (`runtime_db_read_only`) if the application is ever pointed at a standby
  alone.
- The market-events listener reconnects with backoff and catches up from the outbox; nothing is
  lost, only delayed.

## Failure scenarios

### Primary database server lost (failover)

Detection: readiness 503 `runtime_db_unavailable` on every application server; the primary does
not answer; the standby is healthy and in recovery.

1. Confirm the primary is really down (not a network split between you and it). If in doubt,
   power it off or stop its container: two primaries must never run.
2. One command, on the host where compose manages both nodes (or run its steps on each server):

   ```bash
   deploy/ha/failover.sh pg-node1 pg-node2
   ```

   It stops the old primary, **fences** it (puts `standby.signal` in its data directory so that
   if it is ever started again it comes up read-only, and the application ignores it), promotes
   the standby, and starts a full backup on the new primary.
3. Verify: `GET /api/health/ready` returns 200 within a minute; a user can save; the backup
   scheduler of the new primary logs `backup.done`.
4. Later, rebuild the old server as the new standby (delta restore, minutes):

   ```bash
   deploy/ha/rejoin.sh pg-node1
   ```

   Check `SELECT application_name, state FROM pg_stat_replication` on the new primary shows it
   `streaming`.

Escalation: the database owner if the standby was not streaming before the failure (check
`replay_lag` history): then the recovery point is the last archived WAL instead.

### Data damaged or deleted by mistake

Detection: users or reconciliation report wrong or missing records; the audit trail shows the
action and its time.

Recovery: point-in-time restore to the minute before, into a **new** instance, then copy back the
damaged rows or switch over ([BACKUP_RESTORE.md, "Restore to a point in time"](BACKUP_RESTORE.md#restore-to-a-point-in-time)).
Never restore over the running primary. Verification: schema revision, required tables, the
expected rows; readiness 200 if switched over. Escalation: the deployment owner and, if trading
records are affected, compliance.

### Both database servers lost

Recovery: new servers, the image, the `.env` with the same bucket and cipher passphrase; restore
the latest point (`pgbackrest restore` without a target) onto the new primary, start it, take a
full backup, build the standby with `rejoin.sh`. Data lost: at most the WAL not yet archived
(about a minute).

### Object storage unreachable

Detection: `pgbackrest check` fails; `pg_stat_archiver.failed_count` rises; the primary's
`pg_wal` grows.

Impact: none for users while the store comes back; WAL accumulates on the primary's disk.
Recovery: restore access; archiving resumes by itself and catches up. If the disk fills before
that, PostgreSQL stops: free space or extend the volume, never delete files from `pg_wal`.
After a long outage take a full backup.

### Application server lost

Detection: liveness and readiness unreachable; supervisor restart loops. Impact: interactive API
down; database and persisted jobs intact. Recovery: redeploy the previous validated image; rerun
`smoke_release.py`. Verification: live and ready 200.

### Scheduler corruption or orphaned RUNNING jobs

Detection: missing scheduler heartbeat; RUNNING rows older than their thresholds. Recovery:
`python scripts/ops/recover_stale_jobs.py --commit`; restart the scheduler. Verification:
heartbeat returns; source freshness recovers.

### Bad deployment or bad migration

Follow `RELEASE_ROLLBACK.md`. Take a full backup before every upgrade (`pgbackrest --type=full
backup`): a migration that damages data is undone by a point-in-time restore to the minute before
it ran. Migration 0095 adds tables only; its downgrade loses the moved raw pages' only hot copy
unless `python scripts/ops/retention.py inline-raw-pages` runs first.

### Credential compromise

Revoke the API key, disable the principal, rotate the provider credential. If the object-storage
key or the backup cipher passphrase is compromised: rotate the key at the store; for the
passphrase, create a new repository with a new passphrase (`PGBACKREST_REPO1_PATH`), take a full
backup there, and retire the old one after its retention.

### Major provider outage, OIDC outage

Unchanged: affected sources degrade on their own (circuit OPEN, freshness STALE); new logins are
blocked while the identity provider is unreachable, existing sessions continue until expiry.

## TimescaleDB

Where the optional extension is on (`GET /api/health/ready` → `extensions.timescaledb: active`,
ADR Decision 39), every replacement server must run the same TimescaleDB version, preloaded.
pgBackRest restores hypertables and compressed chunks as files; the logical dump needs the
wrapped restore in [BACKUP_RESTORE.md](BACKUP_RESTORE.md#timescaledb-optional-extension-adr-decision-39).

## Drills

Quarterly, and before go-live: `scripts/ops/ha_drill.py pitr` (on the pilot servers at ≥ 50 GB)
and `scripts/ops/ha_drill.py failover --rejoin`. Record the reports' times in
[BACKUP_RESTORE.md](BACKUP_RESTORE.md#measured-results) and here:

| Date | Where | Store | Outage seen by the app | App ready after crash | Failover script | Data loss | Fenced node ignored | Rejoin |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-11-26 | Development machine (rehearsal, before the scheduler stopped promptly on SIGTERM; 10 s were the stop timeout) | 0.6 GB | 503 `runtime_db_unavailable` | 14.8 s | 13.2 s | none (marker written before the crash present) | yes | 14.6 s |
| 2026-11-26 | Development machine, report `docs/operations/drills/2026-11-26-failover-1gb.json` | 1.2 GB | 503 `runtime_db_unavailable` | 2.3 s | 1.4 s (stop 0.3, fence 0.6, promote 0.3) | none (marker written before the crash present on the new primary) | yes (restarted read-only; app kept writing to the new primary) | under 37 s (the report's figure counted the wait twice; fixed since) |
