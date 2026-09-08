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
