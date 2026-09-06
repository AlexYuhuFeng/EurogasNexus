# Production Reliability Specification — CR-11

Status: normative for the CR-11 operations milestone. Reliability is evidence,
not documentation; each claim below is tied to a script, test, or recorded
drill.

## 1. Service/dependency topology

```text
CLIENTS
  Web (React/Vite)  -> /api (HTTPS gateway or direct loopback)
  Tauri Desktop     -> /api + system-browser OIDC loopback
  SDK/CLI           -> /api

APPLICATION
  API (FastAPI/uvicorn)      -- single runtime process per container
  dataops scheduler          -- PostgreSQL SKIP LOCKED claims (script/worker)
  shadow scheduler           -- PostgreSQL SKIP LOCKED claims (script/worker)
  monitoring worker          -- optional alert scan/LLM enrichment
  SSE streams                -- server-sent events polling PostgreSQL
  public ingestion worker    -- optional; invokes bounded provider fetch

STATE
  PostgreSQL 16              -- runtime truth for all durable state

EXTERNAL
  public providers (ECB/ENTSOG/GIE), licensed providers (gated),
  OIDC issuer/JWKS, LLM provider (gated), container registry (deployment only)
```

No message queue, cache server, or object store is required. PostgreSQL is the
job queue, event log, and source of truth.

## 2. Single points of failure

- PostgreSQL is a genuine SPOF and is treated as such: scheduled workers and
  API data routes degrade rather than fabricate data.
- The API process is horizontally restarted by the runtime supervisor
  (`restart: unless-stopped`); no in-memory state is authoritative.
- Scheduler claim state is persisted, so scheduler death leaves QUEUED/
  RUNNING rows recoverable by `recover_stale_runs` and
  `recover_stale_evaluations`.

## 3. Dependency/failure matrix

| Dependency | AVAILABLE | DEGRADED | UNAVAILABLE |
|---|---|---|---|
| PostgreSQL | normal reads/writes | slow pool wait; readiness degraded | API liveness stays up, readiness fails, data routes return 503 |
| Public provider ECB | FRESH | LATE/STALE labels | only ECB-derived FX marked unavailable; unrelated market stays usable |
| Licensed providers | certified/normal | freshness/circuit degradation | gated source surfaces restricted/stale; no fabricated values |
| OIDC/JWKS | login works | cached JWKS for ≤300s | new SSO logins fail; existing sessions remain until expiry |
| LLM | optional enrichment works | retries bounded | deterministic analysis continues without LLM text |
| SSE | event push | polling fallback | frontend re-fetches canonical `/api` state |

Liveness does not depend on any external provider or PostgreSQL.

## 4. Liveness vs readiness

- `GET /api/health` remains process liveness (version/profile only).
- New `GET /api/health/live` returns 200 whenever the ASGI process is alive.
- New `GET /api/health/ready` returns 200 only when mandatory runtime state is
  safe to serve:
  - if no DB URL is configured, readiness is 503 (`runtime_db_not_configured`);
  - if a DB URL is configured, it performs `SELECT 1`, revision presence, and
    required-table inspection;
  - optional external providers are **not** part of readiness.

Compose healthcheck switches from `/api/health` to `/api/health/ready` after
the one-shot migration service has completed.

## 5. Startup/shutdown

Startup is import-safe and DB-free by contract. Mandatory configuration is
validated by `scripts/release/smoke_release.py` and migration preflight before
deployment, not by accidental import-time side effects.

Shutdown policy:
- supervisors send SIGTERM; uvicorn drains in-flight requests;
- scheduled claim loops stop on process termination without in-memory loss;
- QUEUED/RUNNING jobs older than stale thresholds are recovered on the next
  scheduler scan (`dataops_runtime.scan_scheduler`,
  `shadow_runtime.run_due_shadow_evaluations`);
- `scripts/ops/recover_stale_jobs.py --commit` is the explicit operator path
  after a crash.

## 6. Orphaned job recovery

- Ingestion QUEUED/RUNNING older than 900s -> FAILED `INTERNAL:STALE_RUN` and
  the source is rescheduled by policy.
- Shadow RUNNING evaluations older than 300s -> FAILED with failure class
  INTERNAL_ERROR and `OPERATIONAL_FAILURE:STALE_EVALUATION`.
- Strategy/backtest RUNNING records are not auto-completed; they are surfaced
  in diagnostics for operator review (they may be long legitimate backtests).

## 7. Timeout policy

| Scope | Default | Configurable |
|---|---|---|
| PostgreSQL connect | 5s | no (code constant) |
| PostgreSQL pool wait | 5s | `EUROGAS_NEXUS_DB_POOL_TIMEOUT` |
| Provider HTTP (public ingestion) | 30s client / 5s per internal call where applicable | script constants / adapter policy |
| OIDC discovery/JWKS/token | 5s | code constant |
| SSE event cycle | 1.5s poll | code constant |
| Browser API fetch | 30s | client transport |

No unbounded waits exist in the API path.

## 8. DB connection pool

`get_engine` now honors:

```text
EUROGAS_NEXUS_DB_POOL_SIZE       default 10
EUROGAS_NEXUS_DB_MAX_OVERFLOW    default 20
EUROGAS_NEXUS_DB_POOL_TIMEOUT    default 5s
EUROGAS_NEXUS_DB_POOL_RECYCLE    default 1800s
```

