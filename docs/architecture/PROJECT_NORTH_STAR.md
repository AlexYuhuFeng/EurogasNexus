# Project North Star

## Ultimate Goal

Eurogas Nexus is a European gas decision-support, market-intelligence, and
strategy shadow-run workspace for gas traders. It helps a desk understand
physical gas resources, European infrastructure, TSO access, capacity, tariffs,
LNG regas, storage, market marks, FX, source health, route economics, strategy
state, warnings, and indicative PnL before a human commercial decision.

The product is resource-pool-native. Purchase contracts, LNG resources, beach
delivery resources, hub purchases, capacity rights, and imported external
observations feed a portfolio resource pool. The product evaluates how that pool
can be sold or held across European markets and routes, then attributes PnL
back to resources and contracts for review.

## Current V1 Posture

The current repository is no longer only a backend foundation. It is a V1
release-candidate worktree for the tested local scope. It is PostgreSQL-first,
API-first, SDK-ready, and client-active:

- PostgreSQL runtime store and Alembic migrations.
- FastAPI backend under stable `/api` routes.
- Python SDK and CLI consumers.
- React/Vite Web client.
- Tauri Windows/Linux desktop shell wrapping the Web workspace.

Web and Windows client surfaces are active API consumers. They are not sources
of runtime truth. All runtime data remains behind the backend API and
PostgreSQL.

Latest local runtime posture observed in this worktree:

- API import succeeds with `76` routes in development profile.
- Live runtime API reports Alembic `0012_entsog_capacity`.
- Runtime DB reports `33` required tables and `0` missing tables.
- Source Center reports PostgreSQL-backed provider/source posture when the
  operator's API process has `RUNTIME_STORE_DATABASE_URL` configured.

## Source-Of-Truth Rules

- PostgreSQL is the runtime source of truth.
- Backend import must not connect to PostgreSQL or run migrations.
- Migrations are explicit operator actions.
- Web, Windows, SDK, and CLI access runtime data through `/api` or SDK only.
- Clients must not open PostgreSQL connections, read backend local data files,
  read `.env`, store vendor credentials, or call provider APIs directly.
- Local files are documentation, import templates, raw/canonical archives,
  reports, fixtures, or development fallback only.
- Missing runtime data must be shown as unavailable, partial, blocked,
  stale, credential-missing, or table-missing state. It must not be hidden by
  browser-side mock data.
- Preview/test rows, when needed, are inserted into PostgreSQL with explicit
  source provenance and then read back through `/api`. Price previews must use
  `EEX_Sim`, `ICE_OCM_Sim`, and `ICIS_Sim` rows in `market_observations`, not
  client-side or ad hoc demo prices.

## Product Boundary

Eurogas Nexus helps users analyze European gas context, compare options, and
prepare human-reviewed commercial decisions. It is a decision-support and
market-intelligence product, not a research-only notebook. It must not become
any of the following:

- trade execution;
- order entry;
- order routing;
- trade capture;
- nomination submission;
- settlement or accounting;
- official approval workflow;
- legal advice;
- official trading recommendation;
- auto-trading;
- ETRM replacement.

Decision language should be: signal, option, candidate, route, allocation,
blocker, warning, source evidence, human review. Avoid execution language such
as place, route order, approve, nominate, book, execute, or trade now.

## Active Product Shape

The active product consists of these cooperating surfaces:

1. Backend API: owns route registration, runtime status, source posture,
   observations, route-cost, resource-pool, strategy, analysis, glossary,
   credentials, and read-only portfolio observation routes.
2. PostgreSQL/Alembic: owns runtime tables for sources, observations,
   reference network, route cost, contracts/resources, strategy, analysis,
   credentials, audit, entitlement, screen-order observations, and PnL
   snapshots.
3. SDK/CLI: operator and programmatic API consumers; no direct DB access.
4. Web: map-first trader cockpit and operational workspaces.
5. Windows/Tauri: packaged desktop shell for the same Web workspace.

The home cockpit is map-first and resource-pool-native. Detailed source,
runtime, contract, strategy, glossary, and review workflows live on separate
workspace pages so the map remains the primary trading-intelligence surface.

## Development Direction

The early foundation milestones have been completed in this worktree. Future
work should not restart from Milestone 2 unless the user explicitly asks for a
historical replay. Use these current authorities instead:

- `docs/architecture/CURRENT_PAUSE_POINT.md` for current implementation state.
- `docs/architecture/NEXT_DEVELOPMENT_QUEUE.md` for ordered next work.
- `docs/release/V1_RELEASE_READINESS.md` for release-candidate status.
- `docs/clients/MAP_FIRST_TRADER_COCKPIT_SPEC-EN.md` for home cockpit rules.
- `docs/contracts/21_RESOURCE_POOL_CONTRACT-EN.md` for resource-pool and
  EFET-style contract rules.
- `docs/clients/CLIENT_API_CONTRACT.md` for client/API boundaries.

Recommended next work:

1. Keep documentation aligned with the active DB-backed product.
2. Harden live ingestion scheduling, retries, source health, and operator
   diagnostics.
3. Harden entitlement, audit, export governance, and internal import controls.
4. Improve the Web cockpit through focused components and trader-review
   evidence surfaces.
5. Add deeper persisted contract/resource workflows through backend APIs only.

## Historical Reference Policy

Historical local Eurogas Nexus projects clarify ambition and failure modes.
They are reference evidence, not implementation authority. Use them to
understand map-centric workflows, scenario composition, dense trading layouts,
route inspection, runtime status, and report review. Do not copy historical
code, raw data, vendor files, secrets, generated reports, or old UI layouts as
production source.

## Engineering Standard

Every milestone should answer:

- What boundary is being made more true?
- What files are allowed to change?
- What data policy applies?
- What API and DB impact exists?
- What validation proves the milestone?
- What remains `PARTIAL` or `BLOCKED`?

If a requirement is unclear, create a gap report instead of inventing behavior.
