# Post-CR15 UI Audit

Status: **in progress; not whole-product acceptance**

Baseline: `cfbcd58`, 2026-09-07. See the [campaign plan](../engineering/UX01_EXECPLAN.md)
and [CR1-15 matrix](CR1_15_REGRESSION_MATRIX.md). Component counts are being
collected separately. No frontend refactor preceded these observations.

## Runtime truth

The repository was fetched and main was already current. Initially the API,
web server and Docker engine were stopped. The existing Docker Desktop and
web/API runtime were started for this audit; no database was created or migrated.

The existing `eurogas-nexus-db` container became healthy. Read-only
`GET /api/runtime/db` then returned connectivity OK, revision
`0024_cost_observations`, and **41 missing required tables**. `python -m alembic
heads` reports `0032_agent_capability_layer`. Database connectivity is not
application readiness. The new workflows cannot be accepted against this
outdated schema. A backed-up migration and readiness check must precede normal
workflow acceptance. No credentials or database payloads belong in this report.

## Captures reviewed

The following fresh local artifacts were saved and visually inspected using
Playwright with installed Edge, explicit 1440x900 viewport and CSS-pixel output:

| Local artifact under `output/playwright/` | Actual state | Disposition |
| --- | --- | --- |
| `ux01-network-backend-offline-1440.png` | API stopped; Network default; all data requests fail | Accepted as degraded-state evidence only |
| `ux01-network-runtime-started-1440.png` | API started without runtime DB configuration | Accepted as missing-configuration evidence only |
| `ux01-network-schema-behind-1440.png` | API connected to old schema; Network still loading | Accepted as upgrade/loading evidence only; not normal-state acceptance |

These captures do not prove normal data rendering, correct topology, 1920x1080,
native desktop, all-page coverage or accessibility compliance. Initial in-app
captures were cropped relative to the requested viewport and were rejected for
desktop acceptance. A native capture did not show the selected target and was
also rejected. The CLI's default Chrome launch failed because Chrome was not
installed; the existing Edge browser successfully produced the listed captures.

## Confirmed findings

| ID | Severity | Evidence and impact | Required correction |
| --- | --- | --- | --- |
| UX01-001 | P1 | In all three captures, the topbar overlaps the analytical surface. Primary navigation, map controls, context selectors and right-rail tabs occupy the same band. Runtime/language/appearance/account controls wrap over decision content. | Give shell/context/status stable structural rows; let content start below their measured height; verify every workspace and degraded state. |
| UX01-002 | P1 | Offline capture exposes a raw endpoint-name list across the entire top edge, colliding with alerts and navigation. Retry and error text have browser-default styling inconsistent with other controls. | Canonical bounded error surface with useful summary, structured details and retry; it must participate in layout rather than cover controls. |
| UX01-003 | P2 | Network displays "Executable spread candidates" while the UI standard prohibits execution language for decision-support results. | Reconcile EN/CN candidate language with the no-execution boundary without changing calculation semantics. |
| UX01-004 | P2 | Network repeats gas day/product context in the resource panel, uses deeply framed metric/empty-state panels, and devotes substantial rail height to repeated explanatory prose. | Apply common context/evidence and empty-state rules; preserve actionable warnings and provenance while reducing repeated presentation. |

The old schema is an environment acceptance blocker, not proof of a frontend
hydration bug. Persistent loading must be retested after migration before its
root cause is assigned. Similarly, an empty map with unavailable backend data
does not prove that the current geometry implementation is wrong.

## Workflow coverage remaining

| Workspace | Current audit coverage | Required next evidence |
| --- | --- | --- |
| Market / Network / Capacity | Network degraded and loading states only | Normal overview, curves/spreads, asset/route selection, capacity evidence and Scenario handoff |
| Portfolio | Source inventory in delegated matrix only | Resource, route, economics, exposure, optimization and Review sequence |
| Decision Center | Source inventory only | Scenario inputs, run, optimization, provenance and Review interactions |
| Strategy Lab | Source inventory only | Design, version, Backtest, Compare, Shadow and persisted history |
| System | Source inventory only | Sources, Runtime, Settings, Manual, Glossary and Access |
| Research Data | Source inventory flags thin catalog UI | Feature/target/dataset navigation and dataset detail; triage missing required interactions |
| Agent Research | Source inventory flags thin artifact UI | Governed research, findings, confirmation, Review Pack and Replay |

