# Claude Code Master Execution Index

## Purpose

This is the master index for building Eurogas Nexus from documentation. Claude
Code should use this file when the user wants to progress beyond the immediate
backend foundation milestone.

This file does not replace milestone ExecPlans. It tells Claude Code which
phase to select, which documents to read, and what proof is required before
moving on.

## Execution Rule

Execute one milestone transaction at a time.

Do not bundle backend, SDK, CLI, web, and Windows work inside a single
milestone. A full-release goal-mode session may continue to the next milestone
only after the current milestone reports `COMPLETE`, validation evidence is
recorded, and no explicit external approval gate is pending. Do not advance to a
later phase if the earlier phase is `PARTIAL` or `BLOCKED` unless the user
explicitly accepts that state.

## Phase 0: Orientation

Read first:

1. `AGENTS.md`
2. `CLAUDE_CODE_START_HERE.md`
3. `docs/architecture/CLAUDE_CODE_IMPLEMENTATION_DIRECTIVES.md`
4. `PROJECT_DIRECTORY.md`
5. `docs/architecture/CLAUDE_CODE_GOAL_MODE.md`
6. `docs/architecture/CLAUDE_CODE_START_PROMPTS.md`
7. `docs/architecture/WHOLE_PROJECT_CAPABILITY_BLUEPRINT.md`
8. `docs/product/REAL_TIME_MARKET_INTELLIGENCE_BLUEPRINT.md`
9. `docs/architecture/REFERENCE_EVIDENCE_LOG.md`
10. `docs/release/V1_FULL_PROJECT_RELEASE_SCOPE.md`
11. `docs/release/V1_FULL_PROJECT_RELEASE_EXECUTION_PLAN.md`
12. `docs/release/V1_RELEASE_MILESTONE_BACKLOG.md`
13. `docs/release/V1_RELEASE_ACCEPTANCE_MATRIX.md`
14. `docs/release/V1_RELEASE_EXECPLAN_TEMPLATE.md`

Proof:

- Claude Code can state the selected milestone, non-goals, files in scope,
  validation commands, and rollback notes.

## Phase 1: Backend Runtime Foundation

Use now.

Primary prompt:

- Prompt 1 in `docs/architecture/CLAUDE_CODE_START_PROMPTS.md`

Primary ExecPlan:

- `.agent/plans/V1_M2_DB_RUNTIME_HARDENING_EXECPLAN.md`

Read:

- `docs/operations/LIVE_POSTGRESQL_V1.md`
- `docs/architecture/BACKEND_IMPLEMENTATION_BLUEPRINT.md`
- `docs/contracts/04_DB_CONTRACT.md`
- `docs/contracts/05_RUNTIME_STORE_CONTRACT.md`

Proof:

- app import works without DB;
- live PostgreSQL validation is explicit and secret-safe;
- default tests remain DB-free;
- required tables and Alembic revision handling are documented;
- validation commands pass or report `PARTIAL`/`BLOCKED`.

## Phase 2: Runtime Store, Governance, And Data Model

Create or select an ExecPlan before coding.

Read:

- `docs/data/CANONICAL_DATA_MODEL_BLUEPRINT.md`
- `docs/api/API_SURFACE_BLUEPRINT.md`
- `docs/product/REAL_TIME_MARKET_INTELLIGENCE_BLUEPRINT.md`
- `docs/contracts/05_RUNTIME_STORE_CONTRACT.md`
- `docs/contracts/10_INGESTION_ETL_CONTRACT.md`
- `docs/contracts/14_GOVERNANCE_ENTITLEMENT_CONTRACT.md`

Build:

- runtime-store repository pattern;
- source reference, lineage, freshness, quality, entitlement, and audit
  metadata;
- no-file-fallback checks for trial/release;
- migration plan for non-business foundation tables.

Proof:

- repositories are DB-backed;
- API routes do not access DB directly;
- domain modules do not import FastAPI;
- unknown commercial data fails closed.

