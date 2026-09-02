# UI And Content Standards

## Status

This document is the single authoritative UI and content standard for the
Eurogas Nexus Web and Windows/Linux client surfaces. When another client
document conflicts with this one, this document wins; report the conflict and
update the other document.

The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT", "SHOULD",
"SHOULD NOT", "RECOMMENDED", "MAY", and "OPTIONAL" in this document are to be
interpreted as described in RFC 2119 and RFC 8174.

The archived `CLIENT_DESIGN_SYSTEM.md` is historical. `UI_UX_STYLE_GUIDE-EN.md`
and `UI_UX_STYLE_GUIDE-CN.md` remain bilingual implementation companions for
visual direction; they have no independent authority.

## Information hierarchy

1. Global shell and runtime status stay visible and persistent.
2. Workspace page header identifies the active group and page.
3. Local task tabs identify the active view inside the workspace.
4. Panel headers summarize the panel's decision or status.
5. Primary work surface (map, table, editor, or report) gets the most space.
6. Rails carry context and controls; the decision rail and bottom comparison
   panels remain dedicated surfaces.
7. Warnings, missing inputs, source posture, and human-review boundaries MUST
   appear inline near the affected result, never only in a hidden popover or
   secondary tab.

Map-first workspaces keep the map dominant. Non-map workspaces use a compact,
unframed page identity band; they MUST NOT mount a hidden map canvas or
inactive map controls.

## Spacing and surfaces

- Use the existing CSS custom properties in `clients/web/src/styles/app.css`
  for surfaces, text, borders, and state colors.
- Panel radius MUST NOT exceed 8px; pill controls may use full radius.
- Use hairline borders and small stacked elevation. Do not use heavy shadows,
  decorative gradients, orbs, blobs, or stock imagery.
- Avoid nested cards. Prefer grid rows, rails, and compact panels.
- Keep the workspace dense but scannable: compact 12px body text, 8px spacing
  grid increments, and one level of emphasis per row.
- `app.css` is a deliberate global sheet. Scoped UI changes belong in narrowly
  named component or workspace CSS and MUST NOT collide with Strategy WIP
  selectors.

## Typography

- UI text uses the system UI font stack; technical eyebrows, source tags, and
  compact labels use `ui-monospace`.
- Headings are sentence case. All-caps is reserved for short technical mono
  labels only.
- Implemented CSS keeps letter spacing at `0`. Font size MUST NOT scale with
  viewport width.
- Large display type is reserved for a true product header; workspace screens
  use practical panel headings.
- Time and source metadata use compact mono labels with explicit UTC or local
  basis labels.

## Color, legends, and states

- Keep the palette sparse: ink, gray, link blue, positive green, warning amber,
  error red, and domain map colors only where data semantics require them.
- State color MUST NOT be the only signal. Every colored badge or row also
  needs a text label, icon, pattern, or title.
- Standard state vocabulary and tones:
  - `ready` / positive;
  - `partial` / warning;
  - `blocked` / critical;
  - `stale` / warning;
  - `unavailable` / critical;
  - `restricted` or entitlement-missing / warning or critical depending on
    fail-closed impact.
- Map legends MUST distinguish verified geometry from indicative corridors and
  simulated from live or licensed data.
- UI status classes preserve the existing contract names (`source-status`,
  `runtime-readiness-state`, `pipeline-status`, and the workspace tab classes)
  so contract tests and CSS remain stable.

## Controls

- Use familiar controls: tabs for task views, segmented controls for map modes,
  switches/checkboxes for layer toggles, menus for option sets, tables for
  comparisons, and badges for source, entitlement, freshness, and runtime state.
- New or touched workspace task tabs MUST implement `tablist` / `tab` /
  `tabpanel` semantics with `aria-selected`, `aria-controls`, and
  Arrow/Home/End keyboard movement. Use the shared `WorkspaceTabs` primitive.
- New or touched panel title/status pairs MUST use `PanelHeader`; statuses MUST
  use `StatusBadge`; compact KPI rows MUST use `MetricStrip`. Existing screens
  are migrated incrementally, not through a broad rewrite.
- Every icon-only control MUST have an accessible label or tooltip.
- Text MUST NOT overflow buttons, cards, rails, or result rows.

## Responsive behavior

- The shared topbar uses deterministic responsive grid areas.
- Workspace tabs MAY scroll horizontally on narrow widths; the active tab and
  focus state MUST remain visible.
