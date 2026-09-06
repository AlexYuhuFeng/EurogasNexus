# Trader Context Spec

Status: CR-02 implementation contract. Backend/domain remains the authority for
calculations, gas-day boundaries, freshness, provenance, and entitlement.

## 1. Purpose

Continuity of intent: a trader establishes gas day, delivery product, and
optional hub focus once, then moves across Market, Portfolio, Strategy Lab,
and Decision Center without reconstructing that intent. Object selection is a
separate transient context used only for explicit cross-workspace handoffs.

## 2. Context categories

| Category | Owner | Lifetime | Examples |
|---|---|---|---|
| Trader / analytical context | client context hook | persistent | gas day, delivery product, hub focus |
| Cross-workspace selection | client selection hook | session + URL, not localStorage | route id, resource id, strategy run id |
| Display preferences | existing settings/theme stores | persistent | language, theme, currency/unit |
| Evidence / runtime state | backend API response | backend-owned | as-of, freshness, provenance, entitlement, runtime health |

As-of/freshness is never a user-editable fake context value.

## 3. Canonical field definitions

### TraderContext

| Field | Type | Canonical representation |
|---|---|---|
| `gasDay` | string | `YYYY-MM-DD` valid calendar date |
| `deliveryProduct` | `"all" | "day-ahead" | "within-day" | "month-ahead"` | stable machine value; UI translates labels |
| `hubId` | `"TTF" | "NBP" | "THE" | "PEG" | "ZTP" | "PSV" | null` | uppercase canonical hub code from backend-normalized rows |

### SelectionContext

| Field | Type | Identity source |
|---|---|---|
| `routeId` | string or null | `route_id` from backend route/recommendation objects |
| `resourceId` | string or null | `resource_id` from backend resource-pool resources |
| `strategyRunId` | string or null | `run_id` from backend strategy-run records |

No translated labels, array indexes, display positions, or client-generated
fake portfolio ids are used for cross-workspace identity.

## 4. Identifiers vs display labels

- Identifiers are stable machine strings with safe URL serialization:
  `[A-Za-z0-9][A-Za-z0-9._:-]{0,127}`.
- Display labels are derived from the selected backend object where available;
  when a handoff banner shows only an id, it remains honest rather than
  inventing a label.
- Hub codes are canonical backend-normalized codes; venue, product, source, and
  node are distinct concepts and are not collapsed into `hubId`.

## 5. Ownership

- `clients/web/src/app/context/` owns pure context types, normalization,
  persistence, URL serialization, invalidation, and hooks.
- `useAppController` composes the hooks.
- Workspaces consume explicit props; no workspace mutates context except
  through the documented setters (`Market` may set hub focus; topbar may set
  gas day/product/hub).
- Backend owns all calculation and evidence state.

## 6. Defaults

- `gasDay`: corrected CAM gas-day label for the current instant
  (`EU-CAM-UTC-2025`, 05:00Z winter / 04:00Z DST).
- `deliveryProduct`: `all`.
- `hubId`: `null` (all hubs).
- Selection: empty (no route/resource/strategy run).

## 7. Persistence

- Trader context persists under
  `localStorage["eurogas.traderContext.v1"]`, containing only validated
  gas day, delivery product, and hub id.
- Selection context is session/URL-only and is never persisted.
- Backend result/evidence state is never persisted as preference.

## 8. URL serialization

Canonical query model:

```text
?workspace=<technical-view>
&gasDay=YYYY-MM-DD
&product=all|day-ahead|within-day|month-ahead
&hub=NBP
&route=<safe-id>
&resource=<safe-id>
&run=<safe-id>
```

- Legacy `workspace` remains the navigation source of truth.
- Default values are omitted to keep URLs short.
- Secrets, credentials, strategy parameters, and commercial terms are never
  serialized.

## 9. Update/invalidation behavior

Precedence per field:

1. valid explicit URL value;
2. valid persisted trader context;
3. backend/product default.

An invalid explicit URL value falls back to the default, not to persisted
context.

Invalidation rules:

- Change `gasDay`, `deliveryProduct`, or `hubId` marks existing optimizer,
  route, and strategy results as context-mismatched until re-run for the
  current context.
- Change display currency/unit re-renders presentation; it does not invalidate
  strategy identity or result objects.
- Change a selection id may update the target workspace focus but never clears
  unrelated market history automatically.
- Clearing optional hub focus returns hub-consuming views to all-hub scope.

## 10. Workspace consumption matrix

| Primary | gasDay | product | hub | route selection | resource selection | strategy-run selection |
|---|---|---|---|---|---|---|
| Market | RW | RW | RW | R | - | - |
| Portfolio | R | R | R | - | RW | - |
| Strategy Lab | R | R | R | - | R | RW |
| Decision Center | R | R | R | R | R | R |
| System | - | - | - | - | - | - |

R = consumes; W = may update; RW = consumes and may update; - = independent.

## 11. Compatibility

- All existing `?workspace=<technical-id>` links continue to resolve; context
  query keys are optional and additive.
- Direct deep links such as `?workspace=scenario&route=...` restore the parent
  primary workspace and selection context.
- A legacy link with no context query resolves through persisted context and
  then defaults.

## 12. Stale/missing behavior

- A context-specific result generated under a different context key shows a
  `Result context mismatch` warning and a re-run prompt.
- Missing optional hub focus means all hubs.
- Missing/empty strategy or optimizer results retain existing empty states.
- Failed context-specific API calls never silently revert to an unrelated
  previous result.

## 13. Accessibility behavior

- Topbar gas day/product/hub controls are labelled form controls.
- Market hub focus buttons expose `aria-pressed`.
- Optional hub focus can be cleared by keyboard through the topbar select.
- Handoff actions are labelled buttons, never icon-only or color-only.

## 14. Future extension rules

- Add a field only when a real backend identity exists; do not create fake ids.
- New context fields must specify category, lifetime, URL key, precedence,
  invalidation, and workspace matrix before implementation.
- If a workspace needs a new selection concept, add it to `SelectionContext`
  only with a safe stable id contract.
- Display preferences remain outside trader context.
