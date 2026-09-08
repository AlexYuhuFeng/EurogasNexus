# UX-01 Phase 1 Component Census

Status: source census complete at `cfbcd58`; runtime visual validation is pending and is owned by the parent UX-01 task.

Scope: `clients/web/src` only. This document is an evidence-led inventory of the current Web client. It does not change UI code, add dependencies, or claim that source-level counts equal mounted runtime instances.

## Executive Summary

The client has four shared UI exports under `clients/web/src/components/ui`:

- `WorkspaceTabs`: 11 usage sites in 11 files.
- `PanelHeader`: 14 usage sites in 5 files.
- `MetricStrip`: 2 usage sites in 2 files.
- `StatusBadge`: 7 usage sites in 3 files.

The remainder of the phase-1 surface is primarily native HTML plus feature-local CSS. Source evidence at this SHA shows:

- 99 native `button` elements in 26 TSX files; no shared Button component.
- 81 native `input` elements in 15 files; no shared Input component.
- 29 native `select` elements in 9 files; no shared Select component.
- 4 native checkbox inputs in 4 files; no radio inputs and no combobox role.
- 38 `div.data-table` sites plus 1 semantic `<table>` site.
- 132 `.workspace-panel` sites in 22 files and 15 `.panel` sites in 1 file.
- 25 `.metric-grid` sites in 12 files, in addition to the two `MetricStrip` mounts.
- 26 `.panel-title-row` sites in 8 files and 24 `.section-heading` sites in 11 files.
- 12 raw `.status-badge` sites in 6 files, in addition to the seven `StatusBadge` mounts.
- 9 active named card-style class families and 12 explicit card-marked usage sites.

The main convergence opportunity is not a new visual language. It is to retain domain-specific surfaces while moving repeated control, panel, state, table, evidence, and rail contracts into a small set of shared primitives. The existing standards already require this direction: shared primitives live under `components/ui`, panel/title pairs use `PanelHeader`, compact KPI rows use `MetricStrip`, statuses use `StatusBadge`, and workspace tabs use `WorkspaceTabs`.

## Counting Method

### Scope and definitions

The census includes `clients/web/src/**/*.tsx`, `clients/web/src/**/*.ts`, and the five CSS files currently carrying active Web UI rules. It excludes tests, generated output, `node_modules`, the desktop client, and backend templates.

The authoritative source baseline is commit `cfbcd58`. The worktree later advanced to `3bb9ab5`, but `git diff --stat cfbcd58..HEAD -- clients/web/src` is empty; the source counted here is therefore unchanged from the requested baseline. The commit-pinned recursive tree check returns `41` TSX files, including the nested `components/strategy` files.

Counts use three separate measures:

1. **Shared implementation**: an exported reusable React component under `clients/web/src/components/ui`.
2. **Local implementation**: a feature component, stable markup contract, or CSS selector family that independently defines the category's structure or interaction. A CSS variant is not counted as a new implementation merely because it changes domain content.
3. **Usage site**: a JSX opening/self-closing element or named class occurrence in source. Conditional branches are counted because they are distinct authored sites; runtime mount multiplicity is not inferred.

Native HTML elements count as usage sites, not shared implementations. For example, 99 `<button>` sites means 99 authored button instances, not 99 button components. The `div.data-table` and semantic `<table>` models are counted separately because they have different semantics and keyboard/accessibility implications.

### Reproduction

Run from the repository root at the audited SHA:

```powershell
git rev-parse --short HEAD
Get-ChildItem clients\web\src -Recurse -File -Include *.tsx,*.ts,*.css
rg -n --glob '*.tsx' '<button|<input|<select|<textarea|<table|<fieldset|role="tablist"|role="checkbox"|role="radio"' clients\web\src
rg -n --glob '*.tsx' '<WorkspaceTabs|<PanelHeader|<MetricStrip|<StatusBadge' clients\web\src
rg -n --glob '*.tsx' 'className="[^"]*(workspace-panel|data-table|metric-grid|panel-title-row|status-badge|card|evidence|provenance|empty|error|tabs|rail|toolbar)' clients\web\src
rg -n --glob '*.css' '^\.|font-size:|gap:|border-radius:|min-height:|height:' clients\web\src
```

The element totals in this document were cross-checked with a TypeScript compiler-API traversal of the 41 TSX files. The traversal visits both `JsxElement` and `JsxSelfClosingElement`, records intrinsic tags and capitalized component tags, and records the source file for each occurrence. CSS totals are source-level selector/class totals and are intentionally not presented as runtime DOM totals.

