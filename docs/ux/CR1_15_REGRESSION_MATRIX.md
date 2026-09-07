# CR1-15 Regression Matrix

Status: UX-01 Phase 0 draft; evidence audit only

Audited ref: `cfbcd58` (`docs(clients): record evidence-led UI refactor preparation`)

Audited on: 2026-09-07

## Reading rules

This matrix compares the CR1-15 claims with the files present at the audited
ref. It does not treat a file's existence, a source-code assertion, or a test
name as runtime acceptance.

- **Implemented** means that the relevant source surface and focused tests or
  contracts were found. It does not mean that this audit reran them.
- **Partial** means that a material part of the claimed capability is absent,
  intentionally deferred, or only represented by a thin UI/adapter surface.
- **Missing** means that no authoritative implementation surface was found.
- **Unverified** means that current-ref execution evidence is absent from this
  audit. Historical reports are retained as historical evidence, not promoted
  to current acceptance.

No build, full test suite, database migration, browser session, screenshot,
visual suite, or heavy operational check was run by this sidecar. Parent-owned
runtime and visual validation remains required.

## Executive finding

The repository contains substantial CR1-15 implementation, including backend
contracts and focused tests for strategy, backtest, shadow, data operations,
identity, research data, and agent capabilities. The Web client also contains
the five-primary-workspace shell and the Market, Portfolio, Strategy, Decision,
Research, and Agent surfaces.

The main acceptance gap is current-run evidence, not an absence of all
functionality. Separately, the CR-14 and CR-15 UI rows identify concrete scope
gaps that require planner triage; they are not assumed acceptable merely
because the backend exists:
current CI runs backend/static checks plus Web unit tests/build, but does not
run a browser E2E, visual regression, axe/accessibility, bilingual workflow,
1440x900 overflow, or 1920x1080 suite. The only browser smoke is explicitly
optional, requires an ad hoc Playwright install and running seeded services,
and covers only a subset of workflows. The CR-13/14/15 reports record prior
results, but do not identify a tested SHA that can be independently tied to
`cfbcd58`.

## Capability matrix

