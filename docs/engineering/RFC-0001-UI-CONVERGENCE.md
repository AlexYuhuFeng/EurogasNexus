# RFC-0001: Professional Workstation UI Convergence

Status: `draft - implementation approval pending contract review`

Owner: UI architecture and review lead

Reviewers: Web/desktop, domain-interface, accessibility and test owners

Date: 2026-09-08

## Summary

Adopt one professional workstation UI Constitution and motion system across the
existing Web and desktop product. This implements the UX-01 convergence brief;
it is not a new feature architecture or a new styling framework.

## Problem and evidence

The [audit](../ux/POST_CR15_UI_AUDIT.md) records real overlapping Network shell
controls, inconsistent System tabs, overly wide Strategy forms, misleading
empty states and discrepant route status. The [census](../ux/COMPONENT_CENSUS.md)
separates authored usage from shared implementations. Four existing primitives
are only partially adopted; 39 authored table sites use inconsistent models.
The existing executable predates the current shell and cannot prove parity.

## Proposed decision

- Make the Professional UI Constitution the single visual/interaction authority
  after review; reconcile UI_CONTENT_STANDARDS in the same acceptance change.
  Domain, entitlement, time, provenance and no-execution contracts stay binding.
- Use fixed 11/12/13/14/18/20px type, 4/8/12/16/24/32px spacing, 28/32/36px
  controls and 4/6/8px radii. Consolidate existing token families rather than
  introducing an independent third language.
- Put shell, context, status and workspace content in structural layout rows.
  An error banner or wrapped account control MUST NOT cover the workspace.
- Reuse WorkspaceTabs, PanelHeader, MetricStrip and StatusBadge; add only
  demonstrated shared needs for tables, fields, states and workspace layouts.
- Keep global context single-owned. Workspace primary actions go in the upper
  right header; filters stay above their affected surface. Numeric columns are
  right-aligned with explicit units/time basis and local overflow containment.
- Use restrained 0/120/180/240ms motion with reduced-motion support and no
  continuous price flashing or decorative motion. No new UI/animation library.
- Prioritize 1440x900, verify 1920x1080 and a smaller supported desktop, and
  preserve EN/CN structural parity, keyboard/focus and restricted-state safety.
- Required research dataset detail/artifact and governed agent review/replay
  interactions must expose existing backend capabilities. Missing UI is not
  waived merely because the backend exists; do not invent new analytics/models.

## Alternatives

1. Page-by-page restyling: rejected because it preserves competing patterns.
2. New component framework/full frontend rewrite: rejected; unnecessary API,
   interaction, dependency and regression risk.
3. Raw global CSS replacement: rejected; semantic distinctions, map geometry,
   entitlement states and specialist analytical surfaces need scoped migration.

## Scope, compatibility and governance

All existing trader, operator, research and agent workspaces are in scope.
No trade execution, new datastore, new strategy/model architecture, source-rights
changes or client-side domain calculations are authorized by this RFC.
Existing deep links, selections, typed API semantics, units, historical calendar
versions and human gates must survive. Keep domain fixes separate from visual
commits. Backend PostgreSQL remains runtime truth; no UI test may disguise
missing market evidence with unlabelled fabricated values.

Preserve existing class contracts until consumers/tests migrate, then remove
obsolete rules. Roll back a faulty UI batch as a scoped change, not by resetting
unrelated work or downgrading runtime data. No credentials or vendor payloads
belong in source, screenshot baselines or public reports.

## Review and acceptance gates

- [ ] Review proposed Constitution and motion system against every UX-01 rule.
- [ ] Reconcile client standards, bilingual companions and authority links.
- [ ] Append accepted decision to ADR record when this RFC is accepted.
- [ ] Finish pre-refactor workflow inventory and identify test fixture gaps.
- [ ] Review each delegated diff, screenshots, reuse and regression impact.
- [ ] Enforce tokens/components through sensible UI-contract CI and tests.
- [ ] Complete current-ref functional, visual, accessibility, EN/CN, performance,
  long-session, entitlement and desktop validation with exact evidence/counts.
- [ ] Zero P0/P1; explicitly disposition P2/P3; no weakened domain boundaries.

The [ExecPlan](UX01_EXECPLAN.md) sequences the work. Draft status is not proof
that affected owners reviewed this proposal or that the current UI complies.
