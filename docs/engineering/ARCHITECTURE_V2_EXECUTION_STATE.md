# Architecture V2 Execution State

Last updated: 2026-09-16
Repository HEAD: `main` (Waves 0-9 slices below are committed and pushed; see the git log for the exact head)
Working tree: clean except pre-existing `.automation/*` edits from the earlier autonomous harness, which are neither accepted nor reverted.
V2 pack version: 2026-09 autonomous runner
Current wave: Waves 0, 1, 2, 3, 4, 5, 6, 8 (taxonomy/presentation layer) and the first Wave 9 slice are delivered. Waves 7 and 10 are not started; the remaining halves of Waves 5, 8 and 9 are named below.
Wave status: DELIVERED_AND_VALIDATED for the waves listed above.

## Accepted architecture decisions

- V2 documents under `docs/engineering/Architecture-V2/` define target direction; repository truth defines current implemented behaviour.
- Modular monolith + worker runtime remains the default product architecture.
- **ADR-0016 (Decision 15)**: Architecture V2 is the binding target architecture and the product-experience interaction authority; the Professional UI Constitution keeps visual authority. RFC-0001 and Decision 14 history preserved.
- Functional assignment and work mode never grant backend authority; composition is not permission.
- Platform administration is not commercial-data access: `ROLE_PERMISSIONS[ADMIN]` is the platform bundle and `api/dependencies/commercial_access.py` enforces the boundary per request.

## Completed tasks

- [x] **Wave 0** — client inventory (accepted after repair), backend access inventory, conflict register, Wave 0 gate (passed), ADR-0016, architecture fitness tests (`tests/contract/test_architecture_v2_fitness.py`, 28 cases).
- [x] **Wave 1** — shell, Active Context, workspace-pattern and panel registries, action geography, canonical AI actions, Inspector contract, command model, HostCapabilities; machine-readable under `clients/web/src/app/experience/` and `clients/web/src/app/host/`.
- [x] **Wave 2** — capability catalogue and `ExperienceProfile` (`src/eurogas_nexus/security/capabilities.py`, served in `GET /api/me`), platform-administration/commercial-data separation, client composition parsing.
- [x] **Wave 3** — capability-gated Administration surface, restricted control-plane notice, preserved deep links (`W3-01`).
- [x] **Wave 4** — Data Product catalogue (`GET /api/data-products`), Analysis Snapshot v1 (`0034_analysis_snapshots`, `POST/GET /api/analysis-snapshots`), snapshot reference carried by the route-cost recommendation (`W4-01`).
- [x] **Wave 5** — application projections: MarketContext, PortfolioSnapshot, ReviewContext, ScenarioContext (`/api/projections/*`), with the market and portfolio read layers extracted into `application/projections/` so both the existing routes and the projections call one implementation (`W5-01`).
- [x] **Wave 6** — Decision Case domain, persistence (`0035_decision_cases`), API and client contract; a case cannot be decided without evidence, and the actor is the authenticated identity (`W6-01`).
- [x] **Wave 8 (taxonomy/presentation)** — product error taxonomy with ten families, severity, recoverability, correlation ids and operator-only detail; client presentation answering what happened, impact, cause and recovery (`W8-01`).
- [x] **Wave 9 (first slice)** — canonical Inspector region and mounted command palette; every declared shell region is now rendered (`W9-01`).
- [x] Release/security plumbing kept honest: `DB_SCHEMA_REVISION` now reports the real Alembic head and the release-metadata test asserts it equals that head; the security acceptance surface bound moved to 175 paths with the reason recorded.

## Current / next task

- Task ID: **Wave 5 client migration** (highest value next).
- Objective: point the market cockpit and portfolio views at `MarketContext`/`PortfolioSnapshot` and delete the multi-endpoint joins, timestamp arithmetic and client-side reconstruction the W0-01 inventory recorded.
- Relevant contracts: `W5-01_APPLICATION_PROJECTIONS.md`, `W0-01_CLIENT_INVENTORY.md` section 6, `W1-02_WORKSPACE_PATTERN_AND_PANEL_REGISTRY.md`.
- Focused validation: the existing `clients/web` suite (which pins the current join behaviour) plus new tests proving the projection path carries one as-of and one freshness basis.

