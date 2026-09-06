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

1. Global shell, compact trader context strip, and runtime status stay visible
   and persistent.
2. Persistent primary workspace navigation identifies the active professional
   workspace; only five primary workspaces are exposed globally.
3. The workspace page header identifies the active local task and primary
   workspace; local task tabs use the shared `WorkspaceTabs` primitive when the
   primary owns more than one view.
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
  observation time when relevant. Gas-day boundaries follow CAM Article 3(16)
  through backend-owned logic using the corrected versioned calendar
  `EU-CAM-UTC-2025` (05:00 UTC winter / 04:00 UTC DST). The legacy
  `EU-CAM-2025` calendar is frozen for reproducibility and must not be used
  for new data.
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


## Evidence-led UI refactor preparation (2026-09-06)

Status: audit evidence collected; visual acceptance is pending human review of
the local gallery. DOM/source findings below are implementation facts. Image
appearance, overlap aesthetics, and spacing quality are not claimed from DOM
metrics or image dimensions.

Evidence:

- Local gallery: `output/ui-audit-2026-09-06/gallery.html` served at
  `http://127.0.0.1:4173/gallery.html` during review.
- Capture manifest: `output/ui-audit-2026-09-06/capture-manifest.json`.
- DOM audit: `output/ui-audit-2026-09-06/audit-dom.json` and
  `audit-tabs.json`.
- Screenshots: `output/ui-audit-2026-09-06/*.png`, 1440x900 desktop and
  390x844 mobile web sizes, captured through the Vite dev server against the
  running `/api` and PostgreSQL instance. These are web-browser screenshots,
  not native desktop acceptance.

Page inventory covered: Network, Scenario, Review, Resource Terms, Market,
Capacity, Market Positioning, Strategy, Glossary, Data Sources, Runtime,
Settings, Manual. Internal tabs captured for Resource Terms, Capacity,
Strategy, Data Sources, and Runtime.

DOM/source findings (not visual acceptance):

1. Browser dev-server hydration remains in `LOADING WORKSPACE` on Network and
   Strategy for at least 15 seconds, even though `/api/sources`,
   `/api/strategy-lab/runs`, and `/api/strategy-lab/summary` return data
   directly. Strategy DOM consequently showed zero runs and all price bases
   unavailable during capture; the production desktop executable does render
   the two persisted runs. This needs root-cause separation before refactor.
2. Strategy duplicate performance presentation: `StrategyPerformancePanel` is
   mounted in both Monitor and Run History (`components/StrategyShadowRunTerminal.tsx`),
   and Run History also renders a cumulative-performance metric panel below
   the same chart. Reviewer-reported repetition is source-verified.
3. Strategy PnL chart has no axis labels or value scale: the SVG contains only
   grid lines, a zero line, and a polyline (`StrategyShadowRunSections.tsx`).
   `svgAxisText` count is 0 in DOM audit. Reviewer-reported missing axes is
   source-verified.
4. Strategy price context is derived from the current `strategyResult` or the
   latest persisted run, but the observed browser session rendered unavailable
   flags for all seven bases and `n/a` price basis metrics. This is either a
   hydration defect or a real stale-context defect; do not restyle before
   confirming which.
5. Mobile DOM overflow/overlap candidates: workspace page tabs overflow on
   Resource Terms, Market, Capacity, and Market Positioning; data-table rows
   exceed the 390px viewport on Review, Capacity, Market, and Market
   Positioning; Source posture/task controls and Strategy task controls
   extend past the viewport. These are DOM geometry flags, not visual
   acceptance.
6. Reusable primitives remain partially adopted: Source Center and Runtime use
   `WorkspaceTabs`, but Strategy, Capacity, and Resource Terms still have
   local tab markup; panel headers and metric/status rows still mix
   `.panel-title-row`, `.section-heading`, `.metric-grid`, and page-specific
   variants.
7. Labels and units are inconsistent at presentation boundaries: some values
   carry `GBP/MWh`, `MWh/d`, or `TWh`, while strategy monitor averages and
   allocation reference columns omit units; source freshness labels mix local
   and UTC semantics. These are source/DOM observations awaiting visual and
   content review.

Ordered refactor plan:

1. Stabilize workspace hydration and loading completion; make failed/slow
   endpoints observable per endpoint without leaving whole-workspace loading
   state stuck.
2. Strategy consolidation: one performance panel owner, axis/time/value labels,
   persisted-run price basis context, and a clear empty/stale/simulated state.
3. Mobile containment: page tabs, task tabs, tables, and command decks must
   scroll locally without page overflow.
4. Primitive convergence: migrate remaining local tabs, panel headers, metric
   strips, and status badges onto the shared UI primitives; keep existing CSS
   class contracts until migration tests pass.
5. Content/label pass: units on every market/physical/PnL value, UTC/local
   basis, provenance, simulated/stale/unavailable chips, verified-versus-
   indicative map legend.
6. Accessibility pass: keyboard focus, semantic tabs, color-plus-text states,
   and readable chart axes.
7. Visual regression baseline: re-capture the gallery only after implementation
   changes, not before.

Operational-screen brief for GPT Image 2 references:

Advanced, minimal, restrained, professional gas-trader workspace; dense and
readable; clear hierarchy and legends; shared tokens/components; no overlapping
text, decorative nested cards, or marketing composition. Show a strategy
operational screen with: global status and source freshness strip; compact
strategy identity marked PAPER and no execution; Monitor/Economics/Risk &
Evidence/Run History tabs; a price-basis board with units, source systems, and
simulated/stale/unavailable chips; an allocation ladder and risk stack; a PnL
curve with visible axes, units, time basis, and empty-state behavior; and a
run-history table with provenance and human-review flags. Use restrained ink,
gray, link blue, positive/warning/critical state colors, hairline borders,
8px surfaces, mono labels, and no heavy shadows or gradients.


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
