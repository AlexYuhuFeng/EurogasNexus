import type {
  EdgeDTO,
  NodeDTO,
  PortfolioOptimizationResultDTO,
  PortfolioResourceDTO,
  PortfolioSaleOptionDTO,
  RouteCandidateDTO,
} from "@/api/client";
import type {
  ResourcePoolMapPath,
  RouteGeometryState,
} from "@/components/ResourcePoolPathOverlay";
import {
  metadataText,
  normalizePointName,
  routeEdgeMetadataText,
  routeEdgeRouteId,
  routeLegLabel,
} from "./routeMetadata";

type Translate = (key: string) => string;
type ResourcePoolAllocation = PortfolioOptimizationResultDTO["allocations"][number];

export interface ResourcePoolHighlightedRoute {
  fromNodeId: string;
  toNodeId: string;
  routeId: string;
  label: string;
  pnlGbp: number | null;
  routeGeometryState: RouteGeometryState;
  routeLegSummary: string[];
}

interface BuildResourcePoolMapPathsParams {
  portfolioResources: PortfolioResourceDTO[];
  saleOptions: PortfolioSaleOptionDTO[];
  poolAllocations: ResourcePoolAllocation[];
  routeCandidates: RouteCandidateDTO[];
  routeGeometryEdgesByRouteId: Map<string, EdgeDTO[]>;
  poolInputBlockers: string[];
  t: Translate;
}

function metadataNumber(
  metadata: Record<string, unknown> | null | undefined,
  key: string,
  fallback: number,
): number {
  const value = metadata?.[key];
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim() && Number.isFinite(Number(value))) {
    return Number(value);
  }
  return fallback;
}

export function buildRouteGeometryEdgesByRouteId(edges: EdgeDTO[]): Map<string, EdgeDTO[]> {
  const grouped = new Map<string, EdgeDTO[]>();
  edges
    .filter((edge) => {
      const materialization = routeEdgeMetadataText(edge, "materialization");
      return edge.source_system === "route_candidate" || materialization === "route_candidate_edge";
    })
    .forEach((edge) => {
      const routeId = routeEdgeRouteId(edge);
      if (!routeId) return;
      grouped.set(routeId, [...(grouped.get(routeId) ?? []), edge]);
    });
  return grouped;
}

export function resolveRouteGeometryState(
  routeGeometryEdgesByRouteId: Map<string, EdgeDTO[]>,
  routeId: string,
  _routeLegSummary: string[],
): RouteGeometryState {
  const routeEdges = routeGeometryEdgesByRouteId.get(routeId) ?? [];
  if (routeEdges.length === 0) return "directLineFallback";
  const states = new Set(
    routeEdges
      .map((edge) => routeEdgeMetadataText(edge, "route_geometry_state"))
      .filter((value): value is RouteGeometryState =>
        value === "surveyed_pipeline_route" ||
        value === "source_derived_leg_sequence" ||
        value === "source_derived_corridor",
      ),
  );
  if (states.has("surveyed_pipeline_route")) return "surveyed_pipeline_route";
  if (states.has("source_derived_leg_sequence")) return "source_derived_leg_sequence";
  if (states.has("source_derived_corridor")) return "source_derived_corridor";
  return routeEdges.length > 1 ? "source_derived_leg_sequence" : "source_derived_corridor";
}

export function resolveRouteGeometryWarning(
  routeGeometryEdgesByRouteId: Map<string, EdgeDTO[]>,
  routeId: string,
  routeGeometryState: RouteGeometryState,
): string | null {
  const routeEdges = routeGeometryEdgesByRouteId.get(routeId) ?? [];
  const explicitWarning = routeEdges
    .map((edge) => routeEdgeMetadataText(edge, "geometry_warning"))
    .find((warning): warning is string => Boolean(warning));
  if (explicitWarning) return explicitWarning;
  const geometryQuality = routeEdges
    .map((edge) => routeEdgeMetadataText(edge, "geometry_quality"))
    .find((quality): quality is string => Boolean(quality));
  const unmatchedRouteLegCount = routeEdges.reduce(
    (total, edge) => total + metadataNumber(edge.metadata_json, "unmatched_route_leg_count", 0),
    0,
  );
  if (unmatchedRouteLegCount > 0) {
    return `${unmatchedRouteLegCount} route leg node(s) were not matched; map shows source-derived corridor geometry.`;
  }
  if (routeGeometryState === "source_derived_leg_sequence") {
    return "Matched route legs are displayed as source-derived corridor geometry, not surveyed pipeline geometry.";
  }
  if (routeGeometryState === "source_derived_corridor") {
    return geometryQuality === "endpoint_corridor"
      ? "Only endpoint corridor geometry is available for this route."
      : "Only source-derived corridor geometry is available for this route.";
  }
  if (routeGeometryState === "directLineFallback") {
    return "No materialized reference edge exists for this route; direct display fallback is shown.";
  }
  return null;
}

