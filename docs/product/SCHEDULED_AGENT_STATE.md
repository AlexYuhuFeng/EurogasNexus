# Scheduled Agent State

## Current run

- Current milestone: `CR-13 / P12` — Commercial UAT, Trader Workflow
  Acceptance, AI/Copilot Evaluation, Accessibility, Final UX Convergence,
  Documentation, and GA Release-Candidate Stabilization.
- Last completed milestone: `CR-12 / P11` (commit `1cdc1ca`).
- CR-13 commit: the coherent stabilization commit recorded after the final
  validation report below.
- Current branch/commit at CR-13 start: `main` @ `1cdc1ca`.
- Model routing: DSH Pro owns all product-quality judgment, professional
  workflow assessment, AI evaluation methodology, acceptance criteria, UX
  convergence decisions, release-blocker classification, and GA readiness
  decisions. DSH Flash is limited to repetitive defect fixes, i18n parity,
  routine tests, documentation cleanup, and mechanical accessibility fixes.

## Baseline observed at start

- Working tree: ` M docs/clients/UI_CONTENT_STANDARDS.md` (pre-existing audit
  addition, preserved), `?? output/` (assessment evidence, not committed).
- `stash@{0}` preserved: `codex-strategy-wip-before-9f0652d`.
- CI config present: `ci.yml`, `ci-manual.yml`, `release.yml`. Live GitHub CI
  status was not queried; local validation gates are run below.
- CR-01 verified in current main: five primary workspaces and local task
  switchers; 13 legacy technical ids still resolve.
- Duplicated context audit: `useCockpitControls` owned gas day and delivery
  product; MarketTerminal owned its own tenor state; no cross-workspace
  selection or handoff mechanism existed before CR-02.
- Runtime API observed previously: development profile, PostgreSQL head
  `0024_cost_observations`, 46/46 required tables, 86 OpenAPI paths.
- CR-03 adds migration `0025_strategy_registry_v1` (new tables
  `strategies`, `strategy_versions`, `strategy_data_snapshots`, plus nullable
  provenance columns on legacy `strategy_runs`). The runtime PostgreSQL head
  should become `0025_strategy_registry_v1`; live migration was not performed
  because the local environment has no running PostgreSQL service.

## CR-13 implementation plan

1. Verify CR-12 release infrastructure, build a PostgreSQL 16 UAT fixture DB,
   and run browser-based Golden Workflows for Market, Portfolio/Optimize/
   Review, Strategy create/freeze/backtest, Review, and degraded states.
2. Write `docs/uat/COMMERCIAL_UAT_PLAN.md` and the UAT pack, defect register,
   AI/accessibility/i18n/RC acceptance reports.
3. Fix discovered defects in severity order: backtest attribution FK P0;
   review deep-link P1; raw warning-code P1; TSO access propagation P1;
   heading/landmark/contrast accessibility P1; topbar overflow P2; zh-CN
   terminology P2.
4. Add deterministic UAT fixture pack gated to development/test, golden
   workflow contracts, AI eval corpus, accessibility automation, i18n audit,
   and long-session smoke evidence.
5. Create user documentation matching current UI; reconcile GA gates; update
   release readiness/backlog/state; commit one coherent stabilization
   milestone.

## CR-12 implementation plan

1. Audit release triggers, channel semantics, version sources, hard-coded
   versions, tags, artifact naming, permissions, action/toolchain pinning,
   dependency locks, Docker/desktop packaging, signing, SBOM/provenance and
   current GitHub Releases.
2. Write `docs/release/RELEASE_ENGINEERING_SPEC.md` and the channel/gate/
   supply-chain/update/install documentation before broad implementation.
3. Establish `pyproject.toml` as the canonical version and add
   `scripts/release/check_version_consistency.py` plus generated runtime
   version mirrors.
4. Add deterministic tag/channel semantics (`vX.Y.Z`, `-rc.N`,
   `-preview.N.<sha>`) and a tag-only stable trigger.
5. Add `release-context.json` -> artifact naming, `release-manifest.json`,
   final `SHA256SUMS`, SPDX SBOMs, THIRD_PARTY_NOTICES, vulnerability scan
   evidence and policy, signing-state abstraction, stable gate, post-publish
   verification, and a local release dry-run.
6. Refactor `release.yml` into resolve/validate/reliability/scan/build/sign/
   assemble/attest/accept/publish/verify phases with least privilege and full
   commit-SHA action pinning; pin Python/Node/Rust toolchains.
