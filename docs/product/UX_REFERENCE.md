# UX Reference — Product Shell

Status: conceptual reference. GPT Image Gen 2 was not available in this run, so
no generated raster reference is attached. Accepted visual principles below
come from the product brief, public professional-workstation research, and the
repository UI standard.

## Accepted visual concept for the workstation shell

- Five primary workspace tabs in the persistent topbar; active tab is the only
  strong emphasis.
- A compact active local-task chip for the map-first Network view.
- Persistent gas day, delivery product, source freshness, streaming state, and
  runtime status remain in the topbar context strip.
- Non-map workspaces use one compact identity band: primary eyebrow + local task
  title + local task tabs only when the primary owns more than one view.
- No sidebar + group tabs + page tabs + nested tabs at the same time.
- Dense institutional styling: 8px spacing, hairline borders, system fonts,
  tabular numerals, no gradients, no oversized cards, no consumer dashboard.

## Reference targets

- 1920x1080 and dense 1440x900 desktop layouts; 2560x1440 remains readable.
- Desk mode with three tasks: Today, Prices, Network. Network is the map with an information
  panel beside it (Outages · Capacity · Flows, and Our book in the book view); the former
  "Outages & capacity" task is that panel, not a page (docs/ux/LIVE_MAP.md). All three share
  one page frame, so switching tasks does not move the header or the context strip.
- Strategy Lab and Decision Center follow the same shell rather than bespoke
  navigation.

## CR-05 Strategy Lab references

Accepted principles from the CR-05 research pass:

- three-zone research workstation: narrow navigator, primary evidence/result
  surface, contextual provenance rail;
- workflow as local tabs, never four global pages;
- result hierarchy: identity/provenance -> KPI strip -> time series ->
  drawdown/exposure -> attribution -> decision-event table;
- comparison is a matrix/table-first workflow with synchronized series and
  visible compatibility caveats, not a chart wall;
- charts are thin, muted, unit-labelled and break on missing data; they never
  create a smooth illustrative curve;
- dense 8px grid, hairline borders, tabular numerals, 12–13px body text, no
  marketing cards or gradients;
- persistent identity/version/context header in every task.

Sources reviewed include Trayport Joule public material, institutional
portfolio analytics patterns, and strategy experiment-tracking literature;
no proprietary design was copied.

## CR-07 Market cockpit references

GPT Image Gen 2 was not available in this run. Accepted direction from public
commodity-terminal and ENTSOG/GIE research:

- overview first: hub board + map + physical/route rail + bottom spread strip;
- hub selection is the shared anchor; panels react, not duplicate controls;
- capacity tables keep technical/booked/available separate with timestamp;
- map layers are grouped and decision-relevant, with verified vs indicative
  geometry legend;
- degraded state is partial, never a blank cockpit.

## CR-08 Commercial workflow references

GPT Image Gen 2 was not available. Accepted direction from institutional
commodity analytics research: one Portfolio/Decision workflow with shared
resource identity, explicit route feasibility, compact metric strips, binding
constraint tables and a non-execution review pack. Scenario/optimizer/review
remain separate analysis modes, not separate pages.

## Trader-first presentation rules (2026-10-30, supersedes conflicting guidance)

Added after the supplier-acceptance review by an experienced gas trader
(`TRADER_ACCEPTANCE_REVIEW.md`). The backend's provenance and fail-closed rules are
unchanged; these rules govern how much of that evidence is *on screen by default*.

1. **One number, one place.** A price, spread or position appears once per page.
   Hub prices are a single hub × tenor board (bid/ask, mid, tick, spread vs TTF,
   WD/DA/WE/MA mids, source, unit · age), not ticker cards plus lanes plus tables.
2. **Provenance on demand.** Projection slice tables, per-source quotes, source
   matrices and reference-index evidence sit behind a one-line disclosure
   (`<details>`). The default line states the as-of instant and how many slices are
   degraded; a degraded count is coloured, so it still cannot be missed.
3. **Plain desk language.** On-screen text names what the trader can do, not how
   the store works: no "PostgreSQL", "runtime", "measured empty result",
   "receipt-bound" or raw `CODE:detail` strings in visible copy. Codes stay in
   `title` tooltips and evidence views. Tooltip/detail text may keep the precise
   technical statement.