`GET /api/runtime/metrics` exposes
`eurogas_db_pool_checked_out`, `eurogas_db_pool_size`,
`eurogas_db_pool_overflow`, and pool wait timeouts. One pool is reused per DSN;
routes never create a new engine per request.

## 9. Query performance policy

- Add indexes only with query evidence. CR-11 adds:
  - `strategy_runs (strategy_id, started_at_utc)`,
  - `strategy_runs (strategy_version_id, started_at_utc)`,
  - `strategy_runs (run_type, started_at_utc)`,
  - `user_sessions (session_token_hash)` unique,
  - `audit_events (principal, action)`.
- List endpoints remain bounded (`limit` query parameters); historical
  collections never return unlimited rows.

## 10. Interactive vs background isolation

Long backtests and optimization calls execute synchronously in the API process
today. CR-11 records this honestly and applies bounded request validation:
- backtest period is already bounded by validated date range and evidence
  pool limits;
- optimizer inputs are bounded by Pydantic list sizes where present;
- scheduled ingestion/shadow workers run as separate processes in the Compose
  profile, so they do not compete with API workers.
- No distributed queue is introduced without measured need.

## 11. Observability

- Request IDs already attach to every response.
- Data-operations structured events and Prometheus-text metrics exist.
- CR-11 adds in-process HTTP metrics (count/latency/status by low-cardinality
  route bucket), DB pool gauges, and a shared operational error taxonomy.
- Recommended dashboards: System Health, Data Operations, Strategy/Shadow,
  Auth/Security, Database.

## 12. Error taxonomy

`domain/operations/errors.py` defines stable categories:

`CONFIGURATION`, `AUTHENTICATION`, `AUTHORIZATION`, `ENTITLEMENT`,
`DATABASE`, `MIGRATION`, `SOURCE_NETWORK`, `SOURCE_SCHEMA`,
`SOURCE_QUALITY`, `TIMEOUT`, `SOLVER`, `JOB`, `INTERNAL`.

User-facing API errors use these codes without stack traces or secret data.

## 13. Backup strategy

- Logical backup: PostgreSQL custom-format `pg_dump` (`--format=custom
  --no-owner`), timestamped, restore-tested in CI/local drill.
- Engineering RPO: one backup per day (≤24h potential loss) for preview;
  deployment owners may increase frequency. Engineering RTO target: ≤30
  minutes for a local restore of the current database size, measured in the
  drill.
- PITR is not shipped; documented as the production recommendation when
  continuous market ingestion is authorized.
- Backups contain identity/audit/commercial logic and must be treated as
  sensitive; encryption requirements are deployment-owned.

## 14. Restore verification

`scripts/ops/backup_restore_drill.py` automates:

1. `pg_dump` from source DSN;
2. create isolated target database;
3. `pg_restore`;
4. Alembic revision check;
5. required-table check;
6. representative business-record checks (audit, strategy run, source
   metadata, provider credential metadata);
7. DB-backed API read smoke.

CR-11 executed this against a real local PostgreSQL 16 and recorded the
evidence in `docs/operations/BACKUP_RESTORE.md`.

## 15. Migration safety

- Migrations are explicit operator actions (`alembic upgrade head`), never
  import-time.
- `scripts/ops/migration_preflight.py` checks current/expected revision, DB
  reachability, required-table baseline, backup age (warning), and refuses a
  downgrade request.
- PostgreSQL migrations in this repository run in a transaction where the DB
  supports DDL transactions; documented failure behavior: on failure, the
  failed migration is not marked applied and the operator re-runs after
  remediation.
- Expand/contract is required only for future changes that break previous
  binary compatibility; CR-11 documents the procedure.

## 16. Release rollback

`docs/operations/RELEASE_ROLLBACK.md` records the current compatibility
contract: application N-1 must be validated against schema N before rollback.
CR-11 adds `scripts/release/compatibility_check.py` to compare the previous
tag's `/api/health/ready` and OpenAPI path subset where the previous source is
available; in this worktree the local compatibility evidence is recorded as a
procedure, not a fabricated external run.

## 17. Post-deploy smoke

`scripts/release/smoke_release.py` checks, without external commercial calls:

- liveness and readiness;
- DB schema revision + required tables;
- `/api/me` envelope (where auth profile permits);
- source health endpoint;
- strategy run list endpoint;
- portfolio/route read endpoints;
- SSE endpoint contract (non-streaming status via bounded client timeout).

It exits non-zero on critical failures.

## 18. Failure injection

Deterministic tests cover: DB unavailable readiness; optional OIDC outage with
existing session; provider timeout classification; scheduler restart/duplicate
prevention; SSE client disconnect/reconnect is bounded in the frontend path;
process termination during queued jobs is recovered by stale-run policy.

## 19. Performance baseline and budgets

Measured in `docs/operations/PERFORMANCE_BASELINE.md` and enforced in
`docs/operations/PERFORMANCE_BUDGET.md`. CI keeps a broad regression smoke
(200 requests / p95 1000ms / 5% errors) rather than a fragile microbenchmark
gate.

## 20. Release evidence gate

Production release documentation now requires CI, migrations, security tests,
performance smoke, backup/restore verification, release smoke, and known
critical-issue review. GA is still explicitly blocked on external security
acceptance.
