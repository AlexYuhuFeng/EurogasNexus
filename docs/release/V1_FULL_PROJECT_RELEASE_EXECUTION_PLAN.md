# V1 Full Project Release Execution Plan

## Purpose

This document is the release-level build order for Codex. It converts the
whole-project documentation into precise executable milestones.

Codex must execute one milestone at a time. After each milestone, it must
update the relevant report and recommend the next prompt.

## Required Reading Before Any Milestone

1. `AGENTS.md`
2. `PROJECT_DIRECTORY.md`
3. `docs/architecture/CURRENT_PAUSE_POINT.md`
4. `docs/architecture/NEXT_DEVELOPMENT_QUEUE.md`
5. `docs/release/V1_FULL_PROJECT_RELEASE_SCOPE.md`
6. `docs/release/V1_FULL_PROJECT_RELEASE_EXECUTION_PLAN.md`
7. `docs/release/V1_RELEASE_ACCEPTANCE_MATRIX.md`
8. `docs/release/V1_RELEASE_MILESTONE_BACKLOG.md`
9. the selected milestone ExecPlan

If the selected milestone ExecPlan does not exist, create it from
`docs/release/V1_RELEASE_EXECPLAN_TEMPLATE.md` and execute the milestone in the
same goal-mode run. Do not stop after writing the plan unless the user
explicitly asked for planning only.

## Milestone R0: Orientation And Gap Audit

Goal:

- prove the repo can identify the next incomplete V1 release milestone.

Build:

- `data/release_v1/r0_orientation_gap_audit.md`;
- update status markers if stale;
- no runtime behavior.

Acceptance:

- current status, selected milestone, blockers, and validation commands are
  recorded.

## Milestone R1: DB Runtime Foundation

ExecPlan:

- `.agent/plans/V1_M2_DB_RUNTIME_HARDENING_EXECPLAN.md`

Build:

- live PostgreSQL validation path;
- runtime DB status model;
- required table registry;
- migration lifecycle runbook;
- runtime store contract shell.

Acceptance:

- app import requires no DB;
- live validation is explicit, read-only, and secret-safe;
- default tests remain DB-free;
- `data/release_v1/r1_db_runtime_report.md` exists.

## Milestone R2: Runtime Store And Governance Foundation

ExecPlan:

- `.agent/plans/V1_R2_RUNTIME_STORE_GOVERNANCE_EXECPLAN.md`

Build:

- repository factory pattern;
- source reference model;
- lineage model;
- freshness and quality model;
- entitlement/export decision shell;
- audit event shell;
- no-file-fallback checks.

Acceptance:

- API routes do not access DB directly;
- domain modules do not import FastAPI;
- unknown commercial data fails closed;
- `data/release_v1/r2_runtime_governance_report.md` exists.

## Milestone R3: Reference Network And Relationship Mapping

ExecPlan:

- `.agent/plans/V1_R3_REFERENCE_NETWORK_EXECPLAN.md`

Build:

- physical geometry, topology, and market abstraction tables/models;
- explicit mapping records with confidence and eligibility;
- `/api/reference-network/*` routes;
- source-shaped test fixture set and DB seed path for local demo rows.

Acceptance:

- geometry does not imply commercial connectivity;
- mapping eligibility is explicit;
- web client can consume map-ready API shapes;
- no real source data is committed.

## Milestone R4: Source Registry And Ingestion Control Plane

ExecPlan:

- `.agent/plans/V1_R4_INGESTION_CONTROL_EXECPLAN.md`

Build:

- source registry;
- connector definition model;
- gated connector contracts and live-source posture for ECB, ENTSOG, GIE, EEX,
  Trayport, ICE OCM, and weather providers;
- ingestion job/run model;
- normalization status;
- data quality/freshness records;
- mocked connector interface.

Acceptance:

- connectors fetch only;
- no live connector execution by default;
- live execution requires entitlement, credentials, internet access, and
  operator approval;
