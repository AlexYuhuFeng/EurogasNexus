# DB Runtime Hardening

## Status

Status: `complete-in-current-worktree`

DB runtime hardening has delivered the PostgreSQL runtime boundary needed for
the current release-candidate local scope.

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
alembic_revision=0013_gie_lng_dtmi_energy
required_tables=33
missing_tables=0
source=runtime-postgresql
```

## Operator Commands

```powershell
# Validate a running PostgreSQL (read-only, secret-safe)
python scripts/ops/validate_runtime_db.py --json

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
revision `0013_gie_lng_dtmi_energy`, including:

- `alembic_version`;
- `ingestion_runs`;
- `source_references`;
- reference network tables;
- runtime market/fx/capacity/storage/LNG/tariff tables;
- credentials, entitlement, audit, glossary, route-cost, and portfolio
  observation tables.

The authoritative list lives in code and should be validated with:

```powershell
python scripts/ops/validate_runtime_db.py --json
```

## Timeouts

Each timeout has one meaning (`db/session.py`, `db/resilience.py`;
`tests/unit/test_db_timeouts.py`, `tests/unit/test_db_resilience.py`,
`tests/integration/test_db_timeouts_postgres.py`,
`tests/integration/test_db_failover_resilience_postgres.py`). This is the one table: other
runbooks link here.

| Bound | Where | Value |
| --- | --- | --- |
| Connect (TCP, TLS, sign-in) | every engine `get_engine` builds | 5 s |
| | with `EUROGAS_NEXUS_DB_FAILOVER_HOSTS` (primary and standby) | 5 s per host, tried in order, plus one `pg_is_in_recovery()` under the same bound: at most 5 s x hosts |
| Start-up wait (`SELECT 1` with backoff, 0.5 s doubling to 10 s, jitter 20 %) | API and workers at start (`wait_for_database_at_startup`) | `EUROGAS_NEXUS_DB_STARTUP_WAIT_SECONDS`: 0 by default, 60 s in the shipped stacks; each try has the connect bound and a 10 s socket bound |
| Readiness probe (`/api/health/ready`) | one connection per probe, no pool | the connect bound; the container's probe gives up after 3 s |
| Statement (PostgreSQL `statement_timeout`) | API processes, incl. background jobs run inside the API | 30 s per statement (`EUROGAS_NEXUS_DB_STATEMENT_TIMEOUT_MS`) |
| | workers, the scheduler (the daily retention pass included), the demo seed, operator commands | none |
| | migrations (`alembic/env.py`, the gated upgrade) | 1 h, with `lock_timeout` 10 s (`EUROGAS_NEXUS_MIGRATION_*`) |
| Socket read (safety net only) | API connections | statement timeout + 30 s (60 s) |
| | every other connection | none; TCP keepalives instead |
| Dead peer (TCP keepalive, `TCP_USER_TIMEOUT`) | every connection | about 80 s (30 s idle, then 5 probes 10 s apart) |

The socket bound is never the statement limit. pg8000's `timeout` argument stays on the socket
for every read, so passing the connect bound that way (as before 2026-11-26) cut every statement
off after 5 s on the client while the server went on running it, holding its connection and
locks: the demo's re-seed and heavy pages under load failed that way, and the API's 30 s
statement timeout could never act. Now a statement the server cancels answers 503
`runtime_db_timeout` with `Retry-After: 5`, its connection goes back to the pool rolled back,
and `eurogas_db_statement_timeouts_total` counts it; a lost connection is dropped, answered 503
`runtime_db_unavailable` and counted in `eurogas_db_connections_lost_total`. A connection lost
during COMMIT answers 503 `runtime_db_commit_unconfirmed` without a retry hint (the change may be
saved; `db/resilience.py`). One classification serves all of these (`core/db_errors.py`).

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
