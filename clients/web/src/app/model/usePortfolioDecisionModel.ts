import { useEffect, useMemo, useRef, useState } from "react";
import type { TFunction } from "i18next";
import {
  buildHighlightedResourcePoolRoute,
  buildNodeIdByPointName,
  buildResourcePoolMapPaths,
  buildResourcePoolOptimizationRequest,
  buildReviewWarnings,
  buildRouteGeometryEdgesByRouteId,
  buildRouteRecommendationRequest,
  buildStrategyScenario,
  buildWorkspaceLatestRows,
  marketMatchesTradingContext,
  resolveNetworkGeometryState,
} from "@/app/index";
import type { ContractDraft } from "@/app/index";
import type { ApiState } from "@/stores/api";

interface PortfolioDecisionModelParams {
  api: ApiState;
  contract: ContractDraft;
  gasDay: string;
  deliveryProduct: string;
  t: TFunction;
}

export function usePortfolioDecisionModel({
  api,
  contract,
  gasDay,
  deliveryProduct,
  t,
}: PortfolioDecisionModelParams) {
  const lastAutoOptimizerSignatureRef = useRef<string | null>(null);
  const [liveMark] = useState({
    venue: "ICE OCM",
    hub: "NBP",
    product: "Within-day",
    bid_gbp_mwh: null as number | null,
    ask_gbp_mwh: null as number | null,
    last_gbp_mwh: null as number | null,
    mark_time_utc: new Date().toISOString(),
    source_system: "operator-draft-live-mark",
  });

  const portfolioResources = useMemo(
    () => api.resourcePoolOptions?.portfolio_resources ?? [],
    [api.resourcePoolOptions],
  );
  const saleOptions = useMemo(
    () => api.resourcePoolOptions?.sale_options ?? [],
    [api.resourcePoolOptions],
  );
  const saleOptionById = useMemo(
    () => new Map(saleOptions.map((option) => [option.option_id, option])),
    [saleOptions],
  );
  const hasPortfolioResources = portfolioResources.length > 0;
  const totalPoolVolume = useMemo(
    () => portfolioResources.reduce(
      (total, resource) => total + resource.available_quantity_mwh_per_day,
      0,
    ),
    [portfolioResources],
  );
  const contextMarkets = useMemo(
    () => api.markets.filter(
      (observation) => marketMatchesTradingContext(observation, gasDay, deliveryProduct),
    ),
    [api.markets, deliveryProduct, gasDay],
  );
  const resourcePoolOptimizationRequest = useMemo(
    () => buildResourcePoolOptimizationRequest(
      contract,
      portfolioResources,
      saleOptions,
      api.upstreamContracts,
    ),
    [api.upstreamContracts, contract, portfolioResources, saleOptions],
  );
  const routeRecommendationRequest = useMemo(
    () => buildRouteRecommendationRequest(
      portfolioResources,
      saleOptions,
      totalPoolVolume,
      api.upstreamContracts,
    ),
    [api.upstreamContracts, portfolioResources, saleOptions, totalPoolVolume],
  );
  const strategyScenario = useMemo(
    () => buildStrategyScenario(
      contract,
      liveMark,
      contextMarkets,
      portfolioResources,
      api.fxRates,
    ),
    [api.fxRates, contextMarkets, contract, liveMark, portfolioResources],
  );

  const selectedAllocation = api.routeRecommendation?.allocations[0] ?? null;
  const poolAllocations = api.resourcePoolResult?.allocations ?? [];
  const firstPoolAllocation = poolAllocations[0] ?? null;
  const firstPortfolioResource = portfolioResources[0] ?? null;
  const firstAllocationOption = firstPoolAllocation
    ? saleOptionById.get(firstPoolAllocation.option_id)
    : null;
  const rawDecisionPnl =
    api.resourcePoolResult?.total_net_pnl_gbp_per_day ??
    (selectedAllocation?.netback !== undefined && selectedAllocation?.netback !== null
      ? selectedAllocation.netback * selectedAllocation.allocated_mwh_per_day
      : null) ??
    api.portfolioSummary?.total_indicative_pnl_gbp ??
    null;
  const decisionPnl = hasPortfolioResources ? rawDecisionPnl : null;
  const decisionMargin = firstPoolAllocation?.net_margin_gbp_mwh ?? selectedAllocation?.netback ?? null;
  const salePrice =
    firstPoolAllocation?.gross_sale_price_gbp_mwh ??
    selectedAllocation?.sale_price ??
    saleOptions[0]?.sale_price_gbp_mwh ??
    null;
  const purchasePrice = firstPortfolioResource?.contract_cost_gbp_mwh ?? null;
  const routeCharge = firstAllocationOption?.route_cost_gbp_mwh ?? selectedAllocation?.route_cost ?? null;
  const firstStrategyTarget = api.strategyResult?.allocation_targets[0];
  const activeWarning = [
    ...(api.strategyResult?.warnings ?? []),
    ...(api.meta?.warnings ?? []),
  ][0] ?? null;
  const { latestCapacityRows } = useMemo(
    () => buildWorkspaceLatestRows({
      flows: api.flows,
      capacity: api.capacity,
      tsoAccess: api.tsoAccess,
      tsoTariffs: api.tsoTariffs,
      storage: api.storage,
      lng: api.lng,
    }),
    [api.capacity, api.flows, api.lng, api.storage, api.tsoAccess, api.tsoTariffs],
  );
  const reviewWarnings = useMemo(
    () => buildReviewWarnings(
      api.resourcePoolResult,
      api.routeRecommendation,
      api.strategyResult,
      api.analysisResult,
      api.meta,
    ),
    [
      api.analysisResult,
      api.meta,
      api.resourcePoolResult,
      api.routeRecommendation,
      api.strategyResult,
    ],
  );
  const runtimeDbReady =
    api.runtimeDb?.database_url_present === true && api.runtimeDb.connectivity.ok;
  const optionBlockers = api.resourcePoolOptions?.blockers ?? [];
  const canRunPoolOptimizer =
    runtimeDbReady &&
    hasPortfolioResources &&
    saleOptions.length > 0 &&
    optionBlockers.length === 0;
  const poolInputBlockers = useMemo(() => {
    const blockers: string[] = [];
    if (!runtimeDbReady) blockers.push(t("home.blocker_runtime_db"));
    blockers.push(...(api.resourcePoolOptions?.blockers ?? []));
    return blockers;
  }, [api.resourcePoolOptions, runtimeDbReady, t]);
  const autoOptimizerSignature = useMemo(
    () => JSON.stringify({
      resources: portfolioResources.map((resource) => [
        resource.resource_id,
        resource.available_quantity_mwh_per_day,
        resource.contract_cost_gbp_mwh,
        resource.location_point_name,
      ]),
      saleOptions: saleOptions.map((option) => [
        option.option_id,
        option.target_point_name,
        option.sale_price_gbp_mwh,
        option.route_cost_gbp_mwh,
        option.capacity_limit_mwh_per_day,
      ]),
      financingRate: resourcePoolOptimizationRequest.annual_financing_rate_pct,
    }),
    [portfolioResources, resourcePoolOptimizationRequest.annual_financing_rate_pct, saleOptions],
  );

  useEffect(() => {
    if (!canRunPoolOptimizer || api.loading) return;
    if (lastAutoOptimizerSignatureRef.current === autoOptimizerSignature) return;
    lastAutoOptimizerSignatureRef.current = autoOptimizerSignature;
    void api.optimizeResourcePool(resourcePoolOptimizationRequest);
  }, [
    api.loading,
    api.optimizeResourcePool,
    autoOptimizerSignature,
    canRunPoolOptimizer,
    resourcePoolOptimizationRequest,
  ]);

  const routeGeometryEdgesByRouteId = useMemo(
    () => buildRouteGeometryEdgesByRouteId(api.edges),
    [api.edges],
  );
  const resourcePoolMapPaths = useMemo(
    () => buildResourcePoolMapPaths({
      portfolioResources,
      saleOptions,
      poolAllocations,
      routeCandidates: api.routeCandidates,
      routeGeometryEdgesByRouteId,
      poolInputBlockers,
      t,
    }),
    [
      api.routeCandidates,
      poolAllocations,
      poolInputBlockers,
      portfolioResources,
      routeGeometryEdgesByRouteId,
      saleOptions,
      t,
    ],
  );
  const nodeIdByPointName = useMemo(() => buildNodeIdByPointName(api.nodes), [api.nodes]);
  const highlightedRoute = useMemo(
    () => buildHighlightedResourcePoolRoute(resourcePoolMapPaths, nodeIdByPointName),
    [nodeIdByPointName, resourcePoolMapPaths],
  );
  const reviewEvidenceItems = useMemo(() => {
    const items: Array<{ kind: string; text: string }> = [];
    const add = (kind: string, text: string | null | undefined) => {
      if (!text || items.some((item) => item.kind === kind && item.text === text)) return;
      items.push({ kind, text });
    };

    reviewWarnings.forEach((warning) => add(t("home.evidence_warning"), warning));
    poolInputBlockers.forEach((blocker) => add(t("home.evidence_blocker"), blocker));
    (api.resourcePoolResult?.missing_inputs ?? []).forEach(
      (input) => add(t("home.evidence_missing_input"), input),
    );
    (api.routeRecommendation?.assumptions ?? []).forEach(
      (assumption) => add(t("home.evidence_assumption"), assumption),
    );
    [
      ...(api.resourcePoolResult?.source_refs ?? []),
      ...(api.meta?.source_references ?? []),
      ...Object.values(api.endpointMeta).flatMap((item) => item.source_references ?? []),
    ].forEach((sourceRef) => add(t("home.evidence_source"), sourceRef));

    return items.slice(0, 6);
  }, [
    api.endpointMeta,
    api.meta,
    api.resourcePoolResult,
    api.routeRecommendation,
    poolInputBlockers,
    reviewWarnings,
    t,
  ]);
  const networkGeometryState = useMemo(
    () => resolveNetworkGeometryState(runtimeDbReady, api.nodes, api.edges),
    [api.edges, api.nodes, runtimeDbReady],
  );

  return {
    portfolioResources,
    saleOptions,
    saleOptionById,
    hasPortfolioResources,
    totalPoolVolume,
    contextMarkets,
    resourcePoolOptimizationRequest,
    routeRecommendationRequest,
    strategyScenario,
    selectedAllocation,
    poolAllocations,
    firstPoolAllocation,
    decisionPnl,
    decisionMargin,
    salePrice,
    purchasePrice,
    routeCharge,
    firstStrategyTarget,
    activeWarning,
    latestCapacityRows,
    reviewWarnings,
    runtimeDbReady,
    canRunPoolOptimizer,
    poolInputBlockers,
    resourcePoolMapPaths,
    highlightedRoute,
    reviewEvidenceItems,
    networkGeometryState,
  };
}
