# RFC-0001: Professional Workstation UI Convergence

Status: `accepted contract - adopted 2026-09-08; implementation acceptance pending`

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

## Decision

- Make the Professional UI Constitution the single visual/interaction authority
  under this accepted contract; reconcile UI_CONTENT_STANDARDS in the same
  acceptance change.
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

## Authority matrix

| Concern | Authoritative source | Rule |
| --- | --- | --- |
| Visual and interaction contract | `PROFESSIONAL_UI_CONSTITUTION.md` | Sole visual/interaction authority under this accepted contract. |
| Motion | `MOTION_SYSTEM.md` | Binding subordinate motion contract; it cannot create a competing visual contract. |
| Content, domain, time basis, rights, provenance, entitlement, and no-execution boundaries | `UI_CONTENT_STANDARDS.md` | Remains authoritative for these non-visual contracts, including after visual authority is reconciled. |
| Architecture and API semantics | Architecture and API contract documents | Prevail for domain behavior, endpoint semantics, schemas, and server/client boundaries; UI documents cannot override them. |
| English and Chinese paired guides | `UI_UX_STYLE_GUIDE-EN.md`, `UI_UX_STYLE_GUIDE-CN.md` | Paired nonnormative implementation companions with no independent authority. |

This RFC and the authority reconciliation were accepted on 2026-09-08, making
the matrix binding as a contract. Screenshots, tests, and runtime evidence
prove implementation compliance afterward; they are not prerequisites for
contract adoption.

## Contract review record

The planner reviewed the Constitution and Motion drafts, their diffs, the
component census, the runtime UI audit, and the RFC clarifications. Planck
independently reviewed the contract direction; the reviewed clarifications were
addressed. This record does not claim human-owner review or implementation
acceptance.

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

Historical replay MUST preserve the calendar/version recorded with the replayed
artifact or result; it MUST NOT reinterpret that historical record with the
current calendar. New ingestion MUST use the corrected `EU-CAM-UTC-2025`
calendar. DST boundary tests are REQUIRED for both historical replay and new
ingestion, with the calendar/version and test fixture ID recorded in evidence.
The acceptance label `en` means the existing `en-US` runtime alias/locale
surface; this clarifies test terminology only and does not change runtime locale
resolution, resource keys, or fallback behavior.

## Rights validation matrix

Each row requires visible lineage, restriction state, and simulation or
research-only labeling where applicable. Acceptance must use server-side
fail-closed negative fixtures; this RFC invents neither fixture IDs nor pass
claims.

| Surface | Required visible evidence | Required negative/no-leakage check |
| --- | --- | --- |
| Market | Source/observation lineage, freshness, and restricted-source state; simulated values explicitly marked. | Denied or restricted source fixture returns fail-closed and does not expose the protected payload. |
| Portfolio | Resource/contract lineage, entitlement restriction, and scenario/simulated allocation state. | Denied entitlement fixture prevents unauthorized detail or action data; no execution semantics appear. |
| Research | Dataset/artifact lineage and version, rights restriction, and research-only/simulated state. | Restricted dataset/export fixture fails closed and leaks neither protected rows nor metadata beyond the contract. |
| Agents | Capability/tool and result lineage, rights restriction, and simulation/human-gate state. | Unauthorized MCP capability fixture fails closed; replay cannot expose restricted tool inputs or results. |
| Review/export | Evidence lineage, review/entitlement restriction, and research-only/simulated status on the review pack and export. | Denied export/redaction fixture fails closed with no restricted payload leakage through review, replay, or export. |

Record the actual fixture ID, operation ID, request/result, and no-leakage
assertion for each executed case. A missing fixture or unrun negative case is
unverified, not a pass.

## Canonical acceptance cases

- **Canonical technical workspace URL:** each technical workspace has one
  canonical URL and one owning surface. Direct navigation, refresh, and
  in-product navigation MUST resolve the task to that surface without creating
  a competing owner.
- **Remove stale task parameters on handoff:** navigation MUST remove or replace
  a source workspace's local `task` parameter when entering another workspace.
  Preserve gas day, delivery product, Portfolio and applicable selections; do not
  carry unrelated local filters into the destination. This is URL normalization,
  not a new UI strip or a market-data freshness rule.
- **Back/Forward agreement:** browser Back and Forward MUST leave the URL,
  selected tab, heading, and primary content describing the same task. A URL
  change without matching tab/heading/content is an acceptance failure.

## CR14/CR15 endpoint-to-screen evidence

CR14 and CR15 acceptance requires endpoint-to-screen evidence, not endpoint
existence or backend tests alone. For every required workflow step, record the
actual endpoint and operation ID, fixture ID, exact returned result (including
an explicit no-result), rendered screen reference, and tested revision. Do not
invent IDs or infer a rendered result from a successful HTTP response; missing
operation/fixture/result evidence remains unverified.

- **CR14:** trace catalog selection through dataset/artifact detail and the
  existing build/validate, quality, and export operations, including lineage,
  rights, and corrected calendar/version where applicable.
- **CR15:** trace the existing governed path through ResearchPlan, findings,
  StrategyIR, validation, challenge, review-pack, confirmation, and replay
  evidence, including MCP rights and human-gate state. Do not expose hidden
  chain-of-thought or add execution semantics.

Missing current-run evidence, external release gates, and review/fixture gaps
are acceptance prerequisites or evidence gaps, not automatically runtime P1 UX
defects. A P1 classification requires an accepted in-scope requirement and a
reproduced product behavior that violates it. The required CR14/CR15 UI
workflow gaps remain explicit implementation scope and must not be treated as
accepted thin UI or silently relabeled as runtime severity.

Preserve existing class contracts until consumers/tests migrate, then remove
obsolete rules. Roll back a faulty UI batch as a scoped change, not by resetting
unrelated work or downgrading runtime data. No credentials or vendor payloads
belong in source, screenshot baselines or public reports.

## Review and acceptance gates

- [x] Review Constitution and motion system against every UX-01 rule at the
  contract level.
- [x] Reconcile client standards, bilingual companions and authority links at
  the contract level.
- [x] Append accepted decision to ADR record when this RFC is accepted.
- [ ] Finish pre-refactor workflow inventory and identify test fixture gaps.
- [ ] Review each delegated diff, screenshots, reuse and regression impact.
- [ ] Enforce tokens/components through sensible UI-contract CI and tests.
- [ ] Complete current-ref functional, visual, accessibility, EN/CN, performance,
  long-session, entitlement and desktop validation with exact evidence/counts.
- [ ] Zero P0/P1; explicitly disposition P2/P3; no weakened domain boundaries.

The [ExecPlan](UX01_EXECPLAN.md) sequences the work. Accepted contract status
is not proof that the current UI complies. The pre-refactor workflow inventory
and coverage remain incomplete; implementation, visual, accessibility,
performance, EN/CN, entitlement, desktop, and test gates remain unchecked.
