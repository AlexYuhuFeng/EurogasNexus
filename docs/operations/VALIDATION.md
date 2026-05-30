# Validation

Run validation from the repository root.

## Prerequisites

```powershell
docker compose up -d        # start PostgreSQL
pip install -e ".[dev]"     # install project + dev dependencies
```

## Required Commands

```powershell
ruff check .
pytest -q tests/api tests/contract tests/integration tests/sdk tests/cli tests/release tests/security
python -c "from apps.api.main import app; print('app import ok'); print(len(app.routes))"
```

The named test directories are expected to exist. If a future milestone creates
a profile before adding tests, keep the directory present and document the gap
instead of letting CI depend on an absent path.

## Environment Setup

Use a local virtual environment:

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

## Expected Result

- Ruff exits with code 0.
- All tests pass (pre-existing failures noted separately).
- App import prints:

```text
app import ok
<route-count>
```

## BLOCKED Conditions

Report validation as `BLOCKED` if Python, FastAPI, pytest, or Ruff are not
available and dependency installation is not permitted.

Report validation as `PARTIAL` if only a subset of checks can run.

## One-command Validation

```bash
./scripts/ops/validate_repo.sh
```

## Runtime DB Validation

```powershell
python scripts/ops/validate_v1_runtime_db.py --json
```

This script is read-only. It does not write data or run migrations. It is the
standard live local PostgreSQL validation path when a safe DB URL is configured.
Default tests remain DB-free.

See `docs/operations/LIVE_POSTGRESQL_V1.md` for the live PostgreSQL policy.
