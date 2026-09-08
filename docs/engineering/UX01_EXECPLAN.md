# ExecPlan: Professional Workstation Convergence

Status: `in progress - repository and runtime audit`

Owner: UI architecture/review lead; focused implementation delegated to Luna High.

Related contract: [UI and content standards](../clients/UI_CONTENT_STANDARDS.md).
The new UI Constitution requires an RFC and reconciliation of existing standards
before its implementation. This plan does not itself change normative authority.

## Objective

Converge the entire existing European energy decision-support workstation into
one professional UI system, preserving and validating CR1-15 behavior. This is
a whole-product campaign, not a new-feature program or a single-screen redesign.

## Scope and boundaries

- Shared tokens, layout/control/state primitives, action placement, motion,
  navigation, all trader/system/research/agent surfaces, EN/CN and accessibility.
- Permanent visual, interaction, overflow and UI-contract regression coverage.
- Full applicable backend, PostgreSQL, temporal, entitlement, MCP/agent,
  frontend and desktop acceptance; exact results and exclusions recorded.
- PostgreSQL and backend-owned calculations remain authoritative. No execution,
  invented market evidence, new datastore, or speculative feature architecture.
- Preserve verified/indicative topology and human-review/access boundaries.
- No major dependency or competing visual language introduced by delegates.

## Work sequence

1. **In progress:** establish current repository truth, inspect current docs and
   source, restore existing test runtime, navigate primary workflows, collect
   pre-refactor screenshots and identify P0/P1/P2 defects.
2. **In progress:** component census and CR1-15 regression mapping, with separate
   delegated document ownership and independent review.
3. **Pending:** reconcile standards through RFC; write UI Constitution, motion,
   workspace-layout and action-geography contracts based on the audit.
4. **Pending:** consolidate tokens and primitives, then shell/navigation, then
   trader surfaces, then research/system/agent surfaces. Review each batch's
   diff, rendered screens, reuse, regressions and contract compliance.
5. **Pending:** enforce UI contract in CI; component, visual, accessibility,
   bilingual, overflow and long-session coverage; compare performance baseline.
6. **Pending:** run full applicable CR1-15 and desktop acceptance, resolve all
   P0/P1 findings, explicitly disposition remaining debt, and publish the final
   requirement-by-requirement acceptance report.

## Evidence and acceptance

Required audit/report records live under `docs/ux/`: POST_CR15_UI_AUDIT,
COMPONENT_CENSUS, WORKSPACE_LAYOUT_STANDARD, ACTION_GEOGRAPHY,
CR1_15_REGRESSION_MATRIX, VISUAL_ACCEPTANCE_REPORT, ACCESSIBILITY_REPORT,
I18N_UI_REPORT, PERFORMANCE_REPORT, UI_DEBT_REGISTER, UX01_FINAL_ACCEPTANCE
(all Markdown). Binding client records are PROFESSIONAL_UI_CONSTITUTION and
MOTION_SYSTEM. Reports must distinguish implemented, tested, missing and
unverified; source existence is not runtime acceptance.

- Primary viewports: 1440x900 and 1920x1080; one smaller supported desktop.
- Exercises: market investigation; portfolio-to-review; strategy-to-shadow;
  governed agent research/replay; research datasets; degraded data; differing
  entitlements; EN/CN; primary desktop viewport; extended cross-workspace use.
- Verify loading, empty, error, restricted, stale and partial states.
- Record exact commands, counts, tested SHA, screenshots reviewed and exclusions.
- Completion requires zero P0/P1, all primary workspaces converged, enforced
  Constitution, motion and visual suites, and no material functional,
  entitlement or temporal regressions. Partial milestones are not completion.

## Current checkpoint (2026-09-07)

- Fetched origin and fast-forward checked main: `cfbcd58`, clean at audit start.
- Recent history includes research (`f34d469`) and agents (`2663daf`). Their
  actual coverage is being checked rather than inferred from commit titles.
