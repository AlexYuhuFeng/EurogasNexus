# Live PostgreSQL Policy

## Decision

Live PostgreSQL is part of runtime readiness.

Eurogas Nexus supports connecting to a real PostgreSQL database for local
developer and operator validation. This does not mean the API connects during
import, CI requires PostgreSQL, Docker is started automatically, or migrations
run without an explicit command.

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
- Restricted provider access material, licensed vendor data, and internal
  business data must not be committed.
- Public or entitled infrastructure/reference data must be persisted to
  PostgreSQL before API/SDK/client use.
- Price, screen, broker, and proprietary vendor feeds require customer access
  rights or explicit operator-owned input.

## Database URL Precedence

Use this order everywhere:

1. `RUNTIME_STORE_DATABASE_URL`
2. `DATABASE_URL`
3. `EUROGAS_NEXUS_DB_DSN` as legacy fallback only

All logs, reports, exceptions, and command output must use the redacted form.

## What Agents May Do

Agents may:

- implement import-safe SQLAlchemy engine/session helpers;
- implement read-only validation against a configured live PostgreSQL URL;
- inspect Alembic version table through read-only queries;
- report missing required tables;
- write migration files when a selected milestone requires schema creation;
- add explicit operator-invoked ingestion scripts for public or governed sources;
- run tests that do not require a live DB by default;
- add opt-in live DB tests guarded by an environment marker;
- improve Web/Windows client diagnostics that read DB posture through `/api`.

Agents may not:

- start Docker unless the user explicitly requests it;
- create a database without explicit operator instruction;
- run `alembic upgrade` automatically during API import, app startup, or tests;
- print the database URL or any secret-bearing value;
- use historical `.env` files from unrelated reference projects;
- treat SQLite or local files as trial/release runtime truth;
- let clients connect directly to PostgreSQL.

## Official Source Runtime Policy

The runtime path is DB-first. Data available from public or operator-enabled
official sources should be ingested into PostgreSQL and then exposed through
`/api` and the SDK.

Current public/keyed runtime sources:

- ECB daily euro FX reference rates;
- ENTSOG operational flow observations;
- ENTSOG connection points and TSO access metadata;
- GIE AGSI storage observations;
- GIE ALSI LNG observations;
- audited public TSO tariff rows.

Normalization invariants:

- ENTSOG flow ingestion requests only the `Physical Flow` indicator and replaces
  the previous ENTSOG flow snapshot transactionally; capacity indicators cannot
  be written into `flow_observations`.
- GIE AGSI `injection` and `withdrawal` and GIE ALSI `sendOut` are published in
  GWh/d and normalized to TWh/d.
- GIE ALSI nested `inventory.gwh` and `dtmi.gwh` values are normalized to
  `inventory_twh` and `dtmi_twh`; DTMI is an energy capacity, not a percentage.

Price and screen data are different. EEX, ICE OCM, Trayport, ICIS, Argus, Kpler,
Platts, broker, and customer screen/order feeds require customer rights and
source-specific contracts before live ingestion. Until then, only
operator-owned test marks may be inserted into local test PostgreSQL, and they
must be clearly labeled as operator-entered test records.

## Current Runtime Evidence

Latest checked local API posture:

```text
GET /api/runtime/db
database_url_present=true
connectivity.ok=true
alembic_revision=0013_gie_lng_dtmi_energy
required_tables=33
missing_tables=0
source=runtime-postgresql
```

This evidence means the running backend process can reach the configured
PostgreSQL runtime database and sees the required schema. It does not mean each
licensed commercial provider has been live-called.

## Standard Live Validation Command

Run only when the operator has already configured a local PostgreSQL URL in the
shell environment:

```bash
python scripts/ops/validate_runtime_db.py --json
```

Compatibility command:

```bash
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

```bash
alembic upgrade head
```

This command is not part of default CI. It is a live runtime operation.

## Live DB Test Policy

Default validation remains DB-free:

```bash
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

## DB Runtime Hardening Status

The DB runtime hardening milestone is complete in the current worktree for the
tested local scope:

- runtime validation commands are documented;
- migration commands are documented;
- required-table inspection is implemented;
- Alembic revision reporting is implemented;
- import safety is tested;
- default tests remain DB-free;
- live DB validation is safe for an operator-controlled PostgreSQL instance.

Remaining production work is operational hardening, not a restart of the DB
foundation: scheduling, monitoring, backups, multi-user auth, entitlement,
export governance, incident response, and deployment-specific runbooks.

## Failure Reporting

If live PostgreSQL validation cannot run, report one of:

- `BLOCKED: no database URL configured`;
- `BLOCKED: database unreachable`;
- `PARTIAL: database reachable but required tables missing`;
- `PARTIAL: Alembic version table missing`;
- `COMPLETE: database reachable, required tables present, revision reported`.

Never include the password, full URL, `.env` content, or host credentials in the
report.
