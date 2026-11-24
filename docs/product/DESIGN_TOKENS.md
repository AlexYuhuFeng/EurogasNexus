# Design tokens

Status: adopted 2026-11-15 (UX-01, UX-10, UX-02, UX-03; UX-04 page frame). Related:
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
| Figures | `--ds-numeric` | `tabular-nums`, set on `body`: every figure lines up. A component writes a figure with `formatMeasure(measure, value)` (`app/time/valueFormat.ts`): one table gives each measure (price 3 dp, unit value 2 dp, volume, P&L, percent, FX rate, tariff, temperature) its decimals, sign rule and grouping, with a true minus (U+2212), a space before the unit and before %. `toFixed` under `components/` fails `tests/numberFormatUsage.test.ts`; machine values use `plainDecimal` |
| Space | `--ds-space-05` `1` `2` `3` `4` `6` `8` | 2, 4, 8, 12, 16, 24, 32 px |
| Controls | `--ds-control-sm`, `--ds-control`, `--ds-control-touch` | 28 (dense: tables, toolbars), 32 (forms), 44 (coarse pointer) |
| Rows, chips | `--ds-row`, `--ds-row-header`, `--ds-chip` | 32, 28, 20 px (rows and badges are not controls) |
| Radius | `--ds-radius-sm` `md` `pill` | 4 (controls, cells, badges), 8 (panels, popovers, dialogs), 999 (pills, avatars) |
| Elevation | `--ds-shadow-pop`, `--ds-shadow-modal`, `--ds-focus` | two shadows only; panels use a border |
| Focus | `--ds-focus` (ring), `--ds-focus-outline`, `--ds-focus-offset` | every focus rule pairs the ring with a 2 px transparent outline, which Windows High Contrast paints in the system colour after it drops box-shadow; `design-system.css` ends with a small `forced-colors` block (badges, selected row, dialogs). `tests/forcedColorsFocus.test.ts` |
| Motion | `--ds-duration-fast` `base` `slow` `map`, `--ds-ease-out`; `--ds-duration-flash` | 80, 160, 240, 400 ms; off under reduced motion. A live cell's tick is a neutral 400 ms flash; its direction is a ▲/▼ that stays (`DirectionMark`) |

These follow the review's M.2 scale. Where it left a choice: `md` is 15 px for panel titles and
`h3` takes the body size at semibold (a sixth size for sub-headings would break the six-size
budget); badges keep a 20 px chip height of their own because a badge is not a control; the
spacing step 20 px is retired (the old `--ds-space-5` alias now resolves to 16).

## Typeface

The interface face is **Inter** (SIL Open Font License 1.1), shipped with the client: variable
weight, Latin and Latin Extended subsets (133 kB of WOFF2, tabular figures included), declared in
`clients/web/src/styles/fonts.css` with `font-display: swap` and served from the client's own
origin, so no request leaves the deployment. `--ds-font-ui` names it first; Chinese text keeps
the device's CJK face through the fallback list after it (PingFang SC, Microsoft YaHei, Noto Sans
CJK SC, ...), because the Inter faces declare only Latin ranges. Reports print with their own
stack (`styles/reports.css`).

Why it is bundled: on 2026-11-17 a tester's Android phone showed "ᴮreaking", "NᴮP", "ᴳᴮP/MWh"
and "46.2ˣ" everywhere. The stylesheet asked for Inter's stylistic sets (`"cv11", "ss01"`,
`"ss01", "ss02"`) on `body`, but Inter was not shipped, so the phone's own UI font (reached
through `BlinkMacSystemFont`/`Roboto`) drew the text, and in that font `ss01` is the set of
status-bar unit glyphs (the small "B" of "KB/s", the small "%" of the battery). A feature tag means
whatever the face that happens to draw the glyph says it means. So:

- no stylesheet requests a letter feature (`ssNN`, `cvNN`, `liga`, `calt`, `dlig`); only numeral
  features (`tnum` through `font-variant-numeric`) are used;
- `font-variant-ligatures: none` is set on every element, unlayered in `fonts.css`, so a layered
  `font:` shorthand (which resets it) cannot turn ligatures back on;
- no font stack starts with a system family (`system-ui`, `-apple-system`, `sans-serif`, ...).

`clients/web/tests/fontFoundation.test.ts` fails on any of these, and on a face that is not
self-hosted. The font files and their licence are recorded in
`clients/web/src/assets/fonts/fonts.json`; `scripts/release/generate_sboms.py` checks each file's
SHA-256 and reproduces the licence in `THIRD_PARTY_NOTICES.md`
(`tests/release/test_bundled_fonts.py`), and the build copies it to `dist/licenses/`. The
desktop bundle and the demo image ship `dist/`, so they carry both.

