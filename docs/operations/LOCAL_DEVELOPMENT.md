# Local Development

## Public Repository Warning

This is a public repository. Do not commit secrets, real vendor data, internal
commercial data, raw market data, contracts, or real business strategy
parameters.

## Python Setup

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

## Runtime DB URL Policy

DB helpers resolve URLs in this order:

1. `RUNTIME_STORE_DATABASE_URL`
2. `DATABASE_URL`
3. `EUROGAS_NEXUS_DB_DSN` as a legacy fallback

Never print a full DB URL. Use `redact_database_url()` for diagnostics and
reports.

## Import Safety

The API import must work without a DB URL:

```powershell
python -c "from apps.api.main import app; print('app import ok'); print(len(app.routes))"
```

No migration runs automatically during import. Alembic is invoked explicitly by
operators only.

## Validation

```powershell
ruff check .
pytest -q tests/api tests/contract tests/integration tests/ingestion tests/unit tests/sdk tests/cli tests/release tests/security
python -c "from apps.api.main import app; print('app import ok'); print(len(app.routes))"
```

## Runtime DB Check

Live local PostgreSQL validation is part of V1 runtime readiness when a safe DB
URL is configured. Read `docs/operations/LIVE_POSTGRESQL_V1.md` before changing
DB runtime behavior.

The runtime DB validation script is read-only. It performs `SELECT 1`, checks
known required tables, and reads the Alembic revision if available.

```powershell
python scripts/ops/validate_v1_runtime_db.py --json
```

The script exits non-zero when the DB URL is missing, the DB is unreachable, or
required tables are missing.

Default tests do not require PostgreSQL. A missing DB URL blocks only live DB
validation, not app import or DB-free test execution.