7. Add `/api/runtime/release`, client release metadata, About/Diagnostics
   surface, and a blocking client/server compatibility screen.
8. Harden Windows packaging metadata, document online vs offline WebView2,
   keep architecture-specific Linux DEBs, and document the managed/offline
   update policy (no updater ships).
9. Run full validation and a complete release dry-run; update
   RELEASE_READINESS, backlog/state; commit one coherent milestone.

## CR-11 implementation plan

1. Audit deployment topology, health/telemetry, backups, migrations, rollout,
   benchmarks and release profile.
2. Write `docs/operations/PRODUCTION_RELIABILITY_SPEC.md`,
   `PERFORMANCE_BASELINE.md`, `PERFORMANCE_BUDGET.md`, `DISASTER_RECOVERY.md`,
   `RELEASE_ROLLBACK.md`.
3. Split `/api/health/live` (process only) from `/api/health/ready`
   (PostgreSQL/schema only; external providers never gate readiness).
4. Add `/api/runtime/dependencies` dependency/failure matrix, HTTP metrics
   middleware, DB pool metrics and configurable pool/timeout policy.
5. Add operational error taxonomy, recovery script for stale ingestion/shadow
   jobs, migration preflight, backup/restore drill, release smoke and
   compatibility-check scripts.
6. Add evidence-backed indexes (strategy run filters, session token, audit
   actor/action) and bound backtest periods.
7. Measure 10-concurrency baseline; update CI/release workflow with
   PostgreSQL evidence job; update Runtime dependency-health UI.
8. Run full validation, PostgreSQL restore drill, migration-failure test,
   update docs/backlog/state and commit one coherent milestone.

## CR-10 implementation plan

1. Audit current identity/auth/OIDC/Web/desktop/SSE/audit implementation.
2. Write `docs/security/ENTERPRISE_IDENTITY_AUTHORIZATION_SPEC.md` and
   `docs/security/ASVS_CONTROL_MAPPING.md`.
3. Extend the canonical Principal model (roles/email/identity source/last
   login), external identity (issuer+subject), sessions, OIDC authorization
   states, API-key scopes/created_by and audit columns in migration
   `0029_enterprise_identity_v1`.
4. Add centralized fine-grained authorization with VIEWER/ANALYST/REVIEWER/
   OPERATOR/ADMIN matrix and fail-closed unknown permissions.
5. Implement Authorization Code + PKCE browser login with backend HttpOnly
   session cookie, desktop loopback login/token exchange, /api/me, logout and
   CSRF/origin protection.
6. Add `/api/access/*` and `/api/audit` admin APIs; propagate strategy/shadow
   lifecycle audit hooks.
7. Harden SSE/CORS/CSRF/Tauri least privilege and AI entitlement context.
8. Build SYSTEM Access & Identity UI and topbar user menu.
9. Add OIDC/RBAC/deprovisioning/API-key/audit/CSRF tests and PostgreSQL
   integration tests.
10. Measure authorization/audit overhead; update runbooks, release readiness,
    backlog/state; commit one coherent milestone.

## CR-09 implementation plan

1. Audit repo/CI/docs, source registry, ingestion adapters, PostgreSQL
   source/evidence tables, monitoring, auth/scopes, observability and
   credential storage; verify CR-01..CR-08 from code/tests, not labels.
2. Write `docs/product/DATA_OPERATIONS_SPEC.md` with current-state audit and
   the accepted architecture for registry, scheduling, calendars, freshness,
   latency, runs, retry, circuit, backfill, idempotency, quality, lineage,
   certification, licensed-data boundary, entitlement propagation,
   observability, downstream fail-closed behavior, performance and operator
   workflows.
3. Add import-safe `domain/dataops` contracts: source classes/definitions,
   typed schedules, deterministic freshness states, latency decomposition,
   failure classification, backoff/jitter, circuit transitions, quality
   codes and entitlement policy.
4. Add migration `0028_data_operations_v1`: extend `ingestion_runs`,
   add `source_runtime_states`, `ingestion_run_issues`,
   `data_operations_heartbeat`, and dataset/environment evidence columns on
   `provider_certifications`; preserve existing rows.
5. Add dataops repositories/application runtime: reconcile registry into
   runtime state, PostgreSQL SKIP LOCKED scheduling claims, partial unique
   scheduled-run index, run lifecycle, failure-category retry/circuit,
   backfill/manual/recovery triggers and scheduler heartbeat.
