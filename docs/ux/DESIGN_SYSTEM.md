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
5. **Motion explains, never decorates.** 120 ms for hover and focus, 180 ms for panels
   entering and menus opening, eased out. Everything stops under
   `prefers-reduced-motion: reduce`.
6. **Accessible.** WCAG 2.1 AA contrast in both themes, a visible focus ring on every
   control, keyboard paths for every action (⌘K / Ctrl K opens search and navigation).

## Tokens

| Group | Tokens |
|---|---|
| Surfaces | `--ds-bg`, `--ds-surface`, `--ds-surface-2`, `--ds-surface-3` |
| Lines | `--ds-border`, `--ds-border-strong` |
| Text | `--ds-text-1` (primary), `--ds-text-2` (secondary), `--ds-text-3` (meta) |
| Meaning | `--ds-accent`, `--ds-positive`, `--ds-negative`, `--ds-warning`, each with `-soft`; `--pnl-profit`, `--pnl-loss` follow the user's P&L convention |
| Type | `--ds-text-xs` 11, `sm` 12, `base` 13, `md` 14, `lg` 16, `xl` 18, `2xl` 22, `3xl` 28; weights 400 / 500 / 600 |
| Space | 4-pixel grid: `--ds-space-1` 4 … `--ds-space-8` 32 |
| Shape | `--ds-radius-sm` 6 (controls), `md` 8, `lg` 12 (panels), `pill` |
| Elevation | `--ds-shadow-sm` (panels), `md` (raised), `lg` (popovers) |
| Motion | `--ds-duration-fast` 120 ms, `--ds-duration` 180 ms, `--ds-duration-slow` 260 ms; `--ds-ease-out` |

Light and dark themes redefine the same tokens; nothing else changes between themes.

## Layers

`design-system.css` declares the cascade-layer order
`ds-base, legacy, ds-theme, ds-components, ds-motion`. Every pre-existing stylesheet sits in
`legacy` (`scripts/ui/migrate_legacy_css.py`), so the design system's components win without
specificity fights and the legacy rules keep working until each screen is migrated.

## Rules for new work

- Use `var(--ds-*)` tokens. A literal colour or pixel font size in a component stylesheet
  fails `clients/web/tests/designTokens.test.ts`; the legacy count may only go down.
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