4. **Empty states are one line** and say what would fill them ("appears after the
   GIE AGSI source is ingested"), never a paragraph about what is not invented.
5. **History is not an action.** Expired candidates, closed alerts and decided cases
   are counted and one click away, not mixed into the actionable list.
6. **Normal operation earns no badge.** Polling is normal; only a live stream gets a
   chip. Administration posture (credentials, record counts) lives under
   Administration, not on trader pages.
7. **Native units first.** Show each hub in its quoted unit; conversions (p/th,
   $/MMBtu, FX fix used) are explicit and labelled, never silent.
8. **Prices are the landing page.** Market → Curves opens first; map, capacity and
   research are tasks.
9. **Speak the execution screen's language.** Users trade on Trayport or exchange
   screens. Use their product names (WD, DA, WE, BOM, Nov-26, Q1-27, Sum-27, Win-27,
   GY-27, Cal-27), "Bid / Offer", volumes in MW (continental) and th/d (NBP), and offer
   the ladder layout (products down, hubs across, Bid Vol | Bid | Offer | Offer Vol).
   Do not copy any vendor's visual design.
10. **Simulated is never mistaken for market.** Any simulated price on screen carries a
    board-level banner. Real and simulated quotes never compete for a best price.
11. **Accessible by default.** Text meets WCAG AA contrast in light and dark themes, and
    scrollable regions are keyboard focusable. The browser-acceptance axe sweep enforces
    this.

12. **The search bar answers before it navigates** (answer bar, 2026-11-16;
    [user guide](../user/ANSWER_BAR.md)). One bar, three tiers, cheapest and surest first:
    instant (calculator, conversions with the units authority's factors, gas day, glossary;
    no network), looked up (prices, fundamentals, outages, book; existing reads, 250 ms
    debounce, stale reads cancelled), asked (Enter only; a checked AI summary over the desk's
    figures). The answer row is the first option: a `KeyFigure` with the value in tabular
    figures and the desk's unit, the `sim` mark beside a simulated value as on the hub board,
    and the provenance (as-of, source, ECB rate and date, calorific value and its reference
    conditions) one quiet line per fact under it. A conversion that needs an FX rate or a
    calorific value never runs on a silent default. A half-typed name gives no answer row.
    Enter opens the task where the number lives; Tab takes the answer into the field;
    Ctrl/⌘+C copies the number. Hooks: `#palette-answer`, `#palette-ask`, `[data-answer-kind]`,
    `[data-answer-value]`, `.answer-ask-panel[aria-busy]`.

13. **The strip under the top bar is a calm instrument line, not a news ticker**
    (situational strip, 2026-11-17; [design basis](ROLE_FIRST_REDESIGN.md) §5,
    [user guide](../user/SITUATION_STRIP.md)). It shows what needs *this person* now, by
    role: a trader sees a large unplanned outage where the book holds a position or at a
    focus hub and a breach of their own mandate, never pipeline or ingestion state (that is
    the administrator's and data operator's strip only); finance has none. Four states:
    **hidden** (no element at all, so no empty band), **quiet** (one static muted line: booked
    today from the ETRM import, read-only, or the next nomination window, or the counts a
    risk manager starts from), **urgent** (one static line: severity mark, the top item, its
    comparison, "+n more"; a coloured edge; no marquee, nothing to pause) and **expanded**
    (at most seven items, a popover on a desktop and a sheet on a phone; each with its link
    to where the job continues, Hide, Acknowledge only with the permission, Why and Report,
    and a line saying why this person sees it). An item is urgent for six hours after it
    became true or materially changed, then it is standing and only the bell lists it. Every
    item names its source and is a translated sentence built from fields; an unsourced item
    is rejected; a demo figure carries `sim`. Hide is personal and the item comes back when
    its size or status changes. A new item is announced once; a standing state never is.
    Thresholds (outage GWh/d and share, price move %, focus hubs, the quiet line) are personal
    preferences with organisation defaults. Hooks: `[data-shell-region="ticker"]`,
    `[data-strip-state]`, `[data-strip-expand]`, `[data-strip-list]`, `[data-strip-rule]`,
    `[data-strip-why]`, `[data-strip-action]`, `[data-strip-announcer]`.

Source-pinning contract tests should assert behaviour and data hooks
(`data-market-board`, `data-record`, `aria-pressed`) rather than CSS class names or
exact copy, so that presentation can improve without weakening a gate.

## Shell foundation rules (2026-11-17, from the owner's phone review)

13. **Phone rules: the page never scrolls sideways.** At 360-430 px nothing is wider than the
    screen. The frame (`clients/web/src/styles/frame.css`) lets every box shrink to its parent
    and clips the app root on x without becoming a scroll container. Wide content scrolls inside
    its own box with a visible affordance: a DataGrid keeps its primary columns (or the first
    three) and folds the rest into each row's Details; any other table wider than its box is
    marked by the shell (`useWideContent`) and scrolls inside itself with edge shadows; rows of
    tabs and segments scroll inside themselves. Long values wrap or truncate with a `title`.
    Forms use `Field` in a `ds-form-grid` (labels above controls, one column on a phone), never
    label/input pairs flowing in a line. The browser sweep measures every page, task and sub-view
    at 390 px in English and Chinese (`scripts/uat/phoneOverflow.mjs`), clipped by the frame or not.
14. **One structure in every language.** A control row has the same order and shape in English
    and Chinese; nothing depends on how long a label is. The page's context line (gas day,
    product, hub, as-of, data feeds) is one row on a phone: one summary button
    ("16 Nov · All products · All hubs") opens a sheet with the three controls, the as-of is short
    ("as of 00:57 CET"), and the feed status is a short word.
