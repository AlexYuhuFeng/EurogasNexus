# Workspace Layout Standard

**Status: proposed implementation contract.** This document records the reviewed layout direction; it is not an implementation or compliance claim. The current authority remains [`UI_CONTENT_STANDARDS.md`](../clients/UI_CONTENT_STANDARDS.md) until the planner resolves the proposal against the reviewed Constitution, Motion, census, and audit.

## Scope and fixed decisions

This contract covers shell geometry, workspace identity, context ownership, responsive constraints, state placement, and primitive ownership. It does not introduce a UI framework, a new domain model, a new backend capability, or new execution semantics.

The fixed decisions are:

- Use structural shell rows in normal document flow. Do not use fixed overlays for the top bar, global context, or endpoint/degraded banners.
- Preserve the existing five primary workspace IDs and their URL/deep-link behavior: `market`, `portfolio`, `strategy`, `decision`, and `system`.
- Keep one global context owner in the shell. Workspace filters remain local to the surface they modify.
- Put the workspace primary action in the upper-right of the workspace header.
- Right-align numeric values; keep units and time basis visible.
- Do not place cards inside cards or turn whole page sections into nested card stacks.
- Use `1440x900` as the primary review viewport and `1920x1080` as the secondary viewport.
- Treat rail and form dimensions as responsive constraints, not mandatory fixed widths: context rails `280–360px`, entity navigators `220–300px`, and form controls `240–420px` where the content warrants them.

These constraints are intended to preserve the existing product surfaces and deep links, not to create another navigation or layout system.

## Shell contract

The proposed row order is:

1. Global primary navigation and workspace identity.
2. Global context and data/status controls.
3. A bounded endpoint or degraded-state row when needed.
4. The workspace content region.

Every row participates in normal layout measurement. The content region starts below the measured shell height; it must not be hidden beneath a fixed top bar or banner. A local specialist surface may scroll or use a sticky control only when its bounds remain inside the workspace and it cannot cover unrelated content.

The current source owners are [`AppShell`](../../clients/web/src/app/shell/AppShell.tsx) and [`WorkspaceTopBar`](../../clients/web/src/components/WorkspaceTopBar.tsx). [`WorkspaceRenderer`](../../clients/web/src/app/workspaces/WorkspaceRenderer.tsx) owns workspace-page identity and local task-tab placement. The contract keeps those ownership boundaries; it does not require a new shell runtime.

## Navigation and context

The five existing primary IDs and their technical page IDs are preserved by [`productNavigation.ts`](../../clients/web/src/app/navigation/productNavigation.ts) and [`workspaceNavigation.ts`](../../clients/web/src/workspaceNavigation.ts). New visual grouping must not rename, remove, or repurpose those IDs.

Global gas day, product, hub, language, theme, data status, and session/source status have one shell owner. A workspace may display the resulting value as read-only evidence, but must not add a competing global selector. Filters, view modes, dataset/task selectors, and surface-specific scope controls belong immediately above the surface they modify.

## Geometry and surfaces

- The main analytic surface receives the remaining width after local rails and gutters and may shrink to `min-width: 0`.
- A rail or entity navigator is optional and local to the workspace. Use responsive `min/max` constraints in the ranges above; do not require a fixed width at every viewport.
- Forms use bounded fields in the `240–420px` range when a field is not intrinsically full-width. Long evidence, notes, and query text may use the available surface width.
- Page sections are structural bands or unframed layouts. Cards are reserved for repeated items, bounded tools, and dialogs; no page section nests a card inside another card.
- Loading, empty, error, restricted, stale, and degraded states occupy an inline bounded region with stable geometry. They do not float over the shell or push unrelated controls into an overlay.

## Numeric and data surfaces

Text and labels are left-aligned. Quantities, prices, capacities, rates, and dates used for comparison are right-aligned with stable column geometry. The unit, currency, and time basis are visible at the column or value level. Status and provenance remain textual and inspectable rather than being conveyed by color alone.

## Primitive ownership

The following is the source-level ownership boundary for this proposal. “Proposed” means the primitive is absent from the current shared exports and is not being claimed as implemented.

| Primitive or surface | Canonical owner | Contract status |
| --- | --- | --- |
| Global nav, context, data/status rows | `AppShell` + `WorkspaceTopBar` | Existing source owner |
| Workspace identity and local task placement | `WorkspaceRenderer` | Existing source owner |
| Local task tabs | [`WorkspaceTabs`](../../clients/web/src/components/ui/WorkspaceTabs.tsx) | Existing shared primitive; owns tab semantics and keyboard behavior |
| Panel title and metadata | [`PanelHeader`](../../clients/web/src/components/ui/PanelHeader.tsx) | Existing shared primitive; current contract is title/meta, not an action system |
| Metric presentation | [`MetricStrip`](../../clients/web/src/components/ui/MetricStrip.tsx) | Existing shared primitive |
| Status tone/label | [`StatusBadge`](../../clients/web/src/components/ui/StatusBadge.tsx) | Existing shared primitive |
| Workspace header with a primary-action slot | `WorkspaceHeader` | Proposed; absent from current shared exports |
| Tables, bounded forms, toolbar, loading/empty/error states, evidence block, split workspace, context rail, menus/overlays | `DataTable`, `FormSection`, `Toolbar`, `LoadingState`, `EmptyState`, `ErrorState`, `EvidenceBlock`, `SplitWorkspace`, `ContextRail`, and narrowly justified menu/overlay primitives | Proposed; absent from current shared exports |

The shared primitive owns markup, tokens, keyboard/focus behavior, and state presentation. A workspace owns domain-specific rendering, data selection, and local state. A proposed primitive must not be treated as available until it is actually added to the shared source boundary.

## CR14 and CR15 surface obligations

The required workflows stay within the existing backend/API contracts. This layout contract does not add endpoints or invent domain data.

- **CR14 dataset detail/artifact:** Research Data must have a catalog-to-detail path for an existing dataset snapshot and its existing artifact workflow: detail, build/validate, quality, and export where those backend contracts provide the data. The selected dataset identity, provenance, loading/error state, and artifact status remain visible in the workspace; absent data is not synthesized.
- **CR15 review/replay:** Agent Research and Decision must expose the existing governed sequence needed for review/replay: plan, findings, StrategyIR, validation, challenge, review-pack, confirmation, and replay evidence where supplied by the backend. Replay must show inspectable result/status/warnings/blockers and may not expose hidden chain-of-thought or add execution semantics.

The obligation is a composition and presentation target for existing backend contracts, not a claim that the current screens already expose every step.

## References

- [`PROFESSIONAL_UI_CONSTITUTION.md`](../clients/PROFESSIONAL_UI_CONSTITUTION.md)
- [`MOTION_SYSTEM.md`](../clients/MOTION_SYSTEM.md)
- [`COMPONENT_CENSUS.md`](COMPONENT_CENSUS.md)
- [`POST_CR15_UI_AUDIT.md`](POST_CR15_UI_AUDIT.md)
- [`CR1_15_REGRESSION_MATRIX.md`](CR1_15_REGRESSION_MATRIX.md)
- [`ACTION_GEOGRAPHY.md`](ACTION_GEOGRAPHY.md)
