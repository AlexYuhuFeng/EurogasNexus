# Functional acceptance report

**Status: NOT ACCEPTED.** Measured, not asserted: the browser acceptance sweep now checks whether
each surface *renders what its own API returned*, and on 2026-09-19 it reported **140 failures across
the three viewports and both languages**, dominated by one systemic defect.

This report exists because the previous acceptance evidence was green while the product was empty.
The sweep asserted language, one `main h1`, horizontal overflow and axe violations — every one of
which a hidden, empty or unrendered page passes. Nothing in it compared the screen with the data.

## How the gate works

`scripts/uat/browser_workflow_smoke.mjs` now runs a functional check per workspace, from the same
session the browser holds (so it measures the product, not a privileged probe):

1. **The requested page must be the displayed page.** The shell marks the active workspace with a
   `workspace-<id>` class; the check compares that with the deep link. This is the defect that let
   `contracts.png` capture Portfolio → Overview and `orders.png` capture Portfolio → Exposure while
   the run stayed green.
2. **Loading must have finished.** `Loading workspace` must not survive the load.
3. **Data must be rendered.** The surface's own endpoint is read from the page context; if it
   returns rows, the surface must not show an empty/unavailable state. A read with rows and a screen
   with none is a delivery defect, not a cosmetic one.
4. **No uncaught page error, and no console error outside a declared allowlist.** React reports its
   internal errors through the console, which is why the previous pageerrors-only listener never saw
   them.

## The measured state

| Finding | Occurrences | Surfaces | Class |
|---|---|---|---|
| `Internal React error: Expected static flag was missing. Please notify the React team.` | 101 | all 16 workspaces, both languages, all viewports, plus the interaction and agent-research flows | **blocking — systemic** |
| A read returned rows and the surface rendered none of them | 21 | `review` (5 rows), `orders`, `runtime`, `settings` (1 row each) | **blocking** |
| `Loading workspace` still shown after load | 6 | `capacity`, `research` — and `glossary`, `agents` (declared) | **blocking** |
| The requested workspace page is not displayed | 6 | `network` (the market map surface) | **blocking** |
| Resource 404 in the console | 6 | `contracts` | blocking |
| Declared functional gaps carried forward | 21 | `market`, `glossary`, `agents`, `access` | blocking, measured |

### What the React error means

`Expected static flag was missing` is a react-dom internal consistency error raised while rendering:
it usually means **two copies of React, or a react / react-dom pair from different versions**, or a
compiled component tree whose flags disagree with the runtime that renders it. It is not cosmetic —
it fires on every workspace, and a renderer in that state is a credible explanation for surfaces
that mount, fetch nothing, and stay on their loading placeholder. It is the first thing to fix, and
it is one dependency or build configuration, not sixteen surfaces.

### The React error's measured shape

Probed directly rather than guessed at:

- it fires **once per application mount**, not once per workspace - the gate's 101 occurrences are
  101 mounts (16 workspaces x 2 languages x 3 viewports, plus the interaction and agent flows), so
  this is an app-boot condition rather than a per-surface one;
- it carries **no component stack**: React reports it as a plain console error, which is why a
  `pageerror`-only listener never saw it and why the sweep now listens to the console;
- `react` and `react-dom` are both **19.2.6** with a single copy in `node_modules`, so it is not a
  version skew or a duplicated React;
- `index.html` has an empty `#root` and no server-rendered markup, so it is not a hydration
  mismatch against a stale SSR build.

The suite now installs a `console.error` wrapper before the app loads
(`installReactErrorStackCapture`) so the next run records a stack beside the message. **It did not
fire in this environment**: the error is still reported by the console listener with no stack, which
means React is not reaching the page's `console.error` through the patched global — worth knowing
before someone spends an afternoon on the wrapper. The remaining candidates are a second `react-dom`
instance inside a dependency bundle reaching its own console reference, or the error originating in a
context the init script does not cover. Reproducing it against a React development build with source
maps and a breakpoint on the throw remains the direct route. Everything
else in this report is secondary to it: a renderer in this state is a credible cause of surfaces that
mount, fetch nothing and stay on their loading placeholder, and fixing it may clear a large part of
the 140 failures above.

### What the visual review adds to it

Reading the screenshots with a vision model (`deepseek-v4-flash-vision-exp`) produced ~24 further
findings, listed in the run's evidence, of which the recurring ones are: surfaces reporting
`unavailable`/`n/a`/`0` while their endpoints answer 200 with data; below-the-fold content sliced by
the viewport (Settings token field, Research `Validate spec`, Runtime `Release blockers`); truncated
table headers (`FIRM TECHNI…`, `CAPACITY POST…`); empty panels with no empty-state sentence; and, in
the Chinese build, English residue (`ADMIN`, `n/a`, `UTC`, `P&L`, `LLM`, `Release`) with
machine-translation grammar and mixed punctuation.

## What is required before this can be accepted

1. **Resolve the React internal error** (dependency/build), then re-run this gate. Expect the
   failure count to drop sharply; if it does not, the remaining failures are genuinely per-surface.