15. **The top bar holds navigation, search, alerts, data status and the account, nothing else.**
    Below 1024 px the mark is the menu (one control). Every icon-only control has an accessible
    name and a tooltip, and is 44 px on a touch screen. Demo mode is said once and quietly: a small
    "Demo" badge beside the mark and one line in the account menu, never a chip on every page (the
    simulated-prices banner on a board stays, rule 10). Help, keyboard shortcuts and "Report a
    problem" live in the account menu and in the answer bar ("help", "report a problem"), not as a
    "?" button on the bar.
16. **Problems are listed, not pinned.** Reads that did not load show as a count on the top bar's
    data-status dot; its panel names each affected read, says why in plain words and offers the
    action (Retry, Data sources for whoever administers them, or Report a problem). The first time
    a set of problems appears in a session a one-line notice says so under the bar, with Retry,
    Details and Dismiss; dismissing holds until the set changes. Only a critical state stays: the
    data store not answering (a blocking notice) or the sign-in lost (the sign-in screen).
17. **Time rule.** Instants are stored and sent in UTC and shown in the reader's zone (Account ->
    Preferences -> "Times shown in": device, UTC or gas-market time CET/CEST) through one
    formatter (`app/time/timeFormat.ts`, the `Instant` primitive), with the zone named
    ("00:57 CET", "08:57 GMT+8"), the date only when it is not today, seconds only when a screen
    needs them, the full instant and its UTC form as the tooltip. Gas days are not shifted. Words,
    months and numbers follow the app's language, never the browser's.
