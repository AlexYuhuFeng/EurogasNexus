# W1-01 — Canonical Experience Shell and Active Context Contract

Status: **delivered contract (Wave 1)**. Authority: Architecture V2
[04_PRODUCT_EXPERIENCE_ARCHITECTURE.md](04_PRODUCT_EXPERIENCE_ARCHITECTURE.md) sections 3, 8 and 9,
[03_TARGET_PLATFORM_ARCHITECTURE.md](03_TARGET_PLATFORM_ARCHITECTURE.md) section 3, and
[AUTONOMOUS_EXECUTION_POLICY.md](AUTONOMOUS_EXECUTION_POLICY.md).

The key words "MUST", "MUST NOT", "SHALL", "SHALL NOT", "SHOULD" and "MAY" are interpreted as
described in RFC 2119 and RFC 8174.

Machine-readable form: `clients/web/src/app/experience/shellContract.ts`,
`clients/web/src/app/experience/activeContext.ts`,
`clients/web/src/app/experience/vocabulary.ts`.
Focused checks: `clients/web/tests/experienceArchitecture.test.ts`.

## 1. Scope

Wave 1 establishes the experience authority. It fixes the shell, context, pattern, panel,
Inspector, action, AI, palette and host contracts as executable seams. It does **not** migrate
workspaces onto them: mass UI conversion is Wave 9, because
[12_MIGRATION_ROADMAP.md](12_MIGRATION_ROADMAP.md) requires the design authority to exist before
pages move.

## 2. Canonical shell regions

There is one shell. Every work mode composes the same regions; only the content changes.

| Region | Implementation at Wave 1 | Owner today | Markup marker |
|---|---|---|---|
| `global-context` | present | `clients/web/src/components/WorkspaceTopBar.tsx` | `data-shell-region="global-context"` |
| `navigation` | present | `WorkspaceTopBar.tsx` (primary domains) and `WorkspaceRenderer.tsx` (local task row) | `data-shell-region="navigation"` |
| `primary-workspace` | present | `clients/web/src/app/shell/AppShell.tsx`, `WorkspaceRenderer.tsx` | `data-shell-region="primary-workspace"` |
| `inspector` | **planned** | `clients/web/src/app/experience/inspectorContract.ts` | none yet |
| `activity` | **partial** | `AppShell.tsx` (bounded endpoint-failure banner only) | none yet |

Rules:

1. At most one primary workspace SHALL mount at a time
   (`clients/web/src/app/shell/AppShell.tsx` selects `network` or delegates to
   `WorkspaceRenderer`).
2. Global context (gas day, delivery product, hub, identity, data status) SHALL have exactly one
   owner. A workspace MUST NOT mount a second global context selector.
3. A region that the client does not render yet SHALL be declared `planned` in the contract and
   MUST NOT be described as implemented. The focused test fails if a region claims rendered markup
   that no component emits.
4. Shell regions carry no authority. Visibility is not a security boundary
   ([02_ARCHITECTURE_CONSTITUTION.md](02_ARCHITECTURE_CONSTITUTION.md) rules 16-23).

The `activity` region remains partial on purpose: the V2 Unified Job model is Wave 8 work, and
inventing a job strip now would create a surface with no data contract behind it.

## 3. Active Context

Active Context is the single description of the working context a surface, run or artefact belongs
to. Wave 1 makes it a typed contract:

| Field | Source today | URL key |
|---|---|---|
| `workspace` | `useWorkspaceNavigation` | `workspace` |
| task | workspace task resolvers | `task` |
| `gasDay` | `useTraderContext` | `gasDay` |
| `deliveryProduct` | `useTraderContext` | `product` |
| `hubId` | `useTraderContext` | `hub` |
| `routeId` | `useSelectionContext` | `route` |
| `resourceId` | `useSelectionContext` | `resource` |
| `strategyId` | `useSelectionContext` | `strategy` |
| `strategyVersionId` | `useSelectionContext` | `version` |
| `strategyRunId` | `useSelectionContext` | `run` |

Declared gaps, each with its owning wave:

| Gap | Owner | Consequence until delivered |
|---|---|---|
| `organization` | Wave 2 (effective access / `ExperienceProfile`) | No organisational scope in the context key. |
| `portfolio` | Wave 5 (`PortfolioSnapshot` projection) | Portfolio scope is inferred from loaded slices, not from the context. |
| `decision-case` | Wave 6 (Decision Case) | Evidence is not attached to a container. |
| `analysis-snapshot` | Wave 4 (Analysis Snapshot v1) | **A result cannot be reproduced from context alone.** |

Rules:

1. A surface SHALL render the context it is working in; it MUST NOT infer a different one.
2. `activeContextKey` SHALL be used as the identity of a context for cache/subscription and
   cross-surface joins, so two surfaces showing the same key are describing the same context.
3. While `analysis-snapshot` remains a gap, `activeContextIsReproducible()` returns `false` and any
   surface presenting a result MUST NOT claim reproducibility from context alone. This is the
   honest state, not a defect to be hidden.
4. Selecting a portfolio, hub or object never grants access to it. Every read is re-authorised by
   the backend.

## 4. Work modes

Work modes (Trading Analysis, Portfolio Oversight, Research, Review, Administration) change
composition only. The registry lives in `clients/web/src/app/experience/workModes.ts` and each mode
names the canonical experience specification it belongs to
([W1-05](W1-05_CANONICAL_EXPERIENCE_SPECS.md)).

`WORK_MODE_GRANTS_AUTHORITY` is `false` and is asserted by the focused test. Binding a mode to a
backend-delivered `ExperienceProfile` is Wave 2 work; until then nothing in the client consults a
work mode to allow or deny anything.

## 5. Verification

- `clients/web/tests/experienceArchitecture.test.ts` — vocabulary, shell contract honesty, context
  key stability, gap declaration, work-mode composition-only rule, EN/zh-CN labels.
- The shell markup markers are asserted against the components that render them, so a rename cannot
  silently break the contract.

## 6. Compatibility and non-goals

- No route, deep link, workspace id, API call, permission, schema or numerical behaviour changes in
  Wave 1. The 16 technical page ids and the five primaries keep resolving exactly as before.
- No new page is created by this contract. No new dependency is added.
- The Inspector region and the activity row stay unimplemented; the contract says so.
