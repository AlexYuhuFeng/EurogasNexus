# DB Migration Runbook

## Scope

Operational runbook for Eurogas Nexus DB schema migrations.

## Environment

- `EUROGAS_NEXUS_DB_DSN` must be set for target environment.
- Do not embed production credentials in repository files.

## Apply migrations

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
