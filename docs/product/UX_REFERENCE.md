# UX Reference — Product Shell

Status: conceptual reference. GPT Image Gen 2 was not available in this run, so
no generated raster reference is attached. Accepted visual principles below
come from the product brief and the repository UI standard.

## Accepted visual concept for the workstation shell

- Five primary workspace tabs in the persistent topbar; active tab is the only
  strong emphasis.
- A compact active local-task chip for the map-first Network view.
- Persistent gas day, delivery product, source freshness, streaming state, and
  runtime status remain in the topbar context strip.
- Non-map workspaces use one compact identity band: primary eyebrow + local task
  title + local task tabs only when the primary owns more than one view.
- No sidebar + group tabs + page tabs + nested tabs at the same time.
- Dense institutional styling: 8px spacing, hairline borders, system fonts,
  tabular numerals, no gradients, no oversized cards, no consumer dashboard.

## Reference targets

- 1920x1080 and dense 1440x900 desktop layouts; 2560x1440 remains readable.
- Market workspace active with Network/Market/Capacity local tasks.
- Strategy Lab and Decision Center follow the same shell rather than bespoke
  navigation.

## Implementation note

No rasterized screenshots are shipped as application UI. The accepted concept is
implemented with real React/CSS components only.