export function buildResourcePoolMapPaths({
  portfolioResources,
  saleOptions,
  poolAllocations,
  routeCandidates,
  routeGeometryEdgesByRouteId,
  poolInputBlockers,
  t,
}: BuildResourcePoolMapPathsParams): ResourcePoolMapPath[] {
  if (portfolioResources.length === 0 || saleOptions.length === 0) return [];
  const allocationByResourceAndOption = new Map(
    poolAllocations.map((allocation) => [`${allocation.resource_id}:${allocation.option_id}`, allocation]),
  );
  const fallbackWarnings = poolInputBlockers.length > 0 ? poolInputBlockers : [];
  const statePriority: Record<ResourcePoolMapPath["routeState"], number> = {
    allocated: 0,
    candidate: 1,
    blocked: 2,
  };
  const unrankedResourcePoolMapPaths = portfolioResources.flatMap((resource) =>
    saleOptions.map((option) => {
      const allocation = allocationByResourceAndOption.get(`${resource.resource_id}:${option.option_id}`) ?? null;
      const routeCandidate = routeCandidates.find((candidate) => candidate.route_id === option.option_id);
      const routeLegSummary = routeCandidate?.route_legs.map(routeLegLabel) ?? [];
      const routeGeometryState = resolveRouteGeometryState(
        routeGeometryEdgesByRouteId,
        option.option_id,
        routeLegSummary,
      );
      const routeGeometryWarning = resolveRouteGeometryWarning(
        routeGeometryEdgesByRouteId,
        option.option_id,
        routeGeometryState,
      );
      const routeWarnings = [
        ...(allocation?.warnings ?? []),
        ...(option.required_tso_access ?? [])
          .filter((tso) => Array.isArray(resource.accessible_tsos) && !resource.accessible_tsos.includes(tso))
          .map((tso) => `${t("home.missing_tso_access")}: ${tso}`),
        ...fallbackWarnings,
      ];
      const routeState: ResourcePoolMapPath["routeState"] = allocation
        ? "allocated"
        : routeWarnings.length > 0
          ? "blocked"
          : "candidate";
      const displayedQuantityMwhPerDay =
        allocation?.allocated_quantity_mwh_per_day ?? resource.available_quantity_mwh_per_day;
      const capacityUtilizationPct =
        option.capacity_limit_mwh_per_day && option.capacity_limit_mwh_per_day > 0
          ? (displayedQuantityMwhPerDay / option.capacity_limit_mwh_per_day) * 100
          : null;
      const indicativeNetMarginGbpMwh = option.sale_price_gbp_mwh -
        (
          resource.contract_cost_gbp_mwh +
          (resource.variable_cost_gbp_mwh ?? 0) +
          (resource.tolerance_risk_allowance_gbp_mwh ?? 0) +
          (option.route_cost_gbp_mwh ?? 0)
        );
      return {
        pathId: `${resource.resource_id}-${option.option_id}`,
        routeId: option.option_id,
        resourceName: resource.resource_name,
        sourcePointName: resource.location_point_name,
        targetPointName: option.target_point_name,
        availableQuantityMwhPerDay: resource.available_quantity_mwh_per_day,
        allocatedQuantityMwhPerDay: allocation?.allocated_quantity_mwh_per_day ?? null,
        capacityLimitMwhPerDay: option.capacity_limit_mwh_per_day ?? null,
        routeCostGbpMwh: option.route_cost_gbp_mwh ?? null,
        salePriceGbpMwh: option.sale_price_gbp_mwh,
        netMarginGbpMwh: allocation?.net_margin_gbp_mwh ?? indicativeNetMarginGbpMwh,
        routeState,
        routeGeometryState,
        routeGeometryWarning,
        routeLegSummary,
        warnings: routeWarnings,
        routeRank: 0,
        recommendationReason: "",
        capacityUtilizationPct,
        requiredTsoAccess: option.required_tso_access ?? [],
      };
    }),
  );
  const rankedResourcePoolMapPaths = [...unrankedResourcePoolMapPaths]
    .sort((left, right) => {
      const stateDelta = statePriority[left.routeState] - statePriority[right.routeState];
      if (stateDelta !== 0) return stateDelta;
      const marginDelta = (right.netMarginGbpMwh ?? Number.NEGATIVE_INFINITY) -
        (left.netMarginGbpMwh ?? Number.NEGATIVE_INFINITY);
      if (marginDelta !== 0) return marginDelta;
      return (left.routeCostGbpMwh ?? Number.POSITIVE_INFINITY) -
        (right.routeCostGbpMwh ?? Number.POSITIVE_INFINITY);
    })
    .map((path, index) => ({
      ...path,
      routeRank: index + 1,
      recommendationReason: path.routeState === "allocated"
        ? t("home.reason_allocated")
        : path.routeState === "blocked"
          ? path.warnings[0] ?? t("home.reason_blocked")
          : path.capacityLimitMwhPerDay !== null &&
              path.capacityLimitMwhPerDay < path.availableQuantityMwhPerDay
            ? t("home.reason_capacity_constrained")
            : t("home.reason_candidate"),
    }));
  return rankedResourcePoolMapPaths;
}

