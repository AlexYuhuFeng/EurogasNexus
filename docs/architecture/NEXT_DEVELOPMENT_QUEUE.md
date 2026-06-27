# Next Development Queue

## Purpose

This is the ordered execution queue for local goal mode. It is the file
Codex should use to decide what to build next.

Archived Desktop projects are reference evidence only. They are not design
authority. Optimize the architecture and tooling from first principles when the
archived design is unclear, overbuilt, desktop-first, file-first, or hard to
operate.

## Current Queue Rule

Execute the first milestone below whose status is not `complete`.

Do not skip ahead. Later domain and client work depends on earlier backend
foundation milestones.

## Milestone 1: Governance, DB Foundation, API Path Policy

Status: `complete-in-current-worktree`

ExecPlan:

- `.agent/plans/V1_M1_GOVERNANCE_DB_API_PATH_EXECPLAN.md`

Delivered:

- repository governance files;
- DB URL precedence and redaction;
- lazy DB engine/session helpers;
- read-only runtime DB validation script;
- Alembic import safety;
- `/api/health` stable alias;
- `/api/health` compatibility;
- internal/dev API prefixes;
- milestone reports.

Validation:

- `ruff check .`
- `pytest -q tests/api tests/contract tests/integration tests/security`
- `python -c "from apps.api.main import app; print('app import ok'); print(len(app.routes))"`

## Milestone 2: DB Runtime Hardening

Status: `next`

ExecPlan:

- `.agent/plans/V1_M2_DB_RUNTIME_HARDENING_EXECPLAN.md`

Internet required: no

Goal:

Make the DB runtime boundary operator-ready without adding business domains.

Build:

- required-table registry tied to migration revisions;
- DB runtime readiness report;
- explicit live local PostgreSQL validation path;
- explicit migration lifecycle runbook;
- repository factory contract;
- runtime DB status model;
- tests for missing DB, redaction, import safety, and no automatic migrations;
- docs that explain how to validate a real DB only when explicitly configured.

Do not build:

- market data schemas;
- topology schemas;
- route cost/netback schemas;
- live DB migration execution by default;
- live external connector behavior.

Acceptance:

- app import works without DB;
- runtime validation remains read-only;
- missing DB URL fails closed;
- live PostgreSQL validation is safe and read-only when a DB URL is configured;
- default tests do not require PostgreSQL;
- DB URL redaction is tested;
- Alembic revision reporting is documented and tested;
- all listed validation commands pass locally.

## Milestone 3: Runtime Store Contracts

Status: `pending`

ExecPlan:

- create `.agent/plans/V1_M3_RUNTIME_STORE_CONTRACTS_EXECPLAN.md`

Internet required: no

Goal:

Define the repository/runtime-store layer that future domains use for DB-first
reads and writes.

Build:

- runtime store result envelope;
- repository interface pattern;
- no-file-fallback policy tests for trial/release;
- dev fallback metadata shape if development fallback is explicitly allowed;
- docs/contracts for runtime store ownership.

Acceptance:

- API routes do not access DB directly;
- domain modules do not import FastAPI;
- SDK/CLI call API only;
- trial/release file fallback policy is enforceable by tests.

## Milestone 4: Reference Network Contract Slice

Status: `pending`

ExecPlan:

- create `.agent/plans/V1_M4_REFERENCE_NETWORK_CONTRACT_EXECPLAN.md`

Internet required: no

Goal:

Add the first product-shaped but narrow domain slice: canonical reference
network contracts using synthetic fixtures only.

Build:

- canonical ID policy;
- synthetic node/facility/segment fixture;
- DB schema plan, not broad production data load;
- read-only `/api/reference-network/*` route contracts;
- source reference and lineage fields.

Acceptance:

- no real ENTSOG/GIE/vendor data committed;
- API responses are research-safe;
- route contracts are stable enough for future map clients.

## Milestone 5: Ingestion Control Plane

Status: `pending`

ExecPlan:

- create `.agent/plans/V1_M5_INGESTION_CONTROL_EXECPLAN.md`

Internet required: no for mocked control-plane work.

Internet required: yes only if a live vendor/API connector is proposed.

Offline fallback:

- implement connector interfaces, mocks, credentials documentation, and
  entitlement gap reports only.

Goal:

Model ingestion jobs, runs, normalization status, source references, freshness,
and quality results without live source calls.

Acceptance:

- connectors perform no analytics;
- tests use mocks and synthetic fixtures;
- no import-time network calls.

## Milestone 6: Governance, Entitlement, Audit

Status: `pending`

ExecPlan:

- create `.agent/plans/V1_M6_GOVERNANCE_AUDIT_EXECPLAN.md`

Internet required: no for local model/policy work.

Internet required: yes if validating current vendor/legal terms.

Offline fallback:

- fail closed for unknown commercial data and record a gap report.

Goal:

Make entitlement, export policy, audit events, and research-output metadata
enforceable before richer data surfaces exist.

Acceptance:

- unknown commercial data fails closed;
- audit model exists;
- research result envelope exists;
- report/export rules are documented.

## Milestone 7: First Research Workflow

Status: `pending`

ExecPlan:

- create `.agent/plans/V1_M7_FIRST_RESEARCH_WORKFLOW_EXECPLAN.md`

Internet required: yes for public-source ingestion validation; no for DB-free
unit and contract tests.

Goal:

Implement one narrow research-only workflow after DB/runtime/governance
foundations are ready.

Approved first workflow:

- route-cost input validation and assumptions report, or
- reference topology read model.

Acceptance:

- every result includes assumptions, missing inputs, warnings, source
  references, lineage, `research_only`, and `human_review_required`;
- no official recommendation or execution semantics.

## Future Client Milestone

Status: `design-ready-runtime-pending`

Goal:

Implement future SDK, CLI, web, and Windows clients after backend API contracts
are stable.

Reference:

- historical Windows demo may inform workflow shape only.
- `docs/clients/README.md`
- `docs/clients/CLIENT_DELIVERY_MILESTONES.md`
- `docs/clients/SDK_CLIENT_DESIGN_SPEC.md`
- `docs/clients/CLI_CLIENT_DESIGN_SPEC.md`
- `docs/clients/WEB_CLIENT_DESIGN_SPEC.md`
- `docs/clients/WINDOWS_CLIENT_DESIGN_SPEC.md`
- `docs/design/UX_LAYOUT_BLUEPRINTS.md`

Required before starting:

- stable `/api` reference-network API;
- runtime status API;
- research output envelope;
- selected SDK, CLI, web, or Windows milestone ExecPlan;
- explicit user approval to add or expand that client surface.
