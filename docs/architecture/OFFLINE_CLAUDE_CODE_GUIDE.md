# Offline Claude Code Guide

## Assumption

Future Claude Code implementation may run in CLI mode without internet access.
All milestone docs should therefore be executable from repository-local context
unless they explicitly say otherwise.

## Default Rule

Assume internet access is not available.

Claude Code should be able to complete normal architecture, backend, test, and
documentation work from:

- this repository;
- `.agent/plans/`;
- `docs/`;
- local tests;
- local historical reference folders already mentioned by the user;
- installed Python dependencies;
- a locally configured PostgreSQL instance when the selected milestone asks for
  live DB validation and a safe DB URL already exists in the shell;
- local command output.

## Internet Required Marker

If a future task truly needs browsing or external documentation, mark it
explicitly:

```text
Internet required: yes
Reason: <why local docs are insufficient>
Fallback if offline: <what to do instead>
```

Use this marker for:

- checking current vendor API terms;
- confirming current legal/license terms;
- reading current external API documentation;
- verifying current package license metadata when not present locally;
- checking current service-specific deployment instructions.

Do not use this marker for ordinary coding tasks that can be solved from local
tests, source, and docs.

Live local PostgreSQL validation does not require internet. It does require an
operator-provided DB URL and must follow `docs/operations/LIVE_POSTGRESQL_V1.md`.
If the URL is missing, report `BLOCKED: no database URL configured` for the live
validation portion while continuing DB-free tests and documentation work.

## Offline Fallback Pattern

When internet is unavailable:

1. Do not guess current external behavior.
2. Use local documentation and existing contracts.
3. Build mocks, interfaces, and fixture-based tests.
4. Document credential, entitlement, or external-doc requirements in a gap
   report.
5. Keep live integrations disabled by default.

## What Future Plans Should Include

Every implementation plan should include:

- `Internet required: no` for normal local work; or
- `Internet required: yes` with a reason and offline fallback.

Example:

```text
Internet required: no
Reason: This milestone uses local SQLAlchemy/Alembic APIs already installed in
the development environment and validates behavior through local tests.
Fallback if offline: Not needed.
```

Example:

```text
Internet required: yes
Reason: The milestone proposes a live ENTSOG connector and must verify current
API terms and endpoint behavior.
Fallback if offline: Implement only the connector interface, mock transport,
credential requirements, and entitlement gap report. Do not call the live API.
```

## Local Reference Policy

Historical local projects and the Windows demo may be used offline as references
for product intent and workflow shape. They are not authoritative source code
for this repository.

Do not copy:

- `.env` files;
- secrets;
- raw market data;
- vendor data;
- internal business data;
- generated reports;
- old runtime implementation code.

## Validation Without Internet

Expected validation commands are local:

```powershell
ruff check .
pytest -q tests/api tests/contract tests/integration tests/security
python -c "from apps.api.main import app; print('app import ok'); print(len(app.routes))"
```

If dependencies are missing and internet access is unavailable, report
`BLOCKED` or `PARTIAL` with the exact missing local dependency instead of trying
to install from the network.
