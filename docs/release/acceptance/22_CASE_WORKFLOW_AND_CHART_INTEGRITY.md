# Case workflow and chart integrity — 2026-10-24

Scope: Linux Chromium with isolated synthetic identities and PostgreSQL/API
fixtures, plus client regression. This is engineering acceptance, not live trading
approval or a claim that the broader business-workflow redesign is finished.

## Changes and preservation

- Decision cases lead the review task; individual run assessments remain available.
  Canonical case selection survives URL/reload/navigation and is cleared from the
  URL at logout. Backend permissions determine preparation and assessment controls.
  Reviewers no longer request editable upstream-resource terms that their role
  cannot read. No backend grant or authorization rule changed.
- Superseded reads/mutations cannot replace another selected case, including
  A→B→A mutation ordering. Failed attachments retain drafts; current failures
  release busy state. The backend still owns decidability, identity and the pack.
- Strategy charts retain missing/non-finite values as gaps instead of zero
  drawdown. Area fill closes at zero, including an all-zero curve. Units, an
  accessible data table, categorical date spacing and frozen comparison periods
  are explicit. Existing backend indicative PnL and drawdown values are unchanged.
- Portfolio copy distinguishes declared scenario resources/allocations from
  reconciled positions and remaining obligations. Imported observations remain
  separate. No new inventory ledger, VaR or clearing-margin engine is claimed.
- Network canvas minimum height, empty overlays and actual tab selectors corrected.

## Evidence

Full Web regression: **950 passed, 3 skipped, zero failures** (953 total).
Production TypeScript/Vite build passed. Backend decision-case API selection:
**5 passed**. Existing numerical and authorization contracts were retained.

Actual reviewer browser: **9 checks passed** — case deep link, role composition,
no-evidence refusal, URL selection, reload, independent backend-recorded reviewer,
late prior-case response suppression, 1440/768/390 page-overflow checks and no
unhandled client errors. Case B records **needs attention**, with explicit synthetic
evidence and missing-snapshot qualification; it is not a commercial acceptance.
An earlier rerun timeout came from looking for an already decided fixture in the
open-case list; the repeatable test now selects the appropriate tab.

Actual analyst browser reopened the frozen synthetic backtest and preserved
APPROXIMATE / COMPLETED_WITH_WARNINGS and 2,214 GBP net indicative PnL. Updated
chart units, table disclosures and categorical axis text were inspected. Missing
point and zero-area behavior has deterministic geometry regression coverage.
Trader portfolio captured at 1440 and 390 with no page overflow; the narrow data
table and primary navigation retain their own horizontal scrolling.

Ignored evidence: `.local-runtime/business-redesign/` review-results.json,
review-after-*.png, case-api-tests.log, chart-browser-final.log,
portfolio-browser.log, contracts-after-*.png; chart capture under
`.local-runtime/cross-module/backtest-review.png`. Full regression/build logs:
`/tmp/eurogas-web-final.log`, `/tmp/eurogas-web-final-build.log`.

## Delivery limits

The candidate business architecture and role analytics documents are design
requirements. Complete daily obligation accounting, general price/basket strategy
support, validated VaR/clearing margin, live weather forecast vintages and broader
workflow redesign remain outstanding. This client revision has not been rebuilt
into the previously accepted Debian package; that artifact remains scoped to its
recorded source. Production provider/SSO, Windows/native release signing and
practitioner UAT are not established by this acceptance. A merge is not a release
readiness certification.
