import type {
  PortfolioOptimizationResultDTO,
  ResourcePoolOptionsDTO,
  RouteCandidateDTO,
  RouteRecommendationResultDTO,
} from "@/api/client";

export type PortfolioTask = "overview" | "resources" | "routes" | "exposure";
export type DecisionTask = "scenario" | "optimize" | "review";

export const PORTFOLIO_TASKS: PortfolioTask[] = ["overview", "resources", "routes", "exposure"];
export const DECISION_TASKS: DecisionTask[] = ["scenario", "optimize", "review"];

export function portfolioTaskFromLocation(search: string): PortfolioTask {
  const value = new URLSearchParams(search).get("task");
  return value === "resources" || value === "routes" || value === "exposure" ? value : "overview";
}

export function decisionTaskFromLocation(search: string): DecisionTask {
  const params = new URLSearchParams(search);
  const task = params.get("task");
  const workspace = params.get("workspace");
  if (task === "optimize" || task === "review") return task;
  // Legacy deep links: ?workspace=review must open Review, not Scenario.
  if (workspace === "review") return "review";
  if (workspace === "optimize") return "optimize";
  return "scenario";
}

export function portfolioTaskToSearch(search: string, task: PortfolioTask): string {
  const next = new URLSearchParams(search);
  next.set("workspace", "contracts");
  next.set("task", task);
  return next.toString();
}

export function decisionTaskToSearch(search: string, task: DecisionTask): string {
  const next = new URLSearchParams(search);
  next.set("workspace", "scenario");
  next.set("task", task);
  return next.toString();
}

export type RouteFeasibility = "FEASIBLE" | "FEASIBLE_WITH_WARNINGS" | "BLOCKED" | "UNKNOWN";

const SUPPORTED_ALLOCATION_STATUSES = new Set(["SUCCESS", "PARTIAL"]);

export function dedupeWarnings(
  ...warningLists: Array<ReadonlyArray<string> | null | undefined>
): string[] {
  const seen = new Set<string>();
  const warnings: string[] = [];
  for (const warningList of warningLists) {
    for (const warning of warningList ?? []) {
      if (seen.has(warning)) continue;
      seen.add(warning);
      warnings.push(warning);
    }
  }
  return warnings;
}

export function classifyRouteFeasibility(
  route: RouteCandidateDTO,
  recommendation: RouteRecommendationResultDTO | null,
  optimizer: PortfolioOptimizationResultDTO | null,
  resourcePoolOptions: ResourcePoolOptionsDTO | null = null,
): RouteFeasibility {
  // Route-specific blockers are authoritative, even if a stale/conflicting
  // allocation is present in another result layer.
  const explicitlyBlocked = Boolean(
    recommendation?.excluded_routes.some((excluded) =>
      excluded.route_id === route.route_id &&
      Array.isArray(excluded.blockers) &&
      excluded.blockers.length > 0,
    ) ||
    optimizer?.missing_inputs.some((item) => diagnosticMatchesRoute(item, route.route_id)) ||
    resourcePoolOptions?.blockers.some((item) => diagnosticMatchesRoute(item, route.route_id)),
  );
  if (explicitlyBlocked) return "BLOCKED";

  const recommendationAllocation =
    isSupportedAllocationStatus(recommendation?.status)
      ? recommendation?.allocations.find(
          (allocation) =>
            allocation.route_id === route.route_id && allocation.allocated_mwh_per_day > 0,
        )
      : undefined;
  const optimizerAllocation =
    isSupportedAllocationStatus(optimizer?.status)
      ? optimizer?.allocations.find(
          (allocation) =>
            allocation.option_id === route.route_id &&
            allocation.allocated_quantity_mwh_per_day > 0,
        )
      : undefined;

  // A positive allocation from a supported aggregate result is governed
  // evidence; failed/error/stale result statuses are not.
  if (recommendationAllocation || optimizerAllocation) {
    const warnings = dedupeWarnings(
      optimizer?.warnings,
      recommendation?.warnings,
      optimizerAllocation?.warnings,
      resourcePoolOptions?.warnings.filter((warning) =>
        diagnosticMatchesRoute(warning, route.route_id),
      ),
    );
    return warnings.length > 0 ? "FEASIBLE_WITH_WARNINGS" : "FEASIBLE";
  }

  // Required access declarations alone do not prove missing access.
  return "UNKNOWN";
}

function isSupportedAllocationStatus(status: string | null | undefined): boolean {
  return status !== undefined && status !== null && SUPPORTED_ALLOCATION_STATUSES.has(status);
}

function diagnosticMatchesRoute(diagnostic: string, routeId: string): boolean {
  return diagnostic.split(":").some((segment) => segment === routeId);
}
