# Client Documentation Index

## Purpose

This directory defines Eurogas Nexus API-consuming client designs: Python SDK,
CLI, web client, and Windows client. It is documentation for later
implementation, not active client runtime code unless a milestone explicitly
selects that surface.

## Read Order

When Claude Code is asked to implement clients, read these files in order:

1. `docs/architecture/PRODUCT_DELIVERY_MASTER_PLAN.md`
2. `docs/clients/CLIENT_DELIVERY_MILESTONES.md`
3. `docs/clients/CLIENT_API_CONTRACT.md`
4. `docs/clients/CLIENT_DESIGN_SYSTEM.md`
5. `docs/clients/CLIENT_TECH_STACK.md`
6. `docs/clients/CLIENT_I18N_THEME_SPEC.md`
7. `docs/product/REAL_TIME_MARKET_INTELLIGENCE_BLUEPRINT.md`
8. `docs/clients/SDK_CLIENT_DESIGN_SPEC.md`
9. `docs/clients/CLI_CLIENT_DESIGN_SPEC.md`
10. `docs/clients/WEB_CLIENT_DESIGN_SPEC.md`
11. `docs/clients/MAP_FIRST_TRADER_COCKPIT_SPEC-EN.md`
12. `docs/clients/MAP_FIRST_TRADER_COCKPIT_SPEC-CN.md`
13. `docs/clients/MARKET_POSITIONING_COCKPIT_SPEC-EN.md`
14. `docs/clients/MARKET_POSITIONING_COCKPIT_SPEC-CN.md`
15. `docs/clients/WINDOWS_CLIENT_DESIGN_SPEC.md`
16. `docs/clients/WINDOWS_DEMO_UX_REFERENCE.md`
17. `docs/architecture/WEB_CLIENT_IMPLEMENTATION_BLUEPRINT.md`
18. `docs/architecture/WINDOWS_CLIENT_IMPLEMENTATION_BLUEPRINT.md`

## Product Rule

Clients are SDK/API consumers. Runtime data lives in PostgreSQL, but clients
reach it through the backend API boundary:

- SDK calls `/api/v1`.
- CLI calls the SDK first, or `/api/v1` directly only for a documented SDK gap.
- Web calls `/api/v1` through its browser API client.
- Windows packages or launches the web workspace and calls `/api/v1`.

They must not read PostgreSQL, backend local files, raw vendor data, `.env`
files, historical Desktop project files, or connector credentials directly. The
only exception is a documented operations script that performs explicit
read-only runtime DB validation.

Imported screen orders and PnL snapshots are also API-only. They are exposed by
`/api/v1/portfolio/*` and the Python SDK portfolio client as read-only
decision-support observations, not order-entry, order-routing, trade-capture,
or accounting records.

## Implementation Rule

Do not add client runtime dependencies until a client milestone is selected.
If Claude Code is offline and dependencies are missing, create contracts,
mocked API clients, file structure, and a gap report instead of pretending the
client can build.
