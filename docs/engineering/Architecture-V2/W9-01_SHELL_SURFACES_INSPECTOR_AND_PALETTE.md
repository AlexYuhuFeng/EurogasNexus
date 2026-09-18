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
- The contract workbench is the second: every hand-over now goes through one
  composition-checked builder (`inspectorSubjectFor`), so the Wave 1 rule - a page may
  only inspect the subject kinds it declares - is enforced where the selection happens
  and not only inside the resolver, and `marketObservationSubject` delegates to it. The
  workbench's library row hands a saved contract over from an Inspect action beside its
  existing Strategy Lab hand-off, so object detail did not become a third pane.
- The network map is the third: its node popup stays the quick map context and carries an
  Inspect action that hands the node to the Inspector. `GasNetworkMap` renders that action
  only when a surface passes `onInspectNode`, and the callback is part of the click
  handler's effect dependencies, so the market cockpit's overview map (whose page declares
  no node subject) offers nothing it cannot honour.
- The strategy backtest is the fourth: the selected run is handed over from the result
  strip, while the KPI strip and charts stay on the surface. The migration replaces
  duplication rather than capability - the run's facts and provenance live in the one
  Inspector, and the workspace keeps the analysis it exists to do.
- The review decision history is the fifth, and the first whose subject is *evidence*
  rather than a record the surface already lists. Each row hands its entity's resolved
  evidence over when the review projection carries an entry for it, and says so when the
  entry is missing, so the action never appears where it would do nothing. Evidence the
  backend withheld is still inspectable and shows `ENTITLEMENT_DENIED` as its state: a
  reviewer needs to know that evidence exists and was withheld, not that there is none.
  A resolver's artifact has its own shape, so its flat fields are presented under their
  own names - `InspectorFact` therefore carries an optional raw `label` beside its
  translation key, because inventing product copy for data keys would misdescribe them.
- The capacity point panel is the sixth: it keeps its aggregate analysis (utilisation,
  booking, headroom, access products and tariffs) and hands the point's own observation
  record over, only when the runtime actually served one. The resolver needed a small
  extension here - a capacity observation and a market observation are both keyed by
  `observation_id`, so the record's field map follows the subject kind where it must
  (`FIELDS_BY_KIND`), and a test pins that a capacity record never renders with
  market-observation labels.

## 5. Third slice — the shell composes pages, it does not intercept them

Wave 9's remaining navigation work was two conflicting-register items, both of the same
shape: a page and the surface it names disagreed.

- **C9.** The shell branched on the active workspace being the network page and mounted the
  map-first surface itself, with its own screen-reader heading and forty hand-wired props.
  No page is special to the shell any more: it renders the control-plane refusal or
  `WorkspaceRenderer`, and nothing else. The route is composed by the market primary, which
  already resolved that page to its network task, so no URL changed and the surface keeps
  its resource-pool path ladder, its evidence stack and its Inspector hand-over. The
  scenario hand-off moved with the mount, so the selected or highlighted route is still
  carried, and the page's single heading comes from `WorkspaceHeader` - the one component
  that renders an `<h1>` for a page - rather than from a shell-only element.
- **C10.** A bare `?workspace=orders` deep link landed on the portfolio overview even though
  the `orders` page id names the market-positioning view. It now resolves to that view; an
  explicit `?task=` still wins and every other portfolio page still resolves to the
  overview, so the change adds no second owner for the URL.

Five pinned source-text contracts moved with the mount rather than being weakened: the
resource-pool path ladder, the highlighted route, the network geometry gate, the
warning/evidence stack and the network-extracted-from-the-shell guarantee now read the
composing surface, and the shell assertions assert the stronger fact - it mounts no page.

## 6. Fourth slice — the action geography, applied and enforced

Wave 1 declared the action geography (`app/experience/actionGeography.ts`) and Wave 9 mounted
the shell surfaces, but the geography was applied nowhere: `WorkspaceHeader` had a
primary-action slot that no surface used, so "a compute or persist action belongs in the
workspace's single primary slot" lived only in prose and in its own unit test.

- **First application.** The Optimize task now puts running the pool optimiser in that slot -
  a `compute` consequence the geography permits there - instead of inside the panel it
  reports on. The panel keeps the preflight verdict and the allocations the run produced, and
  says in its own copy that the run starts from the workspace's primary action.