| CR | Claimed capability | Actual implementation evidence at audited ref | Focused validation evidence found | Implementation | Current acceptance | Material gap / required follow-up |
| --- | --- | --- | --- | --- | --- | --- |
| CR-01 | Information architecture, five primary workspaces, local task navigation, legacy deep links. | `clients/web/src/app/navigation/productNavigation.ts` defines Market, Portfolio, Strategy, Decision, and System; `clients/web/src/workspaceNavigation.ts`, `clients/web/src/app/hooks/useWorkspaceNavigation.ts`, `WorkspaceTopBar.tsx`, `AppShell.tsx`, and `WorkspaceRenderer.tsx` provide typed pages, fallback, primary derivation, and rendering. | `clients/web/tests/productNavigation.test.ts`; `tests/contract/test_workspace_navigation_contract.py`; `tests/contract/test_client_release_surface.py`; `docs/clients/WORKSPACE_NAVIGATION_SPEC.md`. | Implemented | Unverified | Node/contract coverage proves mapping and source shape, not browser deep-link rendering, active-state behavior, resize, or visual hierarchy at 1440x900/1920x1080. |
| CR-02 | Trader context, selection persistence, gas-day behavior, and cross-workspace handoffs. | `clients/web/src/app/context/` separates trader context, selection, persistence, URL precedence, and invalidation; `tradingContext.ts` contains CAM gas-day logic; handoffs are wired through `NetworkWorkspace`, `ContractWorkbench`, `StrategyShadowRunTerminal`, and `ReviewWorkspace`. | `clients/web/tests/traderContext.test.ts`, `tradingContext.test.ts`; `tests/contract/test_trader_context_contract.py`; `docs/product/TRADER_CONTEXT_SPEC.md`. | Implemented | Unverified | No current browser evidence for persistence across reloads, context mismatch messaging, handoff state, or Mandarin layout. Backend context and client behavior are tested separately, not end to end. |
| CR-03 | Strategy identity/version lifecycle and reproducible run registry. | `src/eurogas_nexus/api/routes/public/strategy_registry.py`, strategy domain/DB repositories, `docs/product/STRATEGY_DOMAIN_MODEL.md`, and Web `StrategyIdentityHeader.tsx`, `StrategyNavigator.tsx`, and `useStrategyLab.ts`. | `tests/api/test_strategy_registry_api.py` covers draft/frozen immutability, fork, run creation, and reproducibility; `tests/unit/test_strategy_repository.py`, `test_strategy_registry_domain.py`; Web `strategyLab.test.ts`; `tests/contract/test_strategy_db_models.py`. | Implemented | Unverified | Current-ref API round trip and browser workflow were not run. The older state report explicitly says the full builder/compare UX belongs to CR-05, so CR-03 should not be credited for that UI scope. |
| CR-04 | Backtest temporal integrity, as-of evidence, economics, events, series, attribution, and experiment linkage. | `src/eurogas_nexus/domain/backtest/`, `application/backtest_service.py`, backtest DB models/repositories, and `src/eurogas_nexus/api/routes/public/strategy_registry.py` implement the engine and persistence paths; `docs/product/BACKTEST_ENGINE_SPEC.md` is the normative contract. | `tests/domain/research/test_backtest.py`, `tests/unit/test_backtest_engine.py`, `tests/api/test_backtest_api.py`, `tests/unit/test_backtest_persistence_fk.py`; API tests cover future-observation rejection and event/series/attribution retrieval. | Implemented | Unverified | Static/domain/API coverage is strong, but no current PostgreSQL migration plus persisted backtest was run here, and no current UI check proves the displayed metrics/provenance match the persisted result. |
| CR-05 | Strategy Design, Backtest, Compare, and Shadow UX with identity, forms, charts, states, and keyboard tabs. | `clients/web/src/components/strategy/StrategyLabWorkspace.tsx`, `StrategyDesignWorkspace.tsx`, `StrategyBacktestWorkspace.tsx`, `StrategyCompareWorkspace.tsx`, `StrategyShadowShell.tsx`, `StrategyLabCharts.tsx`, and `strategy-lab.css` exist and are rendered from `WorkspaceRenderer.tsx`. | `clients/web/tests/strategyLab.test.ts` covers task IDs, deep links, compatibility caveats, and comparison cap; `tests/contract/test_client_release_surface.py` checks component wiring; `docs/product/STRATEGY_LAB_UX_SPEC.md` describes the intended UX. | Implemented | Unverified | No current evidence covers form submission, chart data, loading/error/empty states, keyboard behavior, or the complete Design -> Backtest -> Compare -> Shadow runtime flow. This is a current-acceptance evidence gap, not a finding that the implementation is absent. |
| CR-06 | Shadow lifecycle, monitoring, drift, freshness blocking, candidates, and alert lifecycle. | `src/eurogas_nexus/application/shadow_runtime.py`, `src/eurogas_nexus/api/routes/public/shadow.py`, shadow models/repositories, `docs/product/SHADOW_RUNTIME_SPEC.md`, and `StrategyShadowRunSections.tsx`/`StrategyShadowShell.tsx`. | `tests/api/test_shadow_runtime_api.py` covers activation, pause/resume/retire, due evaluation, stale blocking, alert dedupe/acknowledge, drift, and stale-run recovery; `tests/unit/test_shadow_schedule.py`; `tests/domain/research/test_shadow_run.py`. | Implemented | Unverified | No current scheduler/database run or Strategy Lab browser validation. The repository proves lifecycle semantics more strongly than the end-user monitoring surface. |
| CR-07 | Market, Network, and Capacity cockpit with curves/spreads, map, capacity/events, provenance, and degraded states. | `MarketCockpit.tsx`, `MarketTerminal.tsx`, `NetworkWorkspace.tsx`, `CapacityWorkspace.tsx`, `GasNetworkMap.tsx`, `market-cockpit.css`, and public market/reference-network/capacity routes are present. `marketCockpitModel.ts` defines Overview, Curves, Network, and Capacity tasks. | `clients/web/tests/marketCockpit.test.ts`; `tests/api/test_market_normalized_api.py`, `test_reference_network_api.py`, `test_entsog_capacity_db_api.py`, `test_gie_observation_db_api.py`; `docs/product/MARKET_COCKPIT_SPEC.md`. | Implemented | Unverified | No current browser evidence for map rendering, source freshness/degraded states, hub selection, route highlighting, or 1440x900 overflow. Historical CR-13 browser claims are not current-ref proof. |
| CR-08 | Portfolio, Route, Scenario, Optimization, Review, and non-execution decision workflow. | `PortfolioWorkspace.tsx`, `DecisionWorkspace.tsx`, `ScenarioWorkspace.tsx`, `ReviewWorkspace.tsx`, `ContractWorkbench.tsx`, `MarketPositioningWorkspace.tsx`, optimizer/route/review public routes, and `commercialWorkflowModel.ts` are present. | `clients/web/tests/commercialWorkflow.test.ts`, `goldenWorkflow.test.ts`; `tests/api/test_portfolio_api.py`, `test_optimization_routes.py`, `test_review_api.py`; `tests/optimization/`; `docs/user/PORTFOLIO_WORKFLOW.md`; `docs/operations/PORTFOLIO_NETWORK_OPTIMIZATION.md`. | Implemented | Unverified | Model and API contracts do not prove the current browser sequence, selected context, allocation table, warnings, evidence pack, or review decision recorder. Parent must run the full Portfolio -> Resource -> Route -> Economics -> Scenario -> Optimize -> Review flow. |
| CR-09 | Data operations, freshness, certification, provenance, entitlement, scheduler, retry, and operator surfaces. | `src/eurogas_nexus/domain/dataops/`, `application/dataops_runtime.py`, source-operations/certification routes, repositories, `SourceCenter.tsx`, `RuntimeWorkspace.tsx`, and `docs/product/DATA_OPERATIONS_SPEC.md`/runbooks. | `tests/unit/test_dataops_domain.py`, `test_dataops_runtime.py`, `test_certification_gate.py`; `tests/api/test_dataops_api.py`; `tests/security/test_dataops_entitlement_api.py`; `tests/integration/test_dataops_postgres_backed.py`; `scripts/ops/dataops_benchmark.py`. | Implemented | Unverified; external certification pending | Backend fail-closed behavior is well represented, but provider certification is intentionally not live-complete and no current UI/browser run verifies stale, restricted, missing-capacity, retry, or operator-action states across workspaces. These are acceptance prerequisites/evidence gaps, not automatically P1 UX defects. |
| CR-10 | Identity, OIDC/PKCE, RBAC, sessions, CSRF/origin protection, API keys, entitlements, and audit. | `src/eurogas_nexus/security/oidc.py`, identity models/repositories, permission registry, auth/access routes, audit service, `AccessCenter.tsx`, and `docs/security/ENTERPRISE_IDENTITY_AUTHORIZATION_SPEC.md`. | `tests/security/test_enterprise_oidc_auth.py`, `test_enterprise_access_api.py`, `test_oidc.py`, `test_origin_csrf.py`, `test_public_api_auth.py`, `test_audit_retention.py`; `scripts/security/run_security_acceptance.py --json`. | Implemented | Unverified; external IdP/security acceptance pending | Offline fixture tests establish protocol and authorization behavior. A real enterprise IdP, deprovisioning, browser login, and production entitlement matrix remain external/pending; no current client browser acceptance was run. These are acceptance prerequisites, not automatically P1 UX defects. |
| CR-11 | Reliability, health/readiness, metrics, recovery, migration, backup/restore, and performance operations. | `src/eurogas_nexus/application/` reliability/dataops modules, health/runtime routes, `scripts/ops/migration_preflight.py`, `backup_restore_drill.py`, `performance_baseline.py`, `load_smoke.py`, `recover_stale_jobs.py`, `docs/operations/PRODUCTION_RELIABILITY_SPEC.md`, and `BACKUP_RESTORE.md`. | `tests/unit/test_reliability_ops.py`, `tests/contract/test_reliability_migration.py`, `tests/integration/test_migration_failure.py`, `tests/integration/test_db_health.py`; CI runs `load_smoke.py` and PostgreSQL job; historical state records restore/performance evidence. | Implemented | Unverified | CI does not run every operational command in `docs/operations/VALIDATION.md`. Current-ref PostgreSQL migration, restore, recovery, and performance evidence are absent from this audit; the historical p95 is above the stated 1500ms target even though within the hard threshold. The missing current run is an acceptance evidence gap, not automatically a P1 UX defect. |
| CR-12 | Release/update/install surfaces, compatibility blocking, packaging, signing, SBOM, provenance, and release gates. | `clients/web/src/app/releaseCompatibility.ts`, `AppShell.tsx`, `SettingsCenter.tsx`, `/api/runtime/release`, `scripts/release/`, release workflow, and `docs/release/RELEASE_ENGINEERING_SPEC.md`/`UPDATE_POLICY.md`. | `clients/web/tests/releaseCompatibility.test.ts`; `tests/release/test_release_engineering.py`, `test_release_readiness_contract.py`; CI/release workflow includes packaging and release validation. | Implemented compatibility/release surfaces; updater intentionally not shipped | Unverified; external release gates pending | Compatibility and release evidence machinery exist, but `docs/release/UPDATE_POLICY.md` explicitly says no Tauri updater ships. Clean install/launch/uninstall, previous-version upgrade, Authenticode signing, hosted provenance, Linux packaging matrix, and stable external gates remain pending. These are release prerequisites, not automatically P1 UX defects. |
| CR-13 | Commercial UAT, accessibility, i18n, final workflows, degraded states, long session, and acceptance evidence. | UAT plans/reports/defect register, `scripts/uat/check_i18n_parity.py`, `seed_uat_fixture.py`, `browser_workflow_smoke.mjs`, Web i18n files, and `tests/uat/`/`tests/evals/` are present. | Historical `docs/uat/RC_ACCEPTANCE_REPORT.md` reports Golden A-F, 0 axe violations across 13 URLs, 1,247/1,247 key parity, and long-session smoke; current CI runs `pytest -q tests` and Web test/build but not browser/axe/i18n. | UAT artifacts implemented; acceptance runner coverage partial | Historical-only / unverified | The browser script is explicitly optional, requires separately installed Playwright and seeded services, and covers only Market -> Scenario, Portfolio -> Optimize -> Review, Strategy task visibility, and a short Tab smoke. No current-ref screenshot/axe/overflow/AT evidence exists here; no Playwright or axe dependency is in `clients/web/package.json`. This is an acceptance-surface gap, not automatically a P1 UX defect. |
| CR-14 | Ontology, temporal research datasets, feature/target registries, leakage safety, snapshots, export, and research UI. | `src/eurogas_nexus/domain/research/`, research models/repository, `research_data.py`, seed script, `docs/research/`, and `ResearchDataWorkspace.tsx` are present. Backend routes include catalog, validate, build, detail, quality, and export surfaces. | `tests/domain/research/test_research_data_foundation.py`, `test_research_export.py`; `tests/api/test_research_data_api.py`, `test_research_sandbox.py`; `tests/integration/test_research_data_repository.py`; historical CR-14 report records 13 research tables and a representative dataset. | Backend implemented; required UX01 artifact workflow is a scope gap | Planner triage required; current acceptance unverified | The current UI is a catalog listing for datasets/features/targets; it has no visible dataset detail, build/validate, quality, or export workflow in `ResearchDataWorkspace.tsx`. This is an explicit UX01 scope gap requiring planner decision, not an assumed accepted thin UI. Parquet and live entitlement/runtime behavior were not rerun. |
| CR-15 | Capability Registry/MCP, governed agent research orchestration, ResearchPlan, StrategyIR, Risk Challenger, replay, entitlements, and human gates. | `src/eurogas_nexus/application/agents/`, `domain/agents/`, agent models/repositories, `api/routes/public/agents.py`, `mcp/server.py`, `docs/agents/`, and `AgentsWorkspace.tsx` are present. | `tests/unit/test_agent_capability_runtime.py`, `test_mcp_capability_adapter.py`, `test_mcp_server.py`; `tests/domain/agents/test_agent_contracts.py`; `tests/api/test_agents_api.py`; `tests/integration/test_agent_repository.py`, `test_agent_orchestrator.py`; `tests/evals/test_agent_evals.py`; CI has an MCP handshake smoke. | Backend implemented; required UX01 review/replay workflow is a scope gap | Planner triage required; current acceptance unverified | Backend contracts cover permission/entitlement/no-execution/human-confirmation paths. The UI exposes capabilities, research, runs, and a replay summary, but source evidence does not establish a complete rendered plan -> findings -> StrategyIR -> validation -> challenge -> review-pack flow. This is an explicit UX01 scope gap requiring planner decision, not an assumed accepted thin UI. Live LLM grading is explicitly external/pending; robustness beyond the CR-04 engine is deferred. |

