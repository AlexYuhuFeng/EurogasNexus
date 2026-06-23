# Database Contract

## Purpose

`src/eurogas_nexus/db` owns future SQLAlchemy configuration, PostgreSQL session
factories, repositories, and migration integration. PostgreSQL is the runtime
source of truth.

## Bootstrap State

The package exposes import-safe DB settings, lazy engine/session factories,
and neutral persistence metadata contracts. The API app must not require a DB
connection at import time.

Live local PostgreSQL validation is part of V1 runtime readiness when a safe DB
URL is configured. See `docs/operations/LIVE_POSTGRESQL_V1.md`.

## Future Rules

- Engines and sessions must be created lazily through explicit factory
  functions.
- Alembic migrations live under `alembic/`.
- Repository interfaces must not leak SQLAlchemy sessions into the domain layer.
- Tests that need a database belong under `tests/integration` or
  explicit live DB test paths, not import tests.
- Default tests must not require a live database.
- Live DB validation must be read-only unless the operator runs an explicit
  Alembic migration command.
- Local files may be import templates, raw/canonical archives, reports,
  fixtures, or development fallback only.
- Trial and release modes must not silently fall back to local files.

## Forbidden In Bootstrap

- Creating engines at import time.
- Opening database connections in app factory code.
- Introducing production credentials.
- Printing full DB URLs.
- Running migrations automatically during import, startup, or default tests.

## Milestone 3 Additions

- `IngestionRunRecord` provides neutral ingestion run metadata mapping.
- `IngestionRunRepository` defines a domain-safe repository contract.
- `SqlAlchemyIngestionRunRepository` adapts SQLAlchemy rows into domain-safe dataclasses.

## Milestone 4 Additions

- Alembic revision `0002_m4_create_ingestion_runs` creates `ingestion_runs` DDL.
- Migration lifecycle validation must include revision chain and repository integration checks.