## Inventory and follow-through

Component, typography, spacing, controls, tables, overlays, states and layouts
must be measured in the component census and reconciled with these rendered
findings. Navigation, bilingual, keyboard/focus, menus/modals, chart readability,
overflow and long-session checks remain pending. Do not replace these open
items with source-only assertions or historical UAT numbers.

The next implementation gate is the complete runtime audit plus a reviewed
Constitution/RFC, not this partial Network assessment. The campaign remains
open with confirmed P1 layout defects.

## Runtime recovery and Portfolio follow-up

The test database was backed up and explicitly upgraded from 0024 to 0032.
The custom-format archive is 52,399,199 bytes; its table of contents was readable
(195 output lines), and `pg_restore --file=/dev/null` successfully decoded the
full archive. This is archive validation, not a completed restore drill.
Backup SHA256: `6fe7f04119b25ad8e21f629f66a4ba793ce237500b2617fc0b157e042c51c745`.
The local backup remains outside the repository; no database payload is committed.

`alembic upgrade head` completed all eight pending migrations. Read-only API
validation now reports `0032_agent_capability_layer`, zero missing required
tables, and `/api/health/ready` reports `ready` with both database and required
tables OK. This supersedes the environment blocker above, not the UI findings.

Fresh follow-up captures under `output/playwright/`:

| Artifact | Observed result |
| --- | --- |
| `ux01-network-ready-1440.png` | Despite backend readiness, Network was still loading at capture; not accepted as settled normal-state evidence. |
| `ux01-portfolio-before-1440.png` | Portfolio Overview settled and displayed the existing preview resource; full-width framed sections, browser-default action buttons, oversized section headings and inconsistent account controls are visible. |
| `ux01-portfolio-routes-before-1440.png` | Routes tab works; its comparison uses button rows and full-cell pill statuses, without consistent numeric alignment. |
| `ux01-scenario-route-before-1440.png` | Selecting the TTF-BBL-NBP route opens Scenario and visibly carries its route ID; economics and resource-pool controls render. |

All four images were visually inspected. Portfolio settling establishes that
the prior loading observation is not proof of permanently broken hydration.
Load duration and per-endpoint behavior still require measurement.

Additional triage: Portfolio Overview reports no active warnings, while Routes
labels TTF-BBL-NBP `BLOCKED` yet shows allocation and margin. Scenario carries
that route and shows allocation economics. Trace the API result, feasibility
rules, preview provenance and cross-workspace warnings before deciding whether
this is a stale snapshot, distinct calculation basis or correctness defect.
Do not silently restyle away the discrepancy or present it as a proven backend
calculation error. Scenario execution, Optimize/Review and remaining workflows
have not yet been accepted.

## Strategy and System screen inventory (2026-09-08 local)

Fresh 1440x900 captures were saved under `output/playwright/` and visually
inspected. These are initial-screen reviews, not completed transactional UAT.

