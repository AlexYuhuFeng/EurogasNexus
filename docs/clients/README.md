# Client Documentation Index

## Purpose

This directory defines the active API-consuming clients for Eurogas Nexus:
Python SDK, CLI, Web, and Windows/Tauri. These docs are no longer purely future
design notes. They describe active client runtime code and the rules for
continuing it safely.

Clients are SDK/API consumers. They must not become runtime data stores,
provider connectors, or credential vaults.

## Current Client State

- SDK and CLI exist as API consumers.
- Web exists under `clients/web` as the map-first React/Vite workspace.
- Windows desktop exists under `clients/desktop` as a Tauri shell around the
  shared Web workspace.
- All clients must continue to use backend `/api` or SDK boundaries.

## Read Order

When working on clients, read these files in order:

1. `docs/architecture/PROJECT_NORTH_STAR.md`
2. `docs/architecture/CURRENT_PAUSE_POINT.md`
3. `docs/architecture/NEXT_DEVELOPMENT_QUEUE.md`
4. `docs/clients/CLIENT_DELIVERY_MILESTONES.md`
5. `docs/clients/CLIENT_API_CONTRACT.md`
6. `docs/clients/CLIENT_TECH_STACK.md`
7. `docs/clients/UI_UX_STYLE_GUIDE-EN.md`
8. `docs/clients/UI_UX_STYLE_GUIDE-CN.md`
9. `docs/clients/MAP_FIRST_TRADER_COCKPIT_SPEC-EN.md`
10. `docs/clients/MAP_FIRST_TRADER_COCKPIT_SPEC-CN.md`
11. `docs/contracts/21_RESOURCE_POOL_CONTRACT-EN.md`
12. `docs/contracts/21_RESOURCE_POOL_CONTRACT-CN.md`
13. `docs/clients/WEB_CLIENT_DESIGN_SPEC.md`
14. `docs/clients/WINDOWS_CLIENT_DESIGN_SPEC.md`
15. `docs/clients/MARKET_POSITIONING_COCKPIT_SPEC-EN.md`
16. `docs/clients/MARKET_POSITIONING_COCKPIT_SPEC-CN.md`
17. `docs/clients/OPERATIONAL_GLOSSARY_CONTEXT_SPEC-EN.md`
18. `docs/clients/OPERATIONAL_GLOSSARY_CONTEXT_SPEC-CN.md`

## Client Boundary

Runtime data lives in PostgreSQL, but clients reach it only through backend
contracts:

```text
SDK      -> /api
CLI      -> SDK first, or /api for documented SDK gaps
Web      -> browser API client -> /api
Windows  -> packaged Web workspace -> /api
```

Clients must not:

- connect directly to PostgreSQL;
- import backend DB/session/runtime-store modules;
- read backend local data files for runtime state;
- read `.env`;
- store provider credentials;
- call exchange, broker, vendor, weather, or LLM providers directly;
- present execution, order-entry, nomination, booking, approval, settlement, or
  official recommendation workflows.

## Active Client Responsibilities

The Web/Windows workspace currently owns:

- Network: map-first resource-pool cockpit, resource-path overlay, route
  options, warnings, and PnL summary.
- Capacity: ENTSOG flow/capacity, TSO access, tariffs, storage, and LNG.
- Market: terminal-style European gas hub board, regional TTF spreads, ECB FX,
  and exchange/broker source posture without fabricated prices.
- Scenario: route-cost, resource-pool, and economics review controls.
- Contracts: EFET-style resource term capture, JSON draft import, persisted
  contract library, and backend-owned resource-pool refresh.
- Strategy: paper strategy evaluation.
- Review: route allocation, warning, and analysis/report review.
- Order Records: read-only screen-order observations and PnL snapshots.
- Data Sources: source categories, credentials, freshness, diagnostics, and
  record counts.
- Glossary: bilingual operational terms and DB-derived context.
- Runtime: database/API readiness and governance metadata.
- Settings: non-sensitive language, theme, unit, currency, session, and
  service-access posture preferences; credential entry remains backend-owned.

## Implementation Rule

Improve active client code incrementally. Keep components focused and preserve
API boundaries. When a missing backend route is needed, add a backend/API
milestone or gap report instead of fabricating browser-side runtime data.