6. Extend public sources API with source health/runs and operator run/
   backfill/retry/enable actions; add `/api/source-certifications`; keep
   existing `/api/sources` and `/api/ingestion-runs` compatible.
7. Extend row-entitlement filtering beyond market quotes (physical, storage,
   LNG, route candidates, strategy/shadow evidence reads) and add derived-
   result fail-closed policy with principal matrix tests.
8. Add `/api/runtime/source-operations` and `/api/runtime/metrics`
   (Prometheus text), structured secret-safe dataops events and correlation
   ids.
9. Harden Source Center (Overview/Pipelines/Certification/Credentials) and
   add source-operations health to Runtime workspace; update DTOs and i18n.
10. Add downstream stale propagation in pipeline health/source posture and
    keep historical run immutability untouched.
11. Add scheduler/retry/ingestion/freshness/certification/entitlement/
    observability tests and `scripts/ops/dataops_benchmark.py`; run provider
    live tests where actually possible and record explicit SKIP/NOT
    CERTIFIED where not.
12. Run PostgreSQL migrations + DB-backed smoke against scratch PostgreSQL,
    full Python suite, web tests/build, ruff, markdown and load smoke.
13. Update runbooks (`SOURCE_FAILURE.md`, `BACKFILL.md`,
    `SOURCE_CERTIFICATION.md`, `DATA_FRESHNESS.md`), RELEASE_READINESS.md,
    backlog/state, then commit one coherent milestone.

## CR-08 implementation plan

1. Audit ContractWorkbench, MarketPositioning, Scenario, Review, optimizer
   DTOs, route candidates, TSO access, tariffs, warnings and tests.
2. Write `docs/product/COMMERCIAL_DECISION_WORKFLOW_SPEC.md`.
3. Introduce typed Portfolio and Decision task models with legacy deep-link
   compatibility.
4. Replace separate contracts/scenario/review/orders renderer branches with
   one PortfolioWorkspace and one DecisionWorkspace.
5. Build Portfolio Overview/Resources/Routes/Exposure tasks and Decision
   Scenario/Optimize/Review tasks, sharing trader context and resource/route
   selection.
6. Add conservative route feasibility classification, compact optimizer
   preflight/allocation/constraint/unallocated-reason views and non-execution
   review handoff.
7. Add scoped CSS, EN/ZH parity, Node tests for task/feasibility helpers and
   updated release-surface contracts.
8. Run web tests/build, ruff, markdown, load smoke and full backend suite;
   update docs/backlog/state; commit one coherent slice.

## CR-07 implementation plan

1. Audit Network/Market/Capacity components, map layers, DTOs, trader context
   and responsive behavior.
2. Research public commodity-terminal, ENTSOG and GIE presentation patterns.
3. Write `docs/product/MARKET_COCKPIT_SPEC.md`; update benchmark/UX docs.
4. Introduce typed Market cockpit task model with Overview, Curves & Spreads,
   Network, Capacity & Events and legacy deep-link compatibility.
5. Replace separate Market/Capacity renderer branches with one MarketCockpit;
   Network remains available via AppShell legacy path and the cockpit task.
6. Build Overview: shared context strip, major hub board (real bid/ask/mid,
   source/freshness), linked network map, physical/portfolio/route rail and
   spread strip.
7. Reuse existing MarketTerminal, NetworkWorkspace and CapacityWorkspace as
   the deep-inspection task surfaces.
8. Add scoped `market-cockpit.css`, EN/ZH parity, keyboard-accessible hub
   table and degraded/partial states.
9. Add Node tests for task deep-links, task URL preservation and explicit hub
   list; update web release-surface contracts.
10. Run web tests/build, ruff, markdown, load smoke and full backend suite;
    update docs/backlog/state; commit one coherent slice.

## CR-06 implementation plan

1. Verify CR-03/04/05 foundations and audit legacy shadow/research runtime.
2. Write `docs/product/SHADOW_RUNTIME_SPEC.md`.
3. Add typed monitor/evaluation/candidate/risk/outcome/alert/drift state and
   pure schedule calculation.
4. Add migration `0027_shadow_runtime_v1` with FKs, unique evaluation
   identity, indexes and scheduler heartbeat.
5. Add repository/application runtime with SKIP LOCKED claiming, shared
   CR-04 evaluator, current persisted evidence snapshot, freshness blocking,
   candidate/risk persistence, mark-to-model outcomes, deduplicated alerts
   and interpretable drift.
6. Add public monitor/evaluation/drift/alert/status APIs and internal
   scheduler tick; register permissions.
