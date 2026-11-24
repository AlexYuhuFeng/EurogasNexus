# Eurogas Nexus: UI/UX and design-system research

Date: 2026-11-24. Scope: web client (`clients/web`, React 19 / Vite / TypeScript) and the Tauri 2
desktop shell (`clients/desktop/src-tauri`). This is research. Nothing in the repository was changed.

How to read it:

- Claims about other products and about design systems carry a source tag such as **[S2]**. Section 4
  maps each tag to a public URL. Only public pages were used. No sign-ups, no credentials, no
  screenshots or assets were copied, and everything is described in my own words.
- Claims about Eurogas Nexus cite the file and, where useful, the line.
- **Inferred** marks a conclusion of mine that no source states directly.
- **Measured** marks a number I computed here (the colour-vision test in section 2.3 used a short
  script that applies the Machado 2009 simulation [S36] and CIEDE2000 distances to the hex values
  in `clients/web/src/styles/tokens.css`).

What this report does not redo: the design system is already strict and well tested. It has one
token file, a CSS token lint, a contrast test, a geometry audit, one DataGrid, one chart layer on
uPlot, sentence case, a bundled Inter font and tabular figures (`docs/product/DESIGN_TOKENS.md`,
`docs/ux/DESIGN_SYSTEM.md`). The recommendations below go after the gaps that are left, plus the
places where three documents disagree with the code.

---

## 1. The 12 highest-value recommendations (ranked by user impact)

Impact is judged by how many users a change reaches, how often they hit it in a trading day,
and whether it can cause a misread number. Effort is a rough guess: S (under a day), M (days),
L (a sprint).

### R1. Make P&L and status colours safe for colour-blind users, and test it (impact: very high, effort S–M)

**Why.** Bloomberg estimates that at least 20,000 Terminal users have a colour-vision deficiency
(CVD), mostly red-green. Thin red and green lines were the first thing to fail in its study. It
shipped two extra schemes, Deuteranopia and Protanomaly, which keep up/down meaning by using blue
for up and red for down, and users switch between them in their personal defaults [S2].
Red-green CVD affects up to 8 % of men of Northern European ancestry [S35].

**Measured on our tokens** (CIEDE2000, where a distance under about 10 is hard to tell apart in
small marks):

| Pair (tokens.css) | Normal vision | Deuteranopia | Protanopia |
|---|---:|---:|---:|
| Dark `--pnl-up` #4cc38a vs `--pnl-down` #ff8a80 | 60.5 | **7.8** | **8.3** |
| Light `--pnl-up` vs `--pnl-down` | 58.5 | 12.8 | **9.1** |
| Dark `--ds-status-ok` vs `--ds-status-breach` | 71.5 | **6.9** | 22.7 |
| Dark `--ds-series-5` #f472b6 vs `--ds-series-8` #a8a8b3 | 21.3 | **0.6** | 5.6 |
| Dark `--ds-series-1` #6ea8fe vs `--ds-series-4` #a78bfa | 17.7 | **1.7** | 5.1 |
| Light `--ds-series-1` #1d4ed8 vs `--ds-series-4` #7c3aed | 12.4 | 5.7 | **3.1** |
| Blue #6ea8fe vs orange #fb923c (dark), for comparison | 48.9 | 56.9 | 53.3 |

In dark mode, the P&L up and down colours also have almost the same lightness (L* 71 and 70), so
a deuteranope gets neither a hue cue nor a lightness cue. Today the text sign (+/−) is the only
thing that saves them (`KeyFigure.tsx` puts the sign in the text).

**Change.**
- `clients/web/src/styles/tokens.css`: add a third convention next to `:root[data-pnl="red_up"]`,
  `:root[data-pnl="blue_orange"]`, that sets `--pnl-profit`/`--pnl-loss` to a blue/orange pair.
  Add a matching `data-cvd` override that re-points `--ds-status-ok`/`--ds-status-breach` to
  blue/orange and fixes the series order (below).
- `clients/web/src/components/PreferencesPanels.tsx` (`CHOICES.pnl_colors`, around line 38):
  add the option, labelled by what it does ("Blue up, orange down: colour-vision friendly").
  `app/model/pnlColor.ts` should accept it.
- Series palette: in dark mode, `--ds-series-8` (neutral grey) collapses into `--ds-series-5`
  (pink) for deuteranopes, and `-1` and `-4` (blue and violet) are close in both themes. Change
  the hues or the order so adjacent series differ in lightness as well as hue. Wong advises
  varying lightness and saturation, not only hue [S35]. Carbon fixes a categorical order that is
  built so neighbouring colours contrast strongly [S16].
- `clients/web/tests/tokenContrast.test.ts`: add a CVD test. Simulate deutan, protan and tritan
  (Machado matrices [S36]) and fail when any pair of adjacent series, or P&L up against down,
  falls under a chosen CIEDE2000 floor. The same tokens and the same CI, one more rule.

### R2. Show direction in words and glyphs, not in a colour flash, and flash only on a real tick (impact: very high, effort S)

**Today.** `components/ui/datagrid.css` lines 266–285 flash every changed cell with
`--ds-accent-soft` for a raw 600 ms, the same for up and for down. In `DataGrid.tsx` lines
162–176, `FlashValue` watches only the value, so switching tenor (a different instrument in the
same row) fires it too. That is finding P-19 in
`docs/engineering/Commercial-Intelligence-V3/13_PERSONA_AND_PRACTICE_REVIEW.md`. The review asks
for a "directional flash", but `docs/clients/MOTION_SYSTEM.md` ("Data and market update rules")
forbids an update emphasis that implies direction. A dead rule in `styles/app.css` lines 743–750
(`.market-price-ticker.is-live`) flashes green whatever the direction. No component uses that
class any more.

**Change (meets both documents).**
- Keep the motion neutral and short. Add a token `--ds-duration-flash` (for example 400 ms) and
  use it in place of the raw 600 ms.
- Carry direction in content that stays on screen: a ▲/▼ glyph from the icon set (R9) beside
  the changed value, plus the signed change against the close, until the next tick. The glyph
  is not colour-only, so it also helps CVD users (R1).