## Phase 3: Reference Network And Relationship Mapping

Create or select an ExecPlan before coding.

Read:

- `docs/data/CANONICAL_DATA_MODEL_BLUEPRINT.md`
- `docs/api/API_SURFACE_BLUEPRINT.md`
- `docs/product/RESEARCH_WORKFLOW_BLUEPRINT.md`
- `docs/architecture/WHOLE_PROJECT_CAPABILITY_BLUEPRINT.md`

Build:

- physical geometry, topology, and market abstraction entities;
- explicit mapping tables with confidence and eligibility;
- read-only `/api/v1/reference-network/*` routes;
- synthetic fixtures only.

Proof:

- geometry does not imply commercial connectivity;
- market relevance requires explicit mapping;
- clients can consume map-ready API shapes;
- no real vendor/operator data is committed.

## Phase 4: Ingestion And Source Governance

Create or select an ExecPlan before coding.

Read:

- `docs/contracts/09_INFRASTRUCTURE_CONNECTOR_CONTRACT.md`
- `docs/contracts/10_INGESTION_ETL_CONTRACT.md`
- `docs/policies/DATA_POLICY.md`
- `docs/data/CANONICAL_DATA_MODEL_BLUEPRINT.md`
- `docs/product/REAL_TIME_MARKET_INTELLIGENCE_BLUEPRINT.md`

Build:

- source registry;
- connector definition model;
- gated connector contracts for ECB, ENTSOG, GIE, EEX, Trayport, ICE OCM, and
  weather;
- ingestion job/run model;
- normalization status;
- data quality/freshness records;
- mocked connector interface.

Proof:

- connectors fetch only;
- no live connector runs by default;
- source and entitlement metadata are preserved.

## Phase 5: Market, Physical, LNG, Storage, Weather Context

Create or select an ExecPlan before coding.

Read:

- `docs/data/CANONICAL_DATA_MODEL_BLUEPRINT.md`
- `docs/api/API_SURFACE_BLUEPRINT.md`
- `docs/product/RESEARCH_WORKFLOW_BLUEPRINT.md`
- `docs/product/REAL_TIME_MARKET_INTELLIGENCE_BLUEPRINT.md`

Build narrow slices:

- market observations;
- flow/capacity/outage observations;
- LNG/regas observations;
- storage observations;
- weather demand metrics;
- capacity/contract context;
- live-source posture;
- FX and unit conversion metadata.

Proof:

- synthetic data only until entitlement is approved;
- observations preserve source, timestamp, unit, currency, quality, and
  freshness;
- unknown data scope fails closed for export.

## Phase 6: Research Workflows

Create one ExecPlan per workflow. Do not implement all workflows at once.

Workflow order:

1. route cost;
2. indicative netback;
3. feasibility;
4. allocation scenario;
5. monitoring and alerts;
6. weather-adjusted nowcast;
7. strategy backtest;
8. shadow run;
9. LLM-assisted market movement analysis and glossary;
10. research brief/reporting.

Read:

- `docs/product/RESEARCH_WORKFLOW_BLUEPRINT.md`
- `docs/product/REAL_TIME_MARKET_INTELLIGENCE_BLUEPRINT.md`
- `docs/api/API_SURFACE_BLUEPRINT.md`
- `docs/data/CANONICAL_DATA_MODEL_BLUEPRINT.md`
- `docs/compliance/RESEARCH_ONLY_COMPLIANCE.md`

Proof:

- every output includes assumptions, missing inputs, warnings, source
  references, lineage, `research_only`, and `human_review_required`;
- results are research decision-support;
- no output creates or implies orders, nominations, execution, official
  approvals, or legal advice.

## Phase 7: SDK

Primary prompt:

- Prompt 2 in `docs/architecture/CLAUDE_CODE_START_PROMPTS.md`

Primary ExecPlan:

- `.agent/plans/SDK_M1_API_CLIENT_EXECPLAN.md`

Read:

- `docs/clients/SDK_CLIENT_DESIGN_SPEC.md`
- `docs/clients/CLIENT_API_CONTRACT.md`
- `docs/contracts/15_SDK_CLI_CONTRACT.md`

Proof:

- SDK calls `/api/v1`;
- SDK does not import backend internals;
- SDK preserves response metadata and redacts secrets.

## Phase 8: CLI

Primary prompt:

- Prompt 3 in `docs/architecture/CLAUDE_CODE_START_PROMPTS.md`

Primary ExecPlan:

- `.agent/plans/CLI_M1_OPERATOR_COMMANDS_EXECPLAN.md`

Read:

- `docs/clients/CLI_CLIENT_DESIGN_SPEC.md`
- `docs/clients/SDK_CLIENT_DESIGN_SPEC.md`
- `docs/contracts/15_SDK_CLI_CONTRACT.md`

Proof:

- CLI calls SDK/API only;
- read-only commands work;
- write-like commands require `--execute`;
- human and JSON output are secret-safe.

## Phase 9: Web Client

Primary prompt:

- Prompt 4 in `docs/architecture/CLAUDE_CODE_START_PROMPTS.md`

Primary ExecPlan:

- `.agent/plans/WEB_M1_WORKSPACE_SHELL_EXECPLAN.md`

Read:

- `docs/clients/WEB_CLIENT_DESIGN_SPEC.md`
- `docs/clients/CLIENT_DESIGN_SYSTEM.md`
- `docs/clients/CLIENT_TECH_STACK.md`
- `docs/clients/CLIENT_I18N_THEME_SPEC.md`
- `docs/product/REAL_TIME_MARKET_INTELLIGENCE_BLUEPRINT.md`
- `docs/clients/WINDOWS_DEMO_UX_REFERENCE.md`
- `docs/design/UX_LAYOUT_BLUEPRINTS.md`

Proof:

- web client consumes `/api/v1`;
- no direct DB, vendor, or secret access;
- runtime/source/warning states are visible;
- map/capacity/market/scenario/strategy/review/glossary surfaces match the
  design docs;
- English/Mandarin and light/dark/system modes are implemented.

## Phase 10: Windows Client

Primary prompt:

- Prompt 5 in `docs/architecture/CLAUDE_CODE_START_PROMPTS.md`

Primary ExecPlan:

- `.agent/plans/WINDOWS_D1_DESKTOP_SHELL_EXECPLAN.md`

Read:

- `docs/clients/WINDOWS_CLIENT_DESIGN_SPEC.md`
- `docs/clients/WINDOWS_DEMO_UX_REFERENCE.md`
- `docs/clients/CLIENT_DESIGN_SYSTEM.md`
- `docs/clients/CLIENT_TECH_STACK.md`
- `docs/clients/CLIENT_I18N_THEME_SPEC.md`

Proof:

- Windows client packages or points to the web workspace;
- backend base URL is configurable;
- only non-sensitive UI preferences are stored;
- English/Mandarin and light/dark/system modes are preserved;
- no historical Desktop source is copied.

## Phase 11: Release

Read:

- `docs/release/V1_RELEASE_READINESS.md`
- `docs/release/V1_FULL_PROJECT_RELEASE_SCOPE.md`
- `docs/release/V1_FULL_PROJECT_RELEASE_EXECUTION_PLAN.md`
- `docs/release/V1_RELEASE_MILESTONE_BACKLOG.md`
- `docs/release/V1_RELEASE_ACCEPTANCE_MATRIX.md`
- `release/v1/README.md`
- `docs/operations/VALIDATION.md`
- `docs/policies/DATA_POLICY.md`

Proof:

- release artifacts exclude secrets and raw/vendor/internal data;
- validation commands pass;
- release notes identify `COMPLETE`, `PARTIAL`, and `BLOCKED` areas.

## Completion Rule For The Whole Project

The whole project is complete only when every phase above has a completed
milestone report, passing validation evidence, and no unresolved required work
inside the selected product scope.
