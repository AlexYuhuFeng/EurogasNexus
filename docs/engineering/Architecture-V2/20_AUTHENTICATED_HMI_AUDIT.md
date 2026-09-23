# Authenticated HMI audit

Date: 2026-09-23. Baseline: `f58d7e3`, matched origin/main.
Disposition: **NOT APPROVED FOR CUSTOMER PRODUCTION**.

## Scope

The supplied local UAT account successfully authenticated through the ordinary
sign-in form. No credential or permission was changed. The password is not part
of this report. This supersedes CA-09's missing-access blocker in audit 19;
it does not close whole-product acceptance.

Evidence is from the current local application through the in-app browser.
Screenshots are retained locally under `output/ux-audit-2026-09-23`, not published
as customer artefacts. Observed viewports were 738x461 and 656x369 CSS pixels.
The browser did not apply the requested 1440x900 override; that override was
reset. These are narrow-layout observations, not certified desktop/mobile UAT.

## Flow and findings

| Step | Surface / evidence | Result |
| --- | --- | --- |
| 1 | Login then Market/Network; `01-market-blank.png` | Login succeeds. Navigation renders but main is blank. Switching away and back reproduces it. Browser reports a React static-flag error at authentication transition. P1; focused repair delegated. |
| 2 | Portfolio; `02-portfolio.png` | Main content renders. As-of and count labels expose literal `{value}` and `{count}` placeholders. P1 because freshness evidence becomes unreadable; focused repair delegated. |
| 3 | Strategy Lab; `03-strategy.png` | Empty-state and disabled Save are visible. Two visually dominant Strategy headings and separated tab rows consume scarce space. Default resource/cost examples require review before treating the draft as an actual resource mandate. No strategy was saved or run. |
| 4 | Decision Center; `04-decision.png` | Day board and comparison input surface render. Compare Options uses a browser-default-looking button unlike primary navigation. Operational prose dominates the first viewport. No comparison, optimisation or nomination action was submitted. |
| 5 | System / Research Data; `05-research.png` | Validation/build gates are visible. Repeated Research Data headings, two tab levels and long explanatory text push actual work below the first viewport. Raw registry-id fields require users to recall identifiers rather than select validated entities. No dataset was built. |
| 6 | Glossary; `06-glossary.png` | Selecting TTF updates its article and operational context. At the observed width, a long term list precedes the article rather than preserving the requested efficient list/detail interaction. Selection scrolls to the term; the result is not immediately visible beside it. |
| 7 | Administration; `07-administration.png` | Sources disclose 3/24 workflow-ready, 21 requiring action, missing credentials and disabled scheduler. Useful operational honesty, but unavailable production feeds prevent real-time trading acceptance. No connector was run or edited. |
| 8 | Context disclosure; `08-context.png` | Date, product, hub, identity, alerts and source timestamp are discoverable. The collapsed state hides most readiness/session context at this width. Keyboard command palette opens and navigates to Capacity, providing a path around the initial blank Network view. |
| 9 | Market Overview; `09-market-overview.png` | Reached through Capacity then Overview. Six hub quotes identify simulated sources and four-day age, which is good. Overview combines a quote board and map; basemap is explicitly unconfigured. The separate Curves task needs its own acceptance. |

## Higher-risk unresolved findings

At baseline, the browser smoke harness explicitly listed the hidden Network workspace in
`KNOWN_NON_RENDERING_WORKSPACES` and records the React error as an observation,
not a failing check. Consequently a green historical sweep does not prove those
paths are usable. This change removes both exemptions: absent visible main
content and React internal errors now fail browser acceptance.

1. **Context consistency (P1):** global gas day is 2026-09-07 while Market and
   Portfolio projection strips report 2026-09-22. Confirmed cause: frontend
   projection reads omitted selected context. The September 24 repair below
   fixes request propagation and stale-response handling. Live re-verification
   and disclosure of unapplied backend filters remain open; selected gas day
   must not be mistaken for historical portfolio valuation.
2. **Readiness semantics (P1):** numeric Market says Source posture Ready while
   projection slices are stale/missing and quotes are four days old. Runtime
   connectivity is not market-data fitness. Distinguish store availability,
   ingestion transport and decision-ready evidence; qualify recommendations.
3. **Simulation labelling (P1 investigation):** hub rows show `EEX_Sim` and
   `Trayport_Sim`, while expired opportunity cards use unsuffixed venue labels.
   Verify that venue identity cannot be mistaken for actual licensed source
   evidence. Retain source lineage and simulation classification on every handoff.
4. **Shared HMI consistency (P2):** standardise primary-action styling, one visual
   title per task, compact context summaries, registry-backed selectors and
   narrow list/detail navigation using existing tokens/components. Do not create
   another design system or rebrand this as a cosmetic-only issue.
5. **Map/numeric independence (P2):** Overview intentionally embeds a map, while
   source code specifies separate Curves and Network tasks and a saved preference.
   Verify these paths are actually reachable and preserve their context; do not
   infer failure solely from the optional Overview. Official versus indicative
   geometry remains a separate evidence acceptance requirement.

## Acceptance still needed

Retest fixes after a fresh authentication transition, not only hot reload.
Record actual viewport dimensions before reporting responsive coverage. Run the
agreed 1440/1920/narrow bilingual workflow matrix, keyboard/focus/zoom checks,
screen-reader review, session expiry, entitlement-negative tests and real trader
task timing. Neither these screenshots nor unit tests establish WCAG conformance,
commercial readiness or parity with a professional market-data terminal.