## Historical claims that must not be reused as current acceptance

The following reports are useful evidence of prior work, but their reported
counts are not current-ref results for `cfbcd58`:

- `docs/product/SCHEDULED_AGENT_STATE.md:650-679` reports CR-15 as 1,398
  passed / 10 skipped, 50 Web tests, a PostgreSQL 0032 round trip, 1,314/1,314
  i18n parity, 68 capabilities, and a deterministic UAT agent run. It also
  records external LLM and `rdflib` limitations.
- `docs/product/SCHEDULED_AGENT_STATE.md:466-494` reports CR-13 browser,
  accessibility, i18n, and long-session results, while also stating that no
  browser E2E runner exists in the current test infrastructure.
- `docs/uat/RC_ACCEPTANCE_REPORT.md:3-12` does not print the tested SHA; it
  says only that the CR-13 commit's SHA is recorded in the report. The report
  therefore cannot be independently tied to `cfbcd58` from this file alone.
- `docs/release/RELEASE_READINESS.md:21-39` repeats CR-13 browser and
  performance evidence under a 2026-09-07 release-readiness heading, but the
  source and CI still make browser validation optional. Treat it as preserved
  historical evidence pending rerun at the audited ref.

## Authoritative validation commands

The commands below are copied from current repository guidance or CI. They are
the commands the parent acceptance run should use and record with exit status,
counts, environment, database revision, and tested SHA. None were run by this
sidecar.

