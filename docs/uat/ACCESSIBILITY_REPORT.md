# Accessibility and Browser Acceptance Report

## Current enforced method

The main CI workflow contains a deterministic `browser-acceptance` job. It:

- starts PostgreSQL 16, applies Alembic migrations, and seeds preview/UAT data;
- creates a development/test-only authenticated ADMIN principal with wildcard
  data scope for the acceptance fixture;
- starts the FastAPI and Vite development servers on loopback;
- runs Playwright Chromium against all 16 declared workspaces;
- repeats the workspace sweep in English and Mandarin at 1440x900,
  1920x1080, and 390x844;
- injects axe-core 4.10.3 and checks WCAG 2 A/AA and WCAG 2.1 A/AA;
- requires exactly one `main h1` on every workspace surface;
- rejects document-level horizontal overflow;
- exercises keyboard close/focus-return for the grouped Preferences menu and
  the narrow Context & status disclosure;
- writes a screenshot for every workspace/language/viewport matrix cell plus a
  machine-readable `summary.json`;
- uploads the evidence directory even when the acceptance step fails.

The browser harness is
`scripts/uat/browser_workflow_smoke.mjs`; its fixture identity is created by
`scripts/uat/seed_browser_identity.py`. The identity seed is fail-closed
outside development/test and requires
`EUROGAS_NEXUS_UAT_FIXTURE_ALLOWED=1`.

## Current result

GitHub Actions run **35069353376** on commit **b2c46c0** completed successfully.

- 16 workspaces
- 2 locales: `en`, `zh-CN`
- 3 viewports: 1440x900, 1920x1080, 390x844
- **96 / 96** workspace-locale-viewport checks completed
- **0 axe violations**
- exactly **1 main h1** on every checked workspace
- no browser-harness failures recorded
- Preferences focus-return and narrow disclosure interaction passed

The same workflow run also passed the normal `validate` suite, PostgreSQL
integration, dependency/CVE audit, and Web build/test job.

Evidence artifact:

- name: `eurogas-nexus-browser-acceptance`
- artifact id: `10435269397`
- size: 11,007,983 bytes
- sha256:
  `17a97a32fda12776e869e2fb590f5ce7c73e7d515657f2e68b139f17ec756881`
- retention for this run: through 2026-09-23

## Findings closed while establishing the gate

The first CI-backed sweep exposed defects that older source/unit checks did not
catch. They were fixed before the green run:

- the direct map-first Network route had no semantic `h1`;
- narrow Capacity, Market, Contracts, Review, Positioning, Access, and Agents
  scroll regions could be inaccessible to keyboard users;
- the grouped Preferences menu closed on Escape before focus reliably returned
  to its invoker.

The regression suite now pins the structural fixes, while the browser gate
validates the rendered result.

## Historical CR-13 fixes retained

Earlier accessibility work remains part of the product contract, including:

- accessible naming for the Review analysis control;
- AA-oriented muted/status contrast tokens;
- corrected heading hierarchy;
- preservation of a single main landmark;
- keyboard reachability for resource-path and Network rail scrolling;
- shared arrow/Home/End semantics for true workspace tablists.

## Remaining limitations

A green automated browser gate is not a substitute for:

- NVDA/VoiceOver testing by assistive-technology users;
- packaged Tauri/WebView native interaction evidence;
- rights-negative and live/licensed-data acceptance;
- long-session operational testing.

Those are tracked separately as deployment/native/fixture evidence and must not
be inferred from the automated Web PASS.