No trade execution, persisted strategy/dataset/decision creation, data ingestion,
permission change or production deployment was performed during this review.

## Repair and verification checkpoint

DeepSeek implemented the bounded repairs; the integration reviewer inspected the
diff, simplified the source-contract test and retested the live application.

- Authentication now mounts a separate authenticated shell, preserving hook order
  and the existing authentication gate. A fresh sign-out/sign-in passed with no
  browser console errors in the new verification tab.
- The resolved market task is owned once by the app controller and shared by the
  shell and cockpit. Network layout follows that task, including tab navigation
  and persisted preference, rather than only the URL page id. The previously
  hidden page is visible. Numeric-to-Network switching produced a positioned
  map column of 420 CSS pixels in height at the observed narrow viewport, with
  its map stage visible. This fixes the zero-size/uncontained overlay failure;
  it is not acceptance of the remaining dense layout or map data quality.
- Actual bilingual i18next tests cover projection timestamps, counts and evidence
  labels. Portfolio shows values rather than placeholder tokens in browser QA.
- Verification: 571 frontend tests passed; production build passed; 78 focused
  Python client/architecture/Markdown contracts passed. Locale parity: 2,810 keys
  per language, no missing keys. Existing dynamic-import and dependency
  deprecation warnings remain.
- Additional local evidence: `12-network-tab-fixed.png` and
  `13-portfolio-labels-fixed.png` in the same local audit directory.
- The full 1440/1920/mobile bilingual browser sweep was not run. The in-app
  viewport override did not apply; permission for the alternate local Playwright
  runner was requested but not received in this run. No desktop acceptance or
  full accessibility claim is made.

Next bounded milestone: trace and reconcile selected gas day, projection context
and displayed figure lineage, then separate runtime connectivity from data fitness.

## September 24 context repair

Baseline `42e4be2`. DeepSeek performed implementation in two bounded passes;
integration review added protection against later legacy batches/retries and
unfiltered quote/opportunity streams widening focused market rows.

- Projection requests carry gas day and focused product/hub; `all` is omitted.
  No client-generated as-of is supplied. Each retry retains its original query.
- Pending first reads are re-requested after a context change. Context, request
  sequence and identity ownership reject late responses, including A-B-A switches.
  Old readings are cleared while replacement reads are pending. A portfolio
  refresh receiving a 401 fails the session closed.
- The shared strip reads `time_basis.basis` and `gas_day_calendar`, correcting
  the nonexistent `basis_id` lookup. English/Chinese labels are present.
- Once requested, the market projection owns its price/opportunity rows.
  Unfiltered streams cannot append rows outside that read; the existing
  10-second projection poll supplies updates. This is not tick-by-tick streaming
  acceptance. Global monitoring remains a separate operational feed.
- Independent checks: 585 frontend tests, normal production build, 91 focused
  Python contracts and 42 projection/context tests passed. The Python groups
  overlap. Tests exercise real store actions through Vite with mocked HTTP and
  deliberately reordered promises; no external data is fabricated or ingested.
- No live browser verification was possible in this run: the API was stopped,
  and the read-only validator reported no configured PostgreSQL URL. No database
  health or schema finding can be inferred from that absence. Existing UAT
  runtime configuration is needed before the authenticated retest.

The backend declares gas day but does not filter rows historically by that date;
portfolio/review also do not apply hub/product filters. Existing per-slice
`context_filter` metadata must be surfaced clearly in the next HMI milestone.
Readiness semantics, complete responsive acceptance and release approval remain
open. This checkpoint does not approve customer production.

## Runtime wording and CI evidence

September 24 follow-up, baseline `796b734`: Market Overview, the header and
Settings now label the runtime-data availability explicitly, not overall
readiness. Unknown states remain non-healthy. Other uses of `data.ready`, market
freshness and the projection degradation disclosures are unchanged. This closes
the specific misleading runtime badge, not the broader decision-fitness finding.
Independent checks: 589 frontend tests, production build, 28 focused Python
contracts and locale parity passed. Live layout checks for the longer EN/ZH
labels remain pending; no new authenticated local session was available.

[GitHub CI run 35888959943](https://github.com/AlexYuhuFeng/EurogasNexus/actions/runs/35888959943)
for `796b734` passed the web and PostgreSQL integration jobs but failed browser
acceptance. The downloaded report contains 96 surface checks across EN/ZH and
1440x900, 1920x1080 and 390x844, and 33 failure entries (not 33 distinct defects).
This is CI evidence, not a new local live-browser inspection or a passed UAT.

- Axe reports `scrollable-region-focusable` for `#network-rail-panel` in both
  desktop sizes and both languages.
- Functional probes report persistent loading on Network, Capacity and sometimes
  Research, plus returned-but-not-rendered rows on Orders, Runtime and Settings.
  Probe assumptions and actual surface state both need diagnosis.
- Contracts checks generate six 404 console errors; API logs identify the
  requested path as `/api/contracts/upstream?limit=5`. Check the probe against
  the actual route contract before attributing this to the application.
- The agent-research fixture reports its chain complete; that does not override
  the failed whole-product gate.

Evidence is retained locally under `output/ci-35888959943`, excluded from Git.
These failures are the next acceptance-repair priority. No exemptions were added,
no workflow was disabled, and commercial disposition remains NOT APPROVED.
