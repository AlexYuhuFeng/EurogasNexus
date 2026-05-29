# V1 R14 Web Research Workspace ExecPlan

**Goal:** Create the map-first web research workspace using React/Vite/MapLibre.

**Architecture:** Web client layer; consumes /api/v1 via typed fetch client.

**Tech Stack:** React 19, TypeScript 5, Vite 6, MapLibre GL 5, deck.gl 9,
Zustand 5, i18next 24, lucide-react, date-fns, zod, plain CSS.

---

## Milestone ID

`R14`

## Status

`partial`

## Internet Requirement

Internet required: yes — npm packages (React, Vite, MapLibre GL, deck.gl,
Zustand, i18next, etc.) must be downloaded via `npm install`.

Fallback: Created complete file structure, TypeScript interfaces, i18n resources
(en-US/zh-CN), light/dark/system theme store (Zustand + CSS variables), API
data store, App shell with header/nav/map-placeholder/sidebar, and gap report.
All source code is ready for `npm install && npm run dev`.

## Goal

Deliver the map-first web workspace with English/Mandarin i18n, light/dark/system
themes, and SDK/API-backed data flow. The first visual screen is the workspace.

## Non-goals

- No marketing landing page.
- No direct DB access, vendor credentials, or LLM provider calls from browser.
- No Electron, Next.js, Tailwind, Material UI, Ant Design, Bootstrap, or Redux.

## Files Created (partial)

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

## Remaining

- `npm install` to download dependencies
- `npm run build` to verify compilation
- Map component with MapLibre GL + deck.gl
- Full workspace pages (Network, Market, Scenario, Strategy, Review, Sources,
  Glossary, Runtime, Settings)
- E2E tests

## Rollback

Remove `clients/web/` directory. No backend impact.