| Scope | Exact command | Authority / note |
| --- | --- | --- |
| Python lint | `ruff check .` | `CONTRIBUTING.md`, `docs/operations/VALIDATION.md`, `.github/workflows/ci.yml` |
| Markdown links | `python scripts/ci/check_markdown_links.py` | CI and validation docs |
| Backend/unit/API/contracts | `pytest -q tests` | CI and contributor baseline; includes evals, security, release, API, domain, integration, and contract tests subject to environment skips |
| API load smoke | `python scripts/ops/load_smoke.py --requests 200 --concurrency 8 --p95-threshold-ms 1000` | CI validate job; in-process, not a browser or live deployment test |
| MCP handshake | `echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}' \| python -m eurogas_nexus.mcp.server \| grep -q 'protocolVersion'` | `.github/workflows/ci.yml`; shell form is the CI/Linux form |
| API import/OpenAPI | `python -c "from apps.api.main import app; print('app import ok'); print(len(app.openapi()['paths']))"` | CI and contributor baseline; proves import/OpenAPI construction, not runtime DB readiness |
| PostgreSQL CI | `bash scripts/ci/run_postgres_ci.sh` | `.github/workflows/ci.yml` PostgreSQL 16 service job; includes migration/DB-backed smoke selected by the script |
| Web tests | `npm --prefix clients/web run test` | CI, contributor baseline, and Web `package.json`; Node test runner only |
| Web build/type compilation | `npm --prefix clients/web run build` | CI and contributor baseline; `build` runs `tsc && vite build`; there is no separate `lint` script |
| Desktop compile | `cargo check --manifest-path src-tauri/Cargo.toml --locked` | PR-only desktop CI job; run from `clients/desktop` working directory |
| Desktop packaging | `npm run build -- --bundles ${{ matrix.bundle }}` | PR-only desktop CI job; requires the CI matrix OS/bundle and packaging prerequisites |
| i18n parity | `python scripts/uat/check_i18n_parity.py` | `docs/operations/VALIDATION.md`; not a CI step in `.github/workflows/ci.yml` |
| UAT/evals | `python -m pytest tests/evals tests/uat -q` | UAT validation docs; deterministic fixtures, not live provider/browser acceptance |
| Optional browser smoke | `EUROGAS_UAT_PLAYWRIGHT_PATH=/tmp/eurogas-uat/node_modules/playwright/index.js node scripts/uat/browser_workflow_smoke.mjs` | `scripts/uat/browser_workflow_smoke.mjs`; requires separately installed Playwright, API on `:8000`, Vite on `:3000`, and seeded UAT data; not CI |
| Runtime DB preflight | `python scripts/ops/validate_runtime_db.py --json` | `docs/operations/VALIDATION.md`; read-only and requires configured runtime DB |
| Migration preflight | `python scripts/ops/migration_preflight.py --json` | validation docs; requires runtime DB/configuration |
| Compatibility | `python scripts/release/compatibility_check.py` | validation docs / CR-11 release rollback procedure |
| Security acceptance | `python scripts/security/run_security_acceptance.py --json` | validation docs; automated evidence does not replace external review |
| Version consistency | `python scripts/release/check_version_consistency.py` | validation docs and release readiness |
| Release dry run | `python scripts/release/run_release_dry_run.py --channel preview` | release validation docs; assembles artifacts and evidence, not clean-machine install acceptance |
| Release artifact validation | `python scripts/release/validate_release_artifacts.py --context release-assets/release-context.json --artifacts-dir release-assets` | release validation docs |
| Stable gate | `python scripts/release/validate_stable_release.py --context release-assets/release-context.json --artifacts-dir release-assets` | release validation docs; expected to fail closed while external evidence is absent |
| Vulnerability scan | `python scripts/release/scan_vulnerabilities.py --channel preview` | release validation docs |
| Reliability baseline | `python scripts/ops/performance_baseline.py --requests 200 --concurrency 10 --json` | validation docs; requires `RUNTIME_STORE_DATABASE_URL` |
| Backup/restore | `python scripts/ops/backup_restore_drill.py --target-database-url <isolated-target-dsn>` | validation docs; destructive to the named isolated target and requires PostgreSQL/operator setup |
| Stale-job recovery | `python scripts/ops/recover_stale_jobs.py --commit` | validation docs; mutating operator action and must not be run casually |

