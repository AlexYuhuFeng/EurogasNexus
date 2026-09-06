# Product Information Architecture — CR-01 / P1A

Status: accepted for CR-01 implementation. This document owns the navigation
hierarchy; individual workspace redesigns remain later milestones.

## 1. Current-state problem

The web client exposes 13 technical workspace ids as near-peers and renders two
simultaneous hierarchy presentations (topbar grouped menu + page group tabs).
The resulting first-run impression is "13 small tools", not one professional
gas decision workstation.

Evidence used:

- `clients/web/src/workspaceNavigation.ts` (13 pages, 4 implementation groups)
- `clients/web/src/components/WorkspaceTopBar.tsx` (dropdown menu)
- `clients/web/src/app/workspaces/WorkspaceRenderer.tsx` (page-header group tabs)
- `output/ui-audit-2026-09-06/audit-tabs.json` (redundant page/task strips)
- `docs/clients/WORKSPACE_NAVIGATION_SPEC.md` (previous grouped-menu compromise)

## 2. User personas and jobs

| Persona | Primary job-to-be-done |
|---|---|
| Gas trader / desk analyst | Answer what is happening in markets and network, fast |
| Portfolio manager / structurer | Inspect resources, contracts, exposure, and route economics |
| Quant / strategy researcher | Design, backtest, compare, and shadow-run paper strategies |
| Commercial operator / reviewer | Test scenarios and review decision-support evidence |
| Data/runtime operator | Keep sources, runtime, credentials, and help healthy |

This hierarchy answers those jobs in order and makes operations recede.

## 3. Target primary workspaces

Level 1 (global navigation) contains five primary workspaces:

| PrimaryWorkspaceId | Label EN | Label zh-CN | Trader question it answers |
|---|---|---|---|
| `market` | Market | 市场 | What is happening physically and financially? |
| `portfolio` | Portfolio | 组合 | What resources/exposures do we currently have? |
| `strategy` | Strategy Lab | 策略实验室 | What research strategy are we testing/monitoring? |
| `decision` | Decision Center | 决策中心 | What scenario/optimization output needs review? |
| `system` | System | 系统 | Is the data/application configured and healthy? |

## 4. Child views (level 2, technical ids preserved)

| Primary | Child technical ids | Default | Notes |
|---|---|---|---|
| Market | `network`, `market`, `capacity` | `network` | Network remains map-first; capacity and market stay local tasks |
| Portfolio | `contracts`, `orders` | `contracts` | `contracts` displayed as Resource Terms; `orders` displayed as Market Positioning |
| Strategy Lab | `strategy` | `strategy` | Later milestones add Design / Backtest / Compare / Shadow |
| Decision Center | `scenario`, `review` | `scenario` | Optimization results remain reachable inside scenario/network workflows |
| System | `sources`, `runtime`, `settings`, `manual`, `glossary` | `sources` | Glossary re-homed as help/knowledge; direct links remain |

No backend endpoint is renamed. No database schema is changed. No domain
calculation is changed by this mapping.

## 5. Navigation model

Type separation:

- `WorkspacePageId` — existing technical view id; remains the URL truth and the
  source for deep links (`?workspace=network`, `?workspace=contracts`, ...).
- `PrimaryWorkspaceId` — product-level "where am I" identity.
- `primaryWorkspaceForPage(page)` — deterministic technical view -> primary.
- `defaultWorkspacePageForPrimary(primary)` — deterministic primary -> landing view.

Behavior:

1. Global topbar shows only five primary workspace tabs.
2. Switching a primary opens its default child view.
3. Direct loading of a technical view activates its parent primary.
4. Non-map workspaces show a compact local task switcher only when the primary
   has more than one child view.
5. Map (`network`) has no page-header task switcher; the topbar shows the active
   local task next to the primary tabs.
6. URL/`popstate` behavior remains unchanged: `?workspace=<technical-id>`.
7. Invalid workspace values continue to fall back to `network`.

## 6. Old-route compatibility mapping

| Old `?workspace=` | Resolves to primary | Local task |
|---|---|---|
| `network` | market | Network |
| `market` | market | Market |
| `capacity` | market | Capacity |
| `contracts` | portfolio | Resource Terms |
| `orders` | portfolio | Market Positioning |
| `strategy` | strategy | Strategy |
| `scenario` | decision | Scenario |
| `review` | decision | Review |
| `sources` | system | Data Sources |
| `runtime` | system | Runtime |
| `settings` | system | Settings |
| `manual` | system | Manual |
| `glossary` | system | Glossary |
| invalid/missing | market | Network (centralized fallback) |

`contracts` and `orders` keep their technical ids and display labels from the
existing i18n overrides. No redirect URL rewrite is introduced.

## 7. Workflow examples

- Market scan: open app -> Market/Network -> local task to Market for prices and
  spreads -> local task to Capacity for flows/storage/LNG.
- Portfolio review: Portfolio/Resource Terms -> Portfolio/Market Positioning.
- Strategy research: Strategy Lab -> current shadow terminal; later subviews are
  added under the same primary.
- Decision review: Decision/Scenario -> optimize/compare -> Decision/Review.
- Operations: System/Data Sources -> System/Runtime -> System/Settings ->
  System/Manual or System/Glossary for help.

## 8. Glossary/help placement

- `glossary` remains a technical workspace and deep link.
- It is moved under System and labelled as a help/knowledge surface, not a
  prime analytical destination.
- Contextual glossary entry points already exist inside Review/analysis flows;
  later milestones may add inline help without removing the full glossary.

## 9. Rejected alternatives

- Five primary + sidebar group + page group tabs simultaneously: rejected as
  redundant triple hierarchy.
- Keep current four implementation groups: rejected because group names
  (`Commercial Inputs`, `Analytics`) expose implementation domains rather than
  trader mental models.
- New URL route ids (`resource-terms`, `market-positioning`) now: rejected to
  preserve every existing deep link; aliases may be considered later.
- Put Network under Portfolio: rejected because market/network context is the
  trader's first job and map is the primary market cockpit.
- Delete or hide Glossary: rejected because operational context remains
  required; re-homing preserves reachability.
- Rename backend endpoints: rejected by milestone boundary.

## 10. Next milestone dependencies

- `CR-02` Persistent Trader Context and Cross-Workspace Selection Model is
  implemented in `clients/web/src/app/context/` and documented in
  `docs/product/TRADER_CONTEXT_SPEC.md`.
- Strategy subviews (Design/Backtest/Compare/Shadow) are added in later strategy
  milestones and must not introduce new global peers.
