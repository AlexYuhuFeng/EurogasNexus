# Backup and restore

For operators. Decision record:
[2026-11-26-standby-backup-object-storage-retention](../architecture/decisions/2026-11-26-standby-backup-object-storage-retention.md).
What to do when something has failed is in [DISASTER_RECOVERY.md](DISASTER_RECOVERY.md). How
long each kind of data is kept is in [RETENTION_SCHEDULE.md](../compliance/RETENTION_SCHEDULE.md).

## In short

| | Supported topology (pilot and production) | Single-machine demo only |
| --- | --- | --- |
| How | pgBackRest: the write-ahead log (WAL, the database's change journal) is copied to object storage continuously; full backup weekly, differential daily | `pg_dump` once a day |
| Data you can lose | at most about 1 minute (`archive_timeout` 60 s; a busy database ships every 16 MB) | up to 24 hours |
| Restore to | any moment between the oldest kept backup and now | the moment of the last dump |
| Where backups live | the firm's S3-compatible object storage, encrypted before upload | a local folder |
| Standby | a second database server, a hot copy seconds behind | none |
| Files | `deploy/ha/` | `scripts/ops/backup_runtime.py` |

Targets: recovery point 5 minutes or better (measured: about 1 minute), recovery time under
1 hour. The restore time must be measured each quarter on a store of realistic size (below).

## The supported topology

Two database servers, each running PostgreSQL 16 with pgBackRest (`deploy/ha/compose.yaml`):

- `pg-node1` starts as the **primary**, `pg-node2` as a **hot standby** that streams every change
  from it and can take over in seconds (failover: [DISASTER_RECOVERY.md](DISASTER_RECOVERY.md)).
- Each node has a **backup scheduler** beside it (`pg-node1-backup`, `pg-node2-backup`). Only the
  scheduler whose node is currently the primary does anything, so after a failover the backups
  follow the new primary without a change.
- The primary hands every completed WAL file to pgBackRest (`archive_command`), which compresses,
  encrypts and uploads it to the `backups` bucket. When the database is quiet, a file is closed
  and shipped at least every 60 seconds.
- **Any S3-compatible object storage works**: the firm's own (for example NetApp StorageGRID,
  Dell ECS, Ceph RGW), a cloud bucket (AWS S3, Azure via an S3 gateway, OVH, Scaleway) or a
  provider. Turn on write-once retention (object lock) for the backup bucket where the store
  supports it. MinIO is not supported or shipped: its server is AGPL-licensed (AGENTS.md rule 18).
- The product's own archive (retention: old ticks, raw pages) goes to a second bucket,
  configured in the application (`EUROGAS_NEXUS_OBJECT_STORE_URL`, `deploy/runtime/env.server.example`).

Why pgBackRest (MIT) and not WAL-G (Apache-2.0): both are permissive and proven. pgBackRest
was chosen because it is the tool the decision record names, it restores in parallel and by
delta (only changed files, which makes rebuilding a failed node fast), it builds a standby
straight from the repository, it verifies every file by checksum, encrypts the repository itself
and needs no extra service. WAL-G would also have served; it was not needed.

### First set-up

1. Ask the firm's storage team for a bucket (for example `nexus-backups`), an access key limited to
   it, and the CA certificate of the store if it uses a private one.
2. On each database server: `cp deploy/ha/env.ha.example deploy/ha/.env` and fill in every value.
   Keep the `.env` file readable only by the operators (`chmod 600`). Store
   `BACKUP_CIPHER_PASSPHRASE` in the firm's secret store as well: **without it no backup can be
   restored**.
3. Build the image: `docker build -t eurogas-nexus-postgres-ha:16 deploy/ha/postgres`.
4. Start the primary server's services: `docker compose -f deploy/ha/compose.yaml up -d pg-node1
   pg-node1-backup`. Its scheduler creates the backup repository (the "stanza") and takes the first
   full backup at once.
5. Start the standby server's services: `docker compose -f deploy/ha/compose.yaml up -d pg-node2
   pg-node2-backup`. An empty standby waits for that first backup, restores it and starts
   streaming.
6. Point the application at both (`deploy/runtime/env.server.example`):
   `RUNTIME_STORE_DATABASE_URL=...@pg-node1:5432/...` and
   `EUROGAS_NEXUS_DB_FAILOVER_HOSTS=pg-node2:5432`. Run the migrations as usual.
7. Run the drill below once before go-live and record the result.

### Daily checks (2 minutes)

```bash
# Backups: newest full and differential, sizes, the WAL range kept
docker compose -f deploy/ha/compose.yaml exec -u postgres pg-node1-backup pgbackrest info
# The archive is working end to end (forces a WAL switch and waits for it to arrive)
docker compose -f deploy/ha/compose.yaml exec -u postgres pg-node1-backup pgbackrest check
# The standby is streaming and how far behind it is (run on the primary)
docker compose -f deploy/ha/compose.yaml exec -u postgres pg-node1 \
  psql -c "SELECT application_name, state, replay_lag FROM pg_stat_replication"