The following bounded counter reproduces the recursive TSX totals from PowerShell. Run it from `clients/web`; it uses the repository's installed TypeScript dependency and does not write files:

```powershell
@'
import fs from "node:fs";
import path from "node:path";
import ts from "typescript";

const root = path.resolve("src");
const files = [];
function walk(dir) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const file = path.join(dir, entry.name);
    if (entry.isDirectory()) walk(file);
    else if (/\.tsx$/.test(entry.name)) files.push(file);
  }
}
walk(root);

const tags = new Map();
const custom = new Map();
const add = (map, key) => map.set(key, (map.get(key) ?? 0) + 1);
function visitOpening(node) {
  const name = node.tagName.getText();
  add(tags, name);
  if (/^[A-Z]/.test(name)) add(custom, name);
}
function visit(node) {
  if (ts.isJsxElement(node)) {
    visitOpening(node.openingElement);
    for (const child of node.children) visit(child);
    return;
  }
  if (ts.isJsxSelfClosingElement(node)) {
    visitOpening(node);
    return;
  }
  ts.forEachChild(node, visit);
}
for (const file of files) {
  const source = ts.createSourceFile(
    file,
    fs.readFileSync(file, "utf8"),
    ts.ScriptTarget.Latest,
    true,
    ts.ScriptKind.TSX,
  );
  ts.forEachChild(source, visit);
}
for (const name of ["button", "input", "select", "table", "aside", "label"]) {
  console.log(`${name}=${tags.get(name) ?? 0}`);
}
for (const name of ["WorkspaceTabs", "PanelHeader", "MetricStrip", "StatusBadge"]) {
  console.log(`${name}=${custom.get(name) ?? 0}`);
}
console.log(`tsx_files=${files.length}`);
'@ | node --input-type=module
```

Expected output at `cfbcd58` is `tsx_files=41`, `button=99`, `input=81`, `select=29`, `table=1`, `aside=8`, `label=99`, `WorkspaceTabs=11`, `PanelHeader=14`, `MetricStrip=2`, and `StatusBadge=7`. The class, title, checkbox, radio, and CSS inventories remain reproducible with the `rg` commands above.

### Evidence boundaries

This is a source census, not visual acceptance. The current project guidance records prior DOM/source findings and explicitly says that image appearance, overlap aesthetics, and spacing quality remain pending visual review. Runtime startup and screenshot validation are therefore not repeated here; the parent task owns that validation.

## Phase-1 Category Census

The target column is a proposed phase-1 convergence target. It is deliberately conservative: semantically distinct route cards, evidence panels, charts, maps, source records, and strategy surfaces remain specialist variants instead of being flattened into generic cards.