- **Enforcement.** `clients/web/tests/actionGeography.test.ts` walks every surface source and
  fails on a guarded verb (retire, freeze, delete, remove, revoke, pause, resume, cancel)
  rendered with a primary class, on a surface passing more than one primary action, on a
  surface that starts passing one without appearing in the asserted inventory, and on a
  workspace reaching for a shell utility (sign-out, language, theme). It reads sources, so it
  checks placement rather than behaviour - and says so in the file.

- **Second application (persist).** The Portfolio `resources` task now puts saving a reviewed
  contract draft in that slot - the geography's `persist` consequence - instead of among the
  panel's local controls. This one needed a shared rule first: the panel decided
  `canSave`/`saveStatus` from its own `validationIssues`, and its read-only state came from
  panel-local `taskView` state, so a header could only have guessed. The rule now lives in
  `app/model/contractDraftModel.ts` as pure functions (`contractValidationIssueKeys`,
  `contractViewFacts`, `contractSaveState`), the sub-view state is owned by the workspace that
  hosts the action, and the panel receives `taskView`/`viewFacts`/`saveState` as props: it
  renders the sub-views, the translated issue list and the save outcome, and no longer
  evaluates the rule, holds the payload or renders a save control. The action's blocked state
  and its explanation key therefore come from the same computation the panel reports.

The remaining surfaces still keep their primary actions inside panels; each needs its handler
and blocked-state lifted to the component that owns the header, which is a per-surface change
rather than a shared one. The contract workbench is the first of those lifts: the rule was
extracted to a model rather than copied into the header, because a second copy of "may this be
written" is the failure mode the geography exists to prevent.

**Surfaces that deliberately declare no primary action.** An empty primary slot is also a
claim, so the ones this migration leaves empty are recorded here with their reason rather than
left to be read as unfinished work:

| Surface | Why no primary action |
| --- | --- |
| Review task (`DecisionWorkspace`, `task === "review"`) | Its act is a *decision* with three outcomes (accepted / rejected / needs attention), not one action. Promoting one outcome into the header would make the platform look like it recommends that outcome, and the three buttons are a deliberate step next to the evidence they judge. The report run beside them is supporting evidence for that judgement, not the task's primary act |
| Market cockpit (`MarketCockpit`) | Read-mostly: it presents curves, observations and context. Its actions are the five canonical AI actions in the rail, which the geography places as offers rather than as a workspace primary |
| Runtime / administration (`RuntimeWorkspace`) | Operator surfaces: readiness evidence, the activity timeline and the diagnostics bundle. Their controls are operational (`refresh`, `cancel`, `prepare`), which the geography keeps beside the thing they act on; none is a compute or persist act of the workspace |
| Sources, glossary, access, settings, manual | Administrative and reference surfaces whose acts are row- or field-local (`save credential`, `update access`, `change language`), i.e. `read`, `utility` or `lifecycle`, none of which occupies the primary slot |

The action-geography enforcement asserts the *inventory* of surfaces that pass a primary action,
so a surface that starts passing one fails the test until its consequence is declared. This
table is the complement: it states which surfaces may not, and why.

**One act, one control - across surfaces, not only inside a file.** The per-file guard above could
not see the failure mode that had actually accumulated: running the pool optimiser was reachable
from **three** buttons - the Decision workspace's primary action, the Scenario panel's own
`optimize pool` control, and the network panel over the market map - all calling the same handler
with the same request. A user had to relearn where "run" lived depending on which tab they stood
in, which is precisely what the geography exists to prevent, and it left the primary slot as one
entry point among several rather than the predictable one.

- The Scenario panel now configures the sandbox economics, reports the preflight blockers and
  shows the allocation the run produced, and says in its own copy that the run starts from the
  workspace's primary action - the same treatment the Optimize task's panel already received.
- The network panel hands the user over to the Decision workspace rather than running a second
  copy of the act from the map. It already had a hand-over control, so nothing was lost, and the
  map keeps the preflight verdict and the result.
