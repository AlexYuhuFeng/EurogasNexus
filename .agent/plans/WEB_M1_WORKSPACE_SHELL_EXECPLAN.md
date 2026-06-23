# Web M1 Workspace Shell Implementation Plan

> **For agentic workers:** Optional helper skills may be used if available, but
> this plan is fully executable by plain local CLI. Follow the checkbox
> tasks in order and update them as evidence is produced.

**Goal:** Build the first Eurogas Nexus web workspace shell as an API-consuming client.

**Architecture:** The web client lives only under `clients/web`. It consumes `/api/v1`, starts with health/runtime status and a mocked reference-network layout, and does not own business truth.

**Tech Stack:** Use `docs/clients/CLIENT_TECH_STACK.md` exactly: React,
TypeScript, Vite, MapLibre GL, deck.gl, Zustand, i18next/react-i18next,
lucide-react, date-fns, zod, and plain CSS/CSS modules. Do not substitute
another web framework or UI kit.

---

## Activation Gate

Do not execute this plan until the user explicitly selects the web phase.

Required backend state before execution:

- `/api/v1/health` exists;
- API path policy is stable;
- runtime status API exists or this plan records a mock/gap;
- reference-network API contract exists or this plan records a mock/gap;
- `docs/clients/WEB_CLIENT_DESIGN_SPEC.md` has been read.

## Internet Requirement

Internet required: yes if React, Vite, TypeScript, MapLibre, testing packages,
or package documentation must be installed or verified.

Fallback if offline:

- create the directory/file structure;
- write TypeScript interfaces and mocked API fixtures;
- write a gap report at `data/web_m1/web_m1_gap_report.md`;
- do not claim build/test commands pass if dependencies are missing.

## Non-goals

- No direct DB access.
- No vendor API calls from the browser.
- No browser-side secrets.
- No trade execution, order entry, nomination, official recommendation, or
  auto-trading.
- No Windows packaging.

## Files To Create Or Modify

- `clients/web/package.json`
- `clients/web/index.html`
- `clients/web/tsconfig.json`
- `clients/web/vite.config.ts`
- `clients/web/src/main.tsx`
- `clients/web/src/app/App.tsx`
- `clients/web/src/app/AppShell.tsx`
- `clients/web/src/app/app.css`
- `clients/web/src/api/client.ts`
- `clients/web/src/api/types.ts`
- `clients/web/src/api/mockData.ts`
- `clients/web/src/features/runtime/RuntimeStatusPanel.tsx`
- `clients/web/src/features/network/NetworkWorkspace.tsx`
- `clients/web/src/features/scenario/ScenarioWorkspace.tsx`
- `clients/web/src/features/review/ReviewWorkspace.tsx`
- `clients/web/src/features/sources/SourcesWorkspace.tsx`
- `clients/web/src/components/TopStatusBar.tsx`
- `clients/web/src/components/PrimaryNavigation.tsx`
- `clients/web/src/components/InspectorRail.tsx`
- `clients/web/src/components/BottomResultsPanel.tsx`
- `clients/web/src/components/WarningStack.tsx`
- `clients/web/src/components/StatePanel.tsx`
- `clients/web/src/styles/tokens.css`
- `clients/web/src/test/apiClient.test.ts`
- `clients/web/README.md`
- `data/web_m1/web_m1_report.md`

## Task 1: Confirm Client Docs And Backend Gate

- [ ] Read `AGENTS.md`.
- [ ] Read `docs/clients/README.md`.
- [ ] Read `docs/clients/CLIENT_DELIVERY_MILESTONES.md`.
- [ ] Read `docs/clients/CLIENT_API_CONTRACT.md`.
- [ ] Read `docs/clients/CLIENT_DESIGN_SYSTEM.md`.
- [ ] Read `docs/clients/CLIENT_TECH_STACK.md`.
- [ ] Read `docs/clients/CLIENT_I18N_THEME_SPEC.md`.
- [ ] Read `docs/product/REAL_TIME_MARKET_INTELLIGENCE_BLUEPRINT.md`.
- [ ] Read `docs/clients/WEB_CLIENT_DESIGN_SPEC.md`.
- [ ] Read `docs/design/UX_LAYOUT_BLUEPRINTS.md`.
- [ ] Run:

