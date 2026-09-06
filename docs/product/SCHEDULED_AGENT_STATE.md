# Scheduled Agent State

## Current run

- Current milestone: `CR-03` (recommended next; not started) — Strategy Domain
  Model, Versioning, and Reproducible Run Contract.
- Last completed milestone: `CR-02 / P1B` (evidence below; committed in this
  run). `CR-01` remains committed as `065ab73`; `M0-P0` as `764fbdd`.
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

## CR-02 implementation plan

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
- Focused Python context/navigation contracts: **71 passed**.
- `pytest tests --ignore=tests/contract/test_ontology_grm_parity.py`:
  **1145 passed, 4 skipped**.
- `ruff check .`: **passed**.
- `python scripts/ci/check_markdown_links.py`: **passed**.
- API import: **86 paths**.
- Load smoke: **100 ok / 0 errors** (p50 8.4 ms, p95 640.3 ms, p99 660.8 ms).

## Known failures

- `tests/contract/test_ontology_grm_parity.py` cannot collect locally because
  `rdflib` is not installed in this local environment. Pre-existing environment
  gap; no dependency install performed. CI installs declared dependencies.
- Live GitHub Actions status was not queried; all local gates above are green
  with that one collection exclusion.
- No browser E2E runner exists in the current test infrastructure; CR-02
  handoffs are covered by executable pure-function tests plus source contract
  tests rather than browser automation.

## Unresolved architectural decisions

- Glossary remains a full technical workspace under System; inline contextual
  glossary entry points are deferred.
- Network remains under Market and still contains resource-pool decision rails;
  whether to split its portfolio content is deferred to CR-02/portfolio work.
- URL remains `?workspace=<technical-id>`; no primary-id query parameter or new
  route aliases are introduced in this milestone.
- The proposed persistent trader context is documented but not implemented.

## Next recommended milestone

- `CR-02` — Persistent Trader Context and Cross-Workspace Selection Model.
