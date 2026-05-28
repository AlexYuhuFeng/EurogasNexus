# DB Migration Runbook

## Scope

Operational runbook for Eurogas Nexus DB schema migrations.

## Local Development

Start the PostgreSQL container before running migrations:

```powershell
docker compose up -d
```

The local dev DSN is `postgresql+psycopg://eurogas:eurogas_dev@localhost:5432/eurogas_nexus`.

To reset local data:

```powershell
docker compose down -v
docker compose up -d
alembic upgrade head
```

## Environment

- `EUROGAS_NEXUS_DB_DSN` must be set for target environment.
- Do not embed production credentials in repository files.
- `alembic.ini` holds the local dev DSN only; CI and deployed environments override via `EUROGAS_NEXUS_DB_DSN`.

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