`--ds-font-mono` (identifiers and code only) is not bundled; it never carries a feature request
either.

## PeriodPicker

`components/ui/PeriodPicker.tsx` is the one date control: `kind="day"` (a date or gas day),
`"month"` (a delivery month) and `"datetime"` (a deadline). It replaces the native
`<input type="date|month|datetime-local">`, whose text and calendar follow the device's locale
(a Chinese phone showed "2026年12月" in the English interface); everything here follows the app's
language. Values are the native strings ("2026-11-16", "2026-12", "2026-11-16T09:30"), so a page
swaps the control without touching its data. A button opens a dialog with a Monday-first grid
(arrows a day/week, Home/End the week, PageUp/PageDown a month, Shift a year, Enter chooses,
Escape closes and returns focus), "Today", and "Clear" for an optional date; 44 px targets on
touch. A time of day alone is a text field with an `HH:MM` pattern, never `type="time"`.
`tests/periodPicker.test.ts` fails on a native date input outside the listed pages that are due
to be deleted.

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
| Profit and loss | `--pnl-up`, `--pnl-down`; `--pnl-profit` / `--pnl-loss` follow the user's convention (`data-pnl="red_up"` swaps meaning, not colours; `data-pnl="blue_orange"`, the colour-vision friendly scheme, makes profit, up and "ok" blue and loss and down orange, so no meaning rests on green against red) |
| Chart series | `--ds-series-1` … `--ds-series-8`, each at least 3:1 against the surface; neighbours, and any two of the first four, at least CIEDE2000 10 apart under normal vision and simulated deuteranopia, protanopia and tritanopia (Machado 2009) |
| Brand | `--ds-brand-navy`, `--ds-brand-navy-deep` (the installer, splash and sign-in panel), `--ds-brand-blue` (`#1d4ed8`, the light theme's accent) and `--ds-brand-blue-light` (`#6ea8fe`, the dark theme's accent), `--ds-on-brand*` (text on navy). Fixed in both themes: they colour the mark, not the interface. See [BRAND_MARK.md](BRAND_MARK.md) |

Simulated has its own colour (violet), so a simulated-price banner is never read as a warning
about a real price (UX_REFERENCE rule 10).

`clients/web/tests/tokenContrast.test.ts` computes contrast from the values in `tokens.css`:
every text role on every surface, status text on its own soft background, text on the selected
row and on-colours on their fills at 4.5:1; the brand navy and blue on the light surfaces and white and light blue on the navy panel at 4.5:1; the focus ring and chart series at 3:1; in both
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
retired page by page (UX-06). After UX-02/03/05: 19 stylesheets, 18 clean, 290 values left
in `app.css`.

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

1366 px measures the same. After UX-02/03/05 (Today, DataGrid, new primitives) the six screens
still measure 5 sizes, 3 weights, 2 control heights (28, 32), 3 radii, 0 controls under 24 px,
0 numeric cells without tabular figures (of 277), at most 3 shadows. Today's key figures use
the 18 px step, not the 20 px figure step, to stay within the five-size budget. Run it against a running API and Vite server with a development
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
| `KeyFigure` | label, value (tabular), unit, optional delta (P&L convention), age and non-current state in words; `MetricStrip` renders its items with it. `notes` puts "Why" and "Method" on the label line as quiet inline links (`inline` on `WhyButton`/`MethodNote`), so a figure has one height with or without them; a position is signed (+/−) in neutral ink, never in P&L colour |
| `Panel` | title row with meta and actions slot, body; the section is labelled by its title |
| `EmptyState` | cause, next step, one action; `compact` one-line form |
| `Skeleton` | still bars, shimmer only when motion is allowed; one announced loading status |
| `Field` | label, one control, hint, error; wires `for`, `aria-describedby`, `aria-invalid`; `inline` for toolbars |
| `Select` | the native `<select>` (most robust in WebView2, WKWebView and on phones), typed options, 28/32 px |
| `Tabs` | one `tablist`, roving tabindex (the active tab is the only Tab stop; when no tab is selected, as in the top bar on a utility page, the first is), Left/Right/Home/End move and activate; `line` or `nav` look. `WorkspaceTabs` is Tabs inside a `<nav>` landmark, so the top bar and every task row move the same way |
| `Segmented` | one choice among views of the same data; a labelled `group` of `aria-pressed` toggles, one Tab stop, arrows move, Enter/Space choose. Replaces `.segmented-control` and the ad-hoc pressed groups |
| `Toolbar` | one dense row (`role=toolbar`), start and end groups; Left/Right move between its buttons, every control stays in the Tab order (a desk toolbar mixes selects and inputs, so Tab must reach each: a recorded choice) |
| `.ds-inline-link` | a quiet link in a line of text (a note beside a label, "1 breach · 3 watch"): a 28 px box (44 px on touch) whose negative block margin gives the line back, so it adds no height and no new control height to the geometry budget |
| `Popover` | anchored note in the top layer (native `popover`), placed against collisions (`popoverPosition.ts`: below, flipped above, clamped, scrolls when tall), follows scroll; opening moves focus in, Escape closes and returns focus to the trigger, a click outside or focus leaving closes. Used by Why, Method, the stale-figures list and the feed list |
| `Dialog`, `Sheet` | one implementation over native `<dialog>` + `showModal()`: page behind inert, Tab wraps inside, labelled by its title, Escape (`cancel`) and backdrop call `onClose`, focus returns to the opener. Sheet docks to the end, the bottom or the full screen (the inspector on a phone) |
| `DataGrid` | the one table: see below |
| `BrandMark` | the mark (`mark`), mark + "EN" (`monogram`) or mark + "Eurogas Nexus" (`wordmark`); `tone` mono (`currentColor`, the chrome default), colour, reverse or auto (colour in light, reverse in dark); `size` sm/md/lg/xl (20/24/32/40 px mark, name on the matching text step) or a px number for the mark alone; one image named "Eurogas Nexus", or `decorative` beside the written name. See [BRAND_MARK.md](BRAND_MARK.md) |

