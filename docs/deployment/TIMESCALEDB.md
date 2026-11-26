# TimescaleDB Community Edition (optional)

**Audience:** the operator of a self-hosted PostgreSQL runtime store.
**Decision:** [ADR Decision 39](../architecture/ARCHITECTURE_DECISION_RECORD.md#decision-39-timescaledb-community-edition-is-an-optional-extension-off-by-default).
**Default:** off. PostgreSQL 16 without the extension is a complete runtime store; nothing in the
product needs TimescaleDB, and development, CI, the demo and every test run without it.

## What it changes

With the extension enabled, three append-only tables become hypertables with columnstore
compression (`eurogas_nexus.db.timescale.HYPERTABLE_PLANS`):

| Table | Time column | Chunk | Compressed after | Why it qualifies |
|---|---|---|---|---|
| `raw_payload_archives` | `received_at_utc` | 7 days | 28 days | about 91 % of today's growth (doc 19, section 1.4); append-only |
| `market_quotes` | `observed_at_utc` | 1 day | 7 days | ticks, the largest stream once ticks are licensed (doc 19, scenario C) |
| `market_trades` | `traded_at_utc` | 7 days | 7 days | trade prints, append-only |

Each primary key widens from `(id)` to `(id, time)`: a hypertable needs its time column in every
unique index. No writer names these keys as an `ON CONFLICT` target, so every write path works
unchanged (`tests/integration/test_timescale_present_postgres.py::test_writers_work_on_compressed_chunks`:
the archive, the tick ingestion, an ORM merge that updates a compressed row and the retention
delete, all on compressed chunks).

Not converted, each with its reason in `SKIPPED_TABLES`: the observation tables (written by
upserts keyed on their id alone, which a hypertable cannot keep unique), the event outbox and its
deliveries (idempotence rests on unique keys without time, ADR Decision 28) and the audit log
(governed evidence). No continuous aggregate is created: the daily readers answer as of an
instant and take revisions into account, which a continuous aggregate would not.

## Licence

TimescaleDB's hypertables are Apache-2.0; compression (and continuous aggregates) are in the
Community Edition under the Timescale License (TSL). The product never bundles, ships or hosts
TimescaleDB; the customer installs it on its own server. The review and its conditions are in
[`docs/legal/DEPENDENCY_LICENSE_REVIEW.md`](../legal/DEPENDENCY_LICENSE_REVIEW.md#timescaledb-community-edition-optional-2026-11-26).
In short: a firm running it for its own desk is internal use, which the TSL permits; offering it
to others as a database service is not permitted, and a hosted Eurogas Nexus would have to keep
its customers away from schema changes (it gives them none today).

## Enable it

1. Install TimescaleDB 2.13 or later for the server's PostgreSQL major version (the official
   packages, or the `timescale/timescaledb:<version>-pg16` image). The Community Edition is the
   default of those packages; packages labelled `oss` (and managed services that offer only the Apache-2 edition) lack compression.
2. In `postgresql.conf`: `shared_preload_libraries = 'timescaledb'` and
   `timescaledb.license = 'timescale'`; restart the server.
3. Either let the migration create the extension (the migration role must be allowed to: usually
   a superuser), or create it beforehand as a superuser: `CREATE EXTENSION timescaledb;`.
4. Set `EUROGAS_NEXUS_TIMESCALE`:
   - `off` (default): nothing changes, even where the extension is installed;
   - `auto`: convert where the server can, otherwise log why not and carry on;
   - `require`: as `auto`, but stop the migration when the server cannot (a production server
     that is meant to have it does not silently run without it).
5. Run the migrations (`alembic upgrade head`). Migration `0093_timescale_optional` converts once.
   On a store already at `0093` (the extension installed later), run
   `python scripts/ops/timescale.py apply` with the same setting; it is idempotent.
6. Check: `python scripts/ops/timescale.py status` (mode, versions, licence, each planned table's
   state and any blocker), and `GET /api/health/ready` → `extensions.timescaledb`
   (`active`, `installed`, `available`, `absent`, `not_postgresql`, `unknown`; informational,
   never a readiness failure).

On a large existing table the conversion copies the rows into chunks (`migrate_data`) inside
the migration's transaction: plan it in a maintenance window.

## Downgrade and leaving TimescaleDB

The migration's downgrade is deliberately a no-op: the hypertables stay hypertables. Downgrading
further works (tried past `0072`, which drops columns and a hypertable, see "Proof"), until the
chain's own non-reversible revisions (`0044`, `0042`, `0040`), which stop any store.

To move a converted store back to plain PostgreSQL, copy it into a new plain database instead of
restoring a dump (a dump of a converted store needs the extension to restore; on plain PostgreSQL
the hypertables' rows are lost):

```bash
# 1. a new plain database at the same head, with the setting off
createdb -h <plain-host> -U <user> nexus_plain
DATABASE_URL=postgresql+pg8000://<user>@<plain-host>/nexus_plain EUROGAS_NEXUS_TIMESCALE=off alembic upgrade head
# 2. every other table's rows
pg_dump -h <ts-host> -U <user> -d nexus --data-only --format=custom \
  --exclude-table=alembic_version --exclude-table=raw_payload_archives \
  --exclude-table=market_quotes --exclude-table=market_trades \
  --exclude-schema='_timescaledb*' --exclude-schema=timescaledb_information \
  --exclude-schema=timescaledb_experimental -f data.dump
pg_restore -h <plain-host> -U <user> --data-only --disable-triggers --no-owner -d nexus_plain data.dump
# 3. the three hypertables, row by row through COPY
for t in raw_payload_archives market_quotes market_trades; do
  psql -h <ts-host> -U <user> -d nexus -c "\copy (SELECT * FROM $t) TO STDOUT" |
    psql -h <plain-host> -U <user> -d nexus_plain -c "\copy $t FROM STDIN"
done
```

Then point `RUNTIME_STORE_DATABASE_URL` at the plain database and run
`python scripts/ops/validate_runtime_db.py --json`.

## Backups

See [`BACKUP_RESTORE.md`](../operations/BACKUP_RESTORE.md#timescaledb): the restore target needs
the same TimescaleDB version, and the drill fails (`timescale_not_restored`) when a converted
source comes back as plain tables.

## Proof (2026-11-26, `timescale/timescaledb:latest-pg16`, TimescaleDB 2.32.1, PostgreSQL 16)

- `EUROGAS_NEXUS_TIMESCALE=auto alembic upgrade head` from `0092`: the three tables became
  hypertables with compression and three compression jobs; `scripts/ops/timescale.py status`:
  `state: active`, no blocker.
- `alembic downgrade 0092_lng_berth_rules`: no change (still hypertables); `downgrade
  0089_alert_reader_state`, then `upgrade head` again: unchanged, nothing failed.
- `alembic downgrade 0071_opportunity_pending_inputs` (past `0072`, which drops `market_trades`
  and columns of `market_quotes`), then `upgrade head` with `auto`: converted again.
- With rows in a compressed chunk: `pg_dump --format=custom`, then `timescaledb_pre_restore()`,
  `pg_restore`, `timescaledb_post_restore()` into a new database: hypertables, compressed chunk,
  rows and the three jobs restored. `scripts/ops/backup_restore_drill.py` against the same
  server: `ok`, `timescaledb_source` and `timescaledb_target` both `active`.
- The same dump restored onto plain PostgreSQL 16: the extension is missing and the hypertables'
  rows are not restored; the copy-out procedure above moved every row to a plain database.
- Plain PostgreSQL 16 (`postgres:16`): `off`, `auto` and `require` round trips; `auto` logs "the
  timescaledb extension is not installed on this server" and changes nothing; `require` stops the
  upgrade (`tests/integration/test_timescale_optional_postgres.py`). SQLite: no-op
  (`tests/unit/test_timescale_optional.py`).

Tests: `tests/unit/test_timescale_optional.py`;
`tests/integration/test_timescale_optional_postgres.py` (`EUROGAS_NEXUS_TEST_POSTGRES_URL`, a
server without the extension); `tests/integration/test_timescale_present_postgres.py`
(`EUROGAS_NEXUS_TEST_TIMESCALE_URL`, a server with it).
