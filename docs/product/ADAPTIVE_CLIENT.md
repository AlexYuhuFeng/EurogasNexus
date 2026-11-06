# Adaptive client: phone, tablet, browser and Windows desktop

Status: adopted 2026-11-05 (#40). Fixes and prevents the phone defects in #39. Related: #30,
#36 (information architecture), `docs/product/UX_REFERENCE.md`.

## Decision

One product, one React client, one set of domain objects, words and permissions. The
client adapts its **composition** to the space and input it has. It does not shrink the
desktop page, and it does not keep a second mobile interface. No native mobile rewrite;
Tauri stays the Windows/macOS shell.

## Three independent axes

| Axis | Values | Read from | Decides |
|---|---|---|---|
| Width class | `compact` < 720 px, `medium` 720–1199 px, `wide` ≥ 1200 px | `matchMedia` on the window, not the device | Shell layout, number of panes, table vs. card rows |
| Input | `coarse` (touch) or `fine` (mouse, trackpad) | `(pointer: coarse)` | Hit-target size (44 px on coarse), hover-only affordances get a tap equivalent |
| Platform | browser, Tauri desktop | the existing host adapter (`app/host`) | Native windows, file dialogs, notifications |

A narrow desktop window gets the compact layout, and a tablet with a keyboard gets fine-pointer
targets if it reports a fine pointer. User-agent strings are never used. The shell publishes the
first two axes on `<html>` as `data-width-class` and `data-pointer` (`app/shell/useShellLayout.ts`).
Components and CSS read those attributes instead of inventing their own breakpoints.

Role decides what comes first. The device does not. Layout never grants anything; the backend
authorises every read.

## Shell by width class

| Region | Compact | Medium | Wide |
|---|---|---|---|
| Primary navigation | Menu button with the current line's name; a drawer lists the lines and Help & Settings | Below 1024 px the same drawer; 1024–1199 px tabs | Tabs |
| Search / palette | Icon button | Icon button; a keycap only with a fine pointer | Button with text, keycap with a fine pointer |
| Trading context (gas day, product, hub) | In the drawer; a one-line summary on the menu button | A "Context" button that opens a dropdown panel | Inline |
| Alerts, data status, account | Always on the bar: bell icon with count, status dot, account initials | Short labels | Full labels |
| Page tabs (sub-views) | One row with short labels (`<key>.short`, e.g. "Curves", "Keys", "Infra") | Full labels | Full labels |
| Explanatory panels (scope, context strips) | Folded to their title; open on demand | Open | Open |
| Inspector / detail | Full-screen sheet with Back | Side pane when it fits, else a sheet | Side pane |

**Keyboard affordances follow the input, not the device name.** Keycaps (Ctrl K, ⌘K), the
"Keyboard shortcuts" menu entry and shortcut hints in the command palette appear only where the
primary pointer is fine (a mouse or trackpad) and the window is not compact. A phone or tablet
reader is never shown keys they do not have. The shortcuts still work when a keyboard is attached.

**Icons and abbreviations before truncation.** When a word does not fit, use a recognised icon
(bell, magnifier, menu) or an agreed short form, and keep the full word as the accessible name.
Do not let text wrap into vertical fragments or ellipsise mid-word.

Account, Settings, language, appearance and sign-out are reachable at every width (#39).

## Content rules

1. **Tables become rows at compact width.** A data table shows the identifying column and one
   status or value. The other columns move to the detail view. The Connectors catalogue is the
   pattern: name, one status word, one action.
2. **Forms are one column at compact width.** Labels sit above fields, and grouped choices
   (data scopes) are stacked check rows with 44 px targets. A responsive change never preselects
   broader access.
3. **The map keeps controls out of the data.** Layer switches live in one labelled panel with
   an active-layer count, zoom stays in its corner, and attribution is never covered. "Live"
   means fresh business data, not an open socket.
4. **Empty states are one line** with a reason and a next step. Nothing is drawn as a chart or
   card grid when no data exists.
5. **Nothing scrolls sideways** except a numeric table inside its own focusable region.

## Continuity

Resizing or rotating keeps the page, sub-view and selected object, because they are in the URL
(#31). Moving between devices uses saved server objects and deep links. Unsaved drafts are not
synchronised across devices.

## Verification

Every shell or page change is checked at 390×844 (phone, coarse), 820×1180 (tablet), 1280×800
and 1440×900 (desktop, fine), in EN and ZH, light and dark. The checks are: no horizontal page
scroll, account menu reachable, no control overlap, keyboard focus visible. The browser acceptance
job already runs three viewports. The phone viewport is added to the same sweep.

## Slices

| # | Slice | Done when |
|---|---|---|
| A1 | `useShellLayout`, compact top bar with drawer, status dot, icon search | One-row bar at 390 px; account and Settings reachable; context in the drawer |
| A2 | Compact rows for operational tables (sources done via Connectors; API keys, users) | No table wider than the screen on Admin pages at 390 px |
| A3 | Map layer panel and reserved control corners | No overlap at 390 px in EN/ZH |
| A4 | Inspector as a sheet at compact width | Detail opens full-screen with Back, focus returns to the row |
