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

Next step for whoever picks this up: reproduce it against a React development build with source
maps and a `debugger` on the throw, since the console alone does not name the component. Everything
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
