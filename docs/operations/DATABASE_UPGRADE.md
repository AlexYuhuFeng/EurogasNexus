# Upgrading the database

A new version of Eurogas Nexus may need a newer database schema. In production the schema is
**never changed when the stack starts**: an operator runs the gated upgrade, which checks for a
recent backup, shows what will change and whether it can be undone, runs the change with time
limits, and records who ran it in the audit trail.

The command is `scripts/ops/upgrade_database.py` (in the runtime image). In the runtime
compose stack, run it through the one-shot `migrate` service, which has the database settings:

```sh
docker compose run --rm migrate python scripts/ops/upgrade_database.py <command> ...
```

## What happens when the stack starts

The `migrate` step runs `upgrade_database.py on-start` before the API:

- **Trial and release** (production): it only *checks*. If the database is at the revision
  this version needs, the API starts. If not, the step prints the pending revisions and the
  command to run, exits with an error, and **the API does not start** on an old schema.
  `EUROGAS_NEXUS_AUTO_MIGRATE` is ignored here.
- **Development and the demo server**: it upgrades by itself (`EUROGAS_NEXUS_AUTO_MIGRATE`,
  on by default there; set `0` to turn it off), with the same time limits, recorded in the
  audit trail as `auto-migrate`.

## The upgrade, step by step

### 1. Plan (changes nothing)

```sh
docker compose run --rm migrate python scripts/ops/upgrade_database.py plan
```

It prints the database's revision, the revision this version needs, and each pending revision
in the order it would run, with:

- **can be undone**: `yes` (the downgrade undoes it); `yes, unless data recorded since would
  be lost` (the downgrade then refuses and says why); `nothing to undo` (the previous version
  works on the upgraded schema); or `no: going back means restoring the backup`;
- a note where the answer is not a plain yes.

Read the list. If any revision says "no", the only way back after the upgrade is the backup
you take in step 2. Release notes say which revisions a version brings.

### 2. Take a backup and let the upgrade see it

The upgrade refuses unless a backup was **recorded in the last 24 hours**
(`--max-backup-age-hours` changes the window).

- With the product's dump tool, the backup is recorded automatically:

  ```sh
  python scripts/ops/backup_runtime.py backups/
  ```

  It prints `Backup recorded for the gated upgrade: nexus-runtime-<time>.dump sha256:...`.
- With pgBackRest, a managed database snapshot or any other tool, take the backup the usual
  way, then record it:

  ```sh
  docker compose run --rm migrate python scripts/ops/upgrade_database.py record-backup \
    --operator "Jane Smith" --kind pgbackrest --reference "20261126-020000F"
  ```

The record is an audit event (`database.backup.recorded`), so it lives in the same database
and the auditors see it.

### 3. Choose a quiet moment

Each migration statement waits at most **10 seconds for a lock** (`lock_timeout`) and runs at
most **1 hour** (`statement_timeout`). If a migration cannot get its lock in time (the desk,
ingestion or a report holds the table), it fails and the whole upgrade is rolled back: nothing
is half-done, and nobody waits behind it. (One exception: a revision that builds an index
"concurrently" must commit what ran before it; if a later revision then fails, the earlier
ones stay applied, and running the upgrade again continues from there.) Outside the busiest hours this rarely happens. To
make sure, stop the scheduler first:

```sh
docker compose --profile public-ingestion stop public-ingestion-worker market-events-worker
```

Change the limits only when a release note says so: `--lock-timeout 30s`,
`--statement-timeout 3h` (or the settings `EUROGAS_NEXUS_MIGRATION_LOCK_TIMEOUT`,
`EUROGAS_NEXUS_MIGRATION_STATEMENT_TIMEOUT`).

### 4. Upgrade

```sh
docker compose run --rm migrate python scripts/ops/upgrade_database.py upgrade \
  --operator "Jane Smith"
```

It prints the plan and the backup it relies on, asks you to type `upgrade`, and runs. `--yes`
skips the question in a script. It ends with `upgraded to <revision>; recorded in the audit
trail as Jane Smith`. Exit codes: 0 done (or nothing to do), 1 failed, 2 refused (no backup,
no confirmation, a bad option).

The audit trail records, for each run, `database.upgrade` with the outcome (`started`,
`succeeded`, `failed`), who ran it, the revisions from and to, the backup reference or the
override reason, and the time limits.

### 5. Start the new version

```sh
docker compose up -d
```

The `migrate` step now finds the database up to date and the API starts.

## When something goes wrong

- **"REFUSED: no backup recorded in the last 24 hours"**: take or record a backup (step 2).
  Only if a backup is impossible and the risk is accepted, run with
  `--without-backup "<why>"`; the reason is recorded in the audit trail.
- **"FAILED at <revision>: a migration waited longer than lock_timeout"**: nothing changed
  (the upgrade rolls back as a whole). Stop the writers (step 3) and run it again.
- **"FAILED at <revision>: <error>"**: nothing changed. Keep the old version running, keep the
  output, and contact the vendor with it.
- **The stack does not start after a version change** (`migrate` exits 1): the database needs
  the upgrade; run steps 1 to 5.

## Going back

- If every applied revision says `yes`, the previous version's schema can be restored with
  Alembic's downgrade to the old revision (vendor-assisted; take a backup first).
- If any says `no`, restore the backup from step 2
  ([BACKUP_RESTORE.md](BACKUP_RESTORE.md), [DISASTER_RECOVERY.md](DISASTER_RECOVERY.md)) and
  start the previous version.

## For developers writing migrations

Every migration declares `reversibility` (`reversible`, `conditional`, `no-op`,
`irreversible`) and, unless reversible, a `reversibility_note`; the template
(`alembic/script.py.mako`) has the lines and `tests/contract/test_migration_reversibility.py`
checks that the declaration matches `downgrade()`. An index on a large table
(`eurogas_nexus.db.migration_rules.LARGE_TABLES`: observations, quotes, revisions, raw pages,
events, audit) is built with `create_index_nonblocking`, which uses `CREATE INDEX CONCURRENTLY`
on PostgreSQL so writes continue during the build. Seven migrations written before the rule
built such an index inside the transaction (listed in the contract test); on a large store an
upgrade across them blocks writes to those tables while the index builds.
