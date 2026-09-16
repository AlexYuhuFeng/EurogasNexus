/**
 * Active Context contract (Architecture V2 Wave 1).
 *
 * Architecture V2 section 3 of
 * `docs/engineering/Architecture-V2/03_TARGET_PLATFORM_ARCHITECTURE.md` makes Active
 * Context first-class: one object that says which gas day, organisation, portfolio,
 * hub, resource, route, scenario, decision case and analysis snapshot the user is
 * working in. The W0-01 client inventory records that today those fields live in
 * several independent hooks and that four of them do not exist at all.
 *
 * This module defines the canonical shape, the URL keys that already carry part of
 * it, and - deliberately - the gaps. A gap is not papered over with a null that
 * looks like a value: `activeContextGaps` names what is missing so the surface, the
 * job and the future Analysis Snapshot can be honest about reproducibility.
 *
 * Context is not authority. Selecting a portfolio or a hub never grants access to
 * it; the backend re-authorises every read.
 */

import type {
  DeliveryProductId,
  SupportedHubId,
  TraderContext,
} from "@/app/context/traderContext";
import type { SelectionContext } from "@/app/context/selectionContext";
import type { WorkspacePageId } from "@/workspaceNavigation";

/** Fields of the Active Context that exist in the running client today. */
export interface ActiveContext {
  readonly workspace: WorkspacePageId;
  readonly gasDay: string;
  readonly deliveryProduct: DeliveryProductId;
  readonly hubId: SupportedHubId | null;
  readonly routeId: string | null;
  readonly resourceId: string | null;
  readonly strategyId: string | null;
  readonly strategyVersionId: string | null;
  readonly strategyRunId: string | null;
}

/**
 * Context V2 requires that the client cannot populate yet. Each entry names the
 * workspace or backend contract that will own it, so Wave 2/4/5 work has a
 * declared landing site instead of silently widening this interface.
 */
export const ACTIVE_CONTEXT_GAPS = ["organization", "portfolio", "decision-case", "analysis-snapshot"] as const;

export type ActiveContextGap = (typeof ACTIVE_CONTEXT_GAPS)[number];

const GAP_OWNERS: Readonly<Record<ActiveContextGap, string>> = {
  organization: "Wave 2 - effective access and scope (ExperienceProfile)",
  portfolio: "Wave 5 - PortfolioSnapshot projection",
  "decision-case": "Wave 6 - Decision Case",
  "analysis-snapshot": "Wave 4 - Analysis Snapshot v1",
};

export function activeContextGapOwner(gap: ActiveContextGap): string {
  return GAP_OWNERS[gap];
}

/** URL query keys the Active Context already uses (`?workspace=`, `?task=`, trader/selection keys). */
export const ACTIVE_CONTEXT_QUERY_KEYS = {
  workspace: "workspace",
  task: "task",
  gasDay: "gasDay",
  product: "product",
  hub: "hub",
  route: "route",
  resource: "resource",
  run: "run",
  strategy: "strategy",
  version: "version",
} as const;

export interface ActiveContextParts {
  readonly workspace: WorkspacePageId;
  readonly trader: TraderContext;
  readonly selection: SelectionContext;
}

export function activeContextFromParts(parts: ActiveContextParts): ActiveContext {
  return {
    workspace: parts.workspace,
    gasDay: parts.trader.gasDay,
    deliveryProduct: parts.trader.deliveryProduct,
    hubId: parts.trader.hubId,
    routeId: parts.selection.routeId,
    resourceId: parts.selection.resourceId,
    strategyId: parts.selection.strategyId,
    strategyVersionId: parts.selection.strategyVersionId,
    strategyRunId: parts.selection.strategyRunId,
  };
}

/**
 * Stable identity of a context, used as a cache/subscription key. Two surfaces that
 * print the same `contextKey` are describing the same working context, which is what
 * makes a cross-surface join legitimate instead of accidental.
 */
export function activeContextKey(context: ActiveContext): string {
  return [
    context.workspace,
    context.gasDay,
    context.deliveryProduct,
    context.hubId ?? "ANY",
    context.routeId ?? "-",
    context.resourceId ?? "-",
    context.strategyId ?? "-",
    context.strategyVersionId ?? "-",
    context.strategyRunId ?? "-",
  ].join("|");
}

/** Gaps still open in the running client. Today: all of them, by construction. */
export function activeContextGaps(): ActiveContextGap[] {
  return [...ACTIVE_CONTEXT_GAPS];
}

/**
 * Whether a result computed in a context can be reproduced from the context alone.
 * It cannot while the Analysis Snapshot is absent, and the product must say so
 * rather than implying reproducibility it does not have.
 */
export function activeContextIsReproducible(
  gaps: readonly ActiveContextGap[] = activeContextGaps(),
): boolean {
  return !gaps.includes("analysis-snapshot");
}

/** Context fields a surface may show as "current". Never includes a guessed value. */
export function activeContextSummary(context: ActiveContext): ReadonlyArray<{
  field: keyof ActiveContext;
  value: string | null;
}> {
  return [
    { field: "gasDay", value: context.gasDay },
    { field: "deliveryProduct", value: context.deliveryProduct },
    { field: "hubId", value: context.hubId },
    { field: "resourceId", value: context.resourceId },
    { field: "routeId", value: context.routeId },
    { field: "strategyId", value: context.strategyId },
    { field: "strategyVersionId", value: context.strategyVersionId },
    { field: "strategyRunId", value: context.strategyRunId },
  ];
}