2. **Fix the read-to-render class**: `review`, `orders`, `runtime`, `settings`, `market`, `access`,
   `glossary`, `agents`, `capacity`, `research`. The pattern is a surface that loads data and renders
   none of it, or never leaves `Loading workspace`.
3. **Fix the `network` deep link** so the map surface displays at all.
4. **Fix the `contracts` 404** and confirm the workspace's own page renders.
5. **Re-capture the acceptance screenshots** once the above pass: today `contracts.png` and
   `orders.png` are evidence for other surfaces, so those cases are unverifiable.
6. **Finish localisation** to a commercial standard, not a machine-translated one.
7. Then close the external items (penetration test, OIDC TLS review, production restore drill,
   provider certifications, signing, user acceptance) recorded in
   [HANDOVER_INDEX](../deployment/HANDOVER_INDEX.md).

## Honest limits of this report

- It measures a **local UAT deployment** (seeded PostgreSQL 16, dev API, Vite), not production.
- Its screenshots are captured per workspace at three viewports in two languages; the layout claims
  come from a vision model reading those images, and the DOM claims from the running page.
- The gate does not yet assert *values* (a price matches the API's price); it asserts that a surface
  with data is not rendering an empty state. Value parity is the next tightening.
- The failure count depends on the seeded fixture. An empty fixture would legitimately render empty
  states; this run's fixture has rows in the endpoints named above, which is why each finding is
  stated with the endpoint that returned them.

## 2026-09-25 — the contracts/orders read-to-render group was the gate's own inference

CI run `35996627042` reported nine functional failures: `contracts` (three) and `orders` (six).
Neither was a surface that failed to render its read, and the evidence is in the run's own artifacts
(`output/ci-35996627042`):

- **The verdict came from page copy, not from rows.** The only producer of that failure is
  `apiRows > 0` combined with a whole-page match of `n/a|unavailable|no records|no data|not
  (available|read|configured)` over the first 400 characters of the displayed page. The matched text
  is therefore always copy: the portfolio context strip's own sentence, "N slice(s) stale, missing or
  unavailable", is rendered early on both pages because this payload has slices that are `MISSING`
  with no rows (`screen_orders`, `pnl_snapshots`, `data_sources`, `summary`) and `contracts` is
  `UNKNOWN` (a gas-year contract carries no observation instant). In Chinese that sentence contains
  no matchable word, which is exactly the shape the failures took: `contracts` failed in English
  only, `orders` in both languages (its tables render a language-independent literal `n/a` in their
  empty states, and the Chinese page fits more of itself into the same 400-character window). The
  artifact captured no page text, so the exact substring is identified from the components and the
  payload states rather than quoted from a capture.
- **The orders probe read an endpoint the surface does not use.** `api.log` records
  `/api/portfolio/live-summary` exactly six times - once per orders scope, all six from the probe -
  while the surface's own read, `/api/projections/portfolio-snapshot`, is read 97 times (once per
  scope). The probe's "1 row" was not a row: the gate counted any non-array body as one row, and a
  summary aggregate is an object.
- **Nothing in the seed writes those tables.** Neither `scripts/ops/seed_preview_runtime_data.py` nor
  `scripts/uat/seed_uat_fixture.py` inserts screen order or PnL snapshot observations, so the orders
  surface's empty state was the truthful rendering of a measured zero.
- **The contract row is rendered.** The one returned upstream contract is the resource-pool row the
  Portfolio Overview task renders (`portfolio_resource_from_contract` maps `contract_id` to
  `resource_id` and `contract_name` to `resource_name`), so the read had a rendered row all along.

### What changed

The gate now compares returned rows with rendered rows by exact record identity
(`scripts/uat/readToRender.mjs`, exercised by `clients/web/tests/readToRender.test.ts`): the orders
probe reads the projection's `screen_orders` and `pnl_snapshots` slices, the contracts probe keeps
reading the upstream-terms route the client lane reads, and a returned row whose own id no visible
row carries fails by name.

The evidence is scoped rather than inferred, which was the review finding on the first version of
this helper:

- **Per group, not per page.** Each group names the selector its own rows are rendered under
  (`[data-record="<kind>"]`), and only elements that selector matches inside the displayed page are
  its evidence - another panel's rows cannot answer for it. The pool row, the contract library row,
  the screen-order row and the PnL row now carry `data-record-id` with the record's own identifier
  (`resource_id`, `contract_id`, `order_observation_id`, `pnl_snapshot_id`); the contracts group
  accepts the pool row because the backend maps `resource_id` from `contract_id` in
  `portfolio_resource_from_contract`, and that mapping is asserted by
  `tests/contract/test_browser_probe_paths.py`.
- **Exact ids, not substrings.** `contract-1` no longer matches a page that rendered `contract-11`,
  because the comparison is string equality on the collected attribute rather than `includes` on the
  row's text.