## Deferred / known gaps

- **Wave 5 client half**: no UI reads the projections yet. Also `PortfolioSnapshot.resources` is declared unavailable (`RESOURCE_POOL_COMPOSITION_IS_ROUTE_LOCAL`) until `_compose_resource_pool_options` is extracted from `route_cost.py`.
- **Wave 8**: the API still raises hand-built `HTTPException` details; wiring the taxonomy into the error handler/middleware is the next step. The unified Job model is not implemented.
- **Wave 9**: workspaces are not yet migrated onto the Inspector and the panel taxonomy; the palette is mounted but AI actions stay out of it until Wave 7 gives them an invocation surface.
- **Wave 7** (research/AI convergence) and **Wave 10** (desktop workstation) are not started.
- Security findings C5-C8 from `W0-03_ARCHITECTURE_RECONCILIATION.md` remain open for the authority work: the legacy-principal entitlement behaviour, MCP's environment pseudo-principal, the two direct LLM routes that do not re-authorise against user authority, and the separation-of-duties question (C6b) for entitlement grants.
- Organisation, portfolio, market and region scope still do not exist; `ExperienceProfile.unsupported_scope_kinds` reports that honestly.
- `ruff` is not installed in this environment, so lint is unverified; the Python suites and `clients/web` build/tests are the evidence used here.

## Compatibility

- API: additive only. 12 new public paths across Waves 4-6, each declared in the permission registry, pinned in `tests/contract/test_api_surface_stability.py`, recorded in `docs/architecture/API_CONTRACT_EVOLUTION_POLICY.md` and counted in the security acceptance bound (175).
- DB: two expand-only migrations (`0034_analysis_snapshots`, `0035_decision_cases`); no destructive or incompatible change, no new datastore.
- Client: behaviour preserved; the Wave 1/3/9 changes are seam extractions, and the new i18n vocabulary is bilingual.
- Security: one deliberate narrowing (platform administration is not commercial access) and no widening; the commercial boundary now also covers `/api/projections/`.
- Numerics/release/DR: unchanged; release metadata now reports the true schema head.

## Validation evidence

- `python -m pytest tests -q --ignore=tests/integration` — **1589 passed, 1 skipped, 0 failed**.
- `clients/web`: `node --test "tests/*.test.ts"` — **279 passed**; `npx tsc --noEmit` clean; `npm run build` exit 0.
- `python scripts/security/run_security_acceptance.py` — all automated checks PASS (`api_import_safe`, `public_surface_bounded` 175, `permission_registry_complete` 175, token/identity/OIDC fail-closed, posture retained); external review items remain BLOCKED as before.
- Not run and not claimed: `tests/integration` (live PostgreSQL), packaging/installer evidence, visual/accessibility/UAT review, provider and licence validation, and lint.

## Risks / STOP CONDITIONS

- No STOP condition from `CODEX_ENTRYPOINT.md` was triggered: no commercial-data access broadened, no security control weakened, no destructive migration, no new infrastructure, no Web/Desktop divergence, and no scope crossing into execution, nomination or settlement.
- The Wave 1 interaction contracts, the Wave 2 capability model and the Wave 3 control-plane boundary are now normative. Work that contradicts them (a new top-level page for an object, a second global context owner, an AI button outside the five canonical actions, a client-side reconstruction of commercial state) is an architecture violation, not a style preference.
- Concurrency note: Waves 4-6 were developed in parallel by three workstreams in one working tree; the integrator verified the combined tree (`pytest --ignore=tests/integration`, the client suite, the security acceptance script) rather than each stream's isolated claim.

## Resume instruction

Read `CODEX_ENTRYPOINT.md`, the wave records `W0-01`…`W9-01` and this checkpoint; verify the tree is clean and the suites are green.
Continue with the next task named above (Wave 5 client migration), then the remaining halves of Wave 8 (error-handler wiring, unified jobs) and Wave 9 (workspace migration onto the Inspector and panel taxonomy), then Waves 7 and 10.
