# Design system

The interface follows one design system, defined in
`clients/web/src/styles/design-system.css`. It replaces the earlier mixture of a teal
palette, a "Vercel reference" token block and per-component sizes. Where older UX documents
(`docs/product/UX_REFERENCE.md`, `docs/ux/*`) disagree on visual detail, this document wins;
they remain the reference for information architecture and workflows.

## Principles

1. **Calm by default, loud only for state.** Neutral surfaces and text; colour is reserved
   for meaning (accent for the current selection and links, green/red for profit and loss
   and for up/down, amber for warnings, red for errors).
2. **Data first.** Prices, volumes and times use tabular numerals and line up; tables are
   dense (13 px, 32–36 px rows) but never cramped; units sit beside the figure.
3. **One way to draw each thing.** One button, one input, one tab, one badge, one panel, one
   table. A new screen composes these; it does not invent a variant.
4. **Sentence case.** No forced uppercase, no monospace labels. Monospace is for code and
   identifiers only.
5. **Motion explains, never decorates.** 80 ms for hover and focus, 160 ms for panels
   entering and menus opening, eased out. Everything stops under
   `prefers-reduced-motion: reduce`.
6. **Accessible.** WCAG 2.1 AA contrast in both themes, a visible focus ring on every
   control, keyboard paths for every action (⌘K / Ctrl K opens search and navigation).

## Tokens

The scales and colour roles live in `clients/web/src/styles/tokens.css` and are documented in
`docs/product/DESIGN_TOKENS.md` (six text sizes, weights 400/500/600, a 4 px spacing grid,
controls 28/32 with 44 on touch, radii 4/8/pill, two shadows, status and P&L roles, chart
series), with the token lint, the contrast test and the geometry audit that hold them.

## Layers

`design-system.css` declares the cascade-layer order
`ds-base, legacy, ds-theme, ds-components, ds-motion`. Every pre-existing stylesheet sits in
`legacy` (`scripts/ui/migrate_legacy_css.py`), so the design system's components win without
specificity fights and the legacy rules keep working until each screen is migrated.

## Rules for new work

- Use `var(--ds-*)` tokens. A raw colour, size, radius or control height in a converted
  stylesheet fails `clients/web/tests/cssTokenLint.test.ts`; the baseline may only shrink.
- New component styles live in `ds-components` (or a component file wrapped in that layer).
- Numbers: right-aligned, tabular, sign shown for changes, unit in the header or beside the
  value. Missing values show "–", never zero.
- Status: a badge (`.status-badge`) with a short sentence-case label; detail goes in a
  tooltip or the inspector, not the badge.
- Empty, loading and error states are part of the component: an empty table says what is
  missing and how to get it; loading uses `.ds-skeleton`, not a spinner over content.

## Shell

One sticky top bar: primary workspaces, search (⌘K), the trading context (gas day,
product, hub), source status, alerts and the account menu. Each workspace has one page
header with its local tabs. Below 1600 px the account name and data-plane badge collapse;
below 1280 px search shows only its shortcut.
