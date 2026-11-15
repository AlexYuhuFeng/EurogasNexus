# Design tokens

Status: adopted 2026-11-15 (UX-01, UX-10, first part of UX-02). Related:
`docs/ux/DESIGN_SYSTEM.md` (principles, layers), `docs/product/COMPONENTS.md` (one control per
meaning), `docs/product/UX_REFERENCE.md` (trader-first presentation rules).

Every size, radius, duration and colour value the web client draws with is written once, in
`clients/web/src/styles/tokens.css`. Components use the semantic roles and steps below, never a
raw value and never a palette name. Light and dark redefine the same roles; nothing else changes
between themes.

## Scales

| Group | Tokens | Values |
|---|---|---|
| Type size / line | `--ds-text-xs` `sm` `base` `md` `xl` `num`, with `--ds-line-*` | 11/16, 12/16, 13/20, 15/22, 18/24, 20/24 px; Chinese adds 2 px of line height |
| Weight | `--ds-weight-regular` `medium` `semibold` | 400, 500, 600 (browser 700 for `strong`, `b`, `th` is reset) |
| Figures | `--ds-numeric` | `tabular-nums`, set on `body`: every figure lines up |
| Space | `--ds-space-05` `1` `2` `3` `4` `6` `8` | 2, 4, 8, 12, 16, 24, 32 px |
| Controls | `--ds-control-sm`, `--ds-control`, `--ds-control-touch` | 28 (dense: tables, toolbars), 32 (forms), 44 (coarse pointer) |
| Rows, chips | `--ds-row`, `--ds-row-header`, `--ds-chip` | 32, 28, 20 px (rows and badges are not controls) |
| Radius | `--ds-radius-sm` `md` `pill` | 4 (controls, cells, badges), 8 (panels, popovers, dialogs), 999 (pills, avatars) |
| Elevation | `--ds-shadow-pop`, `--ds-shadow-modal`, `--ds-focus` | two shadows only; panels use a border |
| Motion | `--ds-duration-fast` `base` `slow` `map`, `--ds-ease-out` | 80, 160, 240, 400 ms; off under reduced motion |

These follow the review's M.2 scale. Where it left a choice: `md` is 15 px for panel titles and
`h3` takes the body size at semibold (a sixth size for sub-headings would break the six-size
budget); badges keep a 20 px chip height of their own because a badge is not a control; the
spacing step 20 px is retired (the old `--ds-space-5` alias now resolves to 16).

## Colour roles

| Role | Tokens |
|---|---|
| Surfaces, lowest to highest | `--ds-bg`, `--ds-surface`, `--ds-surface-2` (hover, header), `--ds-surface-3` (pressed) |
| Lines | `--ds-border-subtle` (between rows), `--ds-border` (around surfaces), `--ds-border-strong` (around controls) |
| Text | `--ds-text-1`, `--ds-text-2`, `--ds-text-3`, `--ds-text-disabled` |
| Action and selection | `--ds-accent`, `--ds-accent-hover`, `--ds-on-accent`, `--ds-accent-soft` (selected row), `--ds-focus-ring` |
| Inverse | `--ds-ink`, `--ds-on-ink` |
| Sign | `--ds-positive`, `--ds-negative`, `--ds-on-negative` |
| Status | `--ds-status-{ok,watch,breach,info,simulated,stale}` and each `-soft` background |
| Profit and loss | `--pnl-up`, `--pnl-down`; `--pnl-profit` / `--pnl-loss` follow the user's convention (`data-pnl="red_up"` swaps meaning, not colours) |
| Chart series | `--ds-series-1` … `--ds-series-8`, each at least 3:1 against the surface |

Simulated has its own colour (violet), so a simulated-price banner is never read as a warning
about a real price (UX_REFERENCE rule 10).

`clients/web/tests/tokenContrast.test.ts` computes contrast from the values in `tokens.css`:
every text role on every surface, status text on its own soft background, text on the selected
row and on-colours on their fills at 4.5:1; the focus ring and chart series at 3:1; in both
themes. Control borders (`--ds-border-strong`) are not held to 3:1: controls are identified by
their label and fill, and a 3:1 border on every input would be heavier than the desk wants. That
is a recorded choice, not an oversight.

## Older names

`tokens.css` keeps the earlier names (`--eg-*`, `--space-*`, `--text-meta`, `--radius-control`,
`--ds-text-lg`, `--ds-radius-lg`, …) as aliases pointing at the nearest role or step, so
stylesheets not yet converted already follow the scales. Converted files may not use them.

## The lint