7. Complete Strategy Lab Shadow task with monitor activation, lifecycle
   actions, current candidate, evaluation history, drift and alerts.
8. Add scheduler/lifecycle/stale-evidence/alert/no-execution tests and
   scheduler benchmark.
9. Run focused + broad validation, web build, ruff, markdown and load smoke;
   update docs/backlog/state; commit one coherent slice.

## CR-05 implementation plan

1. Verify CR-03/CR-04 persisted identity, versions, runs, manifests, backtest
   metrics/series/events and evidence state.
2. Audit legacy `StrategyShadowRunTerminal`; write
   `docs/product/STRATEGY_LAB_UX_SPEC.md`; update benchmark/UX references.
3. Extend backend for editable DRAFT versions and strategy metadata without
   mutating frozen versions (`PATCH .../metadata`, `PUT .../draft`).
4. Replace legacy monitor/economics/risk/runs terminal with one
   StrategyLabWorkspace and local Design/Backtest/Compare/Shadow tasks.
5. Add persistent identity header, strategy/version navigator, structured
   designer (hypothesis/component/parameters/risk/assumptions/data/resource),
   preflight validation, backtest configure/result, run history, compare with
   compatibility classification, and truthful Shadow shell.
6. Add persisted-series SVG charts with backend drawdown values; no chart
   dependency, no illustrative data.
7. Extend selection context with strategy/version ids; keep Review handoff and
   trader context URL semantics.
8. Add EN/ZH parity, scoped strategy-lab.css, dense 1440/1920 layout, loading/
   empty/error states, keyboard tablist behavior.
9. Add Node tests for task deep-links and comparison semantics; update web
   release-surface contracts; keep backend tests green.
10. Run web tests/build, ruff, markdown, load smoke, full backend suite;
    update docs/backlog/state; commit one coherent slice.

## CR-04 implementation plan

1. Verify CR-03 precondition from code, not documents.
2. Audit all existing backtest/evaluation/PnL/FX/temporal code paths.
3. Write `docs/product/BACKTEST_ENGINE_SPEC.md` (temporal contract, as-of
   rules, economics, fill/missing-data policy, events, metrics, experiments,
   determinism, precision, versioning, performance, limitations).
4. Add ontology vocabulary for temporal integrity, missing-data/fill-price
   policies, cost treatments, experiment types, decision clock, and backtest
   outcome status.
5. Add domain `backtest` contracts, temporal selection utilities, decision
   clock, economic model, engine loop, event/series/attribution/metrics.
6. Add DB models `backtest_experiments`, `backtest_decision_events`,
   `backtest_series`, `backtest_attribution`; add `backtest_engine_version`
   and `experiment_id` to `strategy_runs`; migration `0026_backtest_engine_v1`.
7. Add batched as-of evidence repository over `market_observations`,
   `market_quotes`, `fx_observations`, `cost_observations`, frozen resource
   contexts, and a CR-03 strategy data snapshot.
8. Extend professional `POST /api/strategy-runs` for `run_type=BACKTEST`;
   add run events/series/attribution endpoints and lightweight
   `backtest_experiments` endpoints.
9. Keep legacy `/api/research/backtest` and `/api/strategy-lab/*` paths
   unchanged and clearly documented as legacy.
10. Update SDK/Web DTOs and add a minimal persisted-metric readout to the
    existing Strategy terminal (no illustrative charts).
11. Add temporal-integrity, economics, reproducibility, metrics, API,
    adversarial-fixture, and gas-day DST tests.
12. Add `scripts/ops/backtest_benchmark.py` and record baseline.
13. Run focused + broad validation, web tests/build, ruff, markdown links,
    load smoke; update backlog/state; commit one coherent slice.

## CR-03 implementation plan

1. Audit current strategy domain, DB, API, SDK, Web DTOs, and tests.
2. Perform focused experiment-lineage research and write
   `docs/product/STRATEGY_DOMAIN_MODEL.md`.
3. Add typed strategy registry domain module with lifecycle enums, structured
   version definition, run manifest, and deterministic content hashing.
4. Add Alembic migration `0025_strategy_registry_v1`: `strategies`,
   `strategy_versions`, `strategy_data_snapshots`, and provenance columns on
   legacy `strategy_runs`; preserve legacy rows.
5. Add repository and application functions for strategy CRUD, draft/frozen
   version lifecycle, fork-on-edit, immutable manifests, and run persistence.