- No listeners on 3000/8000/4173/5432 at runtime check; no DSH or Nexus window
  was present. Docker engine was unavailable. Existing Docker Desktop launch
  requested. Docker subsequently became healthy; API and Vite are running.
- Read-only runtime check: PostgreSQL connectivity OK, revision
  `0024_cost_observations`, 41 missing required tables; source migration head
  `0032_agent_capability_layer`. Backed-up migration/readiness validation is
  the next runtime prerequisite; no schema change has been made.
- Fresh 1440x900 Network captures confirm overlapping shell controls and a
  colliding error banner. See [initial audit](../ux/POST_CR15_UI_AUDIT.md);
  normal-state and whole-product coverage remain pending.
- Current UI standard already describes corrected `EU-CAM-UTC-2025`; historical
  claims about an unfixed calendar must be revalidated against current code.
- No frontend implementation has been changed in this campaign yet.

### Recovery checkpoint

The local test database has now been backed up (archive decoded successfully)
and explicitly migrated to `0032_agent_capability_layer`. API readiness is
`ready`; required-table omissions are zero. The backup remains outside Git.
Portfolio Overview and Routes now load persisted preview data; route selection
hands off to Scenario. Audit notes preserve a blocked-route/allocation warning
discrepancy for investigation. Normal-state Network, all remaining workflows,
1920x1080 and desktop acceptance remain pending. No UI implementation has begun.

The census delegate stopped on a usage limit after writing its draft; its
review/finalization remains pending. Do not mistake that failure for a running
job or completed review. The regression matrix was reviewed and revised to
separate external acceptance prerequisites from actual product defect severity.

## Rollback and risks

### Latest checkpoint (2026-09-08)

Current desktop build: at clean `9a84f5e`, delegate ran `npm run build` from
`clients/desktop`, exit 0. Web TypeScript/Vite and optimized Rust/Tauri build
succeeded; NSIS x64 installer generated. The native executable is now 9,142,272
bytes, written 2026-09-08 11:18:12 UTC, SHA-256
`124A148C6954F7536159F7DFBE413216C7E83F4A37EA203FBF831CCA6EDF41BC`
(parent independently checked hash). Installer SHA-256 is
`01A39F6E8173F11174584689261DF9A2EA1C4EEA6B6D489F652DC8E6CBFC5784`.
Existing Vite ineffective-dynamic-import warning remains non-fatal. No new
dependency or source edit was needed. Native launch/interaction acceptance is
still pending; compilation does not prove UI behavior.

Desktop pre-build verification: no active desktop/cargo/rustc/tauri/msbuild
process or target lock was detected. Existing release executable remains
9,033,728 bytes, last written 2026-09-06 04:26:43 UTC, SHA-256
`236187C7063E722153BD572838263DB22D984F465D8E58DF2585E29C811E3AE1`.
The documented command is `npm run build` from `clients/desktop`. It has NOT
been run for this checkpoint: wait for the active resource source patch to
stabilize, then build and inspect the new native executable. Allowance is
available again; the source-writer gate, not the old quota observation, is the
current prerequisite. Origin/main and local HEAD were fetched and match.

Follow-on checkpoint: `b566459` is pushed and adopts RFC-0001, Constitution and
Motion as binding contracts, not implementation acceptance. `3dbee3a` fixed
navigation handoffs/history with 61 passing Web tests and parent browser checks.
Agent blocked-data research/replay and glossary selection have been exercised;
the audit records exact limitations. The current resource-selection patch is
uncommitted and NOT accepted: selected record versus draft identity/impact/source
separation and unsaved-edit protection remain under review. Do not commit it
based on an earlier test result. Desktop rebuild is deferred at 94% five-hour
usage; recheck allowance and actual agent/process status before restarting work.

- `192cb4a` pushed to origin/main: backend-evidence route classification and
  resource-pool warning aggregation corrected. Parent verified 58/58 Web tests,
  production build, API readiness and two 1440x900 browser screenshots.
