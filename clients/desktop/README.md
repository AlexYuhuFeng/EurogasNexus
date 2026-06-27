# clients/desktop

Eurogas Nexus Windows client shell.

## Blueprint

Read `docs/architecture/WINDOWS_CLIENT_IMPLEMENTATION_BLUEPRINT.md` before
adding code here.

Also read:

- `docs/clients/CLIENT_DELIVERY_MILESTONES.md`
- `docs/clients/CLIENT_API_CONTRACT.md`
- `docs/clients/CLIENT_DESIGN_SYSTEM.md`
- `docs/clients/WINDOWS_CLIENT_DESIGN_SPEC.md`
- `docs/design/UX_LAYOUT_BLUEPRINTS.md`

## Target

Windows-packaged client that reuses the Web workspace and consumes backend
`/api` contracts. The Web client is the single UI/UX source. Any future
layout, theme, i18n, map, or workflow redesign must be implemented in
`clients/web` first so browser and Windows clients stay coherent.

## Stack

Tauri 2 wrapping `clients/web/dist`.

## Commands

```powershell
npm install
npm run web:build
npm run check
npm run build
```

`npm run build` packages the Windows shell using the same Web build. It does
not start the backend and does not connect to PostgreSQL.

## Rules

- No direct DB access.
- No vendor API calls from the client.
- No bundled secrets.
- No historical Desktop source copy-paste.
- The old `eurogas nexus.exe` demo is workflow reference only.

## Runtime

The desktop shell loads the Web workspace and relies on Web/API configuration.
It stores no vendor credentials, no DB URL, no market data, and no strategy
parameters.
