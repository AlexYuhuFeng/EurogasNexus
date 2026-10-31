# Interaction standard: hover, press, focus, motion, elevation

How every control in Eurogas Nexus answers the pointer and the keyboard. The reference
points are the conventions professional desktop software follows (Microsoft Fluent 2,
Apple's Human Interface Guidelines, Material 3's state layers) and the trading screens our
users live in all day (Trayport, exchange front ends): dense, calm, fast, and never
decorative.

## States

| State | What changes | What never changes |
|---|---|---|
| Rest | — | — |
| Hover | Background tints one step (secondary), or the fill lightens (primary); borders strengthen | No shadow, no movement, no size change: the layout must not twitch under the cursor |
| Press | One step darker; settles 0.5 px | No bounce, no ripple |
| Keyboard focus | 2 px focus ring (`:focus-visible` only, so a mouse click does not leave a ring) | The ring is never removed without a replacement |
| Selected | Accent text or underline, or the raised segment in a segmented control | Selection is never shown by colour alone: weight or a marker accompanies it |
| Disabled | Half opacity, not-allowed cursor, no hover response | The control stays in place (no reflow when it becomes enabled) |
| Destructive | Quiet until hovered (red text and border); only the confirm button in the inline confirmation is solid red | Never a one-click destructive action |

## Elevation (shadows)

Shadows mean "this sits above that", not "you can click me".

| Layer | Shadow | Examples |
|---|---|---|
| Canvas | none | page background |
| Resting surface | `--ds-shadow-sm` | panels, cards |
| Floating | `--ds-shadow-md` | menus, popovers, map cards, the finder |
| Modal | `--ds-shadow-lg` + dimmed backdrop | dialogs (report a problem, confirmations) |

So a button does **not** gain a shadow on hover. That is a consumer-web habit; on a dense
workstation it adds noise to every pointer movement across a table of prices.

## Motion

* **Durations**: 120 ms for colour changes (hover, press), 180 ms for panels entering,
  overlays 120–180 ms with a decelerating curve (`--ds-ease-out`). Nothing longer than
  260 ms except a loading indicator.
* **Where motion carries meaning**: a price that changes flashes its cell for about 400 ms
  (the convention on every trading screen), flows move along pipelines that report flow,
  live outages pulse, a dialog rises a few pixels as it opens. Nothing else moves.
* **Never**: animated numbers counting up, parallax, decorative loops, motion on hover.
* **Reduced motion**: under the operating system's *reduce motion* setting every
  transition and animation is cut to nothing; information that motion carried (a changed
  price, a live outage) stays visible statically.

## Density and targets

Controls are 28–32 px high on desktop (the workstation density traders expect) with at
least 24 px pointer targets; on touch devices (tablets) the same controls grow to 40 px.
Tables use tabular numerals, right-aligned numbers and one-line rows.

## Sounds and notifications

The app makes no sound. Alerts reach people through the notification centre in the top
bar and, for what cannot wait, the channels IT configures (email, Teams or Slack, SMS);
see [Support, bug reports and updates](../guides/SUPPORT_AND_UPDATES.md).
