# Accessibility and Browser Acceptance Report

## Current CI evidence

The current whole-product Web acceptance is enforced by GitHub Actions, not by
an ad-hoc local sweep.

- Ref: `6eb1c43b4a66cfe4886e5ee13a1753d1e1d647b0`
- Workflow run: `35069273729`
- Browser job: **success**
- Matrix: 16 declared workspaces × 2 locales × 3 viewports = **96 checks**
- Locales: English and Mandarin (`zh-CN`)
- Viewports: 1440×900, 1920×1080, and 390×844
- Browser tooling: Playwright Chromium 1.55.0 and axe-core 4.10.3
- Runtime: migrated PostgreSQL test database with deterministic preview/UAT
  data and an authenticated development/test-only UAT principal

Each rendered check requires all of the following:

1. zero WCAG 2A/AA/2.1 A/AA axe violations;
2. exactly one `h1` inside the main landmark;
3. the expected document language;
4. no fallback to the sign-in screen after authentication; and
5. no document-level horizontal overflow.

The run completed with `ok: true`, `checks: 96`, and `failures: []`.
Every recorded surface reported `axeViolations: 0`.

The same workflow run also passed the Web build/tests, Python validation suite,
PostgreSQL integration job, and dependency-license/CVE audit. Desktop bundle
jobs remain pull-request-only and were therefore skipped on this `main` push.

## Interaction checks

The CI browser job additionally verifies two shell interactions that previously
had acceptance debt:

- the grouped Preferences menu opens, supports keyboard movement, closes with
  Escape, and returns focus to its invoker; and
- at 390×844 the global Context & status disclosure starts collapsed and can be
  expanded without losing the workspace.

Scrollable narrow-layout regions found by the first CI sweep were corrected
with explicit keyboard focusability. The standalone map-first Network route
also carries one semantic main heading while retaining its visual map-first
layout.

## Evidence artifact

The workflow uploads screenshots, browser logs and `summary.json` even when
the browser step fails.

For the passing run:

- Artifact: `eurogas-nexus-browser-acceptance`
- Artifact ID: `10435537571`
- Size: 11,022,745 bytes
- SHA-256 digest:
  `9e7d343c5f14fd5896e8ba98e584ec051a7ea9651a05cf2bd3516d8a89e3c30b`
- Retention configured by the workflow: 7 days

The harness lives at `scripts/uat/browser_workflow_smoke.mjs`; the guarded
browser identity seed is `scripts/uat/seed_browser_identity.py`.

## Earlier CR-13 fixes retained

The original CR-13 accessibility pass corrected, among other issues:

- accessible naming for the Review analysis textarea;
- critical/serious color-contrast failures;
- heading-order defects;
- main-landmark semantics; and
- keyboard reachability for the original resource-path and Network rail
  scrollers.

Those corrections remain regression-tested; the current CI matrix supersedes
the old 13-workspace/1440-only automated evidence statement.

## Boundaries and remaining evidence

A green automated browser matrix is not equivalent to every form of product
acceptance. The following remain intentionally separate:

- native Tauri/WebView interaction and packaged-desktop accessibility
  (`EVID-DESKTOP-001`);
- assistive-technology validation with NVDA/VoiceOver and human bilingual copy
  judgement;
- long-session/endurance behavior;
- a successful real orchestrator-produced Agent replay/review-pack chain
  (`CR15-UI-001`); and
- licensed-data/export-rights acceptance where commercial redistribution terms
  are required (`CR14-RIGHTS-001`).

Missing evidence in those categories must remain explicit and must not be
inferred from the simulated browser UAT fixture.
