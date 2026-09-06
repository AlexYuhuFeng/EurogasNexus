import type {
  PortfolioOptimizationResultDTO,
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

export function classifyRouteFeasibility(
  route: RouteCandidateDTO,
  recommendation: RouteRecommendationResultDTO | null,
  optimizer: PortfolioOptimizationResultDTO | null,
): RouteFeasibility {
  const requiredAccess = route.required_tso_access ?? [];
  const recommendationForRoute = recommendation?.allocations.some(
    (allocation) => allocation.route_id === route.route_id,
  );
  const optimizerBlocked =
    optimizer !== null &&
    optimizer.status !== "OPTIMAL" &&
    optimizer.status !== "FEASIBLE" &&
    optimizer.missing_inputs.some((item) => item.includes(route.route_id));
  const hasAccess = requiredAccess.length === 0;
  if (!hasAccess || optimizerBlocked) return "BLOCKED";
  if (recommendationForRoute) {
    const warnings = [
      ...(optimizer?.warnings ?? []),
      ...(recommendation?.warnings ?? []),
    ];
    return warnings.length > 0 ? "FEASIBLE_WITH_WARNINGS" : "FEASIBLE";
  }
  if (optimizer?.allocations.some((allocation) => allocation.option_id === route.route_id)) {
    return optimizer.warnings.length > 0 ? "FEASIBLE_WITH_WARNINGS" : "FEASIBLE";
  }
  return "UNKNOWN";
}
