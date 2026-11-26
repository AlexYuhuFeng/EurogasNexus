# Motion System

Status: **Accepted binding subordinate contract - RFC-0001 adopted 2026-09-08; implementation acceptance pending**

This is a binding motion contract, not evidence that motion is implemented or
compliant. RFC-0001 was accepted and authority was reconciled on 2026-09-08.
The Professional UI Constitution is the sole visual and interaction authority
and this document remains subordinate for motion. It adds no domain, API,
agent, analytics, or execution semantics.

## Intent

Motion in Eurogas Nexus is fast, subtle, functional, and predictable. It may
communicate state, hierarchy, continuity, or direct feedback. It MUST NOT
entertain, compete with analytical content, obscure evidence, or make a live
market surface feel unstable.

## Motion tokens

The tokens live in one place, `clients/web/src/styles/tokens.css`; this table
quotes them and `clients/web/tests/motionContract.test.ts` fails when the two
differ. The duration scale is exactly:

| Token | Duration | Use |
| --- | ---: | --- |
| `--motion-none` | 0ms | initial state, immediate feedback, reduced motion |
| `--ds-duration-fast` | 80ms | hover, press, focus/selection, small status change |
| `--ds-duration-base` | 160ms | menu, popover, tab, expand/collapse, toast, page change |
| `--ds-duration-slow` | 240ms | modal and sheet entry, inspector, context rail, agent-step progression |
| `--ds-duration-exit` | 120ms | popover, menu or dialog closing (0.75 × base) |
| `--ds-duration-exit-slow` | 180ms | sheet closing (0.75 × slow) |
| `--ds-duration-flash` | 400ms | a live cell's tick (see data update rules) |
| `--ds-duration-map` | 400ms | map camera |
| `--ds-duration-pulse` | 1200ms | one beat of a busy pulse or a found-pin ping |
| `--ds-duration-loop` | 1400ms | one sweep of a loading shimmer or one turn of the busy ring (`Spinner`) |

The older names `--motion-fast`, `--motion-standard` and `--motion-emphasis`
are aliases of fast, base and slow. No ordinary UI transition SHOULD exceed
240ms; the flash, map, pulse and loop durations are not transitions. A feature
MUST NOT introduce a local duration or easing value without a reviewed contract.

Easing roles:

| Token | Curve | Use |
| --- | --- | --- |
| `--ds-ease-out` | `cubic-bezier(0.2, 0, 0, 1)` | entry: decelerates into place |
| `--ds-ease-in` | `cubic-bezier(0.4, 0, 1, 1)` | exit: accelerates out of the way |
| `--ds-ease-in-out` | `cubic-bezier(0.4, 0, 0.2, 1)` | moving between two places |

An exit takes about three quarters of its entry. Dialogs, sheets and popovers
close with an exit transition (`transition-behavior: allow-discrete` on
`display` and `overlay`); where a browser lacks it they close at once.

A page change fades the page container once, for `--ds-duration-base`; panels
do not play their own entrance, so a tab switch never replays one per panel.

## Transform and opacity rule

Transient motion MUST prefer `transform` and `opacity`. Do not animate layout,
table geometry, text size, or a shell row in a way that moves the analytical
surface or causes cumulative layout shift.

If a surface needs a measured structural row, reserve the row and let content
begin below it. A fixed topbar MUST NOT animate over or overlap content.

## Proposed applications

| Interaction | Proposed motion | Required behavior |
| --- | --- | --- |
| Workspace/task tab | fast (indicator); base (page container, once) | Move the indicator with transform; keep tab semantics, focus, and active content immediate. |
| Menu or popover | base in, exit out | Enter from its anchor with opacity/short transform; remain within the viewport; Escape closes immediately. |
| Drawer/context rail | base or slow | Preserve content dimensions and focus return; do not cover warnings or primary actions. |
| Modal | base in, exit out | Move focus into the modal, keep the backdrop restrained, and return focus to the invoker on close. |
| Toast/status acknowledgement | base | Do not replace the text state with motion; dismissal remains keyboard accessible. |
| Expand/collapse | base | Keep headings and controls stable; do not hide a required warning during transition. |
| Agent-step progression | slow | Show explicit stage text and status; motion is secondary to the observable artifact and human gate. |
| Selection/focus | fast | Use a visible border, background, or text signal immediately; motion is optional. |

These are interaction treatments, not new product capabilities. Existing
workspace components own domain state; shared motion tokens own only transition
behavior.

## Data and market update rules

Prices, curves, tables, maps, KPI values, and source freshness updates MUST NOT
flash, bounce, pulse, or animate on every rapid update. A data update should
repaint predictably, retain stable dimensions, and expose the new value, unit,
time basis, and source/freshness state through content.

A live table cell MAY show one neutral background emphasis of
`--ds-duration-flash` (400 ms, `tokens.css`) when its value changes, and only
then (UX R2, `DataGrid` `flash`):

- The emphasis is the same for up and for down. It never implies direction,
  confidence, execution, or recommendation, and it is off under
  `prefers-reduced-motion`.
- Direction is content, not motion or colour: a ▲ or ▼ (`DirectionMark`) stays
  beside the value until the next tick, with the word for screen readers, and
  the signed change against the close is shown in its own column with the same
  glyph. A green/red flash is not used (colour-blind readers misread it).
- Only a new value of the same instrument is a tick. The cell is keyed to row,
  column and instrument (`flashIdentity`); a tenor switch or another contract in
  the same row resets the cell quietly, with no emphasis and no glyph.
- Each tick restarts the emphasis rather than queuing it, so rapid ticks never
  build up a repeating pulse.

Never animate a `verified` value into an `indicative` value, or conceal a
`stale`, `restricted`, `missing`, or `human-review-required` state behind a
transition.

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

Implementation acceptance remains pending. Binding adoption does not assert
that the product already complies; screenshots, runtime review, tests,
accessibility checks, and visual evidence remain separate unchecked gates.
