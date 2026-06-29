# clients

User-facing API consumers live here.

## Components

- `web/`: React/Vite/MapLibre workspace and the single UI source for Web,
  Windows, and Linux desktop packaging.
- `desktop/`: Tauri shell that packages `clients/web/dist`.
- Python SDK lives under `src/eurogas_nexus/sdk` now and later
  `packages/python-sdk`.
- CLI lives under `src/eurogas_nexus/cli`.

## Rule

Clients consume `/api`. They must not read PostgreSQL, backend local files,
raw vendor data, or credentials directly.

If runtime data is missing, clients show unavailable, degraded, entitlement, or
diagnostic states. They must not fabricate live data in the browser or desktop
shell.

## Design Docs

Read before changing client code:

- `docs/clients/README.md`
- `docs/clients/CLIENT_DELIVERY_MILESTONES.md`
- `docs/clients/CLIENT_API_CONTRACT.md`
- `docs/clients/CLIENT_DESIGN_SYSTEM.md`
- `docs/clients/CLIENT_TECH_STACK.md`
- `docs/clients/WEB_CLIENT_DESIGN_SPEC.md`
- `docs/clients/MAP_FIRST_TRADER_COCKPIT_SPEC-EN.md`
- `docs/clients/MAP_FIRST_TRADER_COCKPIT_SPEC-CN.md`
- `docs/clients/UI_UX_STYLE_GUIDE-EN.md`
- `docs/clients/UI_UX_STYLE_GUIDE-CN.md`
- `docs/clients/WINDOWS_CLIENT_DESIGN_SPEC.md`