## Coverage gaps

1. **No current-ref acceptance ledger.** The repository records historical
   counts, but the CR-13 and CR-15 reports do not provide a machine-verifiable
   tested SHA in the report body. The parent run must record `git rev-parse
   HEAD`, command output, environment, and database migration head together.
2. **Browser validation is outside CI.** The Web package has no Playwright or
   axe dependency and no `e2e`, `visual`, `a11y`, or `lint` script. The optional
   smoke does not cover all primary workflows, CR-09/10/11/12/14/15 states,
   degraded providers, entitlements, Mandarin, screenshots, or 1920x1080.
3. **Web test scope is mostly pure-model/source-contract coverage.** The Web
   tests cover navigation/context/workflow helpers and release compatibility;
   they do not render the full application or assert DOM geometry, overflow,
   focus management, chart/map visibility, or network error states.
4. **Research UI scope is narrower than backend scope.** The backend exposes
   dataset validation/build/detail/quality/export, but the current
   `ResearchDataWorkspace.tsx` only lists datasets, features, targets, and
   capabilities. Detail/export/build acceptance is therefore not established.
5. **Agent UI scope is narrower than CR-15 artifact scope.** The current
   `AgentsWorkspace.tsx` submits research and displays run/replay summaries;
   current source evidence does not establish a full rendered review-pack,
   finding, StrategyIR, challenge, confirmation, and replay workflow.