`clients/web/scripts/cssTokenLint.mjs`, run by `tests/cssTokenLint.test.ts` (so by `npm test`,
which CI runs) and by `npm run lint:css`. In a converted stylesheet it fails on:

- a raw colour (hex, `rgb()`/`hsl()`/…, or a named colour), outside mask properties;
- a font size that is not `var(--ds-text-xs|sm|base|md|xl|num)` (no px, em, rem);
- a radius that is not `var(--ds-radius-sm|md|pill)` or `0`;
- a `height`/`min-height`/`max-height` literal between 18 and 48 px (control-sized: use a token);
- a weight other than 400, 500, 600;
- a legacy variable or a deprecated `--ds-*` alias.

Files not yet converted are listed with their count in
`clients/web/scripts/css-token-baseline.json`. A listed count may only fall; when it falls the
test asks for `npm run lint:css -- --update`, which lowers counts and drops clean files but
never raises a count or adds a file. The test also caps the number of listed files and the total.

At adoption: 15 stylesheets and 1,770 raw values before; 14 clean and 292 remaining after, all in
`app.css` (231 colours, 59 control-sized heights, 2 undefined legacy variables). `app.css` is
retired page by page (UX-06).

## Converting a file

1. `node scripts/cssTokenConvert.mjs src/path/file.css` rewrites what has one right answer:
   legacy variables to roles, fallbacks inside `var(--ds-*)`, rem sizes on the scale, radii.
2. `node scripts/cssTokenLint.mjs --list src/path/file.css` lists the rest. Decide each: a
   colour becomes a role (or a `color-mix` of roles), a control height becomes
   `--ds-control-sm`/`--ds-control`, a row `--ds-row`, an `em` size a step.
3. `npm run lint:css -- --update` and lower the caps in `tests/cssTokenLint.test.ts`.
4. Look at the screens the file styles in both themes, and run the geometry audit.

## Geometry audit (UX-10)

`scripts/uat/geometry_audit.mjs` loads the key screens (Today, Prices, Network, Position,
Limits, Source Center) at 1440 and 1366 px in a real browser and counts the distinct font sizes,
weights, control heights and radii the browser computes, plus controls under 24 px, numeric
cells without tabular figures and shadows. It compares them with
`scripts/uat/geometry_budget.json`, including the count of values off the token scale, and
exits 1 when a budget is exceeded. Clickable table rows and cards are reported apart from
controls; MapLibre's own controls are excluded.

| 1440 px, six screens | Before | After | Budget |
|---|---|---|---|
| Font sizes | 10 (incl. 10.83, 11.05, 9.17 from `em`/`small`) | 5 (11, 12, 13, 15, 18) | 5 |
| Font weights | 5 (400, 500, 600, 700, 900) | 3 | 3 |
| Control heights | 10 (20–42) | 2 (28, 32) | 2 |
| Radii | 7 (999, 6, 50%, 12, 8, 2, 4) | 3 (4, 8, 999) | 3 |
| Controls under 24 px | 30 | 0 | 0 |
| Max shadows on a screen | 4 | 3 | 3 |

1366 px measures the same. Run it against a running API and Vite server with a development
sign-in:

```bash
EUROGAS_UAT_BASE_URL=http://127.0.0.1:3000 \
EUROGAS_NEXUS_DEV_LOGIN_USERNAME=... EUROGAS_NEXUS_DEV_LOGIN_PASSWORD=... \
node scripts/uat/geometry_audit.mjs            # --report to print without failing
```

The CI browser-acceptance job runs it with `--report` after the sweep and keeps the JSON with
the evidence. The budgets were measured on the demo desk (`scripts/demo/seed_demo_desk.py`); the
job seeds the UAT fixture instead, so the step fails nothing until the budgets are confirmed on
that data. Then drop `--report`.

## Primitives

In `clients/web/src/components/ui/`, styled by `primitives.css` (tokens only):

| Primitive | Notes |
|---|---|
| `Button` | `primary`, `secondary`, `quiet`, `danger`; `sm` 28 / `md` 32; `type` always explicit; loading is busy and disabled; disabled looks disabled |
| `IconButton` | required `label` is the accessible name and tooltip; glyph hidden from screen readers |
| `StatusBadge` | `tone`: ok, watch, breach, info, simulated, stale, neutral; the older `variant`/`status` form still works |
| `KeyFigure` | label, value (tabular), unit, optional delta (P&L convention), age and non-current state in words; `MetricStrip` renders its items with it |
| `Panel` | title row with meta and actions slot, body; the section is labelled by its title |
| `EmptyState` | cause, next step, one action; `compact` one-line form |
| `Skeleton` | still bars, shimmer only when motion is allowed; one announced loading status |