- **One element is one row.** Overlapping selectors are de-duplicated by element, so a single
  rendered row cannot satisfy two returned rows; duplicate rows need duplicate rendered rows.
- **Empty means empty.** A successful empty read is checked against the surface's declared
  `data-empty-state` marker (the former orders selector matched any row in the table, so a stale
  populated table passed), and a populated row left under the group's selector now fails the check
  instead of answering it.
- **Unmeasurable is a failure, not a pass.** A returned row that carries no record id, a slice that
  serves rows without declaring availability, a group that declares no rows path, record id field or
  selector, and evidence that does not match the declared groups all fail rather than joining the
  observations. A hidden (`display: none` or zero-size) row is still not evidence, a slice the
  backend did not serve is still reported as unmeasured, and a read that did not answer 200 still
  fails rather than passing quietly.

No exemption, console filter, axe relaxation, fixture row or authorisation change was made, and the
declared gaps for the other surfaces are untouched.

### Limits of this repair

- Verified here by unit and contract tests only (625 web tests, 7 contract tests, `tsc`); **no live
  browser run was performed in this environment**. Re-running the acceptance sweep is the next step.
- With no imported screen orders in the fixture, the orders check reports a measured zero rather than
  proving rows are rendered; it will assert rows as soon as a deployment holds them.
- The contracts probe's deep link lands on the Portfolio Overview task, which declares no empty-state
  row for an empty pool, so an empty contracts read is reported as unmeasured rather than as a
  missing empty state; the contract library's own `data-empty-state="contract-library"` marker is in
  place for the library view.
- A rendered row the read did not return is only a failure when the read is empty (stale rows); in a
  populated group the read's rows must all be present, but extra rows are not yet attributed.