export function buildNodeIdByPointName(nodes: NodeDTO[]): Map<string, string> {
  const lookup = new Map<string, string>();
  nodes.forEach((node) => {
    [
      node.id,
      node.name,
      metadataText(node.metadata_json?.market_code),
      metadataText(node.metadata_json?.eic_code),
      metadataText(node.metadata_json?.balancing_zone),
    ].forEach((value) => {
      const key = normalizePointName(value);
      if (key && !lookup.has(key)) lookup.set(key, node.id);
    });
  });
  return lookup;
}

export function buildHighlightedResourcePoolRoute(
  resourcePoolMapPaths: ResourcePoolMapPath[],
  nodeIdByPointName: Map<string, string>,
): ResourcePoolHighlightedRoute | undefined {
  const resolvePathNodes = (path: ResourcePoolMapPath) => {
    const fromNodeId = nodeIdByPointName.get(normalizePointName(path.sourcePointName));
    const toNodeId = nodeIdByPointName.get(normalizePointName(path.targetPointName));
    return { fromNodeId, toNodeId };
  };
  const firstPath =
    resourcePoolMapPaths.find((path) => {
      const { fromNodeId, toNodeId } = resolvePathNodes(path);
      return path.routeState !== "blocked" && Boolean(fromNodeId && toNodeId && fromNodeId !== toNodeId);
    }) ??
    resourcePoolMapPaths.find((path) => {
      const { fromNodeId, toNodeId } = resolvePathNodes(path);
      return Boolean(fromNodeId && toNodeId && fromNodeId !== toNodeId);
    }) ??
    resourcePoolMapPaths[0];
  if (!firstPath) return undefined;
  const { fromNodeId, toNodeId } = resolvePathNodes(firstPath);
  if (!fromNodeId || !toNodeId || fromNodeId === toNodeId) return undefined;
  return {
    fromNodeId,
    toNodeId,
    routeId: firstPath.routeId,
    label: `${firstPath.sourcePointName} -> ${firstPath.targetPointName}`,
    pnlGbp: firstPath.netMarginGbpMwh !== null
      ? firstPath.netMarginGbpMwh *
        (firstPath.allocatedQuantityMwhPerDay ?? firstPath.availableQuantityMwhPerDay)
      : null,
    routeGeometryState: firstPath.routeGeometryState,
    routeLegSummary: firstPath.routeLegSummary,
  };
}
