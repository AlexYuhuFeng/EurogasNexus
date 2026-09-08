# Motion System

Status: **DRAFT - proposed subordinate specification; RFC not accepted; pending final diff review**

This is a proposal, not evidence that motion is implemented or compliant. Until
the RFC is accepted and authority is reconciled, `UI_CONTENT_STANDARDS.md`
remains the transitional client authority. On acceptance, the Professional UI
Constitution becomes the sole visual and interaction authority and this document
remains subordinate for motion. It adds no domain, API, agent, analytics, or
execution semantics.

## Intent

Motion in Eurogas Nexus is fast, subtle, functional, and predictable. It may
communicate state, hierarchy, continuity, or direct feedback. It MUST NOT
entertain, compete with analytical content, obscure evidence, or make a live
market surface feel unstable.

## Proposed tokens

The proposed duration scale is exactly:

| Token | Duration | Use |
| --- | ---: | --- |
| `--motion-none` | 0ms | initial state, immediate feedback, reduced motion |
| `--motion-fast` | 120ms | focus/selection, tab indicator, small status change |
| `--motion-standard` | 180ms | menu, popover, drawer, toast, expand/collapse |
| `--motion-emphasis` | 240ms | modal entry, context-rail transition, agent-step progression |

No ordinary UI transition SHOULD exceed 240ms. A feature MUST NOT introduce a
local duration or easing value without a reviewed contract.

Proposed easing roles:

- entry: `ease-out`;
- exit: `ease-in`;
- position or selection continuity: `ease-in-out`.

The implementation SHOULD expose these as semantic tokens alongside the existing
semantic token family. It MUST consolidate existing token families rather than
create a third token system.

## Transform and opacity rule

Transient motion MUST prefer `transform` and `opacity`. Do not animate layout,
table geometry, text size, or a shell row in a way that moves the analytical
surface or causes cumulative layout shift.

If a surface needs a measured structural row, reserve the row and let content
begin below it. A fixed topbar MUST NOT animate over or overlap content.

## Proposed applications

| Interaction | Proposed motion | Required behavior |
| --- | --- | --- |
| Workspace/task tab | fast | Move the indicator with transform; keep tab semantics, focus, and active content immediate. |
| Menu or popover | standard | Enter from its anchor with opacity/short transform; remain within the viewport; Escape closes immediately. |
| Drawer/context rail | standard or emphasis | Preserve content dimensions and focus return; do not cover warnings or primary actions. |
| Modal | emphasis | Move focus into the modal, keep the backdrop restrained, and return focus to the invoker on close. |
| Toast/status acknowledgement | standard | Do not replace the text state with motion; dismissal remains keyboard accessible. |
| Expand/collapse | standard | Keep headings and controls stable; do not hide a required warning during transition. |
| Agent-step progression | emphasis | Show explicit stage text and status; motion is secondary to the observable artifact and human gate. |
| Selection/focus | fast | Use a visible border, background, or text signal immediately; motion is optional. |

These are interaction treatments, not new product capabilities. Existing
workspace components own domain state; shared motion tokens own only transition
behavior.

## Data and market update rules

Prices, curves, tables, maps, KPI values, and source freshness updates MUST NOT
flash, bounce, pulse, or animate on every rapid update. A data update should
repaint predictably, retain stable dimensions, and expose the new value, unit,
time basis, and source/freshness state through content.

An optional one-time 120ms selection/update emphasis MAY be used only when it
does not repeat with rapid ticks and does not imply direction, confidence,
execution, or recommendation. Never animate a `verified` value into an
`indicative` value, or conceal a `stale`, `restricted`, `missing`, or
`human-review-required` state behind a transition.

Charts MUST not animate illustrative or fabricated series. Persisted/API-backed
series may use a restrained transition only where the update remains readable
and the axes, units, time basis, and provenance stay visible.

## Loading, error, and evidence states

- Loading uses reserved dimensions and a stable label or skeleton; it MUST NOT
  cause the workspace to jump between shell and content rows.
- Empty and error states appear immediately with their reason and valid next
  action; motion cannot substitute for text.
- Retry and endpoint-error surfaces enter within their assigned layout region;
  they MUST NOT cover navigation, context selectors, or decision content.
- Evidence, source, freshness, entitlement, `verified`, and `indicative`
  semantics remain visible throughout transitions.
- Restricted and degraded states MUST not use attention-grabbing loops or sound.

## Accessibility and reduced motion

The implementation MUST support `prefers-reduced-motion: reduce`.

Under reduced motion:

- all nonessential transitions use `--motion-none`;
- repeated animation, shimmer, pulse, bounce, and attention loops are disabled;
- focus, selected state, expanded state, and status text remain visible;
- keyboard behavior and focus return are unchanged;
- no information is communicated by motion alone.

Focus indication itself MUST be immediate and visible. Do not delay a keyboard
action until an animation finishes. Motion MUST NOT create seizure-risk flashing
or interfere with screen-reader state changes.

## Navigation, overlays, and shell behavior

The shared shell owns global context and status. Motion MUST preserve one owner
for gas day, delivery product, Portfolio where applicable, primary market
context, and runtime/data status.
Workspace transitions MUST preserve URL/deep-link and trader/selection context;
motion must not imply a new navigation model.

Menus, drawers, modals, and popovers MUST implement the existing or proposed
keyboard contracts: accessible name, visible focus, Escape, bounded placement,
and focus return. Their transition MUST not make an off-screen or clipped
control temporarily appear valid.

## English and Mandarin parity

Motion MUST be language-neutral in meaning. EN and CN must expose the same
state, action, boundary, and timing behavior. Longer Mandarin labels MUST fit
without clipping, forced overlap, or a motion-dependent tooltip. The active
control, warning, unit, time basis, and human-review boundary remain available
without hover or animation.

## No-execution and professional boundary

Motion MUST NOT make candidate, scenario, assumption, indicative, research-only,
or human-review-required output look like an execution signal. Do not use rapid
green/red flashes, celebratory effects, progress theater, or automatic action
transitions for strategy, route, portfolio, shadow, research, or agent results.

The agent UI may show observable stage progression, tool status, warnings,
findings, confirmation gates, review-pack state, and replay state. It MUST NOT
animate hidden chain-of-thought, imply autonomous approval, or introduce
execution behavior.

## Implementation boundary

Use CSS/native transitions and the existing client stack. Do not add an
animation framework or new runtime dependency. Shared primitives may own motion
tokens and focus/transition contracts; domain components own the state being
represented.

Do not animate around unresolved data correctness or hydration questions. The
UX audit records loading/schema and blocked-route observations that require
separate validation; motion MUST NOT conceal those causes.

## Binding adoption and compliance evidence

Planner RFC approval plus authority reconciliation makes this contract binding.
The evidence below proves implementation compliance afterward; it is not a
prerequisite for binding the contract:

1. normal, loading, empty, degraded, restricted, stale, and error states;
2. 1440x900 and 1920x1080 shell/overlay checks with no overlap or page-level
   layout shift;
3. representative EN/CN workflows;
4. keyboard focus, Escape, focus return, screen-reader state, and reduced-motion
   checks;
5. rapid price/table updates proving no flash or distracting repeated motion;
6. agent stage/review/replay and dataset evidence states showing explicit text,
   provenance, `verified`/`indicative` meaning, and no-execution boundaries;
7. exact test, screenshot, and runtime commands recorded separately from this
   proposal.

Until RFC approval and authority reconciliation, this document remains a draft
proposal and `UI_CONTENT_STANDARDS.md` remains authoritative. Binding adoption
does not assert that the product already complies.