- Value parity (does a rendered price equal the API's price) remains the next tightening.

## 2026-09-25 — the glossary term index and article are measured, and their exemption is retired

The glossary carried two declarations from the 2026-09-19 run: a functional gap ("glossary terms
return rows while the term index renders 'Loading workspace'") and a surface defect whose reason was
"the surface's own read never completes on a fresh login". They were investigated against the
current store and component and against the last full acceptance artifact (`output/ci-36032330807`,
run `69dd695`, 96/96 checks green):

- **The declaration was stale after the September 24 loader repair.** `GlossaryWiki` takes its
  term-index badge from `api.workspaceLoading` (the workspace batch's own settled lifecycle), and
  the article's "Loading workspace" copy is reachable only when the surface holds no term at all -
  so a failed or absent read is what the old declaration described. Run `36032330807` recorded
  neither a failure nor that declared defect for the glossary scope, and that check does not depend
  on the probe's own read: had the surface held no term, its article fallback would have rendered
  "Loading workspace" and the declaration would have fired. It did not, so the term index was
  rendering. What remained true is the weakness the declaration exposed: it was a statement about
  page copy, and the Chinese scopes could never be compared at all.
- **What replaces it.** The glossary signal now declares a scoped read group (`rowsPath: "data"`,
  `recordIdField: "term_id"`, selector `[data-record="glossary-term"]`, empty state
  `[data-empty-state="glossary-terms"]`): every term `GET /api/glossary?limit=5` returns must be one
  the left term index rendered, as a card carrying that term's own id. The comparison is
  language-independent and per row, so a missing term, a hidden card, a card carrying another term's
  id, a row without an id and a read that did not answer 200 are failures rather than passes. The
  probe is the same route the client lane reads (`api.glossary`), and the contract module
  `tests/contract/test_browser_probe_paths.py` holds the declaration against the served payload and
  the component that renders it.
- **The two-pane interaction is asserted, not assumed.** `interaction/glossary-term-selection` opens
  the surface, holds the opening article to a term the read returned, clicks a *different* term in
  the index and requires the wiki article to carry the clicked term's own record id and to render
  that term's definition from the same read; it then filters the index by that term's own name,
  which must keep the term in the index and the article on it. That is the "left term index selects,
  right wiki article follows" behaviour the b566459 walkthrough (`docs/ux/POST_CR15_UI_AUDIT.md`)
  recorded visually, with no executable assertion until now; the filter is checked against the one
  query whose answer the read states itself, so the harness does not reimplement the filter's
  matching rule.
- **What did not change.** No permission, database, credential, route or payload change; no new page;
  no visual redesign and no copy change. Market, capacity, sources, access, research and agents keep
  their declared gaps exactly as they were. The 2026-09-19 table above is that run's measurement and
  is not rewritten.

### Limits of this repair

- Verified here by the web suite (`readToRender.test.ts`, `browserSmokeGates.test.ts`), the contract
  suite (`tests/contract/test_browser_probe_paths.py`) and `tsc`; **no live browser run was performed
  in this environment**. The CI browser job is the evidence for the interaction, and it is the first
  run in which the glossary index is compared per row in both languages.
- The probe reads five terms while the surface renders its own list (bounded at 40, and the built-in
  catalogue holds 31), so the check proves the index rendered the terms the read returned, not that
  it rendered every term a deployment holds. That bound was re-measured against the route's real
  payload outside the browser: all 31 rendered ids matched the five returned ones, and a hidden,
  missing or substituted card failed by name.
- The article's definition is compared with `definition_en`, because the interaction check runs in
  English; the Chinese article is covered by the term-id comparison only.

## 2026-09-25 — the Source Center's catalog, selection and category filter are measured

The source surface carried a declared functional gap from the 2026-09-19 run: "sources return rows
while the administration surface reports Total sources 0" (`output/ci-36032330807`, run `69dd695`,
96/96 checks green with six declared gaps). It was investigated against the current store and
component:

- **The declaration was page copy, not a measured row.** The only producer of that observation is
  the older whole-page check: `apiRows > 0` combined with a match of
  `n/a|unavailable|no records|no data|not (available|read|configured)` over the page's first 400
  characters - and this surface renders language-independent `n/a` literals of its own: the
  operations table's "Last success" cell is `formatUtcTimestamp(...)` with an `n/a` fallback, and
  the detail panel's freshness, circuit-state and last-ingestion fields fall back to `n/a` too
  (`formatUtcTimestamp`, `sourceLabel`). The artifact captured no page text, so the exact token is
  identified from the component and the fixture rather than quoted from a capture; the Chinese page
  fits considerably more of itself into the same 400-character window, which is the shape the three
  recorded occurrences take.
- **The phrase cannot describe this component.** The metric strip's "Total sources" value and the
  catalog's rows are the same array: `sourceStats.total` is `buildSourceStats(api.sources).total`
  and the catalog's rows are `filterSourcesByCategory(api.sources, category)`. A zero KPI beside a
  rendered table is therefore not a state this surface can produce, and the reader (a vision model
  over the screenshots) was describing an image, not a measurement.

### What replaces it

The surface now declares a scoped read group instead of an exemption, and the row evidence is
exact:

- **The right task, not the filtered one.** `GET /api/sources` answers the whole static registry
  (24 registered sources, no page parameter - the same unbounded read the client lane performs), and
  the surface opens on its *priority queue*, which is that read filtered down to the sources needing
  attention. The group therefore names the catalog task (`taskTab: "source-tab-catalog"`): the sweep
  activates the surface's own catalog tab before collecting evidence and restores the tab that was
  active afterwards, so the screenshot keeps showing the task the deep link opened. Comparing the
  queue with the unfiltered registry - the filtered-UI-against-unfiltered-rows mistake - is what the
  declaration exists to prevent.
- **Exact ids, both directions.** Each catalog row carries its registered source's own id
  (`data-record="source-row"`, `data-record-id={source.source_id}`), and the group declares
  `recordIdField: "source_id"`. Because the catalog renders the whole registry rather than a bound
  over it, the comparison is two-directional (`exactRows`): a returned row no visible row carries is
  a failure, and a rendered row the read did not return is a failure too - each named by id. A
  hidden (`display: none` or zero-size) row is not evidence, and an empty successful read must show
  the table's declared `data-empty-state="source-rows"` row.
- **The workflow is exercised, not inferred.** `interaction/source-center-selection` compares the
  catalog with the same read by exact id, holds the detail panel to a source the read returned,
  clicks a *different* row and requires the panel to follow that row's own record and to render that
  source's own system name from the read, and then exercises the surface's category filter on the
  category the read itself declares for that row: the filtered table must hold exactly the read's
  rows of that category - none missing and none foreign - and asking for "all" again must bring the
  whole read back. The filter control carries its category code
  (`data-source-category={category}`), so no localized label is ever matched. The interaction
  clicks only the surface's own task, row and filter controls: no ingestion run and no credential
  write is performed.
- **The surface's filter workflow is its category filter and its view tasks.** This surface has no
  free-text search control - the two inputs it renders belong to the credential form in the access
  task - so "filter" here means the category rail (exercised above) and the task tabs (the catalog
  itself, whose activation is the scoping mechanism). A text-search check would have to be invented
  for a control the surface does not have.
- **What did not change.** No permission, database, credential, route or payload change; no new
  page; no visual redesign and no copy change. Market, capacity, access, research and agents keep
  their declared gaps exactly as they were. The 2026-09-19 table above is that run's measurement and
  is not rewritten.

### Limits of this repair

- Verified here by the web suite (`readToRender.test.ts` negative cases for the missing, hidden,
  foreign, stale-row and non-200 answers; `browserSmokeGates.test.ts` for the declaration, the task
  activation and the interaction), the contract suite (`tests/contract/test_browser_probe_paths.py`,
  which holds the probe path, the record id and the component markers against each other) and `tsc`;
  **no live browser run was performed in this environment** (no local API or database is
  reachable). The CI browser job is the first run in which the catalog is compared per row, in both
  languages and at all three viewports.
- The comparison proves the *table* renders the read's rows. The metric strip's own KPI copy is not
  asserted; it is derived from the same array the compared rows come from, so the two cannot
  disagree in the direction the old declaration described.
- A registry read that fails in the workspace batch leaves the surface holding no source and
  rendering "Total sources 0" with no error copy of its own (the surface takes no endpoint-error
  prop). That state now *fails* the sweep by name - the read answers in the same session the surface
  does not reflect - rather than being carried as a declared gap. Surfacing the read's own failure
  on the Source Center remains open, as does the same disclosure question on the other surfaces.
  **Closed on 2026-09-27**: the surface now states the read's own pending, failure and measured
  states; see the section below. The disclosure question on the other surfaces is untouched.
- The interaction covers English desktop only; the catalog comparison covers both languages and all
  three viewports. The category filter's expected answer is the read's own `category` field, so the
  check proves the filter hides exactly the rows that field excludes - it does not re-derive the
  surface's category vocabulary, which `source_registry.py` owns.

## 2026-09-27 — the Source Center states its own registry read, failure included

The 2026-09-25 section left one thing open by name: a registry read that fails in the workspace
batch left the surface holding no source and rendering "Total sources 0" with no error copy of its
own. That state is now its own reading:

- **A slice cannot tell a failed read from a measured zero.** The workspace batch clears `sources`
  when its read fails (and the market lane's own refresh keeps the rows it holds), so the surface
  had no way to distinguish "the platform says there are no sources" from "the platform never
  answered". `app/model/sourceRegistryRead.ts` names the five states the store's facts support -
  `unread`, `pending`, `failed`, a measured `empty`, a measured `ready` - and only a committed
  reading may present a number (`hasReading`). The KPI strip and the catalog table are drawn only
  for a committed reading; a failure that still holds rows keeps them and says they are the last
  committed reading, and a failure with no rows presents nothing but the failure.
- **The failure is stated in the surface**, with the shared endpoint vocabulary the shell's own
  banner uses (`workspace.endpoint.sources` plus the safe code message - never the backend's prose,
  never a raw loader key) and the store's existing bounded retry exposed for this read. The retry is
  one control calling `retryFailedWorkspaceEndpoints`, disabled and `aria-busy` while its attempt is
  in flight; the store keeps refusing a second concurrent attempt. No new endpoint, credential,
  permission or loader was added.
- **The measured empty registry is its own sentence.** The catalog's empty row said "No active
  warnings" - a statement about the review queue - and now says the registry read answered with no
  registered sources, so a measured zero cannot be read as a fresh registry.
- **Bilingual and pending/empty/failed states are declared copy**, in both locales, asserted by the
  web suite; the unread, pending and failed sentences are distinct in each locale.

### How it is measured

- **Executable states through the actual store** (`clients/web/tests/sourceRegistryRead.test.ts`):
  a batch that has not answered is `pending` with no count; a successful empty read is `empty` and
  is allowed to state zero; a refused read is `failed` with no count and the shared vocabulary; the
  scoped retry recovers the read (disabled while its attempt is in flight, and a second caller
  issues no request); losing the identity leaves the registry `unread` rather than carrying the
  failure into the new session.
- **The browser error path, refused by the harness itself** (`interaction/source-registry-failure`):
  exactly `GET /api/sources` is intercepted and answered 503, nothing else the page reads; the
  surface must declare `data-source-registry-state="failed"` with its notice, and must present no
  measurement at all - no source row, no `data-empty-state="source-rows"` marker, no KPI strip; the
  interception is then removed and the surface's own retry must render exactly the registry
  `GET /api/sources` then serves, by each source's own `source_id`, with the notice gone. The
  console entry the browser reports for the harness's own refusal is attributed to that exact
  request URL (never added to the declared allowlist, which still carries only the pre-login 401)
  and counted in the summary as an observation.
- **The rules are pure, so their negative cases run without a browser**
  (`scripts/uat/readToRender.mjs`: `evaluateRefusedRegistry`, `evaluateRegistryRecovery`;
  `clients/web/tests/readToRender.test.ts`): a surface reporting any other state, a rendered row, a
  measured-empty marker, a KPI strip, a missing retry or a disabled idle retry each fail by name,
  and a recovery that keeps the notice, drops a returned source or renders a foreign one fails too.

### Limits of this repair

- Verified here by the web suite (646 tests, ten of them added by this repair), `tsc`, the repository
  lint/contract tests (`tests/contract/test_browser_probe_paths.py` holds the refusal to the read
  the catalog compares and to the component's own markers) and `node --check` on the harness;
  **no live browser run was performed in this environment** (no Playwright installation, and the
  local API/database were not exercised). The CI browser job is the first run in which the refusal
  path is walked end to end.
- The failure interaction covers English desktop only, like the other interactions; the pending and
  unread copy is covered in both locales by the web suite and the locale parity gate.
- The change is presentation-only: no route, permission, payload, schema, credential or ingestion
  behaviour changed, and no source-registry write is performed by the check.
- The same disclosure question on the other surfaces that render a shared slice (capacity, access,
  research, agents and the remaining market cells) is untouched and stays open.

## 2026-09-27 — the market hub board is measured against the projection it prices

The market workspace carried the last copy-based declaration in the sweep: "market observations
return rows while every hub card renders n/a - recorded by the visual review and not yet fixed". It
was investigated against the store, the components, the projection contract and a read-only read of
the local runtime database:

- **The probe read an endpoint the lane does not call.** `SURFACE_SIGNALS.market` read
  `/api/market/observations?limit=5`, while the market lane reads one coherent projection
  (`GET /api/projections/market-context`, `api.marketContext`) and the numeric task (`curves` - the
  market primary's default landing view) prices its hub board from that payload's `quotes` slice
  (L1 bid/ask) or, for a hub with no quote, its `normalized_quotes` slice. The declaration itself
  was a statement about an image, produced by the visual review; the whole-page heuristic could only
  have matched the page's own `n/a` literals (`formatPrice`, `formatDelta`, `formatCadence` and the
  empty FX row all render one), so it could say nothing about which hub was unpriced.
- **The projection serves the pairs the board prices.** Read directly from the local runtime
  database (read-only, no HTTP login and no writes): the `quotes` and `normalized_quotes` slices
  each answered 500 rows covering all six major hubs for `day-ahead` - so on this deployment the
  board had a row to price for every hub card, and the honest question is not "does it render
  something" but "does the price it shows belong to the row it priced".
- **The recorded symptom is not reproduced here, and it is not declared fixed.** The declaration
  came from a review of a screenshot from a run whose payload and probe are not the ones this
  environment can reproduce (the probe read a different endpoint, and this environment has no
  Playwright installation), so whether every hub card still renders `n/a` on the CI fixture is
  exactly what the new check decides rather than what this section assumes. What is established
  here is that the *claim* can now be measured: a card that renders no price for a pair the read
  served fails by name.

### What replaces it

The declaration is retired rather than moved. The market signal now declares `quotedBoard`, and the
probe reads the projection the lane reads - for the Active Context the shell is displaying:

- **The displayed request context is captured, not assumed.** The shell states the Active Context it
  shows in machine-readable form (`data-context-gas-day/-product/-hub` on
  `.topbar-context-disclosure`), and the sweep composes the projection query from it with the
  client's own omission rule (product omitted when "all", hub omitted when unfocused -
  `app/model/projectionContext.ts`). A focused board is therefore never compared with another
  context's payload, and a context the sweep cannot read is a failure rather than a silent
  unfiltered read.
- **The board declares what it prices.** The strip declares the hub scope it prices (the model's
  `MAJOR_MARKET_HUBS`) and the tenor it displays (`data-board-tenor`, held to its own active tenor
  tab), and each card declares the row it priced - the record's own id and the slice it came from
  (`quotes` or `normalized_quotes`) - its pair (`data-price-tenor`) and the elements the operator
  reads (hub label, price, meta line, source pill).
- **The verdict is per card and by value** (`evaluateQuotedBoard`): the visible price numbers must
  be the row's own numbers (bid/ask for a quote, the normalized price otherwise; tolerance 0.005,
  the surface's own two-decimal display), the visible source label must be the row's source system,
  the visible text must carry the unit of the row's currency/unit, and the card's declared pair must
  be the pair the read places that row on - at the tenor the board is showing.
- **Missing, hidden and stale are separated from zero.** A pair the read served must be priced by a
  visible card, so a card showing `n/a` for a served pair fails by name and a hidden card is not
  evidence at all; a card that prices nothing is accepted only when the read served that pair no
  row (stated as an observation, "not served" being different from a measured zero); a card naming a
  row the read did not return fails (stale, other-context or foreign); an unread projection (any
  status but 200) or a projection whose price slices were withheld is reported as *unmeasured*.
  Rows of hubs or tenors outside the board's declared scope are counted as observations instead of
  being demanded of a board that legitimately prices one tenor of six hubs at a time, and so are
  served rows the board's own price rule excludes (the backend's `is_gas_price` flag, the same
  predicate the terminal's filter reads) - a card that prices one anyway fails.
- **The surface's own reading is waited for.** The market lane reads its projection outside the
  workspace batch, so the batch's settled state does not cover it: the sweep waits, bounded, for
  the surface to state a projection reading and fails if it never does, instead of judging a board
  whose read is still in flight.

### How it is measured

- **Negative cases run without a browser** (`clients/web/tests/readToRender.test.ts`): wrong price
  (named with both numbers), wrong tenor, wrong hub, a row the read did not return, a served pair
  with no card, a card that prices nothing for a served pair, an unpriced pair the read did not
  serve (honest), a hidden card, a wrong source, a missing unit, a stale or absent as-of, an unread
  projection, a payload whose price slices were withheld, and a card pricing a row the board's own
  gas-price rule excludes. The in-page collector is exercised against a stub page for the
  hidden-card rule, like the group collector before it.
- **The declaration is held to the product**: `clients/web/tests/browserSmokeGates.test.ts` asserts
  the signal, the displayed-context capture, the branch wiring (the pure rule, failures and
  observations, the bounded wait) and the components' markers;
  `tests/contract/test_browser_probe_paths.py` holds the probe to the route the client declares, the
  hub scope to `MAJOR_MARKET_HUBS`, the compared fields to the payload builders (`quote_id`,
  `bid_price`, `ask_price`, `currency`, `unit`, `source_system`; `observation_id`, `price`, `hub`,
  `tenor`), the context mapping to the client's own, and the unit/as-of mirrors to the client's
  formatter and display rule.
- **The rules were run against a real payload**: the projection read from the local runtime
  database was replayed offline through `marketBoardRows` and `evaluateQuotedBoard` with the cards
  built the way the component builds them (newest quote per hub/tenor, else the newest normalized
  observation). The faithful board passed with no failure and named which slices it compared; a
  tampered price failed naming both numbers and the row, and a dropped card failed naming the served
  pair. This is a measurement of the *rules* against real data, not a browser run.

### What did not change, and the limits of this repair

- No API, database, permission, credential, route, payload or calculation change; no new page; no
  ingestion or market-data write. One visible token changed: a bid/ask card now names the unit it
  prices in (`… Bid/ask · EUR/MWh · Quote age 3s …`), because the check requires the unit of the
  row to be visible and a bid/ask without a unit is not a readable quote. The FX table, the curve
  lanes, the source matrix, the market overview's own hub board and the terminal table's other
  columns are unchanged and not asserted.
- Verified here by the web suite (656 tests, ten of them added for this board: nine board cases and
  the sweep-declaration gate), `tsc` (exit 0), the repository lint and the full Python suite
  (1,961 passed, 20 skipped, 1 failed - the pre-existing sandbox permission failure in the
  Markdown-link module, which cannot write outside the repository root here and is unrelated to this
  change). **No live browser run was performed in this environment** - Playwright is not
  installed and child-process spawning is denied in this sandbox, so `vite build` and the default
  isolated test runner cannot run here either; the CI browser job is the first run in which the
  board is compared card by card, in both languages and at all three viewports.
- The board is measured one displayed tenor at a time and only for the six declared hubs. A row of
  another hub or tenor that the board does not show is reported as an observation; it is not
  compared, and no claim is made about the curve lanes, the regional spread list or the source
  matrix. Coverage requires a card for every served pair, but accepts whichever served row of that
  pair the surface chose - the sweep does not re-derive the surface's "newest per pair" rule.
- The value evidence is DOM text and the row's own numbers: a label clipped by CSS (`text-overflow`
  on the source pill) still counts as displayed, and the as-of is compared with the instant the
  surface itself declares (the lane polls, so the distance between the surface's reading and the
  sweep's own read is reported as an observation, not required to be zero). The card's relative
  "quote age" is computed from the browser's clock and is not compared, and the row's delivery
  period (`period_start_utc`/`period_end_utc`) is not printed on the card, so the pair the check
  holds is the row's own hub and tenor. Where a deployment holds no quote for a hub, the card falls
  back to the normalized observation and is compared against that row; both paths are covered, and
  neither is compared against a row from the other slice.

## 2026-09-27 — the capacity operating board states its own read, failure included

The 2026-09-27 capacity diagnosis left one confirmed defect in this report's own words: the
operating board renders `0 / 0` and the sentence "No operating points match the current filters."
without distinguishing a read that has not answered from a measured zero. The board's rows are a
join of **two** workspace reads keyed `point_id:direction` (`flows` and `capacity`), and the batch
clears the rows of a read that failed, so the surface had no way to tell "the platform served no
operating point" from "the platform never answered the capacity read". That state is now its own
reading:

- **Six states name what the board knows** (`app/model/capacityOperatingBoardRead.ts`): `unread`,
  `pending`, `failed`, `partial` (one required read did not answer and the other's rows are held),
  a measured `empty`, and a measured `ready`. The facts are the ones the store already keeps - the
  batch's failure records and safe codes for the two lanes, the committed-pass count and the
  bounded retry's bookkeeping - exactly as the Source Center's registry lane derives its own.
- **No count, KPI or filter result without both reads.** The board's KPI strip (including the
  "latest operational update" instant), the `N / M` row count, the "no comparable live capacity
  points" warning and the filter sentence are drawn only for a board whose two required reads both
  answered. A read that did not answer can no longer appear as a board of zero - the recorded
  defect could only ever be reached from a failed, unread or pending lane, because a committed
  non-empty read always renders rows.
- **A partial board keeps the reading that answered, and says so.** When the flow read answers and
  the capacity read does not (or the other way round), the rows it holds stay on screen - the
  arithmetic, the join key, the posture rule and the 85%/24h thresholds are unchanged - with an
  explicit incomplete-read notice naming the read that did not answer. Nothing is claimed as the
  complete joined board.
- **Measured empty ≠ filter matched nothing.** A board whose two reads answered with no row states
  that (its own sentence and its own `data-empty-state` marker); the filter sentence is made only
  for a fully measured board whose filters exclude the rows it has, and under its own separate
  marker. A read that did not answer makes neither claim.
- **The failure is stated in the surface**, with the shared endpoint vocabulary the shell's banner
  uses (`workspace.endpoint.capacity`/`flows` plus the safe code message - never the backend's
  prose, never a raw loader key) and the store's existing bounded retry
  (`retryFailedWorkspaceEndpoints`), disabled and `aria-busy` while its attempt is in flight. No
  new endpoint, fetch path, credential, permission or loader was added, and no calculation moved
  into the component.
- **Bilingual**: every state's sentence is declared in both locales and asserted by the web suite;
  the unread/pending/failed/partial sentences are distinct in each locale, and the measured-empty
  sentence is not the filter sentence in either.

### How it is measured

- **Executable states through the actual store** (`clients/web/tests/capacityOperatingBoardRead.test.ts`):
  a fresh session is `unread`; a batch in flight is `pending` with no reading; both reads answering
  empty is a measured `empty` that may state zero; one refused read with the other read's rows held
  is `partial` with the shared vocabulary and no KPI claim; both refused with no rows is `failed`
  with nothing that reads as a count; the scoped retry recovers the board (disabled while its
  attempt is in flight, and a second caller issues no request); losing the identity leaves the
  board `unread` rather than carrying the failure into the new session. The pure states' negative
  cases (precedence, `measured` gating, unknown failure codes, raw-key leakage) run in the same
  file.
- **The browser error path, refused by the harness itself** (`interaction/capacity-board-failure`):
  exactly `GET /api/physical/capacity` is intercepted and answered 503, nothing else the page
  reads; the board must declare `data-capacity-read-state="failed"` or `"partial"` with its notice
  and the endpoint vocabulary, and must present no measurement at all - no KPI strip, no
  `data-empty-state="capacity-operating-points"` marker, no filter result, and no row at all in the
  `failed` state; the interception is then removed and the board's own retry must leave it stating
  the reading its two reads then serve (`ready` when either served a row, the measured `empty` when
  both answered with none). The console entry the browser reports for the harness's own refusal is
  attributed to that exact request URL (never added to the declared allowlist) and counted in the
  summary as an observation.
- **The rules are pure, so their negative cases run without a browser**
  (`scripts/uat/readToRender.mjs`: `collectCapacityOperatingBoard`, `evaluateRefusedCapacityBoard`,
  `evaluateCapacityBoardRecovery`; `clients/web/tests/readToRender.test.ts`): a board reporting any
  other state, a row it should not hold, a measured-empty marker, a filter claim, a KPI strip, a
  missing or disabled retry, and a recovery that keeps the notice, claims a filter for a measured
  empty read, drops the measured-empty marker, states no measurement or renders no row for rows its
  reads served - each fails by name.
- **The declaration is held to the product**: `clients/web/tests/browserSmokeGates.test.ts` asserts
  the refusal route, the branch wiring (the pure rules, the fail-closed recovery read, no console
  exemption) and the components' markers; `tests/contract/test_browser_probe_paths.py` holds the
  refusal to the client lane's own `/physical/capacity` and `/physical/flows` reads, the six
  states to the model, and the copy to both locale files.

### What did not change, and the limits of this repair

- **The exemption is not retired.** The capacity entry in `KNOWN_FUNCTIONAL_GAPS` stays declared
  with its original probe, because the proper replacement - comparing the board's visible joined
  keys against *both* reads - is a separate, larger milestone and is not claimed here. This change
  adds a disclosure path and browser evidence for a refused read; it does **not** compare a single
  returned row with a rendered row on this surface.
- **Presentation and disclosure only**: no API, route, payload, database, migration, permission,
  entitlement, credential or ingestion change, no new page and no new fetch machinery. The join
  key, the three capacity roles, the utilization/booking/headroom arithmetic, the 85% constrained
  threshold and the 24-hour staleness window are untouched, as are the storage and LNG views.
- **Verified here by the web suite (668 tests, eleven of them for this board), `tsc` (exit 0), the
  focused Python contract group (`tests/contract/test_browser_probe_paths.py`, 14 passed) and
  `node --check` on both harness modules.** **No live browser run was performed in this
  environment** - Playwright is not installed and child-process spawning is denied in this sandbox
  - so the CI browser job is the first run in which the refusal path is walked end to end.
- The refusal interaction covers English desktop only, like the other interactions; the pending,
  unread and partial copy is covered in both locales by the web suite and the locale parity gate.
- **The populated-deployment half stays unexercised here.** In the CI fixture the capacity and flow
  reads answer with no rows, so the `failed` → `empty` recovery is what is walked; on a deployment
  with ENTSOG ingestion the same check exercises the `partial` → `ready` path (rows kept, then the
  joined reading restored) without comparing the rows themselves. Which `capacity_type` values
  legitimately count as firm technical/booked, whether a measured-empty or failed board should keep
  last-committed rows with a disclosure, whether points without TSO access/tariffs should be
  excluded, and whether acceptance may seed physical observations at all remain parent decisions
  and were deliberately not inferred.