- In `FlashValue`, watch `rowKey + columnId + instrument identity` and reset quietly when the
  identity changes. Only a change in value under the same identity counts as a tick.
- Delete the dead `.market-price-ticker` rule and its keyframes in `app.css`.

Bloomberg found that thin or blended red and green are what CVD users misread [S2]. That makes
a coloured flash the weakest channel to put direction on (**inferred**).

### R3. One formatter per measure, with true minus signs and units written once (impact: high, effort M)

**Today.** P-20 in the persona review says units and decimals differ between screens ("GBp/th"
against "p/th"; 3 dp against 2 dp). The client has 60 `toFixed(` calls inside `components/`
alone. `app/time/valueFormat.ts` covers conversions, and `gasDayModel.ts`/`boardQuote.ts` already
write U+2212 for negative numbers, but nothing stops a component from formatting a number its
own way.

**Change.**
- Add `formatMeasure(measure, value, opts)` to `clients/web/src/app/time/valueFormat.ts`. Back it
  with one table that gives each measure (price per hub quotation, volume, energy, P&L,
  percentage, spread) its decimals, unit spelling and sign rule. Add a test like the CSS token
  lint that fails on a new `toFixed(` in `components/` (the baseline may only shrink).
- Write numbers with U+2212 for minus, a space between a number and its unit, and a space
  before %. NIST SP 811 gives those spacing rules [S41]. Where a column has one unit, name it
  in the header and nowhere else, as `DataGrid` already allows with `unit` [S41].
- Numbers keep tabular lining figures (`font-variant-numeric: tabular-nums`) [S40]. That is
  already the body default (`--ds-numeric`).

### R4. Give overlays their own surface in dark mode, and tint the dark neutrals toward the brand (impact: high, effort S–M)

