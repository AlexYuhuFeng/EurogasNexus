# Windows Demo UX Reference

## Purpose

This file captures the usable UX lessons from the historical Windows demo and
its archived QA reports. It is a reference for future web and Windows client
implementation. It is not permission to copy old code, assets, data, layout, or
runtime assumptions.

## Evidence Used

Executable artifacts were found under:

- `C:\Users\qqshu\Desktop\Eurogas Nexus Project\Eurogas Nexus Artifacts\desktop-builds\eurogas-nexus-v0.5.0.exe`
- `C:\Users\qqshu\Desktop\Eurogas Nexus Project\Eurogas Nexus Artifacts\builds\v0.5.0\eurogas-nexus.exe`

Archived QA reference:

- `C:\Users\qqshu\Desktop\Eurogas Nexus Project\Eurogas Nexus Artifacts\qa\v0.5\ui-ux-audit\real-user-audit-2026-04-02.md`

The executable was not launched during this documentation pass. UX conclusions
come from archived QA evidence and historical docs.

## UX Direction To Preserve

- Dense terminal-style workspace.
- First-screen visibility of recommendation/research posture, data status,
  source readiness, active focus, and warnings.
- Commercial-anchor-led flow from contract/context into scenario.
- Scenario workspace that keeps candidate focus, economics snapshot, data
  readiness, and comparison basis visible.
- Contract blotter plus active editor surface.
- Source/database console that separates bundled reference data, credentialed
  future sources, governance-limited sources, and degraded runtime state.
- Map-centric route/corridor/facility inspection.
- Research output review with assumptions, missing inputs, source references,
  warnings, and lineage.

## UX Direction To Redesign

- Do not keep a generic admin-console feel.
- Reduce oversized cards and decorative spacing.
- Improve keyboard-first navigation for heavy desk use.
- Tighten global search into a dense actionable result surface.
- Make runtime/source/data status visible without forcing users into a separate
  database page.
- Redesign Chinese/English locale behavior deliberately and test for mojibake.
- Treat settings as presentation preferences only, never canonical business
  truth.

## Target Workspace Model

Future visual clients should use this model:

```text
top status bar
  -> backend/API/DB/source/warning posture
left navigation
  -> Network, Contracts, Scenario, Market, Review, Sources, Runtime, Settings
main workspace
  -> map, scenario form, contract editor, market context, or review surface
right monitor
  -> active candidate, selected asset, assumptions, source, lineage
bottom panel
  -> comparison, missing inputs, warnings, result candidates
```

## Professional Desk Requirements

- Warnings and missing inputs must be visible near the action area.
- Sorting/filtering in the client must not rewrite canonical backend research
  output.
- Research idea/ranking cards must be clearly labeled as human-review
  decision-support.
- No button or label should imply order creation, trade execution, nomination
  submission, official approval, or official trading recommendation.
- Data source status must distinguish available, synthetic, credentialed-later,
  governance-limited, stale, and degraded.

## Implementation Use

Read this file together with:

- `docs/clients/CLIENT_DESIGN_SYSTEM.md`
- `docs/clients/WEB_CLIENT_DESIGN_SPEC.md`
- `docs/clients/WINDOWS_CLIENT_DESIGN_SPEC.md`
- `docs/design/UX_LAYOUT_BLUEPRINTS.md`
