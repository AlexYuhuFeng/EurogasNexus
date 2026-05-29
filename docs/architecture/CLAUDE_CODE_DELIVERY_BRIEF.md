# Claude Code Delivery Brief

## Purpose

This document is the implementation handoff for future Claude Code sessions. It
explains the desired end state, the required order of work, and the validation
gates. It is intentionally detailed so coding agents can execute milestone by
milestone without reintroducing failed historical patterns.

## Current Instruction

Do documentation-first architecture work before project code. Code changes
should be limited to future milestones that explicitly allow implementation.
When coding begins, each milestone must have an ExecPlan under `.agent/plans/`
and tests that prove the boundary being changed.

## Product North Star

Eurogas Nexus is a research-only European gas decision-support platform. The
long-term product is a governed internal workspace for:

- European pipeline gas topology and route context;
- LNG regas, storage, beach delivery, and infrastructure analysis;
- market price, tariff, flow, capacity, outage, weather, and demand context;
- route cost, indicative netback, feasibility, allocation, nowcast, strategy
  testing, monitoring, and reporting;
- research outputs with assumptions, missing inputs, warnings, lineage, source
  references, `research_only`, and `human_review_required`.

The V1 repository is not the full product. It is the backend foundation that
must make this product safe to build later.

## Current V1 Implementation Target

Build a DB-first, API-first, SDK-ready Python backend service.

Required posture:

- PostgreSQL is runtime source of truth.
- FastAPI owns the HTTP/API boundary.
- SQLAlchemy owns lazy DB access.
- Alembic owns explicit migrations.
- Live local PostgreSQL validation is part of V1 runtime readiness when the
  operator configures a safe DB URL.
- SDK and CLI call the backend API, not internal modules.
- Trial and release modes fail closed when DB is required but unavailable.
- Local files are import templates, raw/canonical archives, reports, fixtures,
  or explicit development fallback only.
- API import must not connect to DB, network, external APIs, live connectors,
  LLM providers, or secrets.
- Default tests must remain DB-free unless a test is explicitly marked as live
  DB and operator-invoked.

## Product Boundary

Never implement in V1:

- trade execution;
- order entry;
- order routing;
- trade capture;
- nomination submission;
- settlement operations;
- official approval;
- legal advice;
- official trading recommendations;
- auto-trading;
- ETRM replacement behavior;
- production frontend;
- production Windows client;
- company SSO/OIDC;
- live connector execution without entitlement approval;
- LLM provider calls.

Use the language "research output", "scenario output", "risk flag",
"candidate", "indicative", and "human review required". Avoid "trade signal",
"execution recommendation", "order recommendation", or "approval".

## Historical Reference Use

Reference roots reviewed:

- `C:\Users\qqshu\Desktop\Eurogas Nexus Project\Eurogas Nexus`
- `C:\Users\qqshu\Desktop\Eurogas Nexus\eurogas-nexus`
- `C:\Users\qqshu\Desktop\Eurogas Nexus Project\Eurogas Nexus Artifacts`

Use these for architecture lessons only. Do not copy:

- `.env` files;
- credentials;
- raw market data;
- vendor data;
- internal business data;
- contracts;
- generated reports;
- snapshots;
- old implementation code.

The Windows demo executable is a future UX reference only. The UI/UX requires
redesign and should not be copied as-is. It can help a future client milestone
understand the map-centric workspace concept after the backend API contracts are
stable.

Detailed reference evidence is recorded in
`docs/architecture/REFERENCE_EVIDENCE_LOG.md`.

## Lessons From Failed Implementations

Avoid these patterns:

- desktop-first drift before backend source-of-truth is stable;
- local-file runtime truth in trial or release modes;
- broad domain sprawl before contracts, DB schemas, and tests exist;
- API route explosion without DB-backed runtime store;
- connectors that perform analytics;
- services that read raw local files as runtime data;
- SDK/CLI code that imports domain modules directly;
- LLM/RAG/provider surfaces before data permission, citation, and review
  governance are approved;
- business-feature coding before source-of-truth, lineage, and entitlement are
  enforceable.

## Target Runtime Layers

Use this dependency direction:

```text
apps/api
  -> src/eurogas_nexus/api
  -> src/eurogas_nexus/application
  -> src/eurogas_nexus/domain
  -> src/eurogas_nexus/runtime_store
  -> src/eurogas_nexus/db
  -> PostgreSQL
```

Infrastructure adapters and connectors sit beside runtime store boundaries:

```text
src/eurogas_nexus/infrastructure/connectors
  -> external APIs only when explicitly invoked by approved ingestion jobs
  -> no analytics
  -> no import-time calls
```

Rules:

- `domain` must not import FastAPI.
- `db` must not import API/application/domain services.
- `runtime_store` may import `db`; it must not import FastAPI.
- API routes should delegate to application services.
- Application services should depend on interfaces/contracts, not raw local
  files.
- SDK/CLI call API clients.

## Stable API Path Policy

Preferred stable client prefix: `/api/v1`.

Compatibility:

- `/v1/health` may remain during bootstrap.
- `/api/v1/health` is the stable health path.

Profiles:

