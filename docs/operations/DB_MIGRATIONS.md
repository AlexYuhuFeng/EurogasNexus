# DB Migration Runbook

## Scope

Operational runbook for Eurogas Nexus DB schema migrations.

## Local Development

The single local project entry point is:

```powershell
powershell -File scripts/ops/Start-LocalAcceptance.ps1
```

It starts or reuses the canonical Docker PostgreSQL container
`eurogas-nexus-postgres` from the root `docker-compose.yml` on loopback
`127.0.0.1:51356`, using the external verified volume
`eurogas-nexus-postgres-data` and `PGDATA=/var/lib/postgresql/data/pgdata`, then
starts API and Web. It fails closed when the volume or the ignored superuser
secret is missing and never runs initdb, seed, migration or a volume reset.

For a database-only start the same contract is:

```powershell
docker compose up -d
```

There is no literal local DSN in the repository. The application URL lives in
the ignored `.dnx-out/user-uat.env`, is read into the process by the launcher,
and is never printed or passed on a command line. It points at the same loopback
instance.

Runtime API routes obtain sessions through the shared session factory, which
reuses one bounded SQLAlchemy connection pool per resolved DSN. Route code must
not create a new engine or pool per request; doing so can exhaust PostgreSQL
connections during parallel workspace hydration.

The verified volume is retained acceptance evidence. `docker compose down -v`
and every other volume removal or reset command must not be run against it.
Destructive reset belongs to an explicitly disposable scratch database or a
throwaway container that does not mount `eurogas-nexus-postgres-data`.

## Environment

- `RUNTIME_STORE_DATABASE_URL` is preferred for target environments.
- `DATABASE_URL` is supported as a fallback.
- `EUROGAS_NEXUS_DB_DSN` remains a legacy fallback only.
- Do not embed production credentials in repository files.
- Do not print full DB URLs in logs, reports, or issue comments.
- `alembic.ini` uses a placeholder DSN. Runtime URL resolution happens in
  `alembic/env.py`.

## Apply migrations

Run only after the operator confirms the target database. This is a live DB
operation and is not part of import-time code, app startup, or default tests.

```bash
alembic upgrade head
```

## Roll back latest migration

```bash
alembic downgrade -1
```

## Notes

- Importing `apps.api.main` must remain DB-connection free.
- Trial/release modes must not silently fall back to local files.
- Runtime validation is read-only and does not run migrations:

```bash
python scripts/ops/validate_runtime_db.py --json
```

- Current live PostgreSQL policy is documented in
  `docs/operations/LIVE_POSTGRESQL.md`.