### Dependency decision: no React Aria

The owner approved React Aria Components (Apache-2.0) for Popover, Dialog, Select and Tabs. It
was measured and not added: Dialog, Modal, Popover, Select, Tabs and ToggleButtonGroup from
`react-aria-components@1.22.1` add about 195 kB minified / 60 kB gzip to a bundle whose own
change for all of UX-02/03/05 was 23 kB / 9 kB, and 16 packages (73 MB installed). The browser
already supplies the hard parts: `showModal()` gives the inert background, focus containment,
Escape and the top layer; the `popover` attribute gives the top layer for anchored notes; the
native `<select>` is the accessible list on every platform we ship. What remained (roving
tabindex, collision placement) is a few dozen tested lines. Revisit for a Combobox or a date
grid, where the library would carry real weight.

## DataGrid (UX-03)

`components/ui/DataGrid.tsx`, styled by `datagrid.css`. A controlled, typed table:

```tsx
const columns = useMemo<DataGridColumn<Row>[]>(() => [
  { id: "hub", header: t("market.hub"), rowHeader: true, sortable: true, value: (r) => r.hub },
  { id: "net", header: t("position.net"), unit: "MWh", type: "number", sortable: true,
    value: (r) => r.net_mwh, format: (v) => mwh(v as number), flash: true,
    state: (r) => (r.simulated ? { kind: "simulated", label: "sim", description: "Simulated: not a market price" } : null) },
], [t]);
<DataGrid label={t("position.title")} columns={columns} rows={rows} rowKey={(r) => r.id}
  density="compact" defaultSort={{ columnId: "net", direction: "descending" }}
  onRowAction={(r) => focus(r.hub)} selectedKey={focused} maxHeight="70vh" />
```

- A real `<table>`; `rowHeader` gives `<th scope="row">`; `span` merges equal consecutive values
  (a month over its hubs) while the grid is in that column's order.
- `type: "number"` aligns right in tabular numerals. The unit goes in the header (`unit`); when
  units differ by row (marks in each hub's currency, credit lines in their own currency) the
  cell carries it and the column is not sortable across units.
- Sort: header buttons, `aria-sort`, figures sort largest first, missing values last in both
  directions; controlled (`sort`/`onSortChange`) or `defaultSort`.
- `onRowAction` or `selectedKey` makes it a `grid`: one row is the Tab stop; Up/Down,
  Home/End, PageUp/PageDown move; Enter or Space runs the action; `aria-selected` marks the
  selection. Controls inside cells keep their own keys.
- Rows 32 px (`regular`) or 28 px (`compact`) from tokens; `loading` shows Skeleton rows;
  `empty` is one EmptyState line.
- `state` puts a short word beside the value (stale, late, simulated, revised, manual) with its
  full description for screen readers; `flash` flashes the cell once on change, background
  only, never under reduced motion.
- No layout reads; rows are memoised; 500 rows render in one pass (tested).

Migrated (round 3): the outages list (Desk → Outages & capacity), gas for power (Today), trading
books (Book → Limits & P&L) and the daily gas balance (Book → Delivery). Earlier: Position ladder and its roll-up, credit lines and mandates (Limits), the major hub
board (Prices), the NW Europe balance, the capacity profile book (a contract list), and the
Today book row. Removed with them: the `.market-hub-board-*` grid, `.market-hub-curve`, the
overview board's `.data-table` rules, `.position-bar*`, `.position-horizon`, the
`.market-tenor-tab(s)` and `.market-view-switch` pill groups. Other tables still use
`.position-ladder` / `.data-table` and move as their pages are rebuilt (UX-06).

Migrated (round 4): Book (delivery performance, deal hedge approvals, screen orders and P&L
snapshots, nomination windows and decisions, storage dispatch, the portfolio register) and Deals
(route comparison, route-cost components, LNG cargo bid and terminal terms, tariff publications,
review allocations and decision history, retired contracts, contract intake), plus the licence
register, support inbox and notification channels. `.position-ladder` is gone (no table uses it);
the delivery strip's CSS bars became a chart. Still on `.data-table`: Research (strategy
backtest, compare, shadow; agents; research catalogue), Admin (sources, runtime, access,
reference network), the capacity workspace, the decision workspace and the manual. A grid keeps
the acceptance hooks as row attributes: `rowAttributes={(r) => ({ "data-record": "…",
"data-record-id": r.id })}` (the probe contract accepts both spellings).

