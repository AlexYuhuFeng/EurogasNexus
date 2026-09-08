# UI/UX Style Guide - EN

> Bilingual implementation companion to the draft
> [`PROFESSIONAL_UI_CONSTITUTION.md`](PROFESSIONAL_UI_CONSTITUTION.md). Until
> the UX01 RFC is accepted, [`UI_CONTENT_STANDARDS.md`](UI_CONTENT_STANDARDS.md)
> remains transitional authority. On RFC acceptance, the Constitution is the
> sole visual authority and [`MOTION_SYSTEM.md`](MOTION_SYSTEM.md) is
> subordinate; this file has no independent authority.

Eurogas Nexus Web and Windows client UI follows a professional European energy
analytical workstation direction, with a map-first Network workspace.

## Non-Negotiable Visual Rules

- Treat the current neutral palette as a migration reference: `#fafafa` page
  background, `#ffffff` panels, `#f5f5f5` inset surfaces, `#171717` ink, and
  `#ebebeb` hairlines. Implemented feature CSS MUST use semantic tokens rather
  than scattered raw colors.
- Avoid decorative and heavy shadows. Use semantic surfaces and borders rather
  than ornamental elevation.
- Use Inter/system sans for UI text and ui-monospace for technical eyebrows, source tags, and compact labels.
- Use sentence-case headings. Do not use all-caps headings except short technical mono labels.
- The draft Constitution proposes fixed type `11/12/13/14/18/20px`, spacing
  `4/8/12/16/24/32px`, controls `28/32/36px`, and radii `4/6/8px`.
- Do not use decorative pills, giant workspace titles, or arbitrary local type,
  spacing, control, or radius values on RFC adoption.
- Keep the palette sparse: ink, gray, link blue, warning amber, error red, and domain map colors only where data semantics require them.
- Do not use decorative blobs, stock imagery, or miniaturized gradients.
- Do not use negative letter spacing in implemented CSS, even if the visual reference includes it; this repository keeps letter spacing at `0` for renderer consistency.

## Eurogas Cockpit Adaptation

- The Network workspace is map-first. Market quotes, Strategy, and other
  analytical workspaces use the primary table, chart, editor, or report
  surface appropriate to the task.
- The top bar is a clean product/search/control bar, not a marketing hero.
- The home left rail is the resource-pool intake: active portfolio resources,
  route controls, and missing-contract blockers.
- The home right rail is the decision inspector only: net PnL, route allocation
  ladder, economics snapshot, and strategy/warning signal.
- Data-source diagnostics, runtime DB health, TSO access tables, capacity
  summaries, tariff tables, credentials, glossary, and AI reports live on their
  own pages. Do not add them back to the home rails.
- The shared shell owns the five primary workspaces; do not add a competing
  navigation model or decorative pill trigger. Map-local controls remain local.
- The shared shell owns gas day, delivery product, Portfolio where applicable,
  primary market context, and runtime/data status. Do not duplicate global
  context selectors inside pages.
- The map asset search is rendered only in the Network workspace. A control
  must not remain visible on pages where it has no effect.
- Non-map workspaces use a compact, unframed page identity band with local tabs
  for sibling pages in the same workflow group. Runtime state remains in the
  global top bar and is not repeated in a decorative title card.
- Mount only the active workspace surface. Hidden map canvases, overlays, and
  focus targets must not remain active behind non-network pages.
- Strategy uses a persistent governed-paper command strip and exactly four
  task views: Monitor, Economics, Risk & Evidence, and Run History. Cumulative
  PnL charts must be derived from persisted runs and show an empty state when
  history is absent; illustrative performance curves are prohibited.
- Data Sources uses exactly four task views: Attention, Catalog, Access &
  certification, and Infrastructure. Runtime uses Readiness, Delivery, and
  Governance. Only the active view is mounted; compact readiness context stays
  visible, and remediation actions navigate to the owning workspace.
- MapLibre controls, attribution, layer chips, and rails must never overlap.
- AI/LLM features must appear as decision-support analysis and report generation, never as autonomous execution.
- All visible strings must be available in English and Mandarin Chinese.

## Implementation Contract

Current Web implementation should expose these structural classes so contract tests can prevent regression:

- `cockpit-topbar`
- `workspace-primary-tabs`
- `scenario-rail`
- `decision-rail`
- `trade-result-panel`
- `topbar-search`
- `workspace-page-tabs`
- `workspace-topbar-page`
- `strategy-command-deck`
- `strategy-view-tabs`
- `strategy-performance-chart`
- `source-view-tabs`
- `source-readiness-strip`
- `runtime-view-tabs`
- `runtime-operations-strip`

Future client work must update `UI_CONTENT_STANDARDS.md` first, then this companion and its CN counterpart together.
