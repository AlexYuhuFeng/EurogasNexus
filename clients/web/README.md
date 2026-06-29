# clients/web

React/Vite/MapLibre Web workspace for Eurogas Nexus.

The Web client is the single UI source for browser, Windows, and Linux desktop
surfaces. The Tauri desktop package wraps the built Web bundle.

## Runtime Boundary

The client consumes backend `/api` contracts only. It does not connect to
PostgreSQL, read backend local files, call vendor APIs directly, or store
provider credentials.

Missing runtime data must be shown as unavailable, degraded, entitlement, or
diagnostic state. Do not create browser-side synthetic runtime data.

The map cockpit and Scenario optimizer must stay disabled until the backend API
confirms all required PostgreSQL-backed inputs are present: runtime database
connectivity, persisted portfolio resources, route candidates, TSO tariff rows,
and market price observations. The browser may show blockers and next actions,
but it must not invent local fallback rows.

## Workspaces

- Network: map-first resource-pool cockpit and recommended sale paths.
- Capacity: ENTSOG flow/capacity, TSO access, tariffs, GIE storage/LNG.
- Market: price, FX, and market-source observations.
- Scenario: route economics and resource-pool optimization controls.
- Contracts: EFET-style resource contract term capture.
- Strategy: backtest, shadow-run, monitoring, and risk controls.
- Review: decision review, warnings, LLM analysis, and report output.
- Order Records: read-only screen-order observations and portfolio PnL.
- Data Sources: provider categories, credentials posture, and diagnostics.
- Glossary: bilingual operational definitions and context.
- Runtime: API, database, Alembic, and readiness posture.
- Settings: language and light/dark/system theme.
- Manual: customer-facing page map and operating boundary.

The Data Sources workspace owns provider diagnostics. It must group providers
by category, show credential posture, runtime record counts, last success or
failure state, and the next operator action for each feed.

## Commands

```powershell
npm ci
npm run dev
npm run build
```

## Design Docs

Read before changing UI/UX:

- `docs/clients/CLIENT_API_CONTRACT.md`
- `docs/clients/CLIENT_TECH_STACK.md`
- `docs/clients/WEB_CLIENT_DESIGN_SPEC.md`
- `docs/clients/MAP_FIRST_TRADER_COCKPIT_SPEC-EN.md`
- `docs/clients/MAP_FIRST_TRADER_COCKPIT_SPEC-CN.md`
- `docs/clients/UI_UX_STYLE_GUIDE-EN.md`
- `docs/clients/UI_UX_STYLE_GUIDE-CN.md`
- `docs/clients/WINDOWS_DEMO_UX_REFERENCE.md`