| Capture suffix in `ux01-<suffix>-before-1440.png` | Review |
| --- | --- |
| `strategy-design` | Empty registry; edit form is nevertheless populated with defaults. Single-column fields span almost the entire content width; oversized headings and repeated identity/context reduce useful density. |
| `strategy-backtest` | Empty registry; run correctly disabled until a frozen version exists. Form fields and run button stretch across the workspace. No persisted run available for result acceptance. |
| `strategy-compare` | No runs exist, but status says `COMPARABLE`. This is misleading empty-state language; comparison result/chart acceptance remains unavailable. |
| `strategy-shadow` | Offline scheduler and zero monitors are visible. Empty-version activation form is displayed with an apparently available start button; validation behavior needs an interaction test. Full-width pill status and stacked framed sections are inconsistent with the target density. |
| `sources` | Source posture and stale labels render. Native-looking System tabs differ sharply from the styled local tabs. Category cards and nested provider metrics consume substantial space. |
| `runtime` | Live DB readiness is visible, alongside scheduler/certification/external-security blockers. These operational prerequisites must not be hidden or automatically classified as UI defects. |
| `research` | Duplicate Research Data headings, capability-name chips and generic framed sections dominate an empty dataset catalog. Table headers wrap into multiple grid rows. Dataset detail/build/export workflow is not exposed in the observed screen. |
| `agents` | Captured during capability loading; rejected as settled-state evidence. Duplicate title and generic full-width panel structure are visible, but artifacts and completed research require recapture and interaction. |
| `settings` | A literal `RELEASE.COMPAT_COMPATIBLE` label appears. About section labels `0030_reliability_indexes` as DB schema revision, inconsistent with live 0032. Verify whether this is required-schema metadata mislabelled as observed schema before changing semantics. |
| `manual` | Large framed sections and repeated operational prose; workspace map omits the newer Research and Agent workflows. |
| `glossary` | Left term list/right definition structure exists. Large term cards reduce list density; date controls show an older fixed interval and lack visible timezone labels. Definition-selection behavior still needs testing. |
| `access` | Current non-admin principal sees an explicit restricted state, not administration contents. This is one restricted UI check, not entitlement or cross-principal acceptance. |

The Strategy registry is empty following migration; do not invent performance
curves or count tab visibility as Design-to-Shadow completion. Existing labelled
test fixtures may be used for later reproducible end-to-end validation, with
their provenance and mutations recorded. Source/Runtime observations also show
disabled schedulers and stale providers; they do not establish live pricing.

### Additional settled-screen review

`ux01-market-before-1440.png`, `ux01-capacity-before-1440.png`,
`ux01-orders-before-1440.png` and `ux01-review-before-1440.png` were captured
from existing workspace deep links and visually inspected. Market clips quote
text in a narrow left rail while the map dominates the price-investigation
view. Capacity shows explicit incomplete/stale evidence, but truncates column
headings and uses inconsistent control sizes. The legacy `orders` deep link
opens Portfolio Overview under a Market Positioning heading rather than the
Exposure task. Review displays persisted allocation and evidence but omits
option-composition warnings, as Portfolio Overview does.

Source/API investigation identified the blocked-route discrepancy: the frontend
classifier equates a nonempty `required_tso_access` list with missing access.
The backend-composed BBL option and allocated resource contain confirmed access.
This is a P1 false-blocked presentation defect, not proof of incorrect backend
allocation. A narrow classifier/warning regression fix is assigned separately
from layout refactoring. Scenario's selected-route economics binding and the
legacy deep-link task mapping remain separate items to verify/fix.

### Existing executable baseline

The existing `clients/desktop/src-tauri/target/release/eurogas-nexus-desktop.exe`
was launched and inspected using native window capture and accessibility text.
It is 9,033,728 bytes with local modification time 2026-09-06 12:26:43. It shows
the older Workspace menu rather than the current five-primary-workspace shell.
It loaded Network with expired quote cards and a workspace-loading state.
A menu click did not produce an observable changed accessibility tree on the
immediate refresh. This is not a verified menu interaction or current-source
desktop acceptance. Rebuild the executable from the tested source before
claiming CR1-15 native parity; do not use this older binary to approve or reject
current-source layouts. The full native page walkthrough remains pending.
# Route-status correction verification (2026-09-08)

## Navigation correction verification (2026-09-08)

Against 59277a0 plus the navigation patch, parent reran Web tests: 61 passed,
0 failed. Delegate production build passed. Edge runtime assertions passed for
Optimize -> Open in Review, Back to Optimize, Forward to Review, same-page
Decision Center reset to Scenario, and Strategy Backtest -> Decision -> Strategy
reset to Design. Review URL is now `workspace=review&task=review`, with its
heading, active tab and Review content aligned. Gas-day context was retained.

Visually reviewed `output/playwright/ux01-review-handoff-fixed-1440.png`: Review
content is present instead of Optimize. The capture is a loading/empty-data
state and is not normal-data or whole-product visual acceptance. Existing
clipping, card density and warning-state issues remain open.

## Research catalog walkthrough at 59277a0