- Census is complete and reviewed, pending its documentation commit. Constitution
  and motion drafts have been reviewed; authority reconciliation is delegated.
  RFC acceptance and implementation compliance remain separate gates.
- Remaining primary-workflow audit is active. Resource selection retains its URL
  identity but does not open the selected record in the Resources editor; the
  current default draft is a different record. Exposure presents unavailable
  rows beneath zero summaries. Both need explicit UX/correctness disposition.
- No broad visual refactor or final acceptance is claimed. Historical checkpoints
  above are retained as chronology, not current runtime/agent status.

Use coherent independently reviewable commits, preserving existing work.
Do not reset the worktree or rewrite historical calendars/data to simplify UI.
Keep audit-only changes separate from functional fixes. Runtime startup,
fixture rights, missing workflow coverage and stale screenshots are explicit
verification risks, not reasons to weaken final acceptance.

### Allowance checkpoint (2026-09-09)

At 92% five-hour usage, implementation agents stopped at a preserved checkpoint.
Last pushed milestone is `ba26fe2`. Uncommitted client reliability work owns
`clients/web/src/api/client.ts`, `clients/web/src/stores/api.ts`,
`clients/web/src/stores/workspaceLoading.ts`, and
`clients/web/tests/workspaceLoading.test.ts`. Workspace deadlines and generation
guards had 76 passing web tests and a successful build before the latest edits.
Subsequent market/monitoring coalescing and deadlines have only a whitespace
check, not test/build acceptance. Next: add periodic-lane tests, filter retry
keys, verify retry supersession/loading, rerun tests/build, then browser QA.
The separate shell CSS remains uncommitted. PostgreSQL index proposals are
read-only; no migration/index/configuration changes have been applied. Do not
report the latest reliability draft as tested or restart stopped agents without
reading this checkpoint. No automatic credit/reset action was taken.

### Native Sky checkpoint (2026-09-09)

The parent launched the clean `9a84f5e` native executable through Sky. Native
System/Data Sources rendered runtime evidence showing `863032` records, `24`
sources, `3` workflow-ready items, `21` issues, stale ECB labels, simulated
labels, and five primary tabs. A screenshot was visually reviewed. Nested
framing, raw native System tabs, and clipped status labels persist. This is
startup/render evidence only, not a full native walkthrough or acceptance.

A Market UIA click did not establish navigation. The coordinate attempt failed
because the reported target bounds were `15x15` despite the full screenshot;
reselect/activate recovery reported user input detected. No native navigation or
resize acceptance is claimed. The next native action is one fresh
`get_window_state` call after the user is no longer interacting; do not repeat
activation attempts.

Quota status at this checkpoint was `6%` of the five-hour window and `32%` of
the weekly window. No quota reset was consumed. This checkpoint is
documentation-only; no other files were changed and no commit was made.

### Agent QA checkpoint (2026-09-09)

The current candidate diff adds `clients/web/src/app/model/scenarioRouteEconomics.ts`
and wires `ScenarioWorkspace.tsx` through it. The parent visually reviewed
`output/playwright/ux01-scenario-second-route-1440.png` for
`public-route-ttf-local`: the source resource-pool allocation showed sale
`27.05`, resource volume `8000`, and cost `n/a`; the Kant-matched response
showed `gross_sale=27.0472`, `totalcost=25.0219`, `allocated=8000`, with no
recommendation response. The parent independently ran
`npm --prefix clients/web test`: `73 passed, 0 failed`, including explicit
default and ambiguous-pool cases. No backend/full-acceptance suite pass is claimed.

This closes only the specific wrong-route association functional debt: the
helper matches a carried route by `route_id` and uses explicit
`option_id`/resource matching for pool fallback. The browser
`routeRecommendation` fixture is still absent, so broader browser acceptance,
degraded-state behavior, and Scenario/layout acceptance remain open.