- `actionGeography.test.ts` gains a **cross-surface** guard: no surface other than
  `DecisionWorkspace` may reference the pool-run handler, and each surface that hands over must
  name where the run lives. A per-file uniqueness check would not have caught this, so the check
  now spans the surface inventory.

- **Third application (compute).** The agent research surface now puts starting a governed
  research run in that slot, with the same shape as the first: the run is a `compute`
  consequence, the surface's own tab row became a `WorkspaceHeader`, and the action is disabled
  by a rule (`app/model/agentRunModel.ts`) that mirrors the route's contract - an objective of
  8 to 4000 characters and a reachable runtime PostgreSQL, which the run needs because it
  persists its own rows. The disabled action explains itself with the first blocker, and the
  panel carries the full readiness list and the run's disclosures.

- **Fourth application (compute).** The Strategy Lab's backtest task puts running a backtest in
  that slot, and its tab row likewise became a `WorkspaceHeader`. This one needed the draft
  lifted rather than only the rule: the frozen-version requirement, the evaluation period and
  the economic assumptions were all panel state, so the workspace now owns the draft and
  `app/model/strategyBacktestModel.ts` owns the rule (`strategyBacktestReadiness`,
  `strategyBacktestRequest`). The panel renders the fields, reports the preflight blockers from
  the keys it is handed, and no longer starts anything; the header action is disabled by the
  same computation and sends the request the rule composed, so the action and the panel cannot
  disagree about what would run. The panel's configure/result switch stays local: it is a read
  consequence, not the run.

- **Fifth application (persist).** The research surface puts building a dataset snapshot in that
  slot - the act that records a governed artefact and is tracked as a `DATASET_BUILD` job - and
  its tab row became a `WorkspaceHeader`. This one was almost entirely presentational, because
  the workspace already owned the state: the specification draft, the validation outcome and
  `researchBuildGate` all live above the panel, so the lift was to stop rendering a *second*
  build control inside the panel and gate the header action on the same gate. The gate's
  sentence moved into the model (`researchBuildGateLockKey`), so the reason a build is locked has
  one owner rather than an inline ternary in the panel, and the panel keeps the specification,
  the validate step and the line that explains the lock.

- **Sixth application (compute).** The Scenario task puts the route comparison in the slot - the
  other `compute` act the Decision workspace owns - so one workspace now declares a primary action
  per task it runs rather than for only one of them: the optimiser run for Optimize, the
  comparison for Scenario. The panel keeps the sandbox economics, the preflight blockers and the
  economics the comparison produced, and says in its own copy where the comparison starts. The
  cross-surface guard was extended to this act at the same time, so the comparison cannot be
  re-copied into a panel the way the optimiser run had been.

### What is left, and what each one actually needs

Two surfaces still hold a `persist` act inside a panel. Neither is forgotten, and neither is a
rule-extraction away from being finished, so they are recorded with the work they need:

| Surface | The act | Why it has not moved |
| --- | --- | --- |
| Strategy Lab, Design task | `Save draft` (and `Create new version` when the version is frozen) | The draft is **panel state, not a rule**: the whole form (about 25 fields), its validation summary, the request body builder and the busy/message/error state live in `StrategyDesignWorkspace`, so moving the action means lifting that draft to the workspace or into a hook first. The guarded consequences are already right: `Freeze version` changes a version's standing, so it stays a bounded action next to the version it affects and must not be promoted to the slot (`requiresDeliberateStep("lifecycle")` is true). |
| Decision task, Review task | `Record review decision` (three outcomes) and the Decision Case's own persist acts | The review task's primary slot is deliberately empty: its act is a decision with three outcomes, and promoting one outcome would make the platform look like it recommends it (recorded in the table above). The Decision Case panel's acts are form-local persistence inside that same task. |

Everything else that presents a material action is placed: the five `compute`/`persist` applications
above, the Source Center's manual ingestion queue next to the recommendation that asks for it, the
Data Products view (a read), and the surfaces recorded as deliberately having no primary action.

## 7. Fifth slice — the panel taxonomy's disclosure rule, applied and audited

The panel taxonomy states which disclosures a panel owes when it presents a material value:
a figure without its time basis, units, provenance or entitlement state is not decision
evidence. Nothing checked whether the panels that claim to exist could carry them - and the
shared metric strip could not. It rendered a label, a value and a detail, so a unit or an
as-of could only be smuggled into free text by whichever caller remembered.