```

Alert on: no new backup for more than 26 hours; `pgbackrest check` failing; `pg_stat_archiver`
showing `failed_count` rising; replication lag above 60 seconds; the standby missing from
`pg_stat_replication`.

### Backups by hand

```bash
docker compose -f deploy/ha/compose.yaml exec -u postgres pg-node1-backup pgbackrest --type=full backup
docker compose -f deploy/ha/compose.yaml exec -u postgres pg-node1-backup pgbackrest --type=diff backup
```

Take a full backup by hand before an upgrade and after every failover.

## Restore to a point in time

Use this when data was damaged or deleted by mistake (a bad import, a wrong script): you go back
to the minute before. A failed server is a failover, not a restore
([DISASTER_RECOVERY.md](DISASTER_RECOVERY.md)).

1. **Decide the moment** (UTC), for example `2026-11-26 14:02:00+00`: just before the damage.
   The audit trail (`audit_events.event_ts_utc`) usually shows when it happened.
2. **Restore into a new, empty volume or server, never over the running primary.** Restoring next
   to it lets you check the result and copy back only what was damaged, or switch over entirely.

   ```bash
   docker volume create nexus-restore
   docker run --rm -v nexus-restore:/var/lib/postgresql/data --entrypoint sh \
     eurogas-nexus-postgres-ha:16 -c 'chown postgres:postgres /var/lib/postgresql/data; chmod 700 /var/lib/postgresql/data'
   docker run --rm --env-file deploy/ha/.env.pgbackrest -u postgres \
     -v nexus-restore:/var/lib/postgresql/data \
     -v /path/to/objectstore-ca.crt:/etc/nexus/objectstore-ca.crt:ro \
     --entrypoint pgbackrest eurogas-nexus-postgres-ha:16 \
     --type=time "--target=2026-11-26 14:02:00+00" --target-action=promote restore
   ```

   `.env.pgbackrest` holds the same `PGBACKREST_*` values the compose file sets (bucket, endpoint,
   key, cipher passphrase). pgBackRest picks the right base backup and fetches the WAL needed.
3. **Start it with archiving off**, so the copy never writes into the production repository:

   ```bash
   docker run -d --name nexus-restored --env-file deploy/ha/.env.pgbackrest \
     -e NEXUS_ARCHIVE_MODE=off -p 127.0.0.1:5499:5432 \
     -v nexus-restore:/var/lib/postgresql/data \
     -v /path/to/objectstore-ca.crt:/etc/nexus/objectstore-ca.crt:ro eurogas-nexus-postgres-ha:16
   ```

   It replays the WAL up to the moment and opens for writes (`SELECT pg_is_in_recovery()` turns
   `f`).
4. **Check it**: `python scripts/ops/backup_restore_drill.py` checks are available as a function;
   the quickest manual check is the schema revision (`SELECT version_num FROM alembic_version`),
   the rows you expected, and the API's readiness pointed at the copy.
5. **Use it**: either copy the damaged rows back to the primary (`pg_dump -t <table> --data-only`
   from the copy, reviewed, then loaded), or make the copy the new primary: stop the application,
   point `RUNTIME_STORE_DATABASE_URL` at it, start the application, take a full backup, then
   rebuild a standby from it (`deploy/ha/rejoin.sh`). Record what was done in the incident log.

## The drill (quarterly, and before go-live)

`scripts/ops/ha_drill.py` runs both drills end to end and writes a JSON report:

```bash
# On a drill machine without the firm's object store (uses the test double, in memory):
python scripts/ops/ha_drill.py prepare --workdir /srv/nexus-drill
python scripts/ops/ha_drill.py up      --workdir /srv/nexus-drill --no-standby
python scripts/ops/ha_drill.py pitr    --workdir /srv/nexus-drill --target-gb 50
python scripts/ops/ha_drill.py down    --workdir /srv/nexus-drill
# Against the firm's object store: write an env file like deploy/ha/env.ha.example (with a
# drill bucket) and pass --env-file instead of running prepare.
```

What `pitr` does: migrates a scratch database named `drill_*`, fills it with synthetic
observations and quotes to the size asked (every row marked `DRILL-SYNTHETIC`, never a market
price), takes a full base backup, writes more, records a time T and the row counts and an
order-independent checksum of three tables, writes more after T, makes sure the WAL is archived,
then restores to T on a fresh instance and compares: the counts and checksums must equal those at
T, the rows written after T must be absent, the schema revision and required tables must be this
release's and the API must report ready against the copy. It refuses to run against a database
whose name does not start with `drill`, and stops before free disk or memory falls below
`--min-free-gb`.

The plan's exit criterion is a restore to a chosen minute **on a store of at least 50 GB on the
pilot database servers**; record its times here each quarter.

### Measured results

| Date | Where | Store | Base backup | Repository size | Restore files | WAL replay to T and open | Total restore | Checks |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-11-26 | Development machine, 4 cores shared with other work, Docker volumes on its virtual disk; test object store in memory; report `docs/operations/drills/2026-11-26-pitr-5gb.json` | 5.50 GB (5.77 M observations, 5.77 M quotes; synthetic) | 22.8 s | 656 MB (zstd; synthetic rows compress about 8x, real data less) | 13.3 s | 3.5 s | 17.1 s | counts and checksums of 3 tables equal at T, 20 000 + 20 000 + 50 rows written after T absent, schema `0095`, required tables, API ready: pass |
| 2026-11-26 | Same machine, rehearsal | 0.58 GB | 7.7 s | 71 MB | 6.3 s | 2.8 s | 9.5 s | counts, checksums, after-T absent, schema, API ready: pass |
| (quarterly) | Pilot database servers, NVMe | ≥ 50 GB | | | | | | |

The 50 GB drill needs the pilot hardware: the development machine has neither the disk nor the
memory for it. Read the 5.5 GB figures with care: the WAL to replay between the base backup and
T was small (seconds of writes), the object store was local and in memory, and the data was
synthetic. On a production store the replay of a day's WAL after the last differential, and the
network to the firm's object store, dominate; that is what the quarterly drill measures. Loading
the store took 334 s (about 16 MB/s with four shared cores). Earlier evidence (logical dump of a 162 KB scratch store, CR-11, 2.8 s) is kept in
the history and says nothing about a store of realistic size.

## Single-machine demo: the daily dump (secondary option)

The demo stack (`deploy/runtime/compose.yaml`, one PostgreSQL) has no standby and no WAL archive.
It is backed up with a logical dump; up to a day of changes can be lost. Do not use this for a
customer's pilot or production.

```bash
python scripts/ops/backup_runtime.py ./backups          # writes backups/nexus-runtime-<time>.dump
pg_restore --clean --if-exists --no-owner --dbname=<target> backups/nexus-runtime-<time>.dump
python scripts/ops/backup_restore_drill.py --target-database-url <scratch target URL>
```

The dump drill restores into a separate scratch database and runs the same checks as the
point-in-time drill (`verify_restored_database`: schema revision, required tables, representative
tables, TimescaleDB hypertables where the source had them, API readiness against the copy).
Keep at least 7 daily dumps, copied off the machine. Without `pg_dump` on the host, add
`--pg-docker-container <container>`.

### TimescaleDB (optional extension, ADR Decision 39)

pgBackRest copies the data files, so hypertables and compressed chunks come back as they were;
the replacement server must run the same TimescaleDB version, preloaded. For the logical dump,
the restore target must also run the same version, preloaded, and the restore is wrapped:

```bash
createdb -h <host> -U <user> nexus_restore
psql -h <host> -U <user> -d nexus_restore -c "CREATE EXTENSION IF NOT EXISTS timescaledb; SELECT timescaledb_pre_restore();"
pg_restore -h <host> -U <user> --no-owner -d nexus_restore nexus-runtime-<timestamp>.dump
psql -h <host> -U <user> -d nexus_restore -c "SELECT timescaledb_post_restore();"
```

The drills report `timescaledb_source` / `timescaledb_target` and fail with
`timescale_not_restored` when a converted source comes back without hypertables.

## Retention of backups

pgBackRest keeps two full backups (`BACKUP_RETENTION_FULL=2`, so two to three weeks of
point-in-time recovery) and expires older ones with the WAL they needed. The long-term copy of
history is the retention archive, not backups ([RETENTION_SCHEDULE.md](../compliance/RETENTION_SCHEDULE.md)).
Raise `BACKUP_RETENTION_FULL` if the firm's policy wants a longer recovery window.