| Category | Current implementations and usage | Proposed target | Rationale | Migration |
|---|---|---|---|---|
| Button | Shared: **0**. Local/native: **99** `<button>` sites in **26** files; **69** distinct CSS selector lines target buttons. | **1** shared `Button` with primary, secondary, quiet, destructive, and compact variants. | Button geometry, focus, disabled state, and hierarchy are currently distributed across page selectors. | Add the primitive only after preserving existing class contracts; migrate high-traffic shell, tabs, forms, and command bars first. |
| Input | Shared: **0**. Native: **81** sites in **15** files; selector rules are mixed with select/textarea rules. | **1** shared `Input` plus numeric/date/file specialist props. | Field height, border, focus, and width need one contract while domain validation remains local. | Migrate settings, source credentials, strategy forms, and contract fields; retain file-input behavior as a specialist. |
| Select | Shared: **0**. Native: **29** sites in **9** files. | **1** shared `Select`; no separate custom dropdown unless a real menu interaction is required. | Native selects already supply correct option semantics; styling is duplicated. | Wrap native select without changing option values or i18n; migrate context, source, capacity, contract, and strategy controls. |
| Combobox | Shared: **0**. Current: **0** `role="combobox"` or searchable composite sites. | **0** until a searchable option workflow is approved; then **1** canonical specialist. | Creating a combobox now would invent interaction and keyboard behavior without a current use case. | Do not create speculatively. Convert a real search requirement through the shared field contract if one appears. |
| Checkbox | Shared: **0**. Native: **4** `type="checkbox"` sites in **4** files. | **1** shared `Checkbox` with label and disabled/focus states. | Four independent native placements already need consistent sizing and state communication. | Migrate Agents, Review, Strategy Design, and Strategy Compare; preserve boolean semantics and text labels. |
| Radio | Shared: **0**. Current: **0** radio inputs. | **0** until required; one primitive only when a radio group exists. | No current radio group should be created merely to complete the inventory. | Do not add a substitute control. |
| Tabs | Shared: **1** `WorkspaceTabs`; **11** mounts in **11** files. Local groups: **8** (Capacity, Contract task/clause navigation, Glossary, Market tenor, Network rail, Strategy mode, Strategy shadow). | **1** shared semantic tabs primitive with justified task, rail, and segmented variants. | Shared tabs already implement arrow-key movement and ARIA; local groups recreate markup and some omit tab semantics. | Migrate local groups incrementally. Keep clause navigation and map mode as specialist variants only where semantics differ. |
| Panel | Shared: **0** component. Base CSS contracts: `.workspace-panel` (**132** sites / **22** files) and legacy `.panel` (**15** sites / **1** file). | **1** `Panel` with **2-3** structural variants: surface, inset, and rail. | Panel structure is the dominant repeated surface; the two base classes and feature classes create drift. | Establish one base without deleting legacy selectors; migrate feature panels by workspace and remove duplicate rules after visual review. |
| Card | Shared: **0**. Active named families: **9** (`release-compatibility`, glossary term, route decision, route alpha, net PnL, resource path, credential status, strategy tape, strategy price basis); **12** explicit card-marked sites in **7** files. | Prefer `Panel`/`MetricStrip`; retain **3-4** justified specialist card variants. | Several cards are really panels, while route/entity/strategy records have distinct semantics. | Reclassify generic cards first. Keep route decision details, glossary terms, and price-basis records as specialist content variants. |
| Table | Shared: **0** React table component. Usage: **38** `div.data-table` sites plus **1** semantic `<table>` in Source Center, across **16** files. | **1** `DataTable` with semantic, dense, selectable, and local-scroll variants. | The div-row model is widely repeated and the semantic table is an isolated second model. | Preserve column definitions and row actions; migrate div tables first, then align Source Center semantics and loading/empty/error rows. |
| Metric/KPI | Shared: **1** `MetricStrip` with **2** mounts. Local: `.metric-grid` (**25** sites / **12** files) plus domain KPI strips. | **1** `MetricStrip` with compact, two-column, and dense variants. | Metrics are repeated as direct grid markup and page-specific strips; values need stable labels, units, and alignment. | Migrate direct `.metric-grid` sites in Runtime, Source, Market, Portfolio, Decision, Review, and Strategy; retain domain data formatting. |
| Badge | Shared: **1** `StatusBadge`, **7** mounts. Local/raw: **12** `.status-badge` sites / **6** files plus `status-pill` and strategy state styles. | **1** `StatusBadge` with semantic tone and density variants. | Raw status spans duplicate class construction and can communicate color without a consistent label contract. | Replace raw status spans after mapping existing status values; keep strategy state text and source freshness semantics. |
| Alert | Shared: **1** `AlertCenter` drawer mount. Local: **5** raw `.alert` sites plus release compatibility and endpoint-error banner surfaces. | **1** inline `Alert` plus the existing `AlertCenter` as a drawer specialist. | Inline errors, warnings, and the monitoring drawer have different containment and lifecycle needs. | Introduce a shared inline surface for structured failures; keep monitoring behavior and acknowledgement actions in `AlertCenter`. |
| Tooltip | Shared: **0**. Native `title` attributes: **26** source sites; no Tooltip component. | **1** accessible `Tooltip` for non-obvious icon/abbreviation help; do not use for obvious controls. | Native title timing and keyboard behavior are inconsistent and cannot satisfy the full guidance contract. | Inventory the 26 titles; convert only non-obvious or truncated-value help, retaining visible text for state and provenance. |
| Popover | Shared: **0**. Current: **0** popover/dialog role surfaces. | **1** small anchored `Popover` primitive only if a non-modal contextual surface is needed. | No current popover interaction is present; a premature abstraction would add behavior without evidence. | Defer. Reuse Drawer or Menu where the interaction is actually modal or command-oriented. |
| Dropdown | Shared: **0** custom dropdown. Native select usage: **29** sites. | Treat as the shared `Select`; **0** separate dropdown implementations. | A second dropdown abstraction would duplicate native option semantics. | Normalize select styling and width; introduce a custom listbox only for a demonstrated search/multi-select need. |
| Menu | Shared/live semantic menu: **0**. Dormant `.workspace-menu*` CSS exists in `WorkspaceTopBar.css`; current user controls are a `div` with buttons. | **1** `Menu` for grouped overflow/lifecycle actions. | Action geography requires an overflow menu, but the current source has no consistent menu contract. | Add only for grouped secondary/destructive actions; define keyboard navigation, Escape, focus return, and item grouping before migration. |
| Modal | Shared: **0**. Current: **0** `<dialog>`/dialog-role sites. | **1** `Modal` primitive for future blocking confirmations or forms. | The absence of a modal is a real gap, but no current workflow should be changed by inventing one. | Defer until a current flow requires blocking confirmation; do not convert the AlertCenter drawer. |
| Drawer | Shared: **0**. Local: **1** `AlertCenter` drawer/`aside`, mounted once. | **1** shared `Drawer` plus monitoring content as a specialist. | Drawer containment, responsive width, focus return, and Escape behavior should not live only in AlertCenter. | Extract shell behavior after runtime visual validation; keep alert data and analysis actions in the domain component. |
| Form Section | Shared: **0**. Local: **8** Contract Workbench fieldsets in one file; **99** labels across **12** files; strategy and contract grids are separate. | **1** `FormSection` with field, helper, error, and unit slots. | Form grouping and label spacing are repeated but should not erase domain-specific validation. | Migrate Contract Workbench and Strategy Design first, then Settings/Review/Source; keep native `fieldset` semantics. |
| Workspace Header | Shared shell header: **1** `WorkspaceTopBar`, mounted once. Local page identity header: **1** `.workspace-page-header` in `WorkspaceRenderer`. | **1** shared `WorkspaceHeader` with map and page variants. | Global context, workspace identity, and primary action geography are split between shell and page-local markup. | Preserve the fixed map topbar and sticky page header as variants; move shared identity/action slots into one contract. |
| Panel Header | Shared: **1** `PanelHeader`, **14** mounts / **5** files. Local: `.panel-title-row` **26** sites / **8** files and `.section-heading` **24** / **11** files. | **1** `PanelHeader` with title, meta, action, and status slots. | This is the clearest existing duplication and is already covered by the project standard. | Migrate raw title rows before changing panel geometry; retain section-heading for form/command context only where it is not a panel header. |
| Toolbar | Shared: **0**. Local families: at least **5** (`map-toolbar`, `glossary-list-toolbar`, `contract-command-strip`, `capacity-command-bar`, `strategy-command-deck`) plus generic action rows. | **1** `Toolbar` with primary, secondary, filter, and overflow regions. | Controls are authored per workspace and can exceed the intended one-primary-plus-overflow hierarchy. | Map existing controls by action geography; migrate shell, Capacity, Contract, and Strategy command surfaces without changing actions. |
| Empty State | Shared: **0**. Named local families: **9** (`alert`, `capacity`, `fallback`, glossary, intraday, market sparkline, resource path, strategy chart, strategy performance). | **1** `EmptyState` with reason, next action, and compact/dense variants. | Empty copy and dimensions are not stable across tables, charts, rails, and drawers. | Replace only explicit empty branches; preserve domain-specific explanation and provenance. |
| Loading State | Shared: **0**. Current loading is inline text/status (`status.loading`) and conditional page markup; no stable loading component/class contract. | **1** `LoadingState` with stable dimensions and table/chart skeleton slots. | Inline loading is prone to layout shift and the project evidence records whole-workspace loading concerns. | First separate endpoint loading from whole-workspace loading; then migrate surfaces with stable reserved height. |
| Error State | Shared: **0**. Local families include `endpoint-error-banner`, `strategy-error`, raw `.alert`, release blocker, and page-local error branches. | **1** `ErrorState` with structured message, retry, and preserved unaffected content. | Existing failures mix banner, panel, paragraph, and status treatments. | Map API error categories to retryable/non-retryable variants; migrate without replacing backend-safe details. |
| Evidence/Provenance UI | Shared: **0**. Local families include Review evidence, Capacity evidence, Intraday evidence, resource-path evidence, Contract source evidence, Strategy source evidence/run provenance, and Source detail metadata. | **1** `EvidenceBlock` with source, reference, freshness, time basis, and human-review slots. | Provenance is a product trust requirement but is currently page-specific and variably structured. | Inventory fields first; migrate Review and Strategy, then market/physical/source surfaces. Keep entitlement masking backend-owned. |
| Status Indicator | Shared: partially `StatusBadge` (**7** uses). Local families include raw `status-badge`, `status-pill`, stream status, freshness dots, readiness chips, and strategy state badges. | **1** `StatusIndicator` contract, implemented through `StatusBadge` variants. | Freshness, availability, entitlement, runtime, and lifecycle states need common text-plus-tone semantics. | Establish vocabulary mapping (`ready`, `partial`, `blocked`, `stale`, `unavailable`, `restricted`); then replace ad hoc class names incrementally. |
| Split Pane | Shared: **0**. Local layout families include `workspace-grid`, `market-cockpit-overview`, `strategy-lab-grid`, `source-table-split`, Contract terms layout, and fixed map/rail composition. | **1** `SplitPane`/`SplitWorkspace` with primary, secondary, and optional rail regions. | Workspace layouts independently encode columns, widths, overflow, and breakpoint behavior. | Extract structural layout only after preserving map dominance and local table scrolling; do not force every workspace into one column model. |
| Context Rail | Shared: **0**. Local rail families include Scenario, Decision, Market context, Network resource/decision, and Contract decision rails; **8** native `<aside>` sites in **6** files. | **1** `ContextRail` with decision, evidence, and inspector variants. | Rail width, fixed positioning, and evidence/action placement are repeated and currently live in page CSS. | Normalize width and responsive containment; keep domain content and map-specific geometry as variants. |

