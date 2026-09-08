# Action Geography

**Status: binding subordinate implementation contract under RFC-0001, adopted 2026-09-08.** This document defines where actions, filters, and evidence belong. It is not an implementation or compliance claim and does not add a framework, backend capability, domain feature, or execution behavior. The Professional UI Constitution is the visual/interaction authority; `UI_CONTENT_STANDARDS.md` remains authoritative for content, domain, time-basis, rights, provenance, entitlement, no-execution, and client-boundary rules.

## Ownership rules

| Scope | Location | Owner or status |
| --- | --- | --- |
| Global navigation, global context, data/source status | Structural shell rows | [`AppShell`](../../clients/web/src/app/shell/AppShell.tsx) and [`WorkspaceTopBar`](../../clients/web/src/components/WorkspaceTopBar.tsx) are the current source owners |
| Workspace identity and primary action | Upper-right of the workspace header | Header action slot is proposed; a dedicated `WorkspaceHeader` primitive is absent from current exports |
| Local filters and view modes | Immediately above the surface they modify | Workspace-local state; never a second global context owner |
| Task/workspace navigation | Local tab row | Existing [`WorkspaceTabs`](../../clients/web/src/components/ui/WorkspaceTabs.tsx) |
| Row actions | In the affected row or its local action region | Surface-local implementation; do not move row actions into global chrome |
| Secondary, lifecycle, and destructive actions | Secondary control or bounded overflow adjacent to the affected object | Proposed geography; use an existing control when one already exists |
| Evidence, warnings, provenance, and replay status | Adjacent to the artifact/result they qualify | Inline bounded surface; never a detached global toast for required evidence |

## Workspace header

Each workspace presents one identity area. Its primary action is in the upper-right, has one clear label, and acts on the current workspace scope. Secondary actions may sit beside it; lifecycle or destructive actions stay secondary or in a bounded overflow. The proposed header must not duplicate global context selectors.

The current [`WorkspaceRenderer`](../../clients/web/src/app/workspaces/WorkspaceRenderer.tsx) owns page identity and local-tab placement, while [`PanelHeader`](../../clients/web/src/components/ui/PanelHeader.tsx) currently owns only title and metadata. Do not imply that `PanelHeader` already has an action slot; adding a shared header/action primitive is a separate proposal.

## Local filters and data actions

Filters are local to the table, map, catalog, or evidence surface they change and sit immediately above that surface. A filter must identify its scope and preserve the current workspace/deep-link context. Numeric columns are right-aligned; text and status columns are left-aligned; units and time basis remain visible.

For the existing Research Data surface, catalog filters and `datasets/features/targets` task tabs remain local. Dataset-detail actions belong to the selected dataset/artifact surface, not the global shell. For Agent Research, the run/research action belongs to the research workspace header or its local form; run selection and replay belong to the run surface. For review, confirmation and review-pack actions sit with the review result and its evidence.

## Rails, forms, and responsive geography

Context rails and entity navigators are local workspace regions, not fixed global overlays. Use responsive constraints of `280–360px` for context rails and `220–300px` for entity navigators; these are ranges for `min/max` sizing, not mandatory fixed widths. The analytic surface receives the remaining width and may shrink to `min-width: 0`.

Form controls are bounded to `240–420px` when the field is not intrinsically full-width. Long objectives, evidence, notes, and query text may use the available local surface. At `1440x900` the layout is the primary review target; `1920x1080` is the secondary target. Structural rows must push content down rather than cover it.

## CR14 and CR15 action contracts

- **CR14 dataset detail/artifact:** provide navigation from an existing catalog result to its dataset snapshot detail and existing artifact operations: build/validate, quality, and export where supplied by the backend. Keep selection, provenance, warnings, and artifact status beside the selected object. This is a presentation contract over existing backend/API behavior, not a request for new backend features.
- **CR15 review/replay:** place review, confirmation, review-pack, and replay controls beside the existing result/evidence object. The review path must be able to present the existing plan, findings, StrategyIR, validation, challenge, review-pack, confirmation, and replay evidence when returned by the backend. Do not add execution semantics or display hidden chain-of-thought.

## Primitive boundary

Actual shared primitives and owners are recorded in [`WORKSPACE_LAYOUT_STANDARD.md`](WORKSPACE_LAYOUT_STANDARD.md): `WorkspaceTabs`, `PanelHeader`, `MetricStrip`, and `StatusBadge` are current shared exports with their existing scopes. `WorkspaceHeader`, `DataTable`, `FormSection`, `Toolbar`, state surfaces, evidence, split-workspace, context-rail, and menu/overlay primitives are proposed only because they are absent from the current shared exports. Their proposed geography must not be described as current implementation.

## References

- [`WORKSPACE_LAYOUT_STANDARD.md`](WORKSPACE_LAYOUT_STANDARD.md)
- [`PROFESSIONAL_UI_CONSTITUTION.md`](../clients/PROFESSIONAL_UI_CONSTITUTION.md)
- [`MOTION_SYSTEM.md`](../clients/MOTION_SYSTEM.md)
- [`COMPONENT_CENSUS.md`](COMPONENT_CENSUS.md)
- [`POST_CR15_UI_AUDIT.md`](POST_CR15_UI_AUDIT.md)
- [`CR1_15_REGRESSION_MATRIX.md`](CR1_15_REGRESSION_MATRIX.md)