6. Add professional API: strategy list/create/get, version list/create/get,
   freeze, fork, run create/list/get. Only `EVALUATION` run type is executable.
7. Keep `/api/strategy-lab/*` compatibility path unchanged; extend legacy run
   payload with new provenance fields.
8. Update SDK and Web DTOs; minimal Strategy terminal provenance line.
9. Add domain/repository/API/DB/migration/compatibility tests.
10. Run focused + broad validation and web build; update backlog/state; commit.

## CR-02 implementation plan (historical)

1. Verify CR-01 navigation landed in current main and audit duplicated context
   state.
2. Perform focused linked-context research and update
   `docs/product/INDUSTRY_BENCHMARK.md`.
3. Rewrite `docs/product/TRADER_CONTEXT_SPEC.md` with categories, identity,
   persistence, URL precedence, invalidation, and workspace matrix.
4. Add typed `clients/web/src/app/context/` subsystem: trader context,
   selection context, persistence, URL serialization, invalidation, and hooks.
5. Replace duplicated `useCockpitControls` gas-day/product state with one
   `useTraderContext`; preserve existing corrected CAM semantics.
6. Add optional canonical hub focus, propagated through topbar, Market hub
   buttons, Network context strip, and portfolio/strategy market filters.
7. Add session-only cross-workspace selections (route/resource/strategy run)
   with safe URL query keys.
8. Implement explicit handoffs: Network -> Scenario (route), Portfolio ->
   Strategy Lab (resource), Strategy Lab -> Review (strategy run).
9. Mark optimizer/route/strategy results context-mismatched when gas day,
   product, or hub changes; require explicit re-run for current context.
10. Add compact context UI, EN/zh labels, and keyboard/aria contracts.
11. Add focused Node and Python context/navigation tests.
12. Run web tests/build, ruff/markdown, and broader Python suite; update
   backlog/state; commit one coherent slice.

## Legacy CR-01 plan (historical)

1. Research benchmark IA principles and update
   `docs/product/INDUSTRY_BENCHMARK.md`.
2. Write `docs/product/PRODUCT_INFORMATION_ARCHITECTURE.md` before code changes:
   five primary workspaces, child-view mapping, old-route compatibility,
   workflow examples, rejected alternatives, next dependencies.
3. Write `docs/product/TRADER_CONTEXT_SPEC.md` and
   `docs/product/UX_REFERENCE.md`.
4. Add typed primary-workspace model
   `clients/web/src/app/navigation/productNavigation.ts`; keep technical
   `workspaceNavigation.ts` as the URL/deep-link registry.
5. Extend `useWorkspaceNavigation` with primary derivation and
   `openPrimaryWorkspace`.
6. Replace the topbar grouped dropdown with five primary workspace tabs using
   the shared `WorkspaceTabs` primitive; keep the map search and trading
   context; show an active local-task chip for map-first Network.
7. Replace page-group tabs in `WorkspaceRenderer` with local task tabs under the
   active primary; render only when a primary owns more than one view.
8. Update `docs/clients/WORKSPACE_NAVIGATION_SPEC.md`,
   `docs/product/COMMERCIAL_READINESS_BACKLOG.md`, and docs index.
9. Add focused Node/Python tests: page->primary mapping, default child mapping,
   deep-link compatibility, invalid fallback, active state, glossary/manual
   routes, i18n parity, keyboard primitive reuse.
10. Run focused tests, web build, ruff/markdown checks, and relevant broader
    tests.
11. Commit one coherent milestone; do not push unless explicitly authorized.

## Tests run (CR-11)

- `npm --prefix clients/web run test`: **41 passed**; `npm run build`: **passed**.
- `pytest tests --ignore=tests/contract/test_ontology_grm_parity.py`:
  **1277 passed, 10 skipped** (new PostgreSQL integration tests skip locally
  unless `RUNTIME_STORE_DATABASE_URL` is configured).
- PostgreSQL 16 scratch DB `eurogas_nexus_cr10`: `alembic upgrade head` applied
  through `0030_reliability_indexes`; CR-09/CR-10/CR-11 PostgreSQL integration
  tests **6 passed**.
- Automated restore drill: 161798-byte custom-format dump; isolated restore;
  revision `0030_reliability_indexes`; required tables present; API smoke 200;
  elapsed 2.8s.
- Migration failure test: `alembic upgrade 9999_missing_revision` exits
  non-zero and the database head remains unchanged.
