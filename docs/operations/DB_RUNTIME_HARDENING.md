# DB Runtime Hardening (Milestone 2)

## What This Milestone Delivers

Milestone 2 makes the PostgreSQL runtime boundary operator-ready:

- Required-table registry tied to Alembic migration revisions.
- Read-only DB health check (`SELECT 1`, table inspection, revision query).
- Runtime DB validation script that is safe to run against a live PostgreSQL
  instance.
- DB URL redaction everywhere.
- Explicit migration lifecycle runbook.
- Repository factory contract and research-safe result envelope.

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

| Table | Introduced In |
|---|---|
| `alembic_version` | `0001_m2_baseline` |
| `ingestion_runs` | `0002_m4_create_ingestion_runs` |

## Import Safety Guarantee

- `apps.api.main` import does not load `eurogas_nexus.db` or `sqlalchemy`.
- Engine/session factories are lazy and require an explicit `DatabaseSettings` call.
- Default tests (API, contract, integration, security) remain DB-free.