## Shared Primitive Adoption Map

| Primitive | Definition | Current mounts | Primary consumers | Migration priority |
|---|---|---:|---|---|
| `WorkspaceTabs` | `components/ui/WorkspaceTabs.tsx` | 11 | Shell, page headers, Access, Agents, Decision, Market, Portfolio, Research, Runtime, Source, Strategy Lab | High: local tabs remain in Capacity, Contract, Glossary, Market Terminal, Network rail, Strategy mode, and Strategy shadow. |
| `PanelHeader` | `components/ui/PanelHeader.tsx` | 14 | Access, Agents, Research, Runtime, Source | High: 50 raw title/section sites are visible evidence of duplication. |
| `MetricStrip` | `components/ui/MetricStrip.tsx` | 2 | Runtime, Source | High: 25 direct `.metric-grid` sites remain. |
| `StatusBadge` | `components/ui/StatusBadge.tsx` and `statusBadgeClass.ts` | 7 | Access, Runtime, Source | High: raw status badges and status pills coexist. |

## Typography Inventory

Evidence source: `clients/web/src/styles/app.css` plus `WorkspaceTopBar.css`, `market-cockpit.css`, `commercial-workflow.css`, and `strategy-lab.css`.

- There are **16 distinct literal `font-size` values** in active CSS: `10`, `10.5`, `11`, `11.5`, `12`, `12.5`, `13`, `14`, `15`, `16`, `17`, `18`, `20`, `22`, `24`, and `32px`.
- The standards target a smaller fixed workstation scale: metadata 11-12px, body/control 12-13px, panel headings 13-14px, workspace headings 16-18px, and rare page titles 18-20px.
- Current outliers include 10px source/status labels, 22px close controls, 24px workspace page titles, and 32px net PnL display type. These may remain specialist values only if visual review confirms the hierarchy.
- Two root token families coexist: the original `--bg`/`--surface`/`--text` set at the top of `app.css`, and the later `--eg-*` set beginning near the Vercel reference cockpit block. This is a token-consolidation concern, not a reason to create a third family.
- The UI uses a system sans stack and `ui-monospace` for eyebrows, source tags, and compact labels, consistent with current standards. Letter spacing is explicitly `0` in the main panel/page rules; a small number of technical label rules use positive tracking.

