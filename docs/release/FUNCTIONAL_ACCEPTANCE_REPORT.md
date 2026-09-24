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
