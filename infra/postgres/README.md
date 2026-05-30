# infra/postgres

PostgreSQL operator notes live here.

## Status

Active for V1 documentation and local operator validation. This directory does
not provision PostgreSQL by itself.

## V1 Rule

Eurogas Nexus uses PostgreSQL as runtime truth. Local files may support import,
fixtures, reports, and development fallback only. Trial and release modes must
not silently fall back to local files when runtime DB state is required.

## Configuration

Runtime code resolves the database URL in this order:

1. `RUNTIME_STORE_DATABASE_URL`
2. `DATABASE_URL`
3. `EUROGAS_NEXUS_DB_DSN`

Do not write secrets into this repository. Configure the URL in the operator's
shell, a local secret manager, or an uncommitted `.env` file outside version
control.

## Validation

Read-only validation:

```powershell
python scripts/ops/validate_v1_runtime_db.py --json
```

Default tests do not require PostgreSQL:

```powershell
pytest -q tests/api tests/contract tests/integration tests/security
```

## Migration

Migration execution is explicit:

```powershell
alembic upgrade head
```

Do not run this command from import-time code, app startup hooks, or default
tests.

## Docker

Do not start Docker during V1 foundation work unless the user explicitly asks
for a Docker-based local database.