- source references and lineage are persisted.

## Milestone R5: Context Observation Slices

ExecPlan:

- `.agent/plans/V1_R5_CONTEXT_OBSERVATIONS_EXECPLAN.md`

Build:

- market observation metadata;
- flow/capacity/outage observation metadata;
- LNG/regas observation metadata;
- storage observation metadata;
- weather/HDD/CDD/demand metric metadata;
- capacity contract, route eligibility, and contract exposure metadata;
- unit and FX conversion metadata.

Acceptance:

- all observations carry source, timestamp, unit/currency where applicable,
  freshness, quality, and entitlement state;
- no runtime fallback payloads; tests may use source-shaped fixtures, while
  runtime data must come from PostgreSQL-backed public, entitled, or
  operator-owned inputs.

## Milestone R6: Research Workflow Models

ExecPlan:

- `.agent/plans/V1_R6_RESEARCH_WORKFLOW_MODELS_EXECPLAN.md`

Build:

- common research output envelope;
- scenario input/validation model;
- assumption, missing-input, warning, source-reference, and lineage models.

Acceptance:

- every downstream research workflow uses the common envelope;
- `research_only` and `human_review_required` are mandatory.

## Milestone R7: Route Cost And Indicative Netback

ExecPlan:

- `.agent/plans/V1_R7_ROUTE_COST_NETBACK_EXECPLAN.md`

Build:

- route cost input validation;
- cost component matching;
- route cost result;
- indicative netback result;
- `/api/research/route-cost`;
- `/api/research/netback`.

Acceptance:

- outputs are indicative and research-only;
- missing cost/price/FX inputs are explicit;
- no optimization or execution instruction is emitted.

## Milestone R8: Feasibility And Allocation

ExecPlan:

- `.agent/plans/V1_R8_FEASIBILITY_ALLOCATION_EXECPLAN.md`

Build:

- feasibility validation workflow;
- allocation scenario workflow;
- `/api/research/feasibility`;
- `/api/research/allocation`.

Acceptance:

- outputs can be feasible, infeasible, or unknown;
- allocation creates research candidates only;
- no booking, nomination, or official approval exists.

## Milestone R9: Monitoring And Weather-Adjusted Nowcast

ExecPlan:

- `.agent/plans/V1_R9_MONITORING_NOWCAST_EXECPLAN.md`

Build:

- research alert model;
- anomaly candidate model;
- weather-adjusted nowcast model;
- `/api/monitoring/*`;
- `/api/research/nowcast`.

Acceptance:

- alerts are research flags, not trade signals;
- nowcast is labeled as research-only and not production forecasting.

## Milestone R10: Strategy Backtest And Shadow Run

ExecPlan:

- `.agent/plans/V1_R10_STRATEGY_SHADOW_RUN_EXECPLAN.md`

Build:

- strategy hypothesis model;
- backtest run/result;
- shadow run paper-evaluation state;
- `/api/research/backtest`;
- `/api/research/shadow-run`.

Acceptance:

- shadow run creates no orders, trades, nominations, or execution records;
- metrics preserve source snapshots and assumptions.

## Milestone R11: Research Brief And Reporting

ExecPlan:

- `.agent/plans/V1_R11_RESEARCH_BRIEF_REPORTING_EXECPLAN.md`

Build:

- research brief model;
- report generation endpoint;
- export policy evaluation;
- glossary model and `/api/glossary/*` routes;
- LLM-assisted market movement and route explanation interface with mocked
  provider tests and cited output envelope;
- `/api/research/briefs`.

Acceptance:

- required disclaimer is present;
- missing source data is not inferred;
- export fails closed for unknown commercial data.

## Milestone R12: SDK Release Surface

ExecPlan:

- `.agent/plans/SDK_M1_API_CLIENT_EXECPLAN.md`

Extend if needed:

