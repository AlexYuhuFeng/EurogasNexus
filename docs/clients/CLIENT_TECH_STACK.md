# Client Tech Stack Contract

## Purpose

This file is the authoritative V1 library contract for Web and Windows client
implementation. Codex must not substitute frameworks or GPL-family
dependencies.

Historical Desktop evidence under `C:\Users\qqshu\Desktop` used React, Vite,
MapLibre GL, deck.gl, Zustand, and Tauri. V1 keeps that direction, but removes
old local-runtime assumptions and requires SDK/API-only data access.

## License Rule

Prefer permissive licenses:

- MIT;
- Apache-2.0;
- BSD-2-Clause or BSD-3-Clause;
- ISC;
- Unicode/ICU-style permissive licenses only when needed for localization.

Do not add GPL, LGPL, AGPL, SSPL, BUSL, Elastic, Redis-RSAL, Commons-Clause, or
PolyForm dependencies without explicit review.

Every new client dependency must record package name, purpose, license, and
runtime/dev scope in the milestone report.

## Web Runtime Libraries

Use these libraries for `clients/web` when the web milestone is selected.
Library choices are fixed. If installation fails, write a gap report; do not
substitute another framework or library family.

| Package | Version Target | License Expectation | Purpose |
| --- | --- | --- | --- |
| `react` | `^19.1.0` | MIT | UI runtime |
| `react-dom` | `^19.1.0` | MIT | DOM renderer |
| `typescript` | `~5.8.3` | Apache-2.0 | static typing |
| `vite` | `^7.0.4` | MIT | build/dev tooling |
| `@vitejs/plugin-react` | `^4.6.0` | MIT | React/Vite integration |
| `maplibre-gl` | `^5.20.1` | BSD-3-Clause | base map rendering |
| `@deck.gl/core` | `^9.3.1` | MIT | high-volume map overlays |
| `@deck.gl/layers` | `^9.3.1` | MIT | route, point, polygon, and signal layers |
| `@deck.gl/mapbox` | `^9.3.1` | MIT | MapLibre/deck.gl integration |
| `zustand` | `^5.0.11` | MIT | small client UI state store |
| `i18next` | `^25` | MIT | localization engine |
| `react-i18next` | `^15` | MIT | React localization bindings |
| `lucide-react` | `^0.468.0` | ISC | icons |
| `date-fns` | `^4` | MIT | date/time formatting |
| `zod` | `^4` | MIT | client-side API payload validation |

Use plain CSS modules or plain CSS with CSS custom properties. Use browser
`fetch` plus a local typed API wrapper for HTTP calls. Use Zustand for UI state
and lightweight response status state. Do not add
Tailwind, Material UI, Ant Design, Bootstrap, shadcn, Redux, Next.js, Remix,
Electron, or a charting/grid suite unless a later milestone explicitly approves
it.

## Web Development Libraries

Use these only as development dependencies when available:

| Package | Version Target | License Expectation | Purpose |
| --- | --- | --- | --- |
| `vitest` | `^3` | MIT | unit tests |
| `@testing-library/react` | `^16` | MIT | component tests |
| `@testing-library/jest-dom` | `^6` | MIT | DOM assertions |
| `jsdom` | `^25` | MIT | DOM test environment |
| `playwright-core` | `^1.58.2` | Apache-2.0 | optional smoke tests when browser tooling exists |

## Windows Runtime Libraries

Use Tauri 2 for `clients/desktop` when the Windows milestone is selected and
dependencies are available:

| Package/Crate | Version Target | License Expectation | Purpose |
| --- | --- | --- | --- |
| `@tauri-apps/cli` | `^2` | Apache-2.0/MIT family | desktop build tooling |
| `@tauri-apps/api` | `^2` | Apache-2.0/MIT family | desktop API bridge |
| `@tauri-apps/plugin-opener` | `^2` | Apache-2.0/MIT family | safe external open behavior |
| `tauri` | `2` | Apache-2.0/MIT family | Rust desktop shell |
| `tauri-build` | `2` | Apache-2.0/MIT family | Tauri build support |
| `serde` | `1` | MIT/Apache-2.0 | config serialization |
| `serde_json` | `1` | MIT/Apache-2.0 | JSON config |
| `reqwest` | `0.12` with `rustls-tls` | MIT/Apache-2.0 | optional backend health smoke check |

Do not use `rusqlite`, SQLite, local embedded databases, or local data caches in
V1 Windows. The Windows client stores only non-sensitive UI preferences.

Electron is not approved for V1.

## Internationalization Libraries

Use:

- `i18next`;
- `react-i18next`;
- local JSON translation files committed under `clients/web/src/i18n/locales/`.

Required locales:

- `en-US`;
- `zh-CN` for Simplified Chinese/Mandarin UI copy.

Do not use live translation APIs in V1.

## Theme Libraries

No theme framework is required. Use CSS custom properties and a small local
theme store.

Required theme modes:

- light;
- dark;
- system.

The active theme must be visible in UI settings and stored only as a
non-sensitive client preference.

## Offline Rule

If Codex cannot install or verify packages because internet is
unavailable, it must:

1. create the planned file structure;
2. write typed API client interfaces, i18n resources, theme tokens, and gap
   reports;
3. write the gap report required by the selected milestone;
4. not claim `npm run build`, `cargo tauri build`, or browser smoke tests pass;
5. not substitute another package or architecture.
