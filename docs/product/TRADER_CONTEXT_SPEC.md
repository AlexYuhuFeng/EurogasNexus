# Trader Context Spec — CR-02 Input

Status: proposed context contract. Do not implement the full context architecture
in CR-01; this document is the design input for the next milestone.

## Objective

A single persistent trader context should make selection state predictable
across workspaces without uncontrolled global state. CR-02 will implement the
minimum viable slice.

## Proposed context model

| Field | Current source | Proposed owner | Scope |
|---|---|---|---|
| `gas_day` | `useCockpitControls` local state | shared trader context | global persistent |
| `delivery_product` | `useCockpitControls` local state | shared trader context | global persistent |
| `portfolio_id` | hard-coded `web-resource-pool` | shared trader context | global persistent |
| `hub` / `market_area` | local component selections | selection context | workspace-local, linked |
| `currency` | settings preference | preference store | global |
| `quantity_unit` | settings preference | preference store | global |
| `scenario_id` | none (temporary inputs) | scenario context (future) | workflow-local |
| `as_of` / freshness | API-derived per endpoint | read-only derived context | global view |
| `source_entitlement_posture` | Source Center API | read-only derived context | global view |

## Principles

1. URL remains the source of truth for navigation (`?workspace=<technical-id>`);
   trader context may later add an explicit `?asof=`/`?hub=` only after CR-02
   acceptance.
2. Do not duplicate context in multiple Zustand stores.
3. Selection propagation must be bounded: selecting a hub/route/contract updates
   declared linked panels in the same workspace, not every page.
4. Stale/unavailable context must render BLOCKED or DEGRADED, never a
   normal-looking candidate.
5. Backend/domain calculations stay authoritative; client context is selection
   and presentation state only.

## CR-02 acceptance candidates

- Changing gas day updates market, capacity, portfolio decision, and strategy
  panels consistently.
- Selecting a hub/route propagates to declared linked panels.
- Deep link with an explicit context query restores the intended state.
- Invalid/stale context fails closed.
- New context tests cover cross-workspace propagation and URL restoration.
