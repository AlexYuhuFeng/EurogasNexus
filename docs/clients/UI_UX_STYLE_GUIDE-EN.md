# UI/UX Style Guide

Eurogas Nexus Web and Windows client UI must follow the local reference guide supplied at `C:\Users\qqshu\design.md`, interpreted for a professional map-first gas trading decision-support cockpit.

## Non-Negotiable Visual Rules

- Use a Vercel-inspired near-white canvas: `#fafafa` page background, `#ffffff` panels, `#f5f5f5` inset surfaces.
- Use ink black `#171717` for primary text and primary actions.
- Use hairline borders `#ebebeb`; avoid heavy shadows. Elevation is stacked small shadows plus inset hairline.
- Use Inter/system sans for UI text and ui-monospace for technical eyebrows, source tags, and compact labels.
- Use sentence-case headings. Do not use all-caps headings except short technical mono labels.
- Keep card radius at 8px for app surfaces. Pill controls may use full radius.
- Keep the palette sparse: ink, gray, link blue, warning amber, error red, and domain map colors only where data semantics require them.
- Do not use decorative blobs, stock imagery, or miniaturized gradients.
- Do not use negative letter spacing in implemented CSS, even if the visual reference includes it; this repository keeps letter spacing at `0` for renderer consistency.

## Eurogas Cockpit Adaptation

- The map remains the dominant work surface.
- The top bar is a clean product/search/control bar, not a marketing hero.
- The home left rail is the resource-pool intake: active portfolio resources,
  route controls, and missing-contract blockers.
- The home right rail is the decision inspector only: net PnL, route allocation
  ladder, economics snapshot, and strategy/warning signal.
- Data-source diagnostics, runtime DB health, TSO access tables, capacity
  summaries, tariff tables, credentials, glossary, and AI reports live on their
  own pages. Do not add them back to the home rails.
- The workspace pill plus hamburger glyph is the single navigation trigger on
  the map. Do not reintroduce a duplicate horizontal nav on the home screen.
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
- `workspace-menu`
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

The 2026-08-31 Image Gen 2 market-workspace direction is stored at
`docs/design/references/market-workspace-imagegen-2026-08-31.png`. It is a
design reference, not market data or a source of functional requirements.

The 2026-08-31 Strategy workspace reference is stored at
`docs/design/references/strategy-workspace-imagegen-2026-08-31.png`. Its chart
and values are illustrative design material; production charts use strategy
runs persisted in PostgreSQL only.

The 2026-09-01 Operations workspace reference is stored at
`docs/design/references/operations-source-center-imagegen-2026-09-01.png`.
Its source names, counts, states, and values are illustrative design material;
production posture is read from PostgreSQL-backed APIs only.

Future client work must update this guide before changing the UI language or layout model.
