# DB Migration Runbook

## Scope

Operational runbook for Eurogas Nexus DB schema migrations.

## Environment

- `RUNTIME_STORE_DATABASE_URL` is preferred for target environments.
- `DATABASE_URL` is supported as a fallback.
- `EUROGAS_NEXUS_DB_DSN` remains a legacy fallback only.
- Do not embed production credentials in repository files.
- Do not print full DB URLs in logs, reports, or issue comments.

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
python scripts/ops/validate_v1_runtime_db.py --json
```

- V1 live PostgreSQL policy is documented in
  `docs/operations/LIVE_POSTGRESQL_V1.md`.
