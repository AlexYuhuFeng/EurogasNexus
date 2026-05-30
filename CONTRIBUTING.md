# Contributing

Eurogas Nexus V1 is a research-only, DB-first backend foundation. Keep changes
inside the active milestone and update contracts before broadening boundaries.

## Public Repository Warning

This is a public repository. Do not commit secrets, real vendor data, internal
commercial data, raw market data, contracts, or real business strategy
parameters.

## Local Setup

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

## Required Checks

```powershell
ruff check .
pytest -q tests/api tests/contract tests/integration tests/sdk tests/cli tests/release tests/security
python -c "from apps.api.main import app; print('app import ok'); print(len(app.routes))"
```

The named test folders are expected to exist in this repository. If a future
milestone adds an empty test profile, keep the directory present or document the
temporary gap before changing CI.

## Scope Rules

- PostgreSQL is the runtime source of truth.
- API routes stay separated into stable `v1`, `internal`, and `dev` profiles.
- SDK and CLI code call the backend API, not internal domain modules.
- Connectors do not perform analytics.
- Domain modules do not import FastAPI.
- Importing the API must not open DB connections or network sockets.
- Do not add heavy dependencies or restricted-license dependencies without
  explicit review.