## Spacing and Layout Inventory

- The most frequent literal gaps are `8px` (**89** declarations), `6px` (**45**), `10px` (**37**), `4px` (**34**), and `12px` (**27**).
- The CSS also contains `1`, `2`, `3`, `5`, `7`, `14`, `16`, `18`, `20`, `22`, `24px`, compound row/column gaps, and `0.5rem`. This is a broad but recoverable spacing surface; the proposed 4/8/12/16/24 scale should be applied during migration rather than by mass replacement.
- Current structural widths include fixed or clamped rails such as `320-392px`, market columns around `190-290px`, a strategy navigator around `170-230px`, and a `max-width` page surface of `1440px`. These are useful starting points for a shared layout contract.
- The current source has explicit local overflow behavior for some tables and tabs, but not one universal split/rail contract. Prior DOM evidence identified page-tab and data-table overflow candidates at 390px; runtime visual review remains required before changing widths.

## Control, Radius, Border, and Shadow Inventory

- Common control heights are `30`, `32`, `34`, `36`, `38`, and `40px`, with additional feature-specific values. The current guidance proposes compact `28px`, standard `32px`, and prominent `36px`; migration should normalize by intent, not by selector-wide replacement.
- Literal radii include `2`, `3`, `4`, `6`, `8`, `12`, and `18px`, `50%`, `999px`, and `9999px`. Tokenized radii are `--eg-radius-sm: 6px`, `--eg-radius-md: 8px`, and `--eg-pill: 100px`; the standards cap ordinary analytical containers at 8px.
- Borders are predominantly 1px hairlines, but older rules still use raw colors and repeated border declarations. Consolidate through the existing semantic border tokens.
- The legacy `--shadow` is a broad `0 12px 28px` shadow; the later `--eg-shadow-1/2/3` family uses smaller stacked shadows and inset hairlines. The standards prefer borders and restrained elevation, so the later family is the better migration target.
- Feature CSS still contains raw colors, linear gradients, map colors, and fallback colors. Keep map/domain colors where they carry data semantics; remove decorative gradients and raw feature colors when a semantic token exists.

