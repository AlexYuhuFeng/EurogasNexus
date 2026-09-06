# Scheduled Agent State

## Current run

- Current milestone: `CR-06 / P5` — Production-Quality Shadow Run Scheduler,
  Monitoring, Drift, and Alert Lifecycle (implemented; see Tests run below).
- Last completed milestone: `CR-05 / P4` (commit `5517bbe`). Earlier commits:
  `a930199` (CR-04), `77e2168` (CR-03), `89f166e` (CR-02).
- CR-06 planned commit:
  `feat(strategy): add production-grade shadow monitoring runtime`.
- Current branch/commit at CR-06 start: `main` @ `5517bbe`.
- Model routing: DSH Pro owns scheduling semantics, evidence timing,
  strategy/backtest parity, failure-state design, drift methodology, alert
  lifecycle, monitoring architecture and operational reliability.

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

## Tests run (CR-06)

- `npm --prefix clients/web run test`: **34 passed**.
- `npm --prefix clients/web run build`: **passed**.
- Focused shadow tests: schedule **5 passed**, runtime/API **8 passed**,
  no-execution contract **2 passed** (15 focused shadow tests total).
- `pytest tests --ignore=tests/contract/test_ontology_grm_parity.py`:
  **1211 passed, 4 skipped**.
- `ruff check .`: **passed**.
- `python scripts/ci/check_markdown_links.py`: **passed**.
- OpenAPI public surface: **112 paths**, all covered by
  `PINNED_PUBLIC_PATHS` and the route-permission registry.
- Load smoke: **200 ok / 0 errors**.
- Shadow benchmark (SQLite fixture): 10 monitors ~0.13 s scan; 100 monitors
  ~1.07 s scan; duplicate claims prevented.

## Known failures

- `tests/contract/test_ontology_grm_parity.py` cannot collect locally because
  `rdflib` is not installed in this local environment. Pre-existing environment
  gap; no dependency install performed. CI installs declared dependencies.
- Live GitHub Actions status was not queried; all local gates above are green
  with that one collection exclusion.
- No browser E2E runner exists in the current test infrastructure; backtest
  temporal/economic/metric behavior is covered by executable domain/API tests,
  source contract tests, and the production web build.

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

- `CR-07` — Market / Network / Capacity Trader Cockpit Consolidation, unless
  repository evidence reveals a more urgent production blocker.
