# W9-01 — Shell Surfaces: Canonical Inspector and Command Palette

Status: **delivered (Wave 9, first and second slices)**. Authority:
[04_PRODUCT_EXPERIENCE_ARCHITECTURE.md](04_PRODUCT_EXPERIENCE_ARCHITECTURE.md) sections 3, 6, 7 and 11,
[12_MIGRATION_ROADMAP.md](12_MIGRATION_ROADMAP.md) Wave 9, and the Wave 1 contracts
[W1-01](W1-01_SHELL_AND_ACTIVE_CONTEXT_CONTRACT.md) and
[W1-03](W1-03_INSPECTOR_AI_AND_COMMAND_CONTRACT.md).

## 1. What this slice does

Wave 1 declared the shell regions, the Inspector contract, the action geography and
the command model as machine-readable contracts. This slice makes two of those
regions real:

| Region | Before | After |
|---|---|---|
| `inspector` | declared `planned`, nothing rendered | rendered as a canonical detail drawer, marked `data-shell-region="inspector"` |
| command palette | contract only (`buildPaletteCommands`, ranking, shortcut) | mounted in the shell with Ctrl/Cmd+K, arrow/Enter/Escape handling and a bounded result list |

Every shell region is now either `present` or `partial`; nothing remains in the
`planned` state, and the Wave 1 conformance test asserts that
(`plannedShellRegions() === []`).

## 2. Canonical Inspector

- `clients/web/src/stores/inspector.ts` wraps the pure Wave 1 reducer
  (`inspectorReducer`) in a zustand store, so the selection rules stay testable
  without a browser and the runtime only adds identity-reset behaviour.
- `clients/web/src/components/InspectorPanel.tsx` renders the selection: object
  kind, label, reference and the page the selection came from, with back and close
  controls and a politely announced note.
- The panel performs **no fetch** and imports no API store. It therefore cannot
  become a second entitlement path: whatever the caller may see was already
  authorised when the surface loaded it.
- Wave 9 docks it as a right-hand drawer - the same shell-level pattern the alert
  drawer already uses - so no workspace layout changes. Dockable and detachable
  panels are Wave 10 (desktop workstation) work; `shellContract.ts` records that.

## 3. Command palette

- `clients/web/src/app/hooks/useCommandPalette.ts` binds the Wave 1 keyboard model:
  Ctrl/Cmd+K toggles, Escape dismisses, arrows move, Enter runs.
- Commands are **derived**, never hand-maintained: navigation from
  `productNavigation`/`workspaceNavigation`, inspection commands from the Active
  Context (`inspectionCommands`), utilities from the existing `topbar.*`
  vocabulary.
- Unavailable commands are shown with their reason
  (`experience.palette.unavailable_capability` / `..._context`) instead of being
  hidden. Availability is presentation only: the backend still authorises every
  request.
- Canonical AI actions (`ask`, `explain`, `compare`, `challenge`, `draft`) stay in
  the contract but are omitted from the runtime palette until their invocation
  surface exists (Wave 7), so no command is offered that would do nothing.
- Accessibility: `role="dialog"` with `aria-modal`, a labelled search input,
  `role="listbox"`/`role="option"` with `aria-selected` and `aria-activedescendant`,
  and `aria-disabled` on unavailable entries.

## 4. Second slice — the Inspector resolves real detail

The first slice mounted the Inspector but showed only a reference: every hand-over
rendered the same three lines, which is why most surfaces still kept their own
detail panes. The second slice makes the Inspector worth handing a subject to.

- `clients/web/src/app/model/inspectorDetail.ts` resolves a subject into facts,
  provenance and a label. It reads **only** state the calling identity already
  received (`marketQuotes`, `normalizedMarkets`, `monitoringAlerts`,
  `intradayOpportunities`, `upstreamContracts`, `routeCandidates`,
  `resourcePoolOptions.portfolio_resources`, `strategyRuns`, `nodes`): it fetches
  nothing, so it cannot become a second entitlement path.
- It **presents, it does not compute.** Every fact is a field the record carries,
  read by name and formatted for display (a timestamp is rendered as a timestamp).
  No field is derived, aggregated or restated as an authority, and no arithmetic
  happens in the Inspector.
- Absence is honest: a field the record does not carry is omitted rather than shown
  as a zero, and a kind this build has no resolver for (or a ref that is not in the
  loaded data) returns an explicitly *unresolved* detail. The panel then says it
  cannot show the detail, instead of rendering an empty panel that reads like "this
  object has no detail".
- Hand-over stays contractual: `canOpenInspector(kind, page)` is enforced inside the
  resolver as well as at the call site, so a page can only inspect the subject kinds
  its Wave 1 composition declares.
- `InspectorPanel.tsx` renders the resolved facts, an evidence/provenance list taken
  from the fields the record names (`source_reference`, `source_refs`,
  `source_systems`, `required_tso_access`), and the record's own name as the header
  when it carries one.
- The market cockpit is the first migrated consumer: the hub board's focused
  observation (quote when a quote was displayed, otherwise the normalized
  observation) is handed to the Inspector by `marketObservationSubject(...)` from the
  rail's hand-off actions. That is the pattern the remaining surfaces follow -
  rail/panel-local detail is replaced by a hand-over, not by a second copy.

## 5. What this slice does not claim

Wave 9 in the roadmap is larger than its delivered slices. Still open:

- migrating each workspace's panels onto the panel taxonomy, and replacing the
  per-surface rails, drawers and master-detail panes with the Inspector as the
  default detail pattern (the market cockpit now hands over one subject kind; the
  network, contracts, strategy and review surfaces still show detail locally);
- applying the action geography to every header (the contract and resolver exist;
  `WorkspaceHeader` already owns the primary-action slot);
- the remaining `system`-area views that are not URL-addressable.

These are incremental, file-scoped migrations with their own evidence; none of them
requires a new contract.

## 6. Compatibility

- No route, deep link, page id or workspace composition changed in these slices.
- No API, schema, permission, numerical, release or DR behaviour changed.
- New user-visible vocabulary is bilingual (`en`, `zh-CN`), and the shell surfaces
  add no new colour, type or motion family.

## 7. Verification

- `clients/web/tests/shellSurfaces.test.ts` — inspector region rendered and
  fetch-free, command derivation from the registries, inspection commands from the
  Active Context, explained unavailability, the controller's keyboard and ranking
  model, the store's use of the pure reducer, and bilingual vocabulary.
- `clients/web/tests/inspectorDetail.test.ts` — fact and provenance resolution per
  record shape, absent-is-not-zero, timestamp formatting, the page composition gate,
  explicit non-resolution for unknown refs and kinds, the market hand-over, and the
  panel/shell wiring that keeps the panel free of lookups and fetches.
- `clients/web/tests/experienceArchitecture.test.ts` — updated shell-region
  honesty check: every rendered region carries its marker and nothing remains
  `planned`.
- `clients/web/tests/controlPlaneSeparation.test.ts` — the control-plane gate still
  holds after the shell refactor.
- Full suites: `node --test "tests/*.test.ts"` and `npx tsc --noEmit` plus
  `npm run build` (tsc + vite) in `clients/web`; results are recorded in the
  execution checkpoint.