- stable routes: `/api/v1`;
- internal routes: `/api/internal`;
- development routes: `/api/dev`.

Release profile must not expose internal or dev routes.

## DB URL Policy

Resolve DB URLs in this order:

1. `RUNTIME_STORE_DATABASE_URL`
2. `DATABASE_URL`
3. `EUROGAS_NEXUS_DB_DSN` as legacy fallback only

Never print a full DB URL. Always redact before logs, reports, exceptions, or
CLI output.

## Client Surface Policy

Eurogas Nexus has four API-consuming client surfaces:

- Python SDK;
- CLI;
- web client;
- Windows client.

All client work must follow `docs/clients/CLIENT_API_CONTRACT.md`. SDK work must
follow `docs/clients/SDK_CLIENT_DESIGN_SPEC.md`. CLI work must follow
`docs/clients/CLI_CLIENT_DESIGN_SPEC.md`. Visual client work must follow the web
and Windows specs plus the design system.

## Live PostgreSQL V1 Policy

Read `docs/operations/LIVE_POSTGRESQL_V1.md` before changing DB runtime code.

Live PostgreSQL is required for operator readiness in V1, but only through
explicit commands. App import, route registration, and default tests must not
open DB sockets. Read-only live validation may run when a safe database URL is
already configured in the shell environment. Migration execution requires an
explicit operator command such as `alembic upgrade head`.

## Milestone Execution Standard

Every milestone needs:

- ExecPlan in `.agent/plans/`;
- goal;
- non-goals;
- product boundary;
- files to create/modify;
- dependency policy;
- data policy;
- API impact;
- DB impact;
- tests;
- validation commands;
- acceptance criteria;
- rollback notes.

If any requirement is unclear, write a gap report instead of inventing behavior.

## Recommended Next Milestones

### Milestone 2: DB Runtime Hardening

Deliver:

- DB runtime readiness report.
- Required-table registry tied to migrations.
- Live PostgreSQL validation path that is read-only and secret-safe.
- Migration command/runbook that is explicit and never import-time.
- Tests proving app import still works without DB.
- Tests proving DB URL redaction.
- Tests proving missing DB URL fails closed in runtime validation.

Do not deliver:

- business schema expansion;
- live DB migration by default;
- live connector calls.

### Milestone 3: Runtime Store Contracts

Deliver:

- repository interface patterns;
- runtime store result envelope;
- no-file-fallback policy tests for trial/release;
- explicit dev fallback metadata if any fallback is allowed.

Do not deliver:

- broad market/topology/business workflows.

### Milestone 4: Canonical Reference Network Slice

Deliver:

- canonical ID policy;
- synthetic reference-network fixture;
- schema plan for node/facility/segment;
- read-only `/api/v1/reference-network/*` contract;
- lineage/source-reference fields.

Do not deliver:

- real ENTSOG/GIE/vendor data;
- map frontend;
- route optimization.

### Milestone 5: Ingestion Control Plane

Deliver:

- connector interface contract;
- ingestion run model;
- normalization result contract;
- source-reference and freshness metadata.

Do not deliver:

- live external API calls;
- Kafka/Flink;
- connector analytics.

### Milestone 6: Governance, Entitlement, Audit

Deliver:

- entitlement decision contract;
- audit event contract;
- fail-closed export policy for unknown commercial data;
- research-output metadata requirements.

Do not deliver:

- company SSO/OIDC;
- official approval workflow.

## Documentation Requirements For Future Code Work

Before coding any new domain slice, update or create:

- contract doc under `docs/contracts/`;
- API policy doc if routes change;
- DB impact doc if schema changes;
- data policy note if files or fixtures are used;
- gap report if anything is intentionally partial.

## Validation Baseline

Run from repository root:

```powershell
ruff check .
pytest -q tests/api tests/contract tests/integration tests/security
python -c "from apps.api.main import app; print('app import ok'); print(len(app.routes))"
```

Do not run full pytest unless requested. Do not start Docker. Do not run real
migrations against a live DB unless the selected milestone and operator command
explicitly require it.

## Claude Code Working Rules

When implementing later:

1. Read `AGENTS.md`.
2. Read `docs/architecture/PROJECT_NORTH_STAR.md`.
3. Read this file.
4. Read `docs/architecture/OFFLINE_CLAUDE_CODE_GUIDE.md`.
5. Read the milestone ExecPlan.
6. Write tests first for behavior changes.
7. Keep edits inside the milestone scope.
8. Run the listed validation commands.
9. Report `PARTIAL` or `BLOCKED` honestly.

Do not treat old Desktop projects as source code to merge. Treat them as
evidence for what the platform is trying to become and for what failed when too
much was built too early.

## Offline Assumption For Claude Code CLI

Assume Claude Code has no internet access unless the user explicitly provides
it. Milestone docs should be executable from local repository context.

Every future plan should include one of:

```text
Internet required: no
```

or:

```text
Internet required: yes
Reason: <specific external verification needed>
Fallback if offline: <mock/interface/gap-report-only path>
```

If internet is unavailable, do not guess current vendor/API/legal behavior.
Implement only local interfaces, mocks, tests, and gap reports until external
verification is available.
