# Accessibility Report — CR-13

## Method

- axe-core 4.x automated scan on 13 workspace URLs at 1440×900 (Playwright
  Chromium headless).
- Manual keyboard workflow checks for Market, Strategy Design/Backtest, and
  Review (focus path, activation, no focus loss).
- DOM heuristic audit for unlabeled controls, positive tabindex, overflow,
  heading structure.

## Automated result

After CR-13 fixes, axe reports **0 violations across network, market,
portfolio, scenario, strategy, review, orders, sources, glossary, runtime,
settings, manual, and access**.

## Fixed critical/serious findings

- `label` critical: Review analysis textarea had no accessible name.
- `color-contrast` serious: 50+ muted/status nodes failed AA. Corrected
  `--eg-muted` to `#6f6f6f`, added `--eg-positive`/`--eg-warn`/
  `--eg-negative` tokens, dark-mode overrides, and active-row contrast.
- `heading-order` moderate: 88 panel `<h3>` elements now follow the correct
  `h1 -> h2` hierarchy after the workspace heading.
- `landmark-one-main`/`region`: `<main>` no longer overrides its role with
  `tabpanel`; page content is inside the main landmark.
- `scrollable-region-focusable`: resource path list and network resource rail
  are keyboard-focusable.

## Manual keyboard result

- Market: topbar context controls and hub board are reachable/operable by
  keyboard; workspace tabs use roving/arrow semantics.
- Strategy: create-strategy form, save draft, freeze, and run backtest are
  keyboard-operable in sequence.
- Review: decision recorder controls are keyboard-operable and disabled until
  an entity id is present.
- No unexpected focus loss was observed.

## Remaining limitations

- Automated axe PASS is not a substitute for an external accessibility review
  by users of assistive technology; that review remains PENDING_EXTERNAL.
- Map and chart text alternatives are structural; assistive-technology
  validation with NVDA/VoiceOver is deployment acceptance.
