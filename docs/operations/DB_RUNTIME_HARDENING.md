# DB Runtime Hardening

## Status

Status: `complete-in-current-worktree`

DB runtime hardening has delivered the PostgreSQL runtime boundary needed for
the current V1 release-candidate local scope.

## Delivered Capabilities

- Required-table registry tied to Alembic migration revisions.
- Read-only DB health check using `SELECT 1`, table inspection, and revision
  query.
- Runtime DB validation script that is safe to run against a live PostgreSQL
  instance.
- DB URL redaction everywhere validation output is produced.
- Explicit migration lifecycle runbook.
- Repository factory contract and research-safe result envelope.
- API runtime posture exposed through `/api/runtime/db`.

## Current Runtime Evidence

Latest local runtime evidence:

```text
database_url_present=true
connectivity.ok=true
alembic_revision=0012_entsog_capacity
required_tables=33
missing_tables=0
source=runtime-postgresql
```

## Operator Commands

```powershell
# Validate a running PostgreSQL (read-only, secret-safe)
python scripts/ops/validate_v1_runtime_db.py --json

# Apply pending migrations (explicit operator action)
alembic upgrade head

# Roll back one migration
alembic downgrade -1
```

## Validated States

| State | Meaning |
|---|---|
| `COMPLETE` | DB reachable, all required tables present, revision reported |
| `PARTIAL: missing tables` | DB reachable but required tables absent |
| `PARTIAL: no alembic_version` | DB reachable but no migration tracking |
| `BLOCKED: no DB URL` | No `RUNTIME_STORE_DATABASE_URL`, `DATABASE_URL`, or `EUROGAS_NEXUS_DB_DSN` |
| `BLOCKED: unreachable` | DB URL configured but PostgreSQL not responding |

## Required Tables

The required-table registry currently covers 33 tables through Alembic
revision `0012_entsog_capacity`, including:

- `alembic_version`;
- `ingestion_runs`;
- `source_references`;
- reference network tables;
- runtime market/fx/capacity/storage/LNG/tariff tables;
- credentials, entitlement, audit, glossary, route-cost, strategy, and
  portfolio observation tables.

The authoritative list lives in code and should be validated with:

```powershell
python scripts/ops/validate_v1_runtime_db.py --json
```

## Import Safety Guarantee

- `apps.api.main` import does not require a database URL.
- Engine/session factories are lazy and require an explicit DB settings call.
- Default tests remain DB-free.
- Web, Windows, SDK, and CLI observe DB posture through backend API routes only.

## Remaining Operational Work

DB runtime hardening is complete for local release-candidate validation, but
production operations still need:

- scheduled ingestion and retries;
- monitoring and alerting;
- backup and restore runbooks;
- incident response and rollback procedures;
- deployment-specific secret management;
- multi-user auth, entitlement, audit, and export-governance hardening.