```powershell
python -c "from apps.api.main import app; print('app import ok'); print(len(app.routes))"
```

Expected: app imports and route count prints.

## Task 2: Scaffold The Web Project

- [ ] Create the file tree listed above under `clients/web`.
- [ ] If internet and package installation are available, create a working
  React/Vite project.
- [ ] If offline dependencies are unavailable, create the files with static
  TypeScript/CSS content and write `data/web_m1/web_m1_gap_report.md`.

Required package scripts when dependencies are available:

```json
{
  "scripts": {
    "dev": "vite",
    "lint": "tsc --noEmit",
    "test": "vitest run",
    "build": "vite build"
  }
}
```

## Task 3: Define API Types And Client

- [ ] Implement `clients/web/src/api/types.ts` with bootstrap health,
  runtime-status, source-reference, warning, missing-input, and research
  metadata types.
- [ ] Implement `clients/web/src/api/client.ts` with:
  - configurable base URL;
  - `getHealth()`;
  - safe error classification;
  - no credential storage;
  - `/api/v1/health` as default health path.
- [ ] Add tests for path selection and error classification.

## Task 4: Implement Workspace Shell

- [ ] Implement `AppShell` with top status bar, left navigation, main workspace,
  right inspector, and bottom panel.
- [ ] Implement CSS tokens from `CLIENT_DESIGN_SYSTEM.md`.
- [ ] Implement `en-US` and `zh-CN` locale resources.
- [ ] Implement light, dark, and system theme modes through CSS custom
  properties.
- [ ] Implement responsive behavior:
  - desktop shows full layout;
  - tablet turns inspector into drawer-ready panel;
  - mobile collapses navigation and bottom panel into tabs.

## Task 5: Implement Runtime Status Screen

- [ ] Show backend URL, health state, profile if known, DB/runtime state if
  backend exposes it, and mock/degraded warnings.
- [ ] Show safe states for backend unavailable, DB unavailable, partial feature,
  and unknown error.

## Task 6: Implement Network Workspace Shell

- [ ] Render a map-ready workspace surface.
- [ ] Use synthetic mock network data only until backend endpoints exist.
- [ ] Add layer controls for hubs, pipelines/corridors, LNG, storage, beach
  delivery points, interconnectors, and zones.
- [ ] Add disabled/placeholder map controls for capacity/contract, market
  signal, weather/HDD/CDD, strategy, LLM analysis, and glossary surfaces.
- [ ] Add selected asset inspector with source/freshness/warning fields.

## Task 7: Implement Scenario And Review Shells

- [ ] Add scenario input sections for resource/source, destination, route
  preference, volume, timing, price assumptions, cost assumptions, constraints,
  and notes.
- [ ] Add missing-input and assumptions display.
- [ ] Add review panel with candidate table, warnings, sources, lineage,
  `research_only`, and `human_review_required`.
- [ ] Keep export disabled until governance/export policy exists.

## Task 8: Validate

When dependencies are available:

```powershell
npm run lint
npm run test
npm run build
```

Always run backend import check:

```powershell
python -c "from apps.api.main import app; print('app import ok'); print(len(app.routes))"
```

## Acceptance Criteria

- Web client files live only under `clients/web`.
- Client targets `/api/v1`.
- Client uses the fixed library stack in `CLIENT_TECH_STACK.md`.
- Client has English/Mandarin locale resources.
- Client has light/dark/system theme foundation.
- No direct DB, vendor API, or secret access exists.
- Runtime status screen exists.
- Workspace shell matches the documented layout.
- Mock data is synthetic and labeled.
- Validation passes or a gap report states exactly what is blocked.

## Rollback Notes

Remove `clients/web` runtime files created by this plan and `data/web_m1`
reports. Backend code is not affected.
