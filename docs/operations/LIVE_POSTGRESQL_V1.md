# Live PostgreSQL Policy For V1

## Decision

Live PostgreSQL is part of V1 runtime readiness.

V1 must support connecting to a real PostgreSQL database for local developer
and operator validation. This does not mean the API connects during import, CI
requires PostgreSQL, Docker is started automatically, or migrations run without
an explicit command.

## Absolute Rules

- PostgreSQL is the runtime source of truth.
- App import must not connect to PostgreSQL.
- Default unit, API, contract, integration, and security tests must pass without
  a live database unless a test is explicitly marked as live DB.
- Live DB checks are operator-invoked through documented commands.
- Migrations are explicit operator actions.
- Runtime validation is read-only unless the operator runs an Alembic migration
  command intentionally.
- Database URLs must never be printed in full.
- `.env`, credentials, tokens, raw vendor data, and internal business data must
  not be committed.

## Database URL Precedence

Use this order everywhere:

1. `RUNTIME_STORE_DATABASE_URL`
2. `DATABASE_URL`
3. `EUROGAS_NEXUS_DB_DSN` as legacy fallback only

All logs, reports, exceptions, and command output must use the redacted form.

## What Codex May Do In V1

Codex may:

- implement import-safe SQLAlchemy engine/session helpers;
- implement read-only validation against a configured live PostgreSQL URL;
- inspect Alembic version table through read-only queries;
- report missing required tables;
- write migration files when a milestone requires schema creation;
- run tests that do not require a live DB by default;
- add opt-in live DB tests guarded by an environment marker.

Codex may not:

- start Docker unless the user explicitly requests it;
- create a database without explicit operator instruction;
- run `alembic upgrade` automatically during API import, app startup, or tests;
- print the database URL or any password;
- use historical `.env` files from Desktop reference projects;
- treat SQLite or local files as trial/release runtime truth.

## Standard Live Validation Command

Run only when the operator has already configured a local PostgreSQL URL in the
shell environment:

```powershell
python scripts/ops/validate_v1_runtime_db.py --json
```

Expected behavior:

- exit non-zero if no DB URL is configured;
- exit non-zero if PostgreSQL is unreachable;
- exit non-zero if required tables are missing;
- print only redacted URL details;
- perform `SELECT 1`;
- inspect required tables;
- inspect Alembic revision if the version table exists;
- perform no writes.

## Standard Migration Command

Run only when a milestone explicitly instructs migration execution and the
operator has confirmed the target database:

```powershell
alembic upgrade head
```

This command is not part of default CI. It is a live runtime operation.

## Live DB Test Policy

Default validation remains DB-free:

```powershell
ruff check .
pytest -q tests/api tests/contract tests/integration tests/security
python -c "from apps.api.main import app; print('app import ok'); print(len(app.routes))"
```

Opt-in live DB tests must be isolated under a clear name such as:

```text
tests/live_db/
```

Those tests must skip unless a safe live DB URL is present and the operator has
explicitly selected live DB validation.

## Milestone 2 Requirement

Milestone 2 must make the live PostgreSQL path unambiguous:

- document runtime validation commands;
- document migration commands;
- document what missing tables mean;
- document how Alembic revision is reported;
- keep import safety tested;
- keep default tests DB-free;
- make live DB validation safe for a local real PostgreSQL instance.

## Failure Reporting

If live PostgreSQL validation cannot run, report one of:

- `BLOCKED: no database URL configured`;
- `BLOCKED: database unreachable`;
- `PARTIAL: database reachable but required tables missing`;
- `PARTIAL: Alembic version table missing`;
- `COMPLETE: database reachable, required tables present, revision reported`.

Never include the password, full URL, `.env` content, or host credentials in the
report.