The candidate `clients/web/src/styles/app.css` also moves the shell toward
normal-flow grid rows. A reviewed screenshot now shows the context uncut, but
the state is loading/unavailable rather than populated; the CSS remains
unaccepted pending populated screenshots and runtime visual review. The
existing `9a84f5e` native startup/render evidence is the current old baseline
for interaction acceptance; no native navigation or resize acceptance is
claimed. The parent commit scope is the Scenario source and these docs; the
shell CSS remains uncommitted.

### Read-only PostgreSQL diagnosis checkpoint (2026-09-09)

The existing local PostgreSQL 16 container was inspected read-only; no query
was terminated and no restart, migration, configuration change, or write was
made. `resource-pool/options` performs a global newest-row read of
`market_observations` plus bounded per-source coverage, then composes route
prices. Its read-only `EXPLAIN` shows a two-worker parallel sequential scan and
`Gather Merge` sort over an estimated 713,748 rows, ordered by
`observed_at_utc DESC, market_venue, product`. The table is approximately
695 MB and has no index matching that ordering; its observed index is
`(source_system, observed_at_utc)`. The current route-cost selector then
applies tenor, licensed-versus-simulated, and source-family precedence; a
blanket limit or unvalidated latest-per-key rewrite would risk changing that
behavior and source coverage.

During the bounded snapshot there were 22 database sessions, 18 active, 2
idle in transaction, 7 active backends waiting on `ClientWrite`, 4 on parallel
`MessageQueueSend`, and zero blocked lock waiters. `max_connections` was 100.
Database statistics reported 2,203,614 temporary files and 6,193 GB of
temporary I/O, with zero deadlocks. Those counters are cumulative since the
last statistics reset and do not attribute temporary I/O to this single
request. This supports a spill-heavy shared workload and an ordering-index
candidate, but does not by itself prove endpoint-exclusive causality.

The exact next implementation proposal is to support the existing ordering
with a migration-owned PostgreSQL index and add query-plan/result-regression
coverage before considering a latest-per-key SQL rewrite. Required regression
cases must preserve source/venue/product/hub identity, temporal newest
selection, low-frequency source coverage, source entitlement filtering,
simulated-versus-licensed precedence, freshness/provenance, and route-price
blockers. No backend implementation or acceptance claim is made in this
checkpoint.

### Milestone checkpoint (2026-09-09)

Parent reviewed the real endpoint-banner captures
`ux01-shell-endpoint-banner-1440.png`,
`ux01-shell-endpoint-banner-1920.png`, and
`ux01-shell-endpoint-banner-1100.png`. The authenticated runtime settled with
`loading=false` and identity present. Browser market/spreads reads included a
12-second `503`, while other market reads timed out; the banner correctly
listed five affected endpoints rather than reducing the incident to one
failure. Context-banner content did not overlap. Map markers and four
indicative route markers rendered, but the base-map tile remained blank;
nested cards, raw codes, and clipped labels remain open UI debt.

This accepts only the scoped UX01-001 shell structural overlap correction at
the required 1440, 1920, and 1100 desktop viewports. It does not accept the
broader UI/token, bilingual, native, populated-state, or whole-product visual
work. Parent verified `npm --prefix clients/web test` with `84 passed, 0
failed`, then verified `npm --prefix clients/web run build` with exit 0
(TypeScript + Vite, 134 modules, 495 ms); the existing build warning remains.
Startup/retry `/me` generation and auth-fail-closed handling,
bounded market/monitoring lanes, sign-in/read gates, source-failure recording,
and cross-lane invalidation are implementation evidence, not full-auth proof.
User-triggered follow-up read guards remain explicit residual debt. All mocks
are removed. The PostgreSQL ordering-index proposal remains unapplied.

Two commits are expected, reliability first and shell second; no commit SHA is
claimed here. Full CR1-15, native, entitlement, and visual acceptance remain
open.
