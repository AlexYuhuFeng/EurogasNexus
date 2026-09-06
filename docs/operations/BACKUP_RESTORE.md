# Runtime Backup & Restore

## Scope

The runtime PostgreSQL database holds observations, contracts, decisions,
reviews, and audit events. This document defines the backup and restore
procedure for preview/trial deployments. CR-11 adds an automated drill and
records real local PostgreSQL evidence below.

## Backup

Prerequisite: `pg_dump` on PATH and `RUNTIME_STORE_DATABASE_URL` configured.

```powershell
python scripts/ops/backup_runtime.py .\backups
```

The script:

1. resolves the DSN (`postgresql+pg8000://...`), refusing non-PostgreSQL URLs;
2. writes `backups/nexus-runtime-<timestamp>.dump` in PostgreSQL custom format
   (`--format=custom --no-owner`);
3. prints the matching restore command.

Backups are taken **offline or during low-write windows** for preview scale.
Production-grade backups (continuous WAL archiving / PITR) are out of scope
until a production deployment is authorized.

## Restore (drill)

```powershell
# 1. create the target database if needed
createdb -h <host> -U <user> nexus_restore

# 2. restore the custom-format dump
pg_restore --clean --if-exists --dbname=nexus_restore .\backups\nexus-runtime-<timestamp>.dump
```

## Automated drill (CR-11)

```powershell
python scripts/ops/backup_restore_drill.py `
  --target-database-url postgresql+pg8000://user:pass@127.0.0.1:5432/nexus_restore_drill
```

For a local Docker PostgreSQL without `pg_dump` on the host:

```powershell
python scripts/ops/backup_restore_drill.py `
  --target-database-url postgresql+pg8000://eurogas:eurogas_dev@127.0.0.1:5432/nexus_restore_drill `
  --pg-docker-container eurogas-nexus-db
```

Recorded CR-11 drill evidence:

```text
source:      postgresql+pg8000://eurogas:***@127.0.0.1:5432/eurogas_nexus_cr10
target:      postgresql+pg8000://eurogas:***@127.0.0.1:5432/eurogas_nexus_restore_drill
dump_bytes:  161798
revision:    0030_reliability_indexes
missing_tables: []
api_smoke:   200
elapsed:     2.816s
```

## Verification checklist (must run after every drill)

- [ ] `alembic current` reports the expected head revision
      (`0029_enterprise_identity_v1` or later).
- [ ] Required-table check passes:
      `python -c "from eurogas_nexus.db.registry import list_missing_required_tables; print(list_missing_required_tables(engine))"`
- [ ] A DB-backed API read returns `meta.source_references == ["runtime-postgresql"]`
      (e.g. `GET /api/route-cost/tso-tariffs`).
- [ ] Row counts of `audit_events` and `optimization_runs` match the pre-backup
      snapshot (append-only tables are the canary for silent data loss).

## Retention

Keep at least 7 daily dumps for preview/trial. CR-11 engineering RPO target is
≤24h with a measured local restore of 2.8s for the current scratch database
size; production retention and encryption remain deployment-owner policy.