## State and Evidence Inventory

The source has meaningful domain state coverage, but it is distributed across local branches and class families:

- Loading is represented by booleans, topbar status text, and inline `status.loading` rows rather than one stable component.
- Empty states exist for alerts, capacity, fallback map, glossary, intraday opportunities, market sparkline, resource paths, and strategy charts/performance.
- Errors use endpoint banners, release blockers, raw alert panels, strategy error paragraphs, and page-local branches.
- Provenance is strongest in Review and Strategy but is separately structured in Capacity, Intraday, Resource Path, Contract, and Source screens.
- Status vocabulary is partly centralized in `statusBadgeClass.ts`, but raw classes and domain-specific badges remain. The target must retain text labels and must not rely on color alone.

## Migration Plan

1. **Token and contract preparation.** Confirm the authoritative token family in the UI Constitution, add no new visual language, and record existing class contracts that tests depend on.
2. **High-leverage primitives.** Complete `WorkspaceTabs`, `PanelHeader`, `MetricStrip`, and `StatusBadge` migration. These already exist and have tests in `clients/web/tests/uiPrimitives.test.ts`.
3. **Controls and forms.** Introduce Button/Input/Select/Checkbox and FormSection contracts. Preserve native semantics, existing API values, i18n keys, and file/date/number behavior.
4. **Tables and states.** Build `DataTable`, `EmptyState`, `LoadingState`, and `ErrorState` around stable dimensions, local scrolling, structured messages, and explicit units/status/provenance.
5. **Evidence and layout.** Build `EvidenceBlock`, `SplitWorkspace`, and `ContextRail`. Migrate Review, Strategy, Market/Network, Source, and Contract surfaces in that order, retaining domain-specialist panels.
6. **Menus and overlays.** Add Menu, Drawer, Modal, and Tooltip only where current workflows require them. Define focus, Escape, keyboard movement, and focus-return contracts before extracting behavior.
7. **Validation.** Run typecheck, Web tests, build, DOM checks, and the parent-owned runtime visual suite at 1440x900, 1920x1080, and the supported narrow desktop size. Record visual findings separately; this census does not mark them passed.

## Key Findings for the Planner

- The highest return is converging existing primitives and local tab/title/metric/status markup, not creating a large component library.
- The table system is the largest repeated analytical primitive: 39 authored table sites use two rendering models and many width/column variants.
- `.workspace-panel` is already the dominant panel contract at 132 sites, so migration should strengthen it rather than replace it with a competing card language.
- The project guidance and current code agree on map-first, dense, bordered surfaces, but the stylesheet still contains legacy tokens and feature-local control rules that can produce screen-to-screen drift.
- The current browser/runtime evidence includes hydration/loading and narrow-width risks. Those are acceptance blockers to investigate, not reasons to infer visual defects from this source census.

## Validation Status

- Repository SHA inspected: `cfbcd58`.
- Files changed by this task: `docs/ux/COMPONENT_CENSUS.md` only.
- UI source edits: none.
- New designs or dependencies: none.
- Runtime visual validation: **pending; parent task owns it**.