18. **Loading rule: the product never looks frozen.** Anything that waits more than about 300 ms
    shows that it is working: a data panel shows Skeleton rows where its rows will be; an AI or
    long action (Desk brief, Why, a contract import, a report, an optimiser run) shows its named
    stages with a moving bar (`WorkProgress`: "Reading prices and curves", "Reading outages and
    flows", "Writing the draft"), current stage marked, never complete before the answer arrives;
    the button that started it shows its busy state and cannot be pressed twice
    (`Button loading`, `useBusyAction`); the result area keeps the height the result will take, so
    nothing jumps when it arrives. Nothing appears for a wait shorter than 300 ms (no flicker).
    Motion stops under `prefers-reduced-motion`; the words still change. Pages use
    `app/hooks/useWorkProgress.ts` and `components/ui/WorkProgress.tsx` rather than their own.
19. **Coming back is instant; nothing blanks.** A panel reads through the client read cache
    (`app/data/readCache.ts`, `useCachedRead`): returning to a page or task shows its last answer
    at once with a quiet "Updating" mark while a newer one is read; a failed refresh keeps the last
    good answer and lists the problem in the data-status panel (the answer's own as-of says how
    old it is, so kept data is never shown as current). The cache belongs to one signed-in
    principal and any write marks it stale. The workspace batch starts the visible page's reads
    first and runs six at a time with exponential backoff on retry; a read that fails keeps the
    last good slice. The window's scroll position is restored per page and task for the session.
20. **One segment language, two levels.** A page's tasks are underline tabs (level 1,
    `WorkspaceTabs`/`Tabs`). Every in-panel choice and every second-level row under a page's
    tasks is a Segmented control (level 2): a quiet track, the chosen segment a raised surface
    chip, no separators (the look of Desk → Network → Capacity operations, which testers liked).
    On a phone a segmented row scrolls inside itself with its ends fading into the track, never
    clipped mid-word and never wrapped into a second row. Filter chips (several on at once) and
    row selections are not segmented controls.
21. **Enums are said in words; plumbing stays with whoever acts on it.** A state, kind or reason
    the server sends as a code (`SUCCEEDED_WITH_WARNINGS`, `NOT_REQUIRED`, `AVAILABLE`) reads in
    words through `app/model/enumLabels.ts` (`enum.<value>` in the locale, else the humanized
    code); `StatusBadge` does this for every badge and keeps the code in its title. Source
    identifiers read as the desk names them (`ICE_ENDEX` -> "ICE Endex"). Internal ids, evidence
    references and environment switches never appear in a trader's text; they live behind a
    Details disclosure, the Inspector or Administration. Setup notices ("source not approved ->
    Admin -> Connectors") show only to whoever can act on them. The browser sweep's phone pass
    fails on a bare enum code on any page except the ones being deleted.
22. **Nothing floats over the next page.** A Popover, Dialog or Sheet (and the top bar's status
    panel) opened on one page, task or view closes when the reader moves to another
    (`app/shell/navigationKey.ts`, `useCloseOnNavigation`, applied in the primitives). Changing a
    filter on the same page (gas day, hub) is not a move.
23. **Native first; the reader's currency beside it, named.** A price, quote, position or contract
    figure is shown in its native unit and currency; Account → Preferences → Currency and units
    (`reporting_currency`, `energy_unit`) only sets the secondary value. A price shows it on hover,
    focus or tap; P&L, limits and totals show it as a second line when the currencies differ. The
    secondary value always names its rate, the rate's date and the method ("−440,444 USD at
    EUR/USD 1.0870 (ECB 16 Nov; spot)"); a forward that cannot be derived says "Not converted"
    rather than falling back to spot. Contract terms, tariffs and frozen decision evidence are
    never converted; a total over mixed currencies is shown only converted; simulated inputs never
    join a non-simulated total. The server converts (`/api/market/normalise`,
    `/api/market/fx-forward`); the client formats (`app/time/valueFormat.ts`,
    `app/time/useConversion.ts`, `KeyFigure converted`, `ConvertedValue`). Exports add
    `conversionExportColumns` (pair, rate, rate date, method, source).
24. **Every task says what it is for.** Under the title and tabs, one muted sentence (at most 110
    characters) names the decision the task helps with: `purpose.<mode>.<task>` in the locale
    files, drawn by `useModeHeader().purpose` through `WorkspaceHeader` and the shell header
    (`PageIntro`, `[data-purpose]`). What a page needs appears only when something is missing, at
    most three items with the control that fixes each (`ReadinessChecklist`). An empty state is
    one line with its reason; a missing permission names who grants it (`empty.permission`), a
    missing licence says the administrator connects it (`empty.licence`), never a prompt to buy.
    The browser sweep's phone pass fails a commercial task without a purpose line, an empty state
    without a reason, or a page offering a JSON upload (two pages are listed until their packages
    remove it).

## Implementation note

No rasterized screenshots are shipped as application UI. The accepted concept is
implemented with real React/CSS components only.
