import type {
  PortfolioOptimizationResultDTO,
  PortfolioResourceDTO,
  PortfolioSaleOptionDTO,
  RouteRecommendationResultDTO,
} from "@/api/client";

type RouteAllocation = RouteRecommendationResultDTO["allocations"][number];
type PoolAllocation = PortfolioOptimizationResultDTO["allocations"][number];
type Resource = Pick<PortfolioResourceDTO, "resource_id" | "contract_cost_gbp_mwh">;
type SaleOption = Pick<PortfolioSaleOptionDTO, "option_id" | "route_cost_gbp_mwh">;

export interface ScenarioRouteEconomics {
  routeId: string | null;
  scope: "selected" | "recommended";
  source: "route_recommendation" | "resource_pool" | "unavailable";
  volumeScope: "route" | "resource" | "unavailable";
  purchasePrice: number | null;
  salePrice: number | null;
  routeCharge: number | null;
  allocatedVolumeMwhPerDay: number | null;
}

interface SelectScenarioRouteEconomicsInput {
  carriedRouteId: string | null;
  selectedResourceId: string | null;
  routeRecommendation: RouteRecommendationResultDTO | null;
  resourcePoolResult: PortfolioOptimizationResultDTO | null;
  portfolioResources: ReadonlyArray<Resource>;
  saleOptionById: ReadonlyMap<string, SaleOption>;
}

function unavailable(scope: ScenarioRouteEconomics["scope"], routeId: string | null): ScenarioRouteEconomics {
  return {
    routeId,
    scope,
    source: "unavailable",
    volumeScope: "unavailable",
    purchasePrice: null,
    salePrice: null,
    routeCharge: null,
    allocatedVolumeMwhPerDay: null,
  };
}

export function selectScenarioRouteEconomics({
  carriedRouteId,
  selectedResourceId,
  routeRecommendation,
  resourcePoolResult,
  portfolioResources,
  saleOptionById,
}: SelectScenarioRouteEconomicsInput): ScenarioRouteEconomics {
  const scope = carriedRouteId ? "selected" : "recommended";
  const routeAllocation: RouteAllocation | null = carriedRouteId
    ? routeRecommendation?.allocations.find((allocation) => allocation.route_id === carriedRouteId) ?? null
    : routeRecommendation?.allocations[0] ?? null;
  const routeId = carriedRouteId ?? routeAllocation?.route_id ?? null;

  if (!routeId) return unavailable(scope, null);

  const resource = selectedResourceId
    ? portfolioResources.find((candidate) => candidate.resource_id === selectedResourceId) ?? null
    : null;

  if (routeAllocation) {
    return {
      routeId,
      scope,
      source: "route_recommendation",
      volumeScope: "route",
      // Purchase basis is valid only when the user selected a known resource.
      purchasePrice: resource?.contract_cost_gbp_mwh ?? null,
      salePrice: routeAllocation.sale_price ?? null,
      routeCharge: routeAllocation.route_cost ?? null,
      allocatedVolumeMwhPerDay: routeAllocation.allocated_mwh_per_day,
    };
  }

  // The web contracts use option_id === route_id in routeRecommendationRequest
  // and in the backend resource-pool option composition. Keep this as an
  // explicit fallback only when the route result has no matching slice.
  const matchingPoolAllocations = (resourcePoolResult?.allocations ?? [])
    .filter((allocation) => allocation.option_id === routeId);
  const poolAllocation: PoolAllocation | null = selectedResourceId
    ? matchingPoolAllocations.find((allocation) => allocation.resource_id === selectedResourceId) ?? null
    : matchingPoolAllocations.length === 1
      ? matchingPoolAllocations[0]
      : null;
  const hasMatchingSaleOption = saleOptionById.has(routeId);

  if (!poolAllocation || !hasMatchingSaleOption) {
    return unavailable(scope, routeId);
  }

  return {
    routeId,
    scope,
    source: "resource_pool",
    volumeScope: "resource",
    purchasePrice: resource?.contract_cost_gbp_mwh ?? null,
    salePrice: poolAllocation.gross_sale_price_gbp_mwh,
    // Pool allocations do not carry a versioned route-cost result.
    routeCharge: null,
    allocatedVolumeMwhPerDay: poolAllocation.allocated_quantity_mwh_per_day,
  };
}
