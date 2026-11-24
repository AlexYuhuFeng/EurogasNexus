# Python SDK quickstart

From nothing to a first result in about five minutes. You run a local Eurogas Nexus server
with the fictional demo desk (simulated prices, an invented firm), then read it with the SDK.

If your firm already runs a server, skip to [Use an existing server](#use-an-existing-server).

Measured on Linux with Python 3.11: installing took 15 seconds with a warm pip cache,
creating and seeding the demo store 18 seconds, starting the server 2 seconds. A first
install downloads about 60 MB of packages.

## What you need

- Python 3.11 or later (`python3.11 --version`).
- A checkout of this repository, or the source archive of your release.
- No database server, no Docker and no internet access after the install. The demo store is
  a local SQLite file.

## 1. Install

From the repository root:

```bash
python3.11 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
python -m pip install -e .
```

## 2. Create and seed the demo store

```bash
export RUNTIME_STORE_DATABASE_URL="sqlite:///$PWD/.local-runtime/nexus.db"
export EUROGAS_NEXUS_PUBLIC_API_TOKEN=local-dev-token
export EUROGAS_NEXUS_DEMO_MARKS=true
mkdir -p .local-runtime
python -c "from sqlalchemy import create_engine; import eurogas_nexus.db.models; from eurogas_nexus.db.base import Base; Base.metadata.create_all(create_engine('$RUNTIME_STORE_DATABASE_URL'))"
python scripts/demo/seed_demo_desk.py
```

The last line printed is `Demo desk seeded. Set EUROGAS_NEXUS_DEMO_MARKS=true to value it.`

- `RUNTIME_STORE_DATABASE_URL` points the server at the SQLite file. `.local-runtime/` is
  ignored by Git.
- `EUROGAS_NEXUS_PUBLIC_API_TOKEN` is the deployment token. The server refuses every data
  call without one, and the SDK sends the same variable. `local-dev-token` is fine on your
  own machine; never use it anywhere else.
- `EUROGAS_NEXUS_DEMO_MARKS=true` lets the demo prices value the demo book.
- The `python -c` line creates the tables directly. `alembic upgrade head` is the supported
  way on PostgreSQL but does not run on SQLite.

## 3. Start the server

In the same shell:

```bash
uvicorn apps.api.main:app --host 127.0.0.1 --port 8000
```

Leave it running. Interactive API documentation is at <http://127.0.0.1:8000/docs> while the
server runs in the development profile.

## 4. Make a first call

In a second shell, from the repository root:

```bash
source .venv/bin/activate
export EUROGAS_NEXUS_PUBLIC_API_TOKEN=local-dev-token
python examples/sdk/01_first_call.py
```

You see something like:

```text
server 1.0.0-beta, profile development, status ok
gas day 2026-11-24, front month Dec-26, hubs ['NBP', 'TTF', 'THE', 'PEG']
note: Demo data: simulated figures, not market data.
sources: ['runtime-postgresql:desk-today']; warnings: [...]
```

Or in Python directly:

```python
from eurogas_nexus_sdk.desk import fetch_desk_today_result

today = fetch_desk_today_result("http://127.0.0.1:8000").data
print(today.gas_day, today.front_month, today.focus_hubs, today.simulated)
```

That is the desk's Today view: prices per hub in desk units, the book against the market,
fundamentals and what needs attention, computed on the server.

## 5. Next steps

- Run the other scripts in [`examples/sdk`](../../examples/sdk); [Examples](EXAMPLES.md)
  explains each one.
- Look up any function in the [Reference](REFERENCE.md).
- Before connecting to a real server, read [Authentication](AUTHENTICATION.md).

## Use an existing server

Ask your administrator for:

1. the server address, for example `https://nexus.example.com` (the origin, without `/api`);
2. the deployment token;
3. if your firm issues personal or service keys, your identity key (`nexus_...`).

Install the wheel delivered with the release (see the [SDK readme](../../packages/python-sdk/README.md#install)),
then:

```bash
export EUROGAS_NEXUS_PUBLIC_API_TOKEN='<deployment token>'
export EUROGAS_NEXUS_IDENTITY_BEARER='<your nexus_... key>'   # if you have one
export EUROGAS_NEXUS_BASE_URL=https://nexus.example.com
python examples/sdk/01_first_call.py
```

`EUROGAS_NEXUS_BASE_URL` is read by the example scripts only; in your own code pass the
address as the first argument of each function.

## If it does not work

| Symptom | Cause | Fix |
|---|---|---|
| `401 public_api_token_missing` | The SDK sent no token | `export EUROGAS_NEXUS_PUBLIC_API_TOKEN=...` in the shell that runs Python |
| `403 public_api_token_invalid` | Server and SDK have different tokens | Use the same value in both shells |
| `503 public_api_token_not_configured` | The server was started without a token | Restart `uvicorn` with `EUROGAS_NEXUS_PUBLIC_API_TOKEN` set |
| `ValidationError ... DeskToday` | The server has no database configured | Restart `uvicorn` with `RUNTIME_STORE_DATABASE_URL` set |
| `ConnectError` | The server is not running, or on another port | Check the `uvicorn` shell |
| `ModuleNotFoundError: No module named 'psycopg'` from `alembic` | `alembic upgrade head` ran without a database URL | Use the `python -c` line in step 2 for SQLite |

More in [Troubleshooting](TROUBLESHOOTING.md).
