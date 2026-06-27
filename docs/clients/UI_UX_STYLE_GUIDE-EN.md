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
- The left rail is the scenario builder: active resource, destination, route, execution mode, and tariff posture.
- The right rail is the result inspector: net PnL, route alpha, economics snapshot, source posture, strategy, glossary, and AI report context.
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

Future client work must update this guide before changing the UI language or layout model.
