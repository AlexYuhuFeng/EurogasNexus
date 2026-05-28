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
