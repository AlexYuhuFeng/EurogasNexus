# Product Delivery Master Plan

## Purpose

This is the full delivery plan for Eurogas Nexus across backend, SDK, CLI, web
client, and Windows client. It is designed for Claude Code goal mode and assumes
local, offline execution unless a specific milestone says otherwise.

## One Product, Five Surfaces

Eurogas Nexus is one product with five implementation surfaces:

1. Backend service: DB-first, API-first, SDK-ready Python service.
2. Python SDK: typed programmatic API client for `/api/v1`.
3. CLI: safe operator and automation command surface backed by SDK/API.
4. Web client: browser workspace that consumes `/api/v1`.
5. Windows client: packaged desktop experience that consumes the same backend
   API and reuses the web workspace where possible.

The backend is the system of record. The clients are presentation and workflow
surfaces. Clients must not read PostgreSQL, local backend files, raw vendor data,
or historical Desktop artifacts directly.

Runtime data access is always mediated by SDK/API boundaries:

- SDK -> backend `/api/v1` -> repositories -> PostgreSQL.
- CLI -> SDK first, or `/api/v1` directly for a documented SDK gap.
- Web -> `/api/v1` through browser API client.
- Windows -> packaged web workspace/API client -> `/api/v1`.

## Delivery Order

### Phase 1: Backend Foundation

Objective:

Build a reliable backend that owns data, APIs, governance, ingestion,
calculation contracts, SDK, CLI, validation, and release posture.

Blueprint:

- `docs/architecture/BACKEND_IMPLEMENTATION_BLUEPRINT.md`
- `docs/architecture/CLAUDE_CODE_MASTER_EXECUTION_INDEX.md`
- `docs/api/API_SURFACE_BLUEPRINT.md`
- `docs/data/CANONICAL_DATA_MODEL_BLUEPRINT.md`
- `docs/product/RESEARCH_WORKFLOW_BLUEPRINT.md`

Activation paths:

- `apps/api`
- `src/eurogas_nexus`
- `alembic`
- `scripts`
- `tests`
- `docs/contracts`
- `docs/operations`
- `data/milestone_*`

Completion gate:

- stable `/api/v1` API contracts;
- DB runtime and migration lifecycle documented and tested;
- live local PostgreSQL validation documented and safe when configured;
- first reference-network slice delivered with synthetic data;
- research output envelope defined;
- SDK/CLI call API only.

### Phase 2: Python SDK

Objective:

Build the typed Python API client after stable backend route contracts exist.

Blueprint:

- `docs/clients/SDK_CLIENT_DESIGN_SPEC.md`
- `docs/contracts/15_SDK_CLI_CONTRACT.md`
- `.agent/plans/SDK_M1_API_CLIENT_EXECPLAN.md`

Activation paths:

- `src/eurogas_nexus/sdk`
- `packages/python-sdk`
- `tests/sdk`

Completion gate:

- SDK targets `/api/v1`;
- SDK does not import backend internals;
- SDK preserves warnings, missing inputs, source references, lineage, and
  research metadata;
- SDK errors are secret-safe.

### Phase 3: CLI

Objective:

Build the operator and automation command surface after SDK basics exist.

Blueprint:

- `docs/clients/CLI_CLIENT_DESIGN_SPEC.md`
- `docs/contracts/15_SDK_CLI_CONTRACT.md`
- `.agent/plans/CLI_M1_OPERATOR_COMMANDS_EXECPLAN.md`

Activation paths:

- `src/eurogas_nexus/cli`
- `tests/cli`

Completion gate:

- CLI calls SDK/API only;
- read-only commands work;
- write-like commands require explicit `--execute`;
- human and JSON output are secret-safe;
- runtime validation output is clear.

### Phase 4: Web Client

Objective:

Build the browser workspace for research workflows after backend API contracts
are stable enough for client consumption.

Blueprint:

- `docs/architecture/WEB_CLIENT_IMPLEMENTATION_BLUEPRINT.md`
- `docs/clients/WEB_CLIENT_DESIGN_SPEC.md`
- `docs/clients/CLIENT_DESIGN_SYSTEM.md`
- `docs/clients/CLIENT_API_CONTRACT.md`

Activation path:

- `clients/web`

Recommended stack:

- React
- TypeScript
- Vite
- MapLibre GL for base map
- API client generated or hand-written from stable `/api/v1` contracts

Completion gate:

- web app runs locally;
- health/runtime status visible;
- reference-network map view consumes backend API;
- scenario input shell exists without business execution semantics;
- UI displays source, warning, missing-input, and human-review states.

### Phase 5: Windows Client

Objective:

Package the Eurogas Nexus workspace for Windows after the web client and backend
contracts are stable.

Blueprint:

- `docs/architecture/WINDOWS_CLIENT_IMPLEMENTATION_BLUEPRINT.md`
- `docs/clients/WINDOWS_CLIENT_DESIGN_SPEC.md`
- `docs/clients/CLIENT_DESIGN_SYSTEM.md`
- `docs/clients/CLIENT_API_CONTRACT.md`

Activation path:

- `clients/desktop`

Recommended stack:

- Tauri wrapping the web client.

Completion gate:

- Windows app launches the same workspace experience;
- backend base URL is configurable;
- no bundled secrets;
- no direct DB or vendor API access;
- installer/build process excludes raw data and credentials.

## Claude Code Execution Rule

Claude Code must execute one component milestone at a time.

Default next milestone:

- backend Milestone 2 from `docs/architecture/NEXT_DEVELOPMENT_QUEUE.md`

Do not start SDK, CLI, web, or Windows expansion until the user explicitly tells
Claude Code to start that surface milestone or the queue selects it.

Client design documentation may be maintained before that point. Runtime client
dependencies and client code must wait for a selected client milestone.

## Internet Policy

Default:

- Internet required: no

For backend milestones:

- use local docs, source, tests, and synthetic fixtures.

For web/Windows milestones:

- internet may be required only to install new client tooling or verify current
  package documentation.

Offline fallback:

- create the client blueprint, file structure, component contracts, mocked API
  clients, and gap report;
- do not pretend dependencies are installed if they are missing.

## Historical Reference Policy

Historical projects and the Windows demo are product-intent references. They are
not implementation authority.

Use them to understand:

- map-centric workflow;
- scenario composition;
- route and corridor inspection;
- runtime status needs;
- reporting/research review flow.
- dense terminal-style layout from archived QA reports.

Do not copy:

- old source code;
- `.env` values;
- raw data;
- vendor data;
- generated reports;
- historical UI layout as-is.

## Master Completion Definition

The full product is complete only when:

- backend API contracts are stable;
- PostgreSQL-backed runtime truth is implemented for approved domains;
- SDK and CLI consume the backend without bypassing API contracts;
- web client consumes the backend for real workflows;
- Windows client packages the web workflow without bypassing backend APIs;
- research outputs carry assumptions, missing inputs, warnings, source
  references, lineage, `research_only`, and `human_review_required`;
- release validation passes for each component.
