# Database Contract

## Purpose

`src/eurogas_nexus/db` owns future SQLAlchemy configuration, PostgreSQL session
factories, repositories, and migration integration. PostgreSQL is the runtime
source of truth.

## Bootstrap State

The package is intentionally empty except for an import-safe package marker.
The API app must not require a DB connection at import time.

## Future Rules

- Engines and sessions must be created lazily through explicit factory
  functions.
- Alembic migrations live under `alembic/`.
- Repository interfaces must not leak SQLAlchemy sessions into the domain layer.
- Tests that need a database belong under `tests/integration` or
  `tests/api`, not import tests.
- Local files may be import templates, raw/canonical archives, reports,
  fixtures, or development fallback only.
- Trial and release modes must not silently fall back to local files.

## Forbidden In Bootstrap

- Creating engines at import time.
- Opening database connections in app factory code.
- Introducing production credentials.