6. **External gates remain deliberately open.** The repository documents live
   provider certification, enterprise IdP acceptance, external security review,
   clean Windows install/upgrade, code signing, hosted release evidence, real
   trader UAT, and live LLM grading as pending or external.
7. **Performance evidence has a known target miss.** Historical CR-13 reports
   p95 `1668ms` against a `<=1500ms` target, although it remains below the hard
   `<=2500ms` threshold. This needs an explicit UX-01 decision, not a generic
   "performance passed" label.
8. **PostgreSQL/optional dependency evidence is environment-sensitive.** The
   historical full suite excluded `tests/contract/test_ontology_grm_parity.py`
   because `rdflib` was unavailable locally. PostgreSQL, Parquet, provider,
   and desktop evidence must include prerequisites and explicit SKIP reasons.

## Finding classification for parent acceptance

The categories below are deliberately separate. Missing current-run evidence or
an external release prerequisite is not, by itself, a P1 UX defect. A P1/P2
label should be added only after the planner confirms the requirement is in
scope and a reproduced product behavior violates it.

- **Acceptance prerequisite - current CI coverage.** CI cannot establish
  CR1-15 runtime acceptance. It gates Python checks, backend tests, an MCP
  handshake, Web Node tests, and a Web build, but no browser E2E, visual
  regression, axe, bilingual workflow, or viewport/overflow suite.