Visited Research Data, then Features and Targets in Edge at 1440x900 against the
ready PostgreSQL runtime. Both tabs render explicit empty registries; no fixture
definitions were inserted. Capability names are displayed as non-interactive
chips. Source inspection confirms catalog rows have no detail interaction and
there are no dataset build/validate/quality/export controls. Missing records and
missing UI are separate acceptance gaps, not interchangeable explanations.

Visually reviewed `output/playwright/ux01-research-features-before-1440.png` and
`output/playwright/ux01-research-targets-before-1440.png`. Seven-column headings
wrap into two grid rows, task selection lacks clear visible styling, duplicated
Research Data headings and framed sections consume analytical space. This is
empty-state inspection only, not populated research workflow acceptance.

## Additional Portfolio walkthrough at 192cb4a

### Decision handoff defect

On 2026-09-08, clicked Optimize Resource Pool using the existing preview pool,
then Open in Review. The URL became `workspace=review&task=optimize` with gas-day
and resource identity retained. The page heading changed to Review while the
Optimize tab and optimizer content remained active. This is a P1 workflow
defect: the explicit Review handoff does not reach its intended surface.
`decisionTaskFromLocation` currently prioritizes `task` over the legacy workspace;
navigation and mounted task-state synchronization need joint regression coverage,
including browser history. No claim is made that the click proved a newly
completed optimization result; request/response identity was not captured.

Visually reviewed `output/playwright/ux01-optimize-before-1440.png` and
`output/playwright/ux01-optimize-review-handoff-1440.png`. Optimize also shows zero
warnings while Portfolio exposes an options-layer warning; preserve scope or
expose the warning rather than implying globally clean evidence. Its handoff is
below the fold amid oversized framed sections, with PnL row time basis omitted.

At 1440x900 in Edge, clicking the existing preview resource in Overview adds
`resource=preview-portfolio-contract-ttf-pool-2025` to the URL but leaves the
overview unchanged, without a clear selected-detail presentation. Clicking
Resources retains that URL yet opens the default `Operator TTF supply 2025`
draft. The mismatch needs explicit selected-resource versus editable-draft
identity and a coherent inspect/edit handoff; do not assume the displayed draft
is the selected persisted resource. No save/import was performed.

Exposure shows `GBP 0` summary metrics while its screen-observation and PnL
tables contain unavailable placeholder rows. Distinguish missing evidence from
a measured zero during convergence. Current page heading remains Resource Terms
on Exposure, and nested framed sections and inconsistent numeric alignment persist.

Visually reviewed local captures: `output/playwright/ux01-resource-selected-before-1440.png`,
`output/playwright/ux01-resources-before-1440.png`, and
`output/playwright/ux01-exposure-before-1440.png`. These checks extend the audit;
they do not prove the complete resource editing or exposure workflow passes.

Reviewed the functional correction against baseline `3bb9ab5` and the running
PostgreSQL-backed application. Required TSO access alone now yields UNKNOWN;
positive allocations from SUCCESS/PARTIAL results provide feasibility evidence,
and explicit route blockers take priority. Diagnostic identity matching is exact,
not a route-ID prefix match. No access eligibility is recalculated in the UI.
Portfolio Overview includes deduplicated resource-pool option warnings.

- `npm --prefix clients/web test`: 58 passed, 0 failed.
- `npm --prefix clients/web run build`: passed (TypeScript and Vite); existing
  ineffective dynamic-import warning remains.
- `/api/health/ready`: ready; runtime database and required tables both OK.
- Edge at 1440x900, existing preview portfolio, gas day 2026-09-07:
  BBL allocation 2,000 MWh/d and local TTF 8,000 MWh/d display
  FEASIBLE_WITH_WARNINGS; unallocated IUK displays UNKNOWN.
- Overview shows one warning: route starts outside the resource pool for IUK.
- Visually reviewed local evidence:
  `output/playwright/ux01-portfolio-routes-fixed-1440.png` and
  `output/playwright/ux01-portfolio-overview-fixed-1440.png`.

These are functional regression observations, not fresh-market certification or
whole-product visual acceptance. Oversized badges, inconsistent controls and
table alignment remain open UX01 work. No runtime data was inserted for this check.
