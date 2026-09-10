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

The bounded implementation adds only migration `0033_market_obs_order_indexes`
with `ix_market_observations_observed_venue_product` on
`(observed_at_utc DESC, market_venue, product)`. The existing source index is
`(source_system, observed_at_utc)`: related but not an identical duplicate, and
the source-specific four-column extension is deferred until a measured benefit
is demonstrated. No latest-per-key rewrite or query change is included.

The query contract preserves global newest ordering and bounded source
coverage; ties beyond the stated timestamp/venue/product ordering remain
unspecified, so regression checks compare rowsets where the cutoff does not
split a timestamp tie. Focused PostgreSQL coverage uses an isolated schema to
upgrade and downgrade the migration and checks distinct-timestamp source
coverage parity. It is not SQLite evidence and has not been run against the
runtime database.

The migration uses the repository's ordinary transactional Alembic pattern,
not `CREATE INDEX CONCURRENTLY`. Applying it requires a quiesced application,
backup/rollback confirmation, disk headroom, and an observed build-time impact:
ordinary index creation can block writes. No runtime migration or data write
has been performed.

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

### Token/header milestone (2026-09-09)

Last pushed ref: `787d938`. Parent reviewed the current EN/CN shell captures
`ux01-token-fresh-1440.png` and `ux01-token-fresh-cn-1440.png`, plus the three
CN header captures `ux01-marketcockpit-cn-1440.png`,
`ux01-portfolio-cn-1440.png`, and `ux01-decision-optimize-cn-1440.png`.
The actual Market workspace is `market`, not Network; its single H1 correctly
identifies the workspace/task. The shared H1/header source is implemented for
Market, Portfolio, and Decision, but normal-runtime and full international QA
remain open.

The reviewed shell-token foundation computes 4px primary tabs, buttons, header
select, and status; 32px controls; and a 6px banner. Only that foundation is
adopted in this checkpoint. Broad panel-style changes were reverted; legacy
tokens, headings, spacing, raw-code treatment, density, and broader UI/token
work remain open. Parent verified `npm --prefix clients/web test` with `90
passed, 0 failed` and `npm --prefix clients/web run build` with exit 0
(TypeScript + Vite, 135 modules, 1.29s); the existing dynamic-import warning
remains. These are implementation and bounded visual-review evidence, not a
full browser, native, entitlement, or CR1-15 pass.

The earlier `72845` snapshot terminal timed out; it did not establish that the
browser was unavailable. The tab list proved an existing browser was alive.
Parent read console `ERR_INSUFFICIENT_RESOURCES` while the site returned `GET
200`, closed only the automated UX01 browser, and reopened Edge operation
`24588`. Runtime remains partial with many timeouts, so no full-ready claim is
made. CN and three-header QA remain bounded evidence, not whole-product
acceptance. The token/header milestone was committed and pushed as `494ccfa`;
the remote was fetched again on 2026-09-09 and matched local `main`.

### Ordering-index review resumed (2026-09-09)

Parent inspected the pending migration, ORM definition, repository query, and
test changes. No price-selection, source-quota, time, or licensing semantics
are changed. Parent ran `python -m pytest
tests/contract/test_market_observation_indexes.py
tests/release/test_release_engineering.py -q`: 22 passed in 2.29s.
Focused Ruff checks passed. The isolated PostgreSQL test is being strengthened
to cover source retention beyond the global limit and to scope its index
catalog lookup to its generated schema even after the public index exists.

Runtime application remains pending a fresh disk, backup, writer, and process
safety assessment. Neither this checkpoint nor the unit results establish a
runtime performance improvement. Whole-product UX-01 acceptance remains open.

### Ordering-index applied and verified (2026-09-09)

This supersedes the pending-application status above. The test worker briefly
started and stopped the existing PostgreSQL container for its isolated test;
the read-only worker observed that transition. Parent then deliberately started
`eurogas-nexus-db` and left it running. No listeners existed on ports 8000 or
3000. The database had only the inspection query active, revision 0032, and no
proposed index. Host free space was 24.14 GiB; Docker reported 951 GiB available
inside its filesystem (host headroom remains the tighter constraint).

Before applying the migration, parent created a custom-format `pg_dump` at
`C:\Users\qqshu\AppData\Local\EurogasNexus\backups\ux01-before-0033-20260909.dump`:
52,522,874 bytes, timestamp 2026-09-09 11:00:46 UTC, SHA256
`F0E85F3F86345F30A88B467DAA24BEADF816C9B7D4C9B87D3200A7BD06A9E829`.
`pg_restore --file=/dev/null` successfully decoded the complete archive. This
is archive validation, not a restore drill. Older backups were retained.