- On small screens navigation, runtime status, warnings, and the primary action
  MUST stay reachable without horizontal page scroll.
- Tables SHOULD wrap or scroll locally rather than forcing page-level overflow.
- MapLibre controls, attribution, layer chips, and rails MUST NOT overlap.

## Required screen states

Every screen MUST design for:

- loading;
- empty;
- degraded backend;
- DB unavailable;
- missing inputs;
- stale data;
- restricted data;
- partial feature;
- error with safe details;
- research-only / human-review-required output.

The application MUST NOT hide missing live data behind fabricated client
values. If preview or simulated rows are used, their provenance MUST be visible
on the row or in the immediately adjacent panel.

## Provenance, units, and time basis

- Every market, physical, optimization, strategy, or report value MUST be
  traceable to its source system and source reference through API-provided
  lineage.
- Values MUST display currency and unit (`GBP`, `EUR`, `MWh`, `mcm/d`, and so
  on). Do not mix currencies in one calculation display.
- Time values MUST show their basis (`UTC`, local, or gas-day) and the
  observation time when relevant. Gas-day boundaries follow the CAM calendar
  (05:00 CET/CEST) through backend-owned logic.
- PnL is indicative unless the API says otherwise; label `indicative PnL`
  rather than `PnL` when provenance is snapshot or model-derived.
- Source rows MUST distinguish live, delayed, preview, simulated, stale,
  unavailable, partial, access-not-configured, and unsupported states.

## Human-review boundaries

Decision-support output MUST remain a candidate for human review. Use:

- `candidate`;
- `scenario`;
- `assumption`;
- `warning`;
- `missing input`;
- `human review required`;
- `research only` where the legacy envelope requires it;
- `indicative`.

MUST NOT use in UI labels or copy:

- `trade signal`;
- `execute`, `place order`, `route order`;
- `order`, `amend`, `cancel` as actions;
- `approve trade`;
- `official recommendation`;
- `auto-trade`;
- `submit nomination`.

Strategy copy uses paper/shadow-run monitoring language; charts MUST be derived
from persisted PostgreSQL runs and MUST show an empty state when history is
absent. Illustrative performance curves are prohibited.

## English and Mandarin parity

- All user-visible Web and Windows strings MUST be available in English
  (`en-US`) and Mandarin Chinese (`zh-CN`) through the i18n resources.
- EN and CN text MUST describe the same state, action, and boundary. One
  language MUST NOT add an execution or recommendation meaning that the other
  lacks.
- `docs/clients/UI_UX_STYLE_GUIDE-EN.md` and
  `docs/clients/UI_UX_STYLE_GUIDE-CN.md` MUST be updated together.
- Contract tests that sample paired keys in `clients/web/src/i18n/en.json` and
  `zh.json` remain the enforcement baseline.

## Accessibility

- Do not rely on color alone for warnings or state.
- Keyboard focus MUST be visible on every interactive control.
- Tables, tabs, and map controls MUST be reachable by keyboard.
- Icon-only controls MUST have accessible names.
- Semantic list and heading structure SHOULD be preserved when converting
  decorative markup into shared primitives.

## Implementation boundaries

- Shared primitives live under `clients/web/src/components/ui`. A new primitive
  MAY be added only when it removes real duplication in more than one active
  workspace.
- Workspace components own domain rendering and state; primitives own markup
  and keyboard contracts only.
- No UI framework or new runtime dependency MAY be added for styling.
- Global CSS changes require a focused UI review and MUST avoid Strategy WIP
  selectors.

## References

- [Client documentation index](README.md)
- [Client tech stack](CLIENT_TECH_STACK.md)
- [Client i18n and theme](CLIENT_I18N_THEME_SPEC.md)
- [Workspace navigation](WORKSPACE_NAVIGATION_SPEC.md)
- [Web application architecture EN](WEB_APPLICATION_ARCHITECTURE-EN.md) /
  [CN](WEB_APPLICATION_ARCHITECTURE-CN.md)
- [UI/UX style guide EN](UI_UX_STYLE_GUIDE-EN.md) /
  [CN](UI_UX_STYLE_GUIDE-CN.md)
- [Map-first decision cockpit spec EN](MAP_FIRST_TRADER_COCKPIT_SPEC-EN.md) /
  [CN](MAP_FIRST_TRADER_COCKPIT_SPEC-CN.md)
