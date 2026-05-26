# Validation

Run validation from the repository root.

## Required Commands

```powershell
ruff check .
pytest -q tests/api tests/contract
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
- API and contract tests pass.
- App import prints:

```text
app import ok
<route-count>
```

## BLOCKED Conditions

Report validation as `BLOCKED` if Python, FastAPI, pytest, or Ruff are not
available and dependency installation is not permitted.

Report validation as `PARTIAL` if only a subset of checks can run.

