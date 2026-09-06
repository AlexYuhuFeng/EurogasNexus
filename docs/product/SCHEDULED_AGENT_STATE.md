# Scheduled Agent State

## Current run

- Current milestone: `CR-03 / P2` — Strategy Domain Model, Versioning, and
  Reproducible Run Contract (implemented; see Tests run below).
- Last completed milestone before this run: `CR-02 / P1B` (commit `89f166e`).
  Earlier commits: `065ab73` (CR-01), `764fbdd` (M0-P0).
- CR-03 commit planned for the end of this run:
  `feat(strategy): add versioned strategy domain and reproducible run manifests`.
- Current branch/commit at CR-01 start: `main` @
  `764fbdd48209f3adbc5d1c0e3fad77153a9a156e`; `origin/main`
  `399be6aec931849e51379dbb6667c751ece5016a`.
- Model routing: DSH Pro for the full architecture decision and implementation
  review; no Flash delegation for navigation/product decisions.

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

## Tests run

- `npm --prefix clients/web run test`: **29 passed**.
- `npm --prefix clients/web run build`: **passed**.
- Focused CR-03 Python tests (domain/repository/API): **16 passed**
  (`tests/unit/test_strategy_registry_domain.py`,
  `tests/integration/test_strategy_registry_repository.py`,
  `tests/api/test_strategy_registry_api.py`).
- `pytest tests --ignore=tests/contract/test_ontology_grm_parity.py`:
  **1160 passed, 4 skipped**.
- `ruff check .`: **passed**.
- `python scripts/ci/check_markdown_links.py`: **passed**.
- OpenAPI public surface: **94 paths**, all covered by
  `PINNED_PUBLIC_PATHS` and the route-permission registry.
- Load smoke: **200 ok / 0 errors** (p50 10.4 ms, p95 58.2 ms, p99 876.9 ms).

## Known failures

- `tests/contract/test_ontology_grm_parity.py` cannot collect locally because
  `rdflib` is not installed in this local environment. Pre-existing environment
  gap; no dependency install performed. CI installs declared dependencies.
- Live GitHub Actions status was not queried; all local gates above are green
  with that one collection exclusion.
- No browser E2E runner exists in the current test infrastructure; CR-02
  handoffs and CR-03 terminal provenance are covered by executable
  pure-function tests, source contract tests, and the production web build.

## Unresolved architectural decisions

- Glossary remains a full technical workspace under System; inline contextual
  glossary entry points are deferred.
- Network remains under Market and still contains resource-pool decision rails;
  whether to split its portfolio content is deferred to later portfolio work.
- URL remains `?workspace=<technical-id>`; no primary-id query parameter or new
  route aliases are introduced.
- `strategy_definitions` remains a frozen legacy table and is intentionally not
  migrated into the new `strategies`/`strategy_versions` registry in CR-03.
- Only `run_type=EVALUATION` executes in CR-03; backtest, scenario, and shadow
  run types are versioned but not executable. No scheduler or execution
  semantics are added.
- The professional registry API is ready but not yet driven by terminal
  builder/backtest controls; the terminal only displays run provenance.

## Next recommended milestone

- `CR-04` — Professional backtest and dataset-snapshot construction: as-of
  joins, look-ahead-safe observation selection, walk-forward/experiment design,
  and professional backtest metrics on the immutable CR-03 version/manifest
  foundation (see `docs/product/STRATEGY_DOMAIN_MODEL.md` section 21).