## Charts (UX-09)

One chart library: **uPlot** 1.6.32 (MIT, no dependencies; 51 kB, 22 kB gzip, in its own
`vendor-chart` chunk). Why uPlot and not Observable Plot, and the licence evidence:
`docs/legal/DEPENDENCY_LICENSE_REVIEW.md`. The layer is `components/ui/charts/`:
`chartModel.ts` (pure: ticks, stacks, ranges, CSV; tested in `tests/chartModel.test.ts`),
`Chart.tsx` (`Chart`, `Sparkline`) and `charts.css` (imported by the design system).

```tsx
const data: ChartData = {
  axis: "gas-day",                       // "gas-day" | "period" | "time"
  x: days,                               // "2026-11-16" … / "2026-12" … / ISO instants
  xTitle: t("chart.gas_day"),
  unit: "GWh/d",                          // one axis, one unit
  series: [
    { id: "norway", label: t("nwe.norway"), values, style: "bar", stack: true, forecastFrom: 14, simulated },
    { id: "call", label: t("nwe.call"), values: call, style: "line", colour: 4 },
    { id: "target", label: "EU target 90%", values: target, reference: true },
  ],
};
<Chart id="nwe-balance-chart" title={t("nwe.chart_title")} data={data} t={t} asOf={day} simulated={simulated} />
```

- **Axes.** One y axis with the unit in the head and the tooltip (never two scales: two
  measures are two charts). Tick labels in the mono token font (tabular). `gas-day` points sit at
  the gas day's start (05:00 UTC in winter, 04:00 in summer, `gasDayStartUtc`) and are labelled
  with the gas day, never at midnight; ticks thin to every 2/3/7/14 days, then month starts.
  `period` is ordinal with the desk's names ("Dec-26").
- **Series.** `line`, `step` (daily values), `area`, `bar` (stacked with `stack`: positive up,
  negative down), points on period curves. Colours are `--ds-series-N` in a fixed order, read
  from the tokens and re-read when the theme class changes. `simulated` draws dashed, the head
  carries a Simulated badge and the export names the column "[simulated]"; `forecastFrom` draws
  the forecast dashed (bars lighter). `reference` lines (targets, DCQ) are thin and neutral.
  Missing values are `null` and drawn as gaps.
- **Reading it.** The tooltip shows the period, each series with value and unit (forecast marked)
  and the as-of instant and state; it flips to the cursor's other side and never leaves the plot.
  The plot is one Tab stop: Left/Right step, Home/End, PageUp/PageDown by seven; the point is
  read in a live region. **Table** swaps the plot for a DataGrid of the same data; **CSV** exports
  exactly what is plotted (gaps empty, units in the header).
- **Behaviour.** A ResizeObserver resizes with one `setSize` per frame; nothing animates.
- **Where.** Today: storage fill vs the previous year and the EU target, NW Europe supply and
  call (history and forecast), sparklines beside the fundamentals figures. Prices: forward
  curve by delivery month in the hub's quotation, NBP–TTF spread by delivery month (p/th).
  Delivery: nominated vs allocated by gas day against the DCQ for the selected contract.
- **Check.** `scripts/uat/chart_check.mjs` (same environment as the keyboard paths) checks on
  the demo desk that each canvas draws, the keyboard reaches the points, and the table and the
  CSV hold the plotted values. The CI UAT fixture has no curve or storage history, so the
  charts are absent there by design and the script is run against the demo desk.

## Keyboard paths

`scripts/uat/keyboard_paths.mjs` drives tabs, grid rows, sort, the Method popover and a
dialog in Chromium against a running desk and exits 1 when a path breaks (same environment as
the geometry audit).