Parent ran `python -m alembic upgrade 0033_market_obs_order_indexes` using the
existing database credentials in process memory, with 5-second lock and
120-second statement timeouts. Exit 0; command wall time 3.29s. Public revision
is now 0033 and the 39 MB index reports both `indisvalid` and `indisready` true.
Rollback is `alembic downgrade 0032_agent_capability_layer` in a controlled
maintenance window; it drops only the new index and does not remove observations.
No runtime downgrade was performed.

`EXPLAIN (ANALYZE, BUFFERS)` of the existing global latest-2000 ordering now
uses the new index: 2,000 rows, execution 1.598 ms, planning 2.806 ms, 157 shared
buffer hits and 94 reads. The prior plan used parallel scan/sort, but there is
no controlled same-load pre/post latency benchmark. The per-source coverage
query and endpoint/application latency still need measurement; this is not an
end-to-end performance pass.

Parent reviewed the worker's schema-qualified catalog lookup and expanded
distinct-timestamp fixture: low-frequency ICIS remains present beyond the
global newest cutoff. After the public index existed, parent ran `python -m
pytest tests/integration/test_market_observation_indexes_postgres.py
tests/contract/test_market_observation_indexes.py
tests/release/test_release_engineering.py -q` against PostgreSQL: 23 passed in
1.95s. Focused Ruff checks passed. API and frontend remain stopped; restarting
them and measuring real workflow responsiveness is the next acceptance step.
The full UI, native, accessibility, bilingual, and CR1-15 campaign remains open.

### Resumed runtime endpoint evidence (2026-09-09)

Source ref was `eaf68f4`. Parent started the owned API process (PID 1140) and
web process (PID 2204); runtime readiness returned 200 with the runtime DB
available. Parent browser QA was running concurrently, so this is shared-load
runtime evidence, not a controlled benchmark. Each endpoint below was given
one bounded GET request with a 15-second deadline; no retries were used and no
financial rows or response bodies were recorded.

| Endpoint | Status | Elapsed | Payload |
| --- | ---: | ---: | ---: |
| `/api/market/observations` | timeout | 15,038 ms | n/a |
| `/api/route-cost/resource-pool/options` | 200 | 7,809 ms | 3,629 bytes |
| `/api/sources` | 200 | 8,689 ms | 30,585 bytes |
| `/api/runtime/pipeline-health` | 200 | 2,368 ms | 842 bytes |
| `/api/reference-network/edges` | 200 | 2,088 ms | 5,034 bytes |
| `/api/contracts/routes` | 200 | 2,059 ms | 264 bytes |

The residual slow endpoint is `/api/market/observations`, which exceeded the
15-second deadline. Market Overview financial and layout fixes remain in
progress; this runtime snapshot does not claim closure or acceptance.

### Market overview hierarchy and pricing-basis correction (2026-09-09)

Parent reviewed the real populated baseline at 1440x900, then delegated CSS
and comparison-model changes to separate Luna High workers. The overview now
gives the quote board the primary width, with a 320px context rail, a bounded
280px secondary map, flat 36px rows, numeric alignment, and 32px table header.
The narrow layout stacks the surfaces. Network task geometry and behavior are
unchanged. Parent rejected the first revision's blank board space, native row
bevels, clipped ask values and adjacent source/spread text; these were corrected.

The previous fallback subtracted incompatible quotes, labelled the difference
GBP/MWh, and called last trade a midpoint. The overview no longer synthesizes
spreads or a TTF zero. It displays only a matching, unexpired backend gross
opportunity with its quote IDs, direction, delivery/product, units and source
references. Backend conversion remains backend-owned. Quote midpoint requires
both bid and ask; shared-unit bid/ask formatting preserves missing sides.
Expiry invalidation uses a cleaned-up local timeout, measured against wall
time and bounded to the browser timer range; no network polling was added.

Parent reran `npm.cmd --prefix clients/web test`: 104 passed, 0 failed,
0 skipped, 1084.53 ms. `npm.cmd --prefix clients/web run build`: exit 0,
TypeScript plus Vite, 136 modules, 622 ms Vite build; the existing ineffective
dynamic-import warning remains. One earlier `npm` build invocation exited 1
without output; the explicit `npm.cmd` reruns succeeded. Tests cover pure
comparison, expiry scheduling, identity, mismatch and formatting cases, not a
complete mounted-component or browser expiry acceptance suite.

Parent visually reviewed `ux01-market-final-populated-1440.png` and
`ux01-market-final-populated-1920.png`: complete bid/ask values and units,
visible sources/ages, no unjustified spread values, and secondary map framing.
Retained observations are eight days old, not a fresh-market certification.
Parent also reviewed the worker's EN/CN 1440x900 and CN 1100x900 loading-state
captures; final populated bilingual and narrow-state verification remain open.
Earlier full-page screenshots were not counted as exact viewport acceptance.