- The primitive now carries the slots its kind owes: a per-item unit and a strip-level as-of
  and time basis, rendered in a footer that marks each one, and omitted entirely rather than
  invented when a surface does not have them. Items stay the strip's direct children, so
  existing metric-grid layouts and their child selectors are unaffected.
- The agents replay strip is the first caller to use them: it showed run counts with no
  instant, which is exactly the case the taxonomy names, and now reports when the numbers
  were taken.
- `clients/web/tests/panelDisclosures.test.ts` audits the rest instead of assuming it: for
  every panel kind, each owed disclosure must be either carried by a named slot in its owning
  primitive - matched live against that file, so a claim cannot rot into aspiration - or
  recorded as the caller's duty with the reason. A disclosure that is neither fails, and so
  does a claim whose marker has disappeared.

The remaining panel kinds owe their disclosures to their callers, which the audit now states
explicitly per kind rather than leaving implicit.

## 8. What this slice does not claim

Wave 9 in the roadmap is larger than its delivered slices. Still open:

- migrating each workspace's panels onto the panel taxonomy, and replacing the
  per-surface rails, drawers and master-detail panes with the Inspector as the
  default detail pattern (six surfaces now hand subjects over: the market cockpit, the
  contract workbench, the network map, the strategy backtest, the review decision history
  and the capacity point panel; the data, administration, glossary and runtime surfaces
  still show detail locally);
- applying the action geography to every header (the contract and resolver exist;
  `WorkspaceHeader` already owns the primary-action slot, and three consequences are applied:
  the Optimize task's run, the portfolio's contract save and the research run, plus the
  Strategy Lab's backtest);
- the remaining `system`-area views that are not URL-addressable.

These are incremental, file-scoped migrations with their own evidence; none of them
requires a new contract.

## 9. Compatibility

- No route, deep link, page id or workspace composition changed in these slices.
- No API, schema, permission, numerical, release or DR behaviour changed.
- New user-visible vocabulary is bilingual (`en`, `zh-CN`), and the shell surfaces
  add no new colour, type or motion family.

## 10. Verification

- `clients/web/tests/shellSurfaces.test.ts` — inspector region rendered and
  fetch-free, command derivation from the registries, inspection commands from the
  Active Context, explained unavailability, the controller's keyboard and ranking
  model, the store's use of the pure reducer, and bilingual vocabulary.
- `clients/web/tests/inspectorDetail.test.ts` — fact and provenance resolution per
  record shape, absent-is-not-zero, timestamp formatting, the page composition gate,
  explicit non-resolution for unknown refs and kinds, the market hand-over, and the
  panel/shell wiring that keeps the panel free of lookups and fetches.
- `clients/web/tests/contractDraftModel.test.ts` — the contract draft rule as a rule: issue
  keys and their order, the volume/price/cost/fuel-loss thresholds, read-only-library,
  runtime-not-ready and read-in-flight blocking, the view facts' "known" resolution, and the
  wiring that keeps the panel reporting while the header acts.
- `clients/web/tests/agentRunAction.test.ts` — the research run rule and its wiring: the
  route's objective bounds asserted at both boundaries, the runtime-database and in-flight
  preconditions, the request's deliberate omissions (no client-chosen profile, no invented
  period evidence), the strategy-generation disclosure in both states, and every reported key
  present and translated in both locales.
- `clients/web/tests/strategyBacktestAction.test.ts` — the backtest run rule and its wiring:
  the frozen-version precondition, a period asserted to be a real interval at its boundaries, a
  modeled cost that must parse while an unmodeled one is never read, the in-flight blocker, the
  composed request, and the panel that reports without starting.
- `clients/web/tests/experienceArchitecture.test.ts` — updated shell-region
  honesty check: every rendered region carries its marker and nothing remains
  `planned`.
- `clients/web/tests/controlPlaneSeparation.test.ts` — the control-plane gate still
  holds after the shell refactor.
- Full suites: `node --test "tests/*.test.ts"` and `npx tsc --noEmit` plus
  `npm run build` (tsc + vite) in `clients/web`; results are recorded in the
  execution checkpoint.