- create `.agent/plans/V1_R12_SDK_RELEASE_SURFACE_EXECPLAN.md`

Build:

- typed SDK clients for released routes;
- response metadata preservation;
- safe errors.

Acceptance:

- SDK calls `/api`;
- SDK does not import backend internals;
- SDK tests cover released clients.

## Milestone R13: CLI Release Surface

ExecPlan:

- `.agent/plans/CLI_M1_OPERATOR_COMMANDS_EXECPLAN.md`

Extend if needed:

- create `.agent/plans/V1_R13_CLI_RELEASE_SURFACE_EXECPLAN.md`

Build:

- health/runtime/source/scenario/research/release commands;
- `--json` output where useful;
- read-only default behavior.

Acceptance:

- CLI calls SDK/API only;
- no secrets printed;
- future write-like commands require `--execute`.

## Milestone R14: Web Research Workspace

ExecPlan:

- `.agent/plans/WEB_M1_WORKSPACE_SHELL_EXECPLAN.md`

Extend if needed:

- create `.agent/plans/V1_R14_WEB_RELEASE_WORKSPACE_EXECPLAN.md`

Build:

- Network, Capacity, Market, Scenario, Contracts, Strategy, Review, Order
  Records, Data Sources, Glossary, Runtime, Settings, and Manual workspaces;
- API client for released `/api` routes;
- fixed React/Vite/MapLibre/deck.gl/Zustand/i18next stack;
- English/Mandarin language switch;
- light/dark/system theme switch;
- dense terminal-style UI based on client docs;
- map-ready reference network view;
- route option, capacity/contract, market signal, weather/HDD/CDD,
  strategy-shadow-run, LLM analysis, and glossary surfaces;
- research output review panels.

Acceptance:

- web app consumes API only;
- source/warning/missing-input/lineage states are visible;
- English/Mandarin and light/dark/system modes work;
- no browser-side secrets or direct DB access.

## Milestone R15: Windows Client Package Shell

ExecPlan:

- `.agent/plans/WINDOWS_D1_DESKTOP_SHELL_EXECPLAN.md`

Extend if needed:

- create `.agent/plans/V1_R15_WINDOWS_RELEASE_SHELL_EXECPLAN.md`

Build:

- packaged desktop shell;
- backend URL configuration;
- health/runtime status;
- English/Mandarin language and light/dark/system theme preservation;
- packaged or launched web workspace.

Acceptance:

- no bundled secrets;
- no direct DB or vendor API access;
- no Electron, SQLite, or copied historical architecture;
- historical Desktop code is not copied.

## Milestone R16: Release Pack And Final Validation

ExecPlan:

- `.agent/plans/V1_R16_RELEASE_PACK_EXECPLAN.md`

Build:

- release manifest;
- validation report;
- known gaps report;
- operator runbook;
- SDK/CLI usage notes;
- web/Windows smoke-test notes.

Acceptance:

- `docs/release/V1_RELEASE_ACCEPTANCE_MATRIX.md` is fully satisfied or
  accepted gaps are explicit;
- release artifacts exclude secrets and real data;
- validation commands pass;
- app route count is reported.

## Standard Validation Commands

Backend/default:

```powershell
ruff check .
pytest -q tests/api tests/contract tests/integration tests/security tests/sdk tests/cli
python -c "from apps.api.main import app; print('app import ok'); print(len(app.routes))"
```

Live PostgreSQL validation, only when a safe DB URL is configured:

```powershell
python scripts/ops/validate_v1_runtime_db.py --json
```

Web validation, when web tooling exists:

```powershell
npm run lint
npm run test
npm run build
```

Windows validation, when desktop tooling exists:

```powershell
npm run build
cargo test
cargo tauri build
```

## Stop Rule

If a milestone cannot satisfy acceptance, Codex must write a gap report,
mark the milestone `PARTIAL` or `BLOCKED`, and stop before starting the next
milestone.