Residual scope: endpoint latency, source-ready versus unavailable wording,
explicit visible product/basis presentation (current row titles contain raw
English metadata), full accessible table semantics, action geography and
whole-workspace visual convergence. No whole-product or native PASS is claimed.

### Source-summary truthfulness (2026-09-10 Shanghai)

Resumed from clean `8d4da18`, fetched origin with no divergence. Five-hour
usage had reset to 3%; weekly usage was 86%, so this batch stayed bounded.
Parent reproduced the false-ready header with a browser-only `/api/sources`
503 response: `ux01-source-status-before-503.png` shows Sources ready alongside
the failed-source banner. No database data or server response was changed.

Luna implemented a pure summary state over existing source statistics, loading,
source endpoint errors and runtime data status. Empty, checking, unavailable,
unknown and partial states cannot claim readiness. Ready requires populated,
fully ready statistics. Source read failures override retained counts, and
unsettled counts are omitted rather than displayed as known zeros. EN/CN copy
distinguishes unavailable status from an assertion that all sources are down.
Existing source-statistics and market timestamp semantics remain unchanged.

Parent reviewed the diff and `ux01-source-status-final-503-en.png` plus
`ux01-source-status-final-503-zh.png` at 1440x900. Both show unavailable status
without clipping or false counts. The first language selection used `zh`
instead of the actual `zh-CN` option and failed; the corrected selection and
replacement capture succeeded. All browser response overrides were removed.
The requested retry click timed out because its button was no longer present;
the subsequent real-runtime capture `ux01-source-status-recovery-zh.png` shows
partial readiness, 3/24 active and 8 issues, with no error banner. This proves
recovered display, not successful execution of that retry click.

Parent ran `npm.cmd --prefix clients/web test`: 112 passed, 0 failed,
0 skipped, 944.37 ms. `npm.cmd --prefix clients/web run build`: exit 0,
136 modules, Vite 510 ms, existing dynamic-import warning. Pure helper tests
cover empty/loading, retained failure, unknown statuses, partial and ready;
they are not full mounted-component tests. Other source surfaces, Network
summary styling, endpoint latency and whole-product acceptance remain open.

### Low-allowance profiling checkpoint (2026-09-10 Shanghai)

At clean `6e14270`, usage was 44% of the five-hour window and 93% weekly.
No new implementation or load test was started. Read-only source inspection
corrects the interpretation of the earlier endpoint timings:

- `/api/market/observations` calls `_db_market_observations`, which orders and
  materializes the entire observation table with `.all()`, serializes every
  row, then applies identity source filtering. Its 15-second timeout is not a
  measurement of the UI's normalized request.
- The Web client's normalized request is `/api/market/normalized?limit=500`;
  no call to the raw `marketObservations()` client method was found in Web
  source. Profile this actual request before attributing UI delays to the raw
  endpoint or changing its compatibility contract.
- `list_normalized_market_view` still reads bounded source coverage (distinct
  source count plus a partitioned row-number query) and all FX observations,
  with an ECB fallback. The new global ordering index does not by itself
  establish that those operations are bounded or fast.

Next bounded work: measure normalized request and constituent reads with
timeouts and no repeated full-table load; inspect FX selection requirements
before restricting history; retain daily-source coverage. Any raw-endpoint
pagination change needs explicit SDK/API compatibility and entitlement tests,
not a blanket row limit. Also inspect normalized-route entitlement enforcement:
its handler returns the repository rows directly, unlike the raw handler's
explicit source filter. Middleware may supply controls; this is an audit target,
not a proven disclosure finding. Preserve the full UX-01 objective and keep
heavy work deferred while weekly allowance is low.

### Actual normalized-request checkpoint (2026-09-10)

After the user resumed, parent fetched origin and found the worktree clean.
Weekly allowance was 95% used. One read-only request to
`http://127.0.0.1:8000/api/market/normalized?limit=500`, with a 15-second deadline,
returned HTTP 200 in 6,315 ms and 510,969 response bytes. No response rows were
printed. This is a single warm-runtime observation, not a controlled benchmark
or a claim that the earlier intermittent timeouts are resolved.

Access-control inspection found that the normalized handler returns repository
rows without the raw-observation handler's `_filter_entitled_rows` call.
`require_entitlement` returns immediately when no source is supplied; its
existence alone does not prove row filtering. Existing
`tests/security/test_identity_row_entitlement.py` covers raw observations and
legacy-token behavior, not normalized rows. Next priority is a focused
normalized-endpoint scoped-identity denial test, including restricted rows and
derived warnings, followed by a minimal correction if reproduced. Use
PostgreSQL or isolated mocked dependencies, not a new SQLite store. Preserve
legacy-token compatibility deliberately and inspect router/middleware wiring
before claiming a full-route disclosure. No code, permissions, database data,
or runtime configuration was changed in this assessment.
