# R14: Web Research Workspace Report

**Milestone ID:** R14 | **Status:** PARTIAL | **Date:** 2026-05-29

## Status: PARTIAL

**Reason:** npm package installation requires internet access. Full build cannot
be verified without `npm install` and `npm run build`.

**What was created:**
- Full web workspace file structure under `clients/web/`
- `package.json` with approved stack: React 19, Vite 6, TypeScript 5,
  MapLibre GL 5, deck.gl 9, Zustand 5, i18next 24, lucide-react, date-fns, zod
- `vite.config.ts` with `/api` proxy to backend
- `tsconfig.json` with strict mode and path aliases
- Typed API client (`src/api/client.ts`) calling `/api/v1` with fetch
- i18n resources: English (en.json) and Mandarin Chinese (zh.json)
- Light/dark/system theme store (Zustand + CSS variables + localStorage)
- API data store (Zustand) with loading/error/dataStatus states
- Main App component with header, nav, map placeholder, sidebar panels
- Production-grade CSS with light/dark/system theme variables

**What remains:**
- `npm install` to download and install dependencies
- `npm run build` to verify TypeScript compilation and Vite bundling
- Map component with MapLibre GL + deck.gl integration
- Full workspace pages (Network, Market, Scenario, Strategy, Review, Sources,
  Glossary, Runtime, Settings)
- E2E tests

**Internet required:** yes — npm packages must be downloaded.

**Fallback applied:** Created file structure, TypeScript interfaces, i18n/theme
resources, mocked API client, Zustand stores, and CSS theme system. All source
code is ready for `npm install && npm run dev`.

## Files

- `clients/web/package.json`
- `clients/web/tsconfig.json`
- `clients/web/vite.config.ts`
- `clients/web/index.html`
- `clients/web/src/main.tsx`
- `clients/web/src/App.tsx`
- `clients/web/src/api/client.ts`
- `clients/web/src/i18n/index.ts`
- `clients/web/src/i18n/en.json`
- `clients/web/src/i18n/zh.json`
- `clients/web/src/stores/theme.ts`
- `clients/web/src/stores/api.ts`
- `clients/web/src/styles/app.css`

## Next

R15: Windows Client Package Shell (also PARTIAL — requires Tauri/Rust toolchain)
