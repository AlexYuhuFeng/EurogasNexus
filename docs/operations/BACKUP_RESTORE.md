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

For the current local Docker PostgreSQL without `pg_dump` on the host,
provision a separate disposable drill database and supply its connection through
the process environment. Never target the retained application database:

```powershell
python scripts/ops/backup_restore_drill.py `
  --target-database-url $env:EUROGAS_RESTORE_DRILL_DATABASE_URL `
  --pg-docker-container eurogas-nexus-postgres
```

The current local container uses loopback port `51356` and externally managed
credentials; it has no default development password. Start it through
`scripts/ops/Start-LocalAcceptance.ps1`. The drill target must be distinct from
`nexus_browser` and all other retained project databases.

Historical CR-11 drill evidence (not the current container configuration):

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

For the user's current workstation migration, the explicit instruction is to
delete old embedded data and migration backups after successful migration and
application verification. Do not apply the generic retention policy below to
those migration copies. This local instruction does not establish a customer
production backup policy.

Keep at least 7 daily dumps for preview/trial. CR-11 engineering RPO target is
≤24h with a measured local restore of 2.8s for the current scratch database
size; production retention and encryption remain deployment-owner policy.
