# Reference Evidence Log

## Purpose

This file records which local historical references informed the current docs.
It prevents future agents from needing to rediscover the same evidence and
keeps historical projects as references rather than implementation authority.

## Reviewed Local Roots

- `C:\Users\qqshu\Desktop\Eurogas Nexus Project`
- `C:\Users\qqshu\Desktop\Eurogas Nexus`

## Windows Demo Evidence

Executable artifacts found:

- `C:\Users\qqshu\Desktop\Eurogas Nexus Project\Eurogas Nexus Artifacts\desktop-builds\eurogas-nexus-v0.5.0.exe`
- `C:\Users\qqshu\Desktop\Eurogas Nexus Project\Eurogas Nexus Artifacts\builds\v0.5.0\Eurogas Nexus_0.5.0_x64-setup.exe`
- `C:\Users\qqshu\Desktop\Eurogas Nexus Project\Eurogas Nexus Artifacts\builds\v0.5.0\eurogas-nexus.exe`

No Desktop-root shortcut named `eurogas nexus.exe` was found during this pass.
The executable artifacts were not launched. UI/UX conclusions come from archived
QA reports and docs.

No attached project-structure image was available as a local file in this
worktree. Directory decisions are therefore based on the current repository,
archived project structures, and the user's written objective.

## Useful Archived Files

- `Eurogas Nexus Artifacts\qa\v0.5\ui-ux-audit\real-user-audit-2026-04-02.md`
- `Eurogas Nexus\eurogas-nexus\docs\TARGET_ARCHITECTURE.md`
- `Eurogas Nexus\eurogas-nexus\docs\THREE_LAYER_GRAPH.md`
- `Eurogas Nexus\eurogas-nexus\docs\ROUTE_COST_ENGINE_MODEL.md`
- `Eurogas Nexus\eurogas-nexus\docs\WEATHER_ADJUSTED_NOWCAST_MODEL.md`
- `Eurogas Nexus\eurogas-nexus\docs\STRATEGY_SHADOW_RUN_MODEL.md`
- `Eurogas Nexus\eurogas-nexus\docs\RESEARCH_DECISION_BRIEF.md`
- `Eurogas Nexus\eurogas-nexus\docs\API_CLIENT_SDK.md`
- `Eurogas Nexus\eurogas-nexus\docs\API_CLI_CLIENT.md`

## Extracted Product Lessons

- The mature client should feel like a dense desk terminal, not a generic admin
  app.
- First-screen status should include backend, DB/data, source, and warning
  posture.
- Scenario work should be anchored by commercial context, active candidate
  focus, economics snapshot, and data readiness.
- The contract/source/database views should separate presentation preferences
  from canonical business truth.
- Geometry, topology, and market abstraction must remain separate layers linked
  by explicit mappings.
- Route cost, netback, feasibility, allocation, nowcast, backtest, and shadow
  run should be research-only workflows with assumptions, missing inputs,
  warnings, source references, and lineage.
- SDK and CLI should call the backend API only.

Derived UX notes are recorded in
`docs/clients/WINDOWS_DEMO_UX_REFERENCE.md`.

## Failure Lessons

- Do not copy old code or UI wholesale.
- Do not treat local files as runtime truth.
- Do not add broad domain modules without DB/API contracts.
- Do not turn research outputs into order, nomination, execution, or official
  approval workflows.
- Do not read `.env`, credentials, vendor data, raw market data, internal
  commercial files, contracts, or generated reports.
