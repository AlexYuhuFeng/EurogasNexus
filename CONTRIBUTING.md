# Contributing

Eurogas Nexus is a public, source-visible repository for a proprietary European
gas decision-support platform. Contributions must preserve the product boundary,
API boundary, and data-governance rules in this document.

This guide is for human contributors and repository maintainers. Agent-specific
execution plans and milestone instructions belong in `AGENTS.md` and `.agent/`.

## Repository Boundary

This repository is not an open-source project unless a separate written license
says otherwise. See `LICENSE` for the proprietary all-rights-reserved notice.

Do not submit changes that add or imply:

- trade execution;
- order entry or order routing;
- order amendment or cancellation;
- nomination submission;
- official approval workflows;
- settlement/accounting behavior;
- legal advice;
- official trading recommendations;
- auto-trading;
- ETRM replacement behavior.

All route, strategy, resource-pool, market-positioning, analysis, and report
outputs must remain decision-support candidates requiring human review.

## Public Repository Data Rules

Do not commit confidential credentials, raw licensed market data, real vendor
payloads, internal commercial data, confidential contracts, counterparty terms,
customer deployment details, real business strategy parameters, or secret-bearing
runtime configuration.

Use synthetic, public, or explicitly provenance-labelled preview data only.

## Local Setup

### Windows PowerShell

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[dev]"
npm --prefix clients/web ci
```

### macOS / Linux shell

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -e ".[dev]"
npm --prefix clients/web ci
```

PostgreSQL is required for runtime workflows. Importing the API must remain
DB-free and network-free.

## Required Checks

Run the baseline validation before pushing:

```bash
ruff check .
pytest -q tests/api tests/contract tests/integration tests/sdk tests/cli tests/release tests/security
npm --prefix clients/web run build
python -c "from apps.api.main import app; print('app import ok'); print(len(app.routes))"
```

Run focused checks when touching client contracts, route-cost logic, or release
surfaces:

```bash
pytest -q tests/contract/test_client_release_surface.py
pytest -q tests/integration/test_route_cost_db_api.py tests/api/test_route_cost_api.py
```

If a future milestone adds type-checking, secret scanning, or dependency audit
jobs, keep this section and CI in sync.

## Architecture Rules

- PostgreSQL is the runtime source of truth.
- Public SDK, CLI, Web, Windows, Linux, and customer integrations target `/api`.
- Do not add versioned or bootstrap aliases. Public clients use `/api`; internal
  and development routes use `/api/internal` and `/api/dev`.
- SDK, CLI, Web, and Windows code call the backend API or SDK, not internal
  domain modules.
- Clients do not connect directly to PostgreSQL.
- Clients do not store provider credentials or raw vendor data.
- Provider credentials are backend-owned and write-only from client forms.
- Domain modules do not import FastAPI.
- Connectors ingest and normalize data; they do not perform analytics.
- Importing the API must not open DB connections or network sockets.
- Do not add heavy dependencies or restricted-license dependencies without
  explicit review.

## Pull Request Expectations

Each PR should state:

- the milestone or issue it implements;
- changed product boundary or API contract, if any;
- validation commands run;
- whether data, credentials, or source entitlements are affected;
- whether screenshots or UI evidence are needed.

For UI changes, prefer map-first, decision-support language. Do not use labels
such as "place order", "submit nomination", "route order", "approve trade", or
"official recommendation" unless a future approved milestone changes the product
boundary.