- `ruff check .`: **passed**. Markdown links: 159 files, all resolve.
- OpenAPI public surface: **140 paths**, pinned and permission-declared.
- Automated security acceptance: **PASS** (external review remains BLOCKED).
- Desktop Tauri `cargo check`: **passed**.
- Representative 10-concurrency baseline: p50 20.5ms, p95 1172.3ms,
  p99 2173.9ms, 0 errors (scratch PostgreSQL).
- CI load smoke: **200 ok / 0 errors** (p50 5.2ms, p95 12.7ms).

## Tests run (CR-12)

- `pytest tests --ignore=tests/contract/test_ontology_grm_parity.py`:
  **1299 passed, 10 skipped**.
- PostgreSQL 16 scratch DB `eurogas_nexus_cr12` (head
  `0030_reliability_indexes`): integration suite **50 passed**.
- `npm --prefix clients/web run test`: **47 passed**; `npm run build`:
  **passed**.
- `ruff check .`: **passed**. Markdown links: 168 files, all resolve.
- Version consistency gate: **25 surfaces, all agree**.
- OpenAPI public surface: **141 paths**, pinned and permission-declared.
- Automated security acceptance: **PASS** (external review remains BLOCKED).
- Desktop `cargo check --locked`: **passed** (Rust 1.94.0 pinned toolchain).
- Release dry-run (`--channel preview --with-performance --build-container
  --container-smoke`): **ok**, 16 steps, final manifest/SHA256SUMS/SPDX SBOMs
  verified; Windows NSIS bundled, Web/Server bundles packaged, container image
  built and import-smoked; Linux DEB platforms recorded as CI-only local gaps.
  Final dry-run duration 34s on the local Windows workstation.
- Stable gate simulation: fail-closed on missing external evidence and
  unsigned Windows artifacts (by design).

## Tests run (CR-13)

- `pytest tests --ignore=tests/contract/test_ontology_grm_parity.py`:
  **1316 passed, 10 skipped** (CR-12 1299 + 17 CR-13 tests).
- Fresh PostgreSQL 16 scratch DB `eurogas_nexus_cr13` (head
  `0030_reliability_indexes`): integration **50 passed**.
- Web: **50 passed**; production build **passed**. Desktop `cargo check
  --locked`: **passed**.
- axe-core: **0 violations** across 13 workspace URLs at 1440×900 after fixes.
- EN/zh-CN key parity: **1,247/1,247**, no missing static keys.
- AI deterministic eval corpus: **13/13 critical cases pass**.
- Browser golden workflows: A PASS, B PASS, C PASS, E PASS; keyboard smoke 0
  errors. Long-session smoke: 60 workspace switches, 0 errors, heap stable.
- Performance on dense UAT fixture: p50 44.5ms / p95 1668ms / p99 3099.5ms
  (inside approved hard thresholds; `/api/sources` recorded as post-RC
  optimization backlog).
- CR-12 release dry-run re-run after CR-13 changes: **ok**, 16 steps.

## Known failures

- `tests/contract/test_ontology_grm_parity.py` cannot collect locally because
  `rdflib` is not installed in this local environment. Pre-existing environment
  gap; no dependency install performed. CI installs declared dependencies.
- Live GitHub Actions status was not queried; all local gates above are green
  with that one collection exclusion.
- No browser E2E runner exists in the current test infrastructure; scheduler,
  retry, freshness, certification, entitlement, observability and UI behavior
  are covered by executable domain/API/integration tests and the production
  web build.

## Unresolved architectural decisions

- Glossary remains a full technical workspace under System; inline contextual
  glossary entry points are deferred.
- Network remains under Market and still contains resource-pool decision rails;
  whether to split its portfolio content is deferred to later portfolio work.
- URL remains `?workspace=<technical-id>`; no primary-id query parameter or new
  route aliases are introduced.
- `strategy_definitions` remains a frozen legacy table and is intentionally not
  migrated into the new `strategies`/`strategy_versions` registry in CR-03.
- `EVALUATION` and `BACKTEST` execute; `SHADOW` and `SCENARIO` remain
  versioned but not executable. No scheduler or execution semantics are added.
- The professional registry API is ready, and the terminal now displays a
  minimal persisted backtest metric/provenance readout; full Strategy Lab
  builder/compare UX is CR-05.

## Next recommended milestone

- `CR-14` — External UAT / Security Acceptance Closure, Commercial Provider
  Certification, Release Candidate Burn-In, and GA Go/No-Go, unless CR-13
  evidence reveals an unresolved P0/P1 that requires another stabilization
  run first.
