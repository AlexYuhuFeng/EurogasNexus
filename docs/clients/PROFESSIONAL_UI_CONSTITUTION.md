# Professional UI Constitution

Status: **Accepted binding contract - RFC-0001 adopted 2026-09-08; implementation acceptance pending**

This contract is not implemented-compliance evidence. RFC-0001 was accepted and
authority was reconciled on 2026-09-08. This Constitution is the sole visual
and interaction authority; `MOTION_SYSTEM.md` is its subordinate motion
specification. `UI_CONTENT_STANDARDS.md` continues to own content, domain,
time-basis, provenance, entitlement, no-execution, and client-boundary rules.

## Contract basis

The contract is based on the UX01 brief, `docs/ux/POST_CR15_UI_AUDIT.md`, and
`docs/ux/COMPONENT_CENSUS.md` at the audited baseline. Those documents record
runtime findings, source counts, and open validation work; this contract does not
turn those observations into claims that the current UI complies.

Accepted contract decisions:

- fixed type, spacing, control, radius, and motion values below;
- canonical primitive ownership and migration order;
- required CR-14 dataset detail/artifact and CR-15 full governed review/replay
  workflows within existing backend capabilities;
- Constitution sole visual authority on RFC acceptance, with Motion subordinate.

The required CR-14 and CR-15 workflows MUST be met within existing backend
capabilities and API contracts. UX01 MAY reorganize or expose existing
catalog/detail/build/validate/quality/export, plan/findings/StrategyIR/
challenge/review-pack, confirmation, and replay surfaces, but MUST NOT invent
new domain models, analytics, agent capabilities, or execution semantics.

## 1. Product visual character

Eurogas Nexus SHOULD read as a professional, dense, analytical European gas
decision-support workstation. Information hierarchy, readability, consistency,
speed, provenance, predictable controls, precise state communication, and
restrained motion take priority over novelty or decoration.

It is not a consumer dashboard, marketing page, card-heavy BI template,
futuristic AI demo, Bloomberg imitation, or mobile-first product. CR1-15
capabilities remain feature-frozen during UX01.

## 2. Information hierarchy

Use this order unless a map or domain surface has a documented specialist need:

1. shell, global context, and runtime/data status;
2. primary workspace and local task identity;
3. workspace primary action and affected-surface filters;
4. primary analytical surface;
5. context, evidence, warnings, and human-review boundary;
6. secondary and lifecycle actions.

Warnings, missing inputs, freshness, entitlement, and human-review boundaries
MUST appear next to the affected result, not only in a hidden overlay or tab.
The Network workspace is map-first and may keep the map dominant; Market
quotes, Strategy, and other non-map analytical workspaces SHOULD use the
primary table, chart, editor, or report surface appropriate to the task and a
compact page identity band.

## 3. Typography

Use fixed tokens only. Proposed values:

| Token | Value | Use |
| --- | ---: | --- |
| `--text-meta` | 11px | compact metadata, timestamps, source tags |
| `--text-body` | 12px | dense analytical body text |
| `--text-control` | 13px | controls, table cells, helper text |
| `--text-panel-title` | 14px | panel and section headings |
| `--text-workspace-title` | 18px | workspace identity |
| `--text-page-title` | 20px | rare major page/title use only |

The fixed scale is exactly 11/12/13/14/18/20px. Existing 10/10.5/11.5,
12.5/15/16/17/22/24/32px values are migration inventory, not contract tokens.
Feature-local exceptions require planner review. Use the existing system
UI font stack and `ui-monospace` for technical labels. Letter spacing is `0`;
font size MUST NOT scale with viewport width.

## 4. Spacing

Use the 4px token scale: `--space-1: 4px`, `--space-2: 8px`,
`--space-3: 12px`, `--space-4: 16px`, `--space-5: 24px`, and
`--space-6: 32px`.

Recurring gaps, padding, stack spacing, and section spacing MUST use these
tokens. Do not mass-replace existing values without visual review; preserve a
specialist value only when its geometry or domain semantics are documented.

## 5. Density

Optimize for scanning at 1440x900 first and 1920x1080 second. Prefer compact
rows, stable columns, explicit units, and one clear emphasis level per row.
Whitespace MUST support grouping or readability; it MUST NOT be used to make a
small amount of content look like a marketing hero.

## 6. Panel and container rules

Prefer unframed structural rows, rails, tables, and compact panels. Do not put
cards inside cards. Proposed ordinary radii are exactly 4/6/8px:

- `--radius-control: 4px`;
- `--radius-panel: 6px`;
- `--radius-large: 8px` maximum for ordinary analytical containers.

Use hairline borders and semantic surface/border tokens. Heavy shadows,
decorative gradients, glass effects, orbs, blobs, and ornamental imagery are
prohibited. A specialist visualization MAY use domain colors or geometry when
they carry data meaning.

## 7. Control sizing

Use exactly three normal control heights:

- `--control-compact: 28px`;
- `--control-standard: 32px`;
- `--control-prominent: 36px`.

Controls MUST have stable dimensions and visible focus. Trading workspace
controls SHOULD use compact or standard sizing. Text MUST fit its control at
both English and Mandarin lengths. Icon-only controls require an accessible
name and a tooltip only when the icon is not self-evident.

## 8. Navigation

Expose the existing five primary workspaces globally. Keep technical page IDs
and deep-link compatibility while migrating presentation. Use
`WorkspaceTabs` for task navigation and preserve its tablist/tab/tabpanel,
selection, focus, and Arrow/Home/End behavior.

The shell MUST own global navigation. A workspace owns only its local tasks;
feature components MUST NOT introduce a competing top-level navigation model.

## 9. Action placement

- Global context has one owner in the shared shell/context region: gas day,
  delivery product, Portfolio where applicable, primary market context where
  applicable, and runtime/data status. Do not duplicate global selectors inside
  pages.
- The workspace primary action belongs in the upper-right of the
  `WorkspaceHeader`.
- Filters belong immediately above the surface they modify.
- Row actions belong in the row or its context action region.
- Destructive and lifecycle actions belong in a grouped overflow menu or
  secondary region, not beside routine primary actions.

One command surface SHOULD contain one primary action, zero to three visible
secondary actions, and an overflow menu where additional actions are needed.

## 10. Tables

Propose one canonical `DataTable` with dense, semantic, selectable, and local
scroll variants. It MUST define stable row/header heights, loading/empty/error/
restricted/stale states, sorting/filtering/selection contracts where used,
row actions, and explicit units/time basis.

Text is left-aligned; numeric values are right-aligned; status has consistent
text-plus-tone treatment. Numerical cells SHOULD not wrap. Tables and charts
should use analytical width and local scrolling rather than page overflow.

## 11. Charts

Charts MUST answer a trader question and use persisted/API-provided data. They
MUST provide title, legend, axes, units, time basis, readable time labels,
comparison colors, zero-line semantics where relevant, and loading/missing/
stale/restricted states.

Do not use illustrative curves, decorative charts, unnecessary gradients, or
large chart titles. PnL and model-derived values MUST be labelled `indicative`
unless the API explicitly establishes another status.

## 12. Forms

Use a canonical `FormSection` contract for labels, helper text, errors, required
indication, units, field spacing, and logical grouping. Ordinary fields SHOULD
be 240-420px wide according to content, with `min-width: 0` so they can shrink
inside a constrained grid. They MUST NOT span an entire workspace by default.

Use native semantics for text, number, date, select, checkbox, and file fields.
Numeric fields and values use right alignment where comparison or data entry
benefits from it. Preserve existing API values, domain validation, i18n keys,
and file/date/number behavior; this document introduces no domain rules.

## 13. Menus and toolbars

Menus are for option sets and grouped secondary/lifecycle actions, not a
dumping ground. A menu with more than about seven peer items SHOULD be grouped
or moved to the correct workspace surface.

Toolbars MUST preserve action geography and hierarchy. Use familiar controls:
tabs for tasks, segmented controls for modes, checkboxes/switches for binary
layers, menus for option sets, tables for comparisons, and badges for state.

## 14. Overlays

Use an overlay only when the interaction requires temporary focus or an
anchored contextual surface. Proposed shared behavior:

- `Tooltip` for non-obvious icon or abbreviation help only;
- `Popover` for small non-modal contextual information when required;
- `Drawer` for inspect/monitor content with focus return and Escape;
- `Modal` for blocking confirmation or form workflows only;
- `Menu` for command grouping with keyboard navigation and focus return.

Do not use an overlay to hide warnings, provenance, restricted state, or a
required action. No new overlay dependency is proposed.

## 15. Status semantics

Use one semantic vocabulary across Market, Portfolio, Strategy, Sources,
Research Data, and Agent workflows. Keep freshness and operational state
distinct:

- freshness: `Fresh`, `Late`, `Stale`, `Missing`;
- operational/access: `Ready`, `Unavailable`, `Restricted`, `Partial`,
  `Unknown`, `Blocked`, `Degraded`;
- review/boundary: `Research-only`, `Human review required`.

`Ready` describes operational availability; it MUST NOT replace or imply
`Fresh`. A source MAY be `Ready` and `Late`. `Unavailable` describes whether a
surface can be served; it MUST NOT collapse a separately known freshness state.

Status color MUST never be the only signal. Use visible text and, where useful,
an icon, pattern, or title. Preserve existing status class/API contracts during
migration. Do not invent synonymous labels per screen.

## 16. Evidence and provenance

Every market, physical, optimization, strategy, research, agent, or report value
MUST expose API-provided source/reference lineage, freshness, time basis, unit,
currency, and entitlement/restriction state where applicable.

Use `EvidenceBlock` as the proposed shared structure with source, reference,
freshness, time basis, and human-review slots. Preserve specialist evidence
content in Review, Capacity, Intraday, Resource Path, Contract, Strategy, and
Source surfaces.

