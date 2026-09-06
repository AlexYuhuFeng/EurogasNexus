# UX Reference — Product Shell

Status: conceptual reference. GPT Image Gen 2 was not available in this run, so
no generated raster reference is attached. Accepted visual principles below
come from the product brief, public professional-workstation research, and the
repository UI standard.

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

## CR-05 Strategy Lab references

Accepted principles from the CR-05 research pass:

- three-zone research workstation: narrow navigator, primary evidence/result
  surface, contextual provenance rail;
- workflow as local tabs, never four global pages;
- result hierarchy: identity/provenance -> KPI strip -> time series ->
  drawdown/exposure -> attribution -> decision-event table;
- comparison is a matrix/table-first workflow with synchronized series and
  visible compatibility caveats, not a chart wall;
- charts are thin, muted, unit-labelled and break on missing data; they never
  create a smooth illustrative curve;
- dense 8px grid, hairline borders, tabular numerals, 12–13px body text, no
  marketing cards or gradients;
- persistent identity/version/context header in every task.

Sources reviewed include Trayport Joule public material, institutional
portfolio analytics patterns, and strategy experiment-tracking literature;
no proprietary design was copied.

## CR-07 Market cockpit references

GPT Image Gen 2 was not available in this run. Accepted direction from public
commodity-terminal and ENTSOG/GIE research:

- overview first: hub board + map + physical/route rail + bottom spread strip;
- hub selection is the shared anchor; panels react, not duplicate controls;
- capacity tables keep technical/booked/available separate with timestamp;
- map layers are grouped and decision-relevant, with verified vs indicative
  geometry legend;
- degraded state is partial, never a blank cockpit.

## Implementation note

No rasterized screenshots are shipped as application UI. The accepted concept is
implemented with real React/CSS components only.