**Today.** Popovers, menus and dialogs use `--ds-surface`, the same colour as the panels under
them. In dark mode, only a shadow tells them apart, and a shadow barely shows on #131316
(`components/ui/primitives.css` lines 362 and 476, `components/ui/controls.css` lines 201 and 302,
`styles/design-system.css` lines 1282, 1926, 3124, 3254 and 3917). The dark neutrals are plain
zinc greys, so the brand navy (`--ds-brand-navy` #101c34) appears only on the splash and the
sign-in screen.

**What the leaders do.** Atlassian pairs a surface token with a shadow token at each level
(sunken, default, raised, overlay). It says shadows are harder to see in dark mode, so higher
levels use lighter surfaces [S24]. Apple uses dimmer "base" and brighter "elevated" background
sets in dark mode, so the layer in front advances [S27]. Material 3 moved from tinted overlays
to tone-based surface-container roles [S26]. Linear builds its themes in LCH from three inputs
(base, accent, contrast), keeps blue chroma limited in the neutrals, and uses the same model to
step surface levels [S29].

**Change.**
- `tokens.css`: add `--ds-surface-raised` and `--ds-surface-overlay`, each paired with
  `--ds-shadow-pop`/`--ds-shadow-modal`. In light mode they equal `--ds-surface`. In dark mode
  they step lighter (for example #1a1b21 and #202129), with a 1 px top inner highlight of
  `color-mix(in oklab, white 6%, transparent)`.
- Re-point the eight call sites above to the new roles.
- Generate the dark neutrals in OKLCH with a hue near the brand navy and very low chroma
  (about 0.005–0.012), so the dark theme reads as "Eurogas" without colouring any data. That
  gives the product an identity of its own instead of a generic grey, and it costs nothing in
  contrast (**inferred**; `tokenContrast.test.ts` will confirm).

### R5. Keep the focus ring visible in Windows High Contrast (impact: high for keyboard and low-vision users on the Windows desktop build, effort S)

**Today.** The global focus style is `outline: none; box-shadow: var(--ds-focus)`
(`styles/design-system.css` lines 127–130, and `components/ui/primitives.css` lines 93–96 for
buttons). In forced-colours mode the browser sets `box-shadow` to `none` [S37], so keyboard focus
disappears completely [S38]. The desktop build targets Windows (NSIS in `tauri.conf.json`), where
contrast themes are a system setting. A search of `src/` found no `forced-colors` rule.

**Change.** Put `outline: 2px solid transparent; outline-offset: 2px;` next to the box-shadow.
The transparent outline does not show normally, and the system colour shows it in forced
colours. Add a small `@media (forced-colors: active)` block: badges get a 1 px `CanvasText`
border, the selected grid row an outline, and chart reference lines `stroke: CanvasText`. MDN
advises small targeted tweaks, not a second design [S37].

### R6. Make the desktop host do what `HostCapabilities` says it does (impact: high for desktop users, effort M)

**Today.** `clients/web/src/app/host/hostCapabilities.ts` (lines 113–131) declares
`notifications`, `windowPersistence`, `autoUpdate`, `deepLinks`, `systemTray` and `multiWindow`
as true for every desktop host. But `clients/desktop/src-tauri/Cargo.toml` depends only on
`tauri`, `serde` and `serde_json`. There is no updater, window-state, single-instance,
notification or deep-link plugin, and `capabilities/default.json` grants only `core:default`.
The web code can therefore believe in features that do not exist. P-24 also notes that the
installer images are 1x and the app is not signed.

**Change (all plugins are MIT/Apache-2.0 [S48]).**
1. `tauri-plugin-single-instance`, registered first, as its docs require. A second launch
   focuses the running window [S44].
2. `tauri-plugin-window-state`: restore position and size. Create the main window hidden and let
   the plugin show it after restoring, so there is no flash [S43]. That fits the existing
   splash-then-reveal flow in `main.rs`.
3. `tauri-plugin-updater`: signing cannot be turned off, the keys must be kept, and Windows
   `installMode: "passive"` shows only a small progress window [S42]. In the app, show "Update
   ready: restart now / at next launch" in the account menu. Never restart during market hours
   without asking (**inferred**: Bloomberg times big changes for when markets are closed and
   lets users delay them [S1]).
4. `tauri-plugin-notification` for acknowledged-alert escalation only. The payload keeps the
   "codes, never commercial values" rule in `app/host/workstation.ts`. On Windows it works
   only for installed apps [S45].
5. `tauri-plugin-deep-link` with the single-instance `deep-link` feature, so a link like
   `eurogas://open?page=…` opens in the running instance. Check the URL on arrival, as the
   Tauri docs warn [S47] and as `workstation.ts` already does for deep links.
6. Until each plugin ships, set its capability to `false` in `hostCapabilities()`, and add a
   test that pins each `true` to a plugin in `Cargo.toml`.

### R7. Bring the native menu up to date with the current product and the platform conventions (impact: medium-high, effort S)

**Today.** `main.rs` lines 331–361 build a "Workspace" menu with Market, Portfolio, Strategy Lab,
Decision Center, System and Administration. Those are the old primary workspaces. The product
now shows the modes Desk, Deals, Book and Research (`app/navigation/modeNavigation.ts`). The
labels are English only, though the app is bilingual. "Search commands…" has no accelerator.
There is no View, Help or Settings item.

**What the conventions say.** Apple: keep the standard menus in their order, put commands in
the menu bar so people can find them and assign shortcuts, disable unavailable items instead of
hiding them, provide a Window menu even with one window, and put a Settings item in the app
menu [S28].

**Change.** Menus: Workspace (Search… Ctrl/⌘ K; Desk Ctrl+1, Deals Ctrl+2, Book Ctrl+3,
Research Ctrl+4), Edit, View (Theme; Zoom in, out and reset; Density, see R11; Full screen F11),
Window, Help (Manual, Keyboard shortcuts ?, Report a problem, Release notes, About and version).
Add Settings… on Ctrl/⌘ ,. Build the labels from the same i18n keys the web uses. Pass them from
the web when it reports ready (`notify_client_ready`), or keep an en/zh table in Rust. Unpermitted
items stay visible but disabled.

### R8. Turn the command palette into the way to find any object, with recency and typo tolerance (impact: high, effort M)

**Today.** `app/experience/commandPalette.ts` `filterPaletteCommands` (lines 418–452) ranks
prefix matches first, then substring matches, over pages, tasks, glossary terms and aliases. P-21
says it "finds pages only, not instruments". It has no notion of recency and no tolerance for
typos.

**What the leaders do.** LSEG Workspace's search bar takes "natural language or codes" to launch
apps or look up data [S12]. Kpler's new map search is one field for vessels, locations, players
and products, with each suggestion labelled by type and a filter to narrow by type [S7].
Superhuman's palette advice: show each command's shortcut so users learn it, use fuzzy matching
with aliases and a score threshold, boost by context, and make one palette reachable from
everywhere [S33].

**Change.**
- Add result groups: hubs and instruments (with the hub's quotation unit), contracts, cargoes and
  vessels (Desk → Cargoes already has a deep link), counterparties, glossary terms. Label each
  row by type, and let a prefix such as `h:`, `c:` or `v:` filter to one type.
- Rank with a small fuzzy score (subsequence plus edit distance 1 on tokens of 4 or more
  characters), then multiply by recency. Keep recent picks per viewer in `localStorage`, wrapped
  in try/catch, because it is only a convenience.
- Show the shortcut on every row that has one (`paletteShortcut` already exists) and the matched
  alias, in the form "Prices (Market)".
- Results come from data already in the client, or one indexed endpoint. Keep the palette under
  0.1 s per keystroke, the limit for a reply to feel instant [S34].

### R9. Adopt one licensed icon set behind one `Icon` primitive (impact: medium-high, effort M)

**Today.** There is no icon library. Close buttons are a "×" character (31 uses), chevrons are
"▾" (5) and "›" (3), and the few inline SVGs do not match. The top-bar chevron
(`WorkspaceTopBar.tsx` line 225) is a 12 px viewBox with a 1.5 stroke, and the search glass
(line 314) is an 18 px viewBox with a 1.6 stroke. The UI constitution bans "mystery icons" and
lets status carry "an icon, pattern, or title" as a second signal
(`docs/clients/PROFESSIONAL_UI_CONSTITUTION.md` §15 and §22), but nothing supplies those icons.

**Change.**
- Choose **Lucide** (ISC; icons derived from Feather are MIT) [S49]. Its strokes are drawn as
  SVG paths, 2 px by default, and the stroke width can be changed [S50]. Alternatives with
  friendly licences: **Phosphor** (MIT, 1,248 icons in six weights) [S51], **Tabler** (MIT, about
  6,200 icons on a 24 grid with a 2 px stroke) [S52], **IBM Carbon icons** (Apache-2.0) [S53].
  Lucide suits Inter's geometry and imports one icon at a time (**inferred**).
- Add `components/ui/Icon.tsx` (a name from a curated list of about 60 icons, `size` 16 or 20,
  `aria-hidden`) and tokens `--ds-icon-sm: 16px`, `--ds-icon: 20px`, `--ds-icon-stroke: 1.5`.
  Make `IconButton` take an icon name instead of a string glyph.
- Pair status with shape: ok ✓-circle, watch triangle, breach octagon, stale clock, simulated a
  flask or dashed circle. That gives a non-colour cue (R1) and keeps the constitution's rule
  that the label is always text.
- Add a lint that fails on a new bare "×", "▾" or "›" used as a control.

### R10. Reconcile the motion contract with the tokens, and add exit motion (impact: medium, effort S)

**Today.** There are three authorities and they disagree:

| Source | Durations | Radii | Control heights |
|---|---|---|---|
| `tokens.css` / `DESIGN_TOKENS.md` | 80 / 160 / 240 / 400 ms | 4 / 8 / pill | 28 / 32 / 44 touch |
| `docs/clients/MOTION_SYSTEM.md` | 120 / 180 / 240 ms | – | – |
| `docs/clients/PROFESSIONAL_UI_CONSTITUTION.md` §6–7 | – | 4 / 6 / 8 | 28 / 32 / 36 |

The tokens have no exit easing, though `MOTION_SYSTEM.md` proposes ease-in for exits. Every
`.workspace-panel` replays `ds-enter` when it mounts (`styles/design-system.css` lines 2087–2089),
so a tab switch fades in a whole page of panels. Raw values remain at 600 ms (grid flash),
420 ms (`app.css` ticker) and 1.4 s (shimmer).

**Benchmarks.** Carbon separates "productive" motion (subtle, for focused task work such as
tables and dropdowns) from "expressive" motion (significant moments). Its durations start at
70 and 110 ms, and its exit curve accelerates out [S15]. Material says desktop transitions should
take 150–200 ms, with deceleration for entry and acceleration for exit [S25]. WinUI uses
83 / 167 / 250 ms [S23].

**Change.** Keep 80 / 160 / 240 and update `MOTION_SYSTEM.md` to match (the code and tests already
use them). Add `--ds-ease-in: cubic-bezier(0.4, 0, 1, 1)` for exits and an exit duration of
about 0.75 × the entry. Add exit transitions for `<dialog>` and `[popover]` with
`@starting-style` and `transition-behavior: allow-discrete`, which are Baseline for entry [S39].
WebView2 is Chromium, so the desktop build gets exits too; elsewhere they degrade to an instant
close. Animate the page container once per navigation, not each panel. Fix the constitution's
radius and height lists to match the tokens.

### R11. Offer a density preference (impact: medium-high for traders on laptops, effort S–M)

**Today.** The tokens already define `--ds-row` 32 and `--ds-row-header` 28, and `DataGrid` has
`density="compact"` (28 px) per grid. Users cannot choose. P-18 and QA-T-03 show that "prices
above the fold" is a live complaint.

**Benchmarks.** Carbon's data table comes in row heights of 24, 32, 40, 48 and 64 px [S20].
Joule's market sheets can be docked and stacked into dense layouts [S10]. Bloomberg replaced its
fixed four-panel grid with resizable windows and tabs, so users decide how many rows they see
[S1].

**Change.** Add a `density` preference (`comfortable` | `compact`) in `PreferencesPanels.tsx`
(`DISPLAY_KEYS`) and in the Appearance group of `HeaderPreferencesMenu.tsx`. It sets
`:root[data-density="compact"]`, which re-points `--ds-row` to 28 and `--ds-row-header` to 24 and
lowers panel padding one step. It leaves the 28/32 control heights and the 44 px touch targets
alone, so the geometry budget and the "no control under 24 px" rule still hold. Rows are not
controls (`DESIGN_TOKENS.md`). Run the geometry audit for both densities.

### R12. Split Settings by who owns each setting (impact: medium, effort M)

**Today.** `components/SettingsCenter.tsx` puts the backend API URL, an API token and operator
principal, map-tile provider tokens, runtime and DB status, release metadata, personal
preferences, organisation defaults and personal API keys on one page. A trader looking for
"units" finds deployment plumbing first.

**Benchmarks.** Apple keeps app-level settings in one Settings window opened with ⌘, [S28].
LSEG puts Workspace settings, profile and sign-out under one workspace menu [S12]. Bloomberg
keeps colour schemes in personal defaults that users can share with colleagues [S2].

**Change.** Use four groups, each with "Reset to organisation default":
- **Personal**: appearance (theme, density, colour vision, P&L convention), language, time zone,
  units and currency, notifications.
- **Workspace**: landing view, strip thresholds, board layout, saved layouts (later).
- **Organisation** (administrators): what `OrganisationDefaultsPanel` holds today.
- **Connection and diagnostics**: backend URL, tokens, map tiles, runtime and release. Move these
  to first-run setup (`FirstRunSetup.tsx`) and the desktop "Connection…" item, behind an
  Advanced disclosure, because a deployment usually fixes them (`deploymentConfig`).

Put chart and table options (series shown, scale, table/chart toggle) in each panel's own menu,
not in Settings. That is where TradingView keeps per-layout sync choices [S11].

---

## 2. Topic by topic: today against best practice

### 2.1 Density and layout

| Today | Best practice | Gap or action |
|---|---|---|
| 13 px body, 32 px rows (28 compact), 1440 × 900 first (`PROFESSIONAL_UI_CONSTITUTION.md` §5, `tokens.css`) | Carbon offers five row heights from 24 to 64 [S20] | R11: a user preference |
| Five primary workspaces with tasks; one global trading context row (`WorkspaceTopBar.tsx`, `workspaceNavigation.ts`) | Bloomberg moved from four fixed panels to resizable windows and tabs, and Launchpad lets each user lay out connected apps across monitors and share the layout [S1][S3] | `workstation.ts` already declares window profiles (`trading-desk`, `market-monitor`, …). Build them once R6 lands (multi-window plus window-state) |
| Linked context through the shared trading context (`TRADING_CONTEXT_PAGES`) | TradingView syncs symbol, interval, crosshair, time and date range across a layout, and uses named sync groups so different chart sets can follow different symbols [S11] | Later: let a chart panel "follow context" or pin itself, and show the state with a small link glyph (R9) |
| Map-centric Network view, search in the top bar | Kpler's MarineTraffic redesign puts search at top centre, navigation on the left and map filters on the right, with muted greys and blue only for selection [S5] | We match the restrained palette. Keep map filters in one right-hand rail |

### 2.2 Typography and numerals

| Today | Best practice | Gap or action |
|---|---|---|
| Inter variable (wght only), bundled under OFL; six sizes; `tabular-nums` on body (`fonts.css`, `fonts.json`) | `tabular-nums` maps to `tnum` and makes all figures the same width; `slashed-zero` helps where 0 and O meet [S40] | Fine. Optional: `slashed-zero` in identifier cells (cargo IDs, contract refs). The allowlist in `tests/fontFoundation.test.ts` (line 73) already includes `zero` |
| Chart tick labels are drawn on canvas in `--ds-font-mono` (`Chart.tsx` lines 121 and 334). JetBrains Mono is named but **not bundled**, so ticks render in Consolas, Menlo or DejaVu depending on the OS; compact ticks are 10 px, below the 11 px scale step | One face on every platform. Canvas cannot switch on `tnum`, which explains the mono choice (**inferred**) | Bundle a digits-and-punctuation subset of JetBrains Mono (OFL-1.1) and record it in `fonts.json` like Inter. Raise compact ticks to 11 px |
| Linear uses Inter Display for headings and Inter for text [S29] | — | Optional: Inter's opsz build for the 18 and 20 px steps (key figures and page titles) gives a crisper "premium" headline with no new family. Weigh it against the 133 kB font budget |
| Units: in the header where one unit fits (`DataGrid` `unit`) | Space between number and unit, space before %, unit given once in the column heading [S41] | R3 |

### 2.3 Colour and status semantics, including colour-blind safety

| Today | Best practice | Gap or action |
|---|---|---|
| Semantic roles only; status text meets 4.5:1 on its soft background; series meet 3:1; simulated has its own violet (`tokens.css`, `tokenContrast.test.ts`) | Carbon keeps a fixed categorical order and separate light and dark variants; sequential ramps flip lightness in dark themes; diverging palettes stay the same in both themes [S16] | Add a diverging pair (for spreads against fair value, and storage against the 5-year mean) as tokens `--ds-diverge-neg/mid/pos`, rather than borrowing P&L colours |
| `pnl_colors`: `green_up` or `red_up` (the Asian convention) | Bloomberg: CVD schemes that keep meaning, blue for up and red for down; users found alternative sets more accurate and preferred them [S2] | R1, measured above |
| Status badges always carry a text label (`StatusBadge.tsx`) | Colour is never the only signal (our own constitution §15); Wong advises varying lightness, not only hue [S35] | R9 adds a shape per status |
| Colours chosen by hand in sRGB hex | Stripe tunes its palette in a perceptual space so that any two colours a fixed number of steps apart are guaranteed enough contrast [S30]; Linear generates themes in LCH [S29] | Generate the next palette revision in OKLCH, and keep the hex output in `tokens.css` so the lint and tests stay as they are |

### 2.4 Elevation and shadows

| Today | Best practice | Gap or action |
|---|---|---|
| Two shadows (pop, modal); panels use a border; the constitution bans heavy shadows | Atlassian: sunken, default, raised and overlay levels, each surface paired with a shadow, flat cards with a border [S24]. Fluent: a key shadow plus an ambient shadow, with a ramp from 2 to 64 px blur [S21] | The structure is right: border for panels, shadow only for floating UI |
| Dark mode: overlays share `--ds-surface` with panels | Lighter surfaces for higher levels in dark mode [S24][S27][S26] | R4 |
| `--ds-scroll-shadow` for sideways overflow | Atlassian's "overflow" shadow is for scroll edges that a border would not show [S24] | Already matches. Use the same edge on the DataGrid's vertical scroll |

### 2.5 Motion

| Today | Best practice | Gap or action |
|---|---|---|
| 80 / 160 / 240 / 400 ms, one ease-out curve, everything off under reduced motion (`tokens.css`, `design-system.css` lines 2112–2118) | Carbon's productive durations are 70–150 ms and its exits accelerate [S15]; Material puts desktop at 150–200 ms [S25]; WinUI 83 / 167 / 250 ms [S23]; Fluent says motion should be functional and natural [S22] | R10: exit curve and exit transitions |
| Every panel fades in on mount | Productive motion suits focused task work and should stay subtle [S15] | Animate once per navigation |
| Skeleton shimmer (1.4 s, infinite) | Carbon uses skeletons for first load of tables and cards only, never for menus or modals, and gone within a few seconds [S19] | Matches. Give the shimmer period a token |
| No flash of fabricated data; neutral update emphasis (`MOTION_SYSTEM.md`) | — | R2 settles the conflict with P-19 |

### 2.6 Iconography

| Today | Best practice | Gap or action |
|---|---|---|
| Text glyphs and a handful of unmatched SVGs | Apple: use familiar icons for common actions, the same everywhere [S28]. Fluent and Carbon ship one set at fixed sizes [S53] | R9 |
| `IconButton` requires a `label` (accessible name and tooltip) | Constitution: icon-only controls need an accessible name | Keep this; it is good |
| Map icons drawn on their own (`app/mapIcons.ts`) | Kpler shows low-confidence AIS positions with a distinct vessel and track style, off by default behind a map filter [S6] | Use the same idea for estimated or projected positions and for "published against estimated" terminal figures, which the persona review already asks for. Draw them hollow or dashed, with a legend entry |

### 2.7 Chart selection by question

The chart layer (`components/ui/charts/`) already has line, step, area and stacked bar,
`AlignedPanels` (two units shown as two panels, never a dual axis), `SmallMultiples`,
`Waterfall`, `PercentileStrip` and season bands (`seasonModel.ts`). The FT Visual Vocabulary
groups charts by the relationship they show: deviation, correlation, ranking, distribution,
change over time, part-to-whole, magnitude, spatial and flow [S31]. Carbon groups by purpose in
a similar way [S17]. Datawrapper: line charts need not start at zero, label lines directly
instead of using a legend, and grey out context lines [S32].

| Question a user asks | Recommended form | Have it? | Note |
|---|---|---|---|
| How did TTF front-month move today, this week? (time series) | Line, or a step line for daily settlements; direct end label; previous close as a thin grey reference | Yes (`Chart`, `reference`) | Prefer direct labels to the legend where there are 4 or fewer series [S32] |
| What does the forward curve look like, and how did it shift? (curves) | Points joined by a line across delivery months, with today against yesterday or last week as a grey line, and the **change by month** in an aligned panel below | Partly (`AlignedPanels`, `compare`) | The shift panel is deviation, so use diverging bars [S31] |
| Is the NBP–TTF or summer–winter spread wide? (spreads) | Two curves above, the spread below with a zero line (`AlignedPanels`); for many pairs, a **month × month matrix** coloured on a diverging scale | Panel yes; matrix **no** (a search found only the source matrix) | The matrix suits a calendar-spread board. Use the diverging tokens (§2.3) |
| Where is storage against history? (seasonality, distribution) | Season band (min–max and mean of 5 years) with this year and last year as lines; the percentile strip for the headline | Yes | Matches the FT "fan" and band forms [S31] |
| Where is gas flowing, and how much? (flows) | Map flow lines sized by **measured** flow; stacked area for supply mix over time; ranked bars by entry point | Yes (`FlowsPanel`, map) | A Sankey is in the FT flow family [S31], but on a network that has a map it repeats the map (**inferred**); see section 3 |
| Am I long or short by month? (positions) | Diverging bars by delivery month around zero, net position as a line; table toggle | Ladder grid yes; chart **partly** | A ladder is deviation from flat: diverging bar [S31] |
| What is the cargo's timeline, and what is uncertain? (cargo timelines) | A horizontal timeline with load, voyage and discharge windows as bars, ETA as a point with an uncertainty whisker, and contract windows as a band | Yes (`CargoPlanView.tsx` timeline, `role="img"`) | Add the estimate styling from §2.6 and keyboard stepping like `Chart` |
| Where does the value of this cargo or route go? (part-to-whole) | Waterfall | Yes (`Waterfall`) | — |
| Which hubs or countries compare? (ranking or magnitude) | Ordered bars, or small multiples on a shared scale | Yes (`SmallMultiples`) | Shared scale by default, as now |

### 2.8 Customisation, and where settings belong

- Settings structure: R12.
- Per-viewer conveniences (last tab, collapsed panels, recent palette items): `localStorage`
  wrapped in try/catch is enough. Anything that must follow the user across devices goes through
  the existing preferences API (`app/preferences/remotePreferences.ts`).
- Saved and shared layouts (Bloomberg Launchpad [S3], LSEG layouts with autosave and a sheet per
  portfolio [S12]): `workstation.ts` already models window profiles that persist no identity.
  The next step is a named, shareable layout, made of the profile plus pinned panel options,
  stored server-side per user with an organisation default.
- Change management for layout and visual changes: Bloomberg rolls out visual changes a little
  at a time, gives advance notice, lets users preview or put off a change, and ships before a
  weekend [S1]. Apply the same to R4 and R9: a "Try the new look" toggle for one release.

### 2.9 Keyboard and command palette

| Today | Best practice | Gap or action |
|---|---|---|
| ⌘K/Ctrl K palette; `?` opens the shortcut list; roving focus in tabs, grids and toolbars; charts reachable by keyboard (`keyboard.ts`, `KeyboardShortcutsDialog.tsx`, `DESIGN_TOKENS.md`) | Superhuman: one palette everywhere, shortcuts taught inline, fuzzy search with aliases [S33]. Joule: prices updated from the keyboard [S10]. Apple: menu commands get shortcuts and stay findable [S28] | R7 and R8 |
| No number-key navigation between modes | — | Ctrl+1–4 for the modes; `g` then a letter as a chord (only when focus is not in a field) |
| The shortcut dialog lists a fixed set | — | Generate it from the same declaration as the palette, and group it by surface |

### 2.10 Empty, loading and error states

| Today | Best practice | Gap or action |
|---|---|---|
| `EmptyState`: cause, next step, one action; `need` = data, permission or licence; "See an example" (`EmptyState.tsx`) | Carbon: the empty state replaces the whole element (headers included) so screen readers do not read an empty table; positive titles; never a dead end; tertiary actions when several show at once [S18] | Check that `DataGrid`'s `empty` drops the header row for screen readers. Use quiet buttons when two or more empty states share a screen |
| `Skeleton` with one announced status; a spinner only in `AnswerBar` | Skeletons for the first load of tables and cards, a progress indicator for anything longer than a moment or two, a notification after a few minutes [S19]; past 1 s show that work is happening, past 10 s show progress and a way to cancel [S34] | Reports and evaluations (persona review: a full evaluation takes 6.5 s) should show stage text and a Cancel past 1 s. `JobTimeline` is the place |
| Data problems: a dot and count in `TopBarStatus.tsx`, a one-time dismissible line, a blocking notice when the store is lost | Bloomberg hides back-end changes from users [S1] | Matches. Keep last-good values visible with their age, never blank |

### 2.11 Tauri desktop polish

| Area | Today (file) | Best practice | Action |
|---|---|---|---|
| Single instance | none (`Cargo.toml`) | Register the plugin first; focus the existing window on a second launch [S44] | R6 |
| Window state | none; fixed 1440 × 900, centred (`tauri.conf.json`) | Restore size and position; keep the window hidden until restored [S43] | R6 |
| Menus | old workspace names, English only, no Help, View or Settings (`main.rs` lines 331–361) | Standard menus, shortcuts, Window menu, Settings item [S28] | R7 |
| Tray | none | `TrayIconBuilder` with a menu; left-click shows and focuses the main window; Linux has no tray mouse events [S46] | Optional: a tray menu with "Show Eurogas Nexus", alert count and Quit. Do not keep running after the last window closes unless the user turns that on (**inferred**) |
| Notifications | none, though declared | Permission check, title and body; Windows needs an installed app; actions are mobile only [S45] | R6, for escalations only, with no commercial values |
| Updates | none, though declared; no code signing (P-24) | Signed updates are required; passive install on Windows; progress events for the UI [S42] | R6, plus an in-app "restart to update" |
| Deep links | declared, not wired | Static schemes in config; single-instance `deep-link` feature; validate the URL [S47] | R6 |
| Startup | borderless splash until `notify_client_ready`, with a bounded fallback (`main.rs`, `public/splash.html`) | — | Good. Add the version and "Connecting to <host>…" text on the splash after 2 s, so a slow backend is not mistaken for a hang [S34] |
| Installer | NSIS per-machine, en + zh, 1x bitmaps (`tauri.conf.json`, P-24) | — | Ship 2x installer bitmaps. Offer a per-user mode so updates can stay silent: `quiet` works only per-user or with admin rights [S42] |
| Offline install | `tauri.offline.conf.json` embeds the WebView2 offline installer | — | Good for locked-down trading floors. Document which build to use when |

### 2.12 Other lessons from the named products

- **Bloomberg, consistency as a process.** Its UX standards are part of the development
  lifecycle, with UX advocates inside engineering and training for new hires, rather than a
  check at release [S4]. We already do this through the token lint, the contrast test and the
  geometry audit. Extend it with the CVD test (R1), an icon lint (R9) and a formatter lint (R3).
- **Kpler, alerts as a product surface.** Kpler's recent updates include richer insight
  notifications, webhook notifications and LNG diversions as notification types, and they add
  tabs to existing workspaces rather than new top-level pages [S8]. That supports our
  `NotificationChannelsPanel` and the decision to keep tasks inside modes. Webhook and email
  delivery of acknowledged alerts is worth checking against our alert centre (**inferred**).
- **Vortexa, a spreadsheet path next to the UI.** Vortexa pairs its maps, charts and tables with
  an Excel connection that refreshes on demand [S9]. Our charts have Table and CSV views
  (`DESIGN_TOKENS.md`, Charts). A "copy as table" for any grid selection (tab-separated, units
  in the header) is the cheap next step for desks that live in Excel (**inferred**).
- **Kraken (Octopus Energy), one end-to-end view with named owners.** Kraken's
  asset-optimisation product promises a single end-to-end view from onboarding to settlement,
  each step defined with a clear owner, and customisable alerts on asset health [S13]. Public
  material on Kraken's own UI is thin. The transferable idea fits our gas-day spine and
  shift-handover practice (items 2 and 17 in the persona review): every open step shows its
  owner and its deadline in one place. Octopus's front-end talk adds the lesson in section 3,
  item 6 [S14].
- **Trayport Joule, from quote to chart in one move.** Joule lets users open a chart straight
  from a live contract with one click and dock or stack market sheets [S10]. For us that means
  every price cell in a grid should open its chart in the inspector or a popover (Enter on the
  selected row), not only through navigation.

---

## 3. Things not to adopt, and why

1. **Coloured price flashes that encode direction** (the usual blotter green and red flash).
   They break `MOTION_SYSTEM.md`, they are the thin, blended red and green that CVD users
   misread [S2], and they turn decision support into execution-style excitement. R2 puts
   direction in glyphs and text instead.
2. **A Bloomberg-style amber-on-black "terminal" theme as the default.** Bloomberg keeps it for
   its installed base and changes it only gradually [S1]. For us it would be imitation, not
   identity. R4's navy-tinted dark neutrals give a recognisable look of our own.
3. **Free-floating, unlinked windows everywhere.** Our benchmark already rejected them
   (`docs/product/INDUSTRY_BENCHMARK.md`, "linked widgets … over free-floating windows").
   Window profiles with one context (R6, `workstation.ts`) keep the benefit without the chaos.
4. **Dual-axis charts, 3D charts and pie charts for more than a few parts.** We already show
   two units as two aligned panels (`AlignedPanels.tsx`). Keep it that way.
5. **A Sankey for gas-network flows.** On a physical network the map already shows topology,
   and a Sankey loses geography and direction over time (**inferred**). Use map flows plus
   ranked bars, and keep a Sankey for a balance that has no geography (supply sources to uses)
   if one is ever needed.
6. **A component framework such as Material UI as the base.** Octopus started on MUI and moved
   away because it limited their own design decisions. Their lesson: keep the design system
   independent of any outside library [S14]. Our own decision not to adopt React Aria
   (`DESIGN_TOKENS.md`) agrees.
7. **An animation library (Framer Motion and similar).** `MOTION_SYSTEM.md` forbids new motion
   dependencies, and native `@starting-style` plus `allow-discrete` covers dialogs and popovers
   [S39].
8. **Expressive motion, glass, gradients and big hero layouts** to make it "feel premium".
   Carbon keeps expressive motion for rare moments [S15], and the constitution bans the rest.
   Premium here should come from precision: aligned figures, consistent icons, real elevation
   in dark mode, fast search and native desktop behaviour.
9. **An app-only appearance setting that ignores the system.** Apple advises against it [S27].
   We default to "system" and allow an override, which is fine. Do not remove "system".
10. **Copying vendor iconography, layouts or colour schemes** (Kpler's map styling, Bloomberg's
    function codes, TradingView's toolbars). Only the principles above were taken.
11. **Desktop notifications that carry prices or positions.** `workstation.ts` already forbids
    this, because the OS notification centre is outside entitlement control.
12. **The FT Visual Vocabulary poster itself as an in-app asset.** Its repository says
    "all rights reserved" [S31]. Use the categories as guidance only.

---

## 4. Sources

Product and vendor sources:

- [S1] Bloomberg, "How Bloomberg Terminal UX designers conceal complexity": https://www.bloomberg.com/company/stories/how-bloomberg-terminal-ux-designers-conceal-complexity
- [S2] Bloomberg, "Designing the Terminal for color accessibility": https://www.techatbloomberg.com/blog/designing-the-terminal-for-color-accessibility/
- [S3] Bloomberg UX, "Relaunching Launchpad": https://www.bloomberg.com/ux/2017/11/10/relaunching-launchpad-disguising-ux-revolution-within-evolution/
- [S4] Bloomberg UX, "Consistency: more than just a buzzword": https://www.bloomberg.com/ux/2020/08/11/consistency-more-than-just-a-buzzword/
- [S5] Kpler, "Designing the new MarineTraffic app": https://www.kpler.com/blog/designing-the-new-marinetraffic-app
- [S6] Kpler Help, low-confidence AIS positions on the map: https://help.kpler.com/en/articles/14997903-5-may-2026-low-confidence-ais-positions-added-to-map
- [S7] Kpler Help, new map search: https://help.kpler.com/en/articles/17458690-5-october-2026-new-map-search
- [S8] Kpler Help, recent updates (workspaces, notifications, webhooks): https://help.kpler.com/en/collections/2123469-recent-updates
- [S9] Vortexa, cargo and vessel tracking maps (charts, tables, Excel link): https://www.vortexa.com/feature/cargo-vessel-tracking-maps
- [S10] Mondo Visione, Trayport launches Joule (docking and stacking, chart from contract, keyboard price update): https://mondovisione.com/news/trayport-launches-joule-the-faster-more-flexible-and-feature-rich-energy-trad-20111123/
- [S11] TradingView Help, syncing charts in a layout: https://in.tradingview.com/support/solutions/43000629992
- [S12] LSEG Workspace Quick Start Guide: https://www.lseg.com/content/dam/lseg/learning-centre/documents/workspace-quick-start-guide.pdf
- [S13] Kraken (Octopus Energy group), Generation flexibility and asset optimisation: https://www.kraken.tech/asset-optimization
- [S14] Octopus Energy, "Introducing Design System to Multinational Web Apps" (React Summit 2022): https://gitnation.com/contents/introducing-design-system-to-multinational-web-apps

Design systems and platform guidelines:

- [S15] IBM Carbon, Motion overview: https://carbondesignsystem.com/elements/motion/overview/
- [S16] IBM Carbon, Data-visualisation colour palettes: https://carbondesignsystem.com/data-visualization/color-palettes/
- [S17] IBM Carbon, Chart types: https://preview.carbondesignsystem.com/building-blocks/data-visualization/chart-types
- [S18] IBM Carbon, Empty states pattern: https://carbondesignsystem.com/patterns/empty-states-pattern/
- [S19] IBM Carbon, Loading pattern: https://carbondesignsystem.com/patterns/loading-pattern/
- [S20] IBM Carbon, Data table style (row sizes): https://carbondesignsystem.com/components/data-table/style/
- [S21] Microsoft Fluent 2, Elevation: https://fluent2.microsoft.design/elevation
- [S22] Microsoft Fluent 2, Motion: https://fluent2.microsoft.design/motion
- [S23] Microsoft Learn, Windows timing and easing: https://learn.microsoft.com/en-us/windows/apps/design/motion/timing-and-easing
- [S24] Atlassian Design System, Elevation: https://atlassian.design/foundations/elevation
- [S25] Material Design (v1), Duration and easing: https://m1.material.io/motion/duration-easing.html
- [S26] Flutter docs, Material 3 tone-based surface roles: https://docs.flutter.dev/release/breaking-changes/new-color-scheme-roles
- [S27] Apple HIG, Dark Mode: https://developer.apple.com/design/human-interface-guidelines/dark-mode
- [S28] Apple HIG, The menu bar: https://developer.apple.com/design/human-interface-guidelines/the-menu-bar
- [S29] Linear, "How we redesigned the Linear UI": https://linear.app/blog/how-we-redesigned-the-linear-ui
- [S30] Stripe, "Designing accessible color systems": https://stripe.com/cn/blog/accessible-color-systems

Data visualisation, typography and accessibility:

- [S31] Financial Times, Visual Vocabulary (chart-doctor repository): https://github.com/Financial-Times/chart-doctor/blob/main/visual-vocabulary/README.md
- [S32] Datawrapper, "What to consider when creating line charts": https://www.datawrapper.de/blog/line-charts
- [S33] Superhuman, "How to build a remarkable command palette": https://blog.superhuman.com/how-to-build-a-remarkable-command-palette/
- [S34] Nielsen Norman Group, "Response times: the 3 important limits": https://www.nngroup.com/articles/response-times-3-important-limits/
- [S35] B. Wong, "Color blindness", Nature Methods Points of View (copy hosted at UC Berkeley): https://nature.berkeley.edu/garbelottoat/wp-content/uploads/nmeth.1618.pdf-WT.pdf
- [S36] Machado, Oliveira and Fernandes (2009), physiologically based CVD simulation: https://www.inf.ufrgs.br/~oliveira/pubs_files/CVD_Simulation/CVD_Simulation.html
- [S37] MDN, `forced-colors` media feature: https://developer.mozilla.org/docs/Web/CSS/@media/forced-colors
- [S38] tempertemper, "Windows High Contrast Mode and focus outlines": https://www.tempertemper.net/blog/windows-high-contrast-mode-and-focus-outlines
- [S39] web.dev, "Now in Baseline: animating entry effects": https://web.dev/blog/baseline-entry-animations
- [S40] MDN, `font-variant-numeric`: https://developer.mozilla.org/docs/Web/CSS/font-variant-numeric
- [S41] NIST SP 811, Chapter 7, rules for expressing values of quantities: https://nist.gov/pml/special-publication-811/nist-guide-si-chapter-7-rules-and-style-conventions-expressing-values

Tauri and libraries (licences as stated by each source):

- [S42] Tauri v2, Updater plugin: https://v2.tauri.app/plugin/updater/
- [S43] Tauri v2, Window State plugin: https://v2.tauri.app/plugin/window-state/
- [S44] Tauri v2, Single Instance plugin: https://v2.tauri.app/plugin/single-instance/
- [S45] Tauri v2, Notification plugin: https://v2.tauri.app/plugin/notification/
- [S46] Tauri v2, System tray: https://v2.tauri.app/learn/system-tray/
- [S47] Tauri v2, Deep linking: https://v2.tauri.app/plugin/deep-linking/
- [S48] Tauri plugins-workspace (Apache-2.0 and MIT): https://github.com/tauri-apps/plugins-workspace
- [S49] Lucide licence (ISC; Feather-derived icons MIT): https://lucide.dev/license
- [S50] Lucide, stroke width: https://lucide.dev/guide/react/basics/stroke-width
- [S51] Phosphor Icons (MIT): https://github.com/phosphor-icons/homepage
- [S52] Tabler Icons (MIT): https://github.com/tabler/tabler-icons
- [S53] IBM Carbon icons, `@carbon/icons` (Apache-2.0): https://www.npmjs.com/package/@carbon/icons

Eurogas Nexus files read (read-only): `clients/web/src/styles/tokens.css`,
`styles/design-system.css`, `styles/app.css`, `components/ui/{primitives,controls,datagrid}.css`,
`components/ui/{DataGrid,StatusBadge,EmptyState,Button,KeyFigure}.tsx`,
`components/ui/charts/*`, `components/{CommandPalette,KeyboardShortcutsDialog,SettingsCenter,
PreferencesPanels,HeaderPreferencesMenu,WorkspaceTopBar,TopBarStatus,CargoPlanView}.tsx`,
`app/experience/commandPalette.ts`, `app/host/{hostCapabilities,workstation}.ts`,
`app/navigation/{modeNavigation,productNavigation}.ts`, `app/time/valueFormat.ts`,
`clients/desktop/src-tauri/{tauri.conf.json,Cargo.toml,src/main.rs,capabilities/default.json}`,
`clients/web/public/splash.html`, `docs/ux/DESIGN_SYSTEM.md`, `docs/product/DESIGN_TOKENS.md`,
`docs/product/INDUSTRY_BENCHMARK.md`, `docs/clients/MOTION_SYSTEM.md`,
`docs/clients/PROFESSIONAL_UI_CONSTITUTION.md`, `docs/clients/WINDOWS_CLIENT_DESIGN_SPEC.md`,
`docs/engineering/Commercial-Intelligence-V3/13_PERSONA_AND_PRACTICE_REVIEW.md`.