The UI MUST distinguish `verified` geometry/evidence from `indicative`
corridors, model-derived PnL, previews, and assumptions. Map legends MUST
distinguish verified geometry from indicative corridors and live/licensed data
from simulated data. Do not fabricate missing live data.

## 17. Loading, empty, error, and degraded states

Propose canonical `LoadingState`, `EmptyState`, and `ErrorState` contracts with
stable dimensions. Every surface MUST design for loading, empty, degraded
backend, DB unavailable, missing inputs, stale data, restricted data, partial
feature, structured error/retry, and research-only or human-review-required
output.

- Loading reserves space and avoids layout shift.
- Empty explains why it is empty and the next valid action, if any.
- Error states identify the failed scope, preserve unaffected content, and
  expose retry only when retry is valid.
- Stale states show data age and impact.
- Restricted states explain the limitation without revealing protected content.

## 18. Motion

Motion follows the subordinate `MOTION_SYSTEM.md`. The fixed subordinate scale is
0/120/180/240ms,
using transform/opacity for transient movement and stable layout for data
surfaces. Frequently updating prices MUST NOT flash, bounce, or animate on each
tick.

## 19. Accessibility

All interactive controls MUST have keyboard access, visible focus, a stable
accessible name, and a semantic role. Tabs use the shared keyboard contract.
Tables, map controls, rails, menus, drawers, and modals MUST be reachable and
operable by keyboard; focus must move into temporary surfaces and return to the
invoker.

Do not rely on color alone. Preserve heading/list structure, label fields,
provide text alternatives for status, and respect reduced motion. Accessibility
acceptance requires runtime checks; this contract does not claim they pass.

## 20. Responsive behavior

The shell MUST use structural rows whose measured height pushes content below
them. A fixed topbar MUST NOT overlap analytical content, controls, warnings, or
rails. Global context and runtime status may occupy separate shell rows.

Workspace content uses `min-width: 0`, local table/tab scrolling, and stable
rail containment. The primary analytical surface gets remaining width. Validate
1440x900 and 1920x1080, plus the supported narrow desktop viewport. MapLibre
controls, attribution, layer controls, and rails MUST NOT overlap.

## 21. English and Mandarin behavior

Every user-visible string MUST exist in `en-US` and `zh-CN` and communicate the
same state, action, unit, time basis, and human-review boundary. Layouts MUST
survive longer Mandarin labels without clipping, hierarchy changes, or hidden
actions. EN/CN changes are paired; no language may add execution or
recommendation meaning.

## 22. Prohibited patterns and implementation boundary

Prohibited without an approved exception: marketing hero composition, giant
titles, decorative pills, nested cards, heavy shadows, gradients/glass effects,
random font sizes or spacing, page-level overflow, equal-weight toolbar
overload, color-only status, illustrative performance curves, rapid price
flashes, mystery icons, hidden provenance, fabricated data, and execution
language.

The no-execution boundary remains explicit: outputs are candidates, scenarios,
assumptions, warnings, indicative values, research-only results, or human-review
items. This proposal does not add order entry, nomination, approval, trade
execution, new analytics, new domain semantics, or a new top-level workspace.

## Canonical primitives and token ownership

The existing shared `WorkspaceTabs`, `PanelHeader`, `MetricStrip`, and
`StatusBadge` are canonical primitives for migration. Add only the necessary shared
contracts identified by the census: `DataTable`, `FormSection`,
`LoadingState`, `EmptyState`, `ErrorState`, `EvidenceBlock`, `SplitWorkspace`,
`ContextRail`, `Toolbar`, and narrowly justified menu/overlay primitives.

Shared primitives own markup, tokens, keyboard, focus, and state contracts;
workspace components own domain rendering and state. The census migration order
is proposed: existing primitives, controls/forms, tables/states, evidence/layout,
then menus/overlays.

Consolidate the existing `--bg`/`--surface` and `--eg-*` token families into
one semantic token family. Do not create a third token system or add a UI
framework/new runtime dependency. Preserve class/API contracts while migrating
and remove legacy aliases only after focused tests and visual review.

## Binding adoption and compliance evidence

RFC approval plus authority reconciliation makes this contract binding. The
following evidence is required afterward to prove implementation compliance; it
is not a prerequisite for binding the contract:

1. token/class inventory and migration plan;
2. runtime review of normal, degraded, loading, restricted, and empty states;
3. 1440x900 and 1920x1080 screenshots with no shell overlap or page overflow;
4. EN/CN representative workflows;
5. keyboard/focus and reduced-motion checks;
6. provenance, verified/indicative, and no-execution copy review;
7. contract, Web test, build, visual, and accessibility results recorded
   separately from source implementation claims.

Implementation acceptance remains pending. Binding adoption does not assert
that the product already complies; screenshots, runtime review, tests,
accessibility checks, and visual evidence remain separate unchecked gates.
