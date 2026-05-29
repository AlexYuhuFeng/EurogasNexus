# Dependency Policy

## Allowed Backend Default Stack

- Python
- FastAPI
- Pydantic
- SQLAlchemy
- Alembic
- PostgreSQL
- HTTPX
- pandas
- NumPy
- PyArrow
- python-dateutil
- PyYAML
- pytest
- Ruff

## Bootstrap Dependency Scope

Backend foundation milestones use the smallest useful subset:

- FastAPI
- Pydantic
- SQLAlchemy
- Alembic
- HTTPX
- pytest
- Ruff

Heavy optional dependencies are deferred until a milestone proves they are
needed.

## Required V1 Client Stack

V1 includes SDK, CLI, web, and Windows client surfaces.

Allowed only when the selected milestone activates that surface:

- SDK and CLI: Python standard library plus HTTPX/Pydantic if already approved
  for backend client use.
- Web client: React, TypeScript, Vite, plain CSS or CSS modules, test tooling,
  and MapLibre GL where dependencies are available.
- Windows client: Tauri and Rust wrapping the web workspace.

Client dependencies must not be added during backend foundation milestones.
Electron is not approved for V1.

If internet access is unavailable and dependencies are not already installed,
the client milestone must create local file structure, interfaces, mocks, and a
gap report instead of claiming a working build.

## Restricted Licenses

Do not add dependencies under GPL, LGPL, AGPL, SSPL, BUSL, Elastic,
Redis-RSAL, Commons-Clause, or PolyForm terms without explicit review.

## Review Requirements

Every new dependency must document:

- purpose;
- license;
- runtime or development scope;
- why the standard library or existing dependency is insufficient;
- whether it introduces network, process, data, or deployment risk.