- **Acceptance evidence gap - ref binding.** Historical CR-13 and CR-15 counts
  and browser results must be rerun or explicitly scoped to their original
  tested ref before use in UX-01 final acceptance. This is not a P1 defect
  finding by itself.
- **Release-external prerequisite.** The repository records real IdP
  acceptance, provider certification, external security, signing, clean
  install/upgrade, hosted provenance, and real trader UAT as pending. This is
  consistent with the documented RC status, not a GA pass, and is not
  automatically a P1 UX defect.
- **Planner triage - CR-14/CR-15 UX01 scope.** Research is currently a
  catalog-only System view and Agent Research is a compact run/replay surface;
  the missing dataset detail/artifact workflow and full agent review/replay
  workflow are recorded in the matrix as explicit scope gaps. The planner must
  decide whether UX-01 requires them. Do not mark them accepted as thin UI or
  label them P1 until that scope decision and a concrete behavior comparison
  exist.
- **Performance evidence caveat.** Historical p95 exceeds the stated target;
  reports must preserve both the target miss and hard-threshold result. This is
  a performance acceptance finding until a product severity is assigned.

## Evidence disposition

This draft changes only this matrix. It contains no source edits, test runs,
build artifacts, database changes, commits, or runtime screenshots. The parent
task should append executed results after its own validation and should not
replace `Unverified`, `Historical-only`, `Partial`, or `PENDING_EXTERNAL` with
`PASS` without matching current-ref evidence.
