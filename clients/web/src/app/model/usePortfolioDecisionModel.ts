import { useEffect, useMemo, useRef, useState } from "react";
import type { TFunction } from "i18next";
import { warningLabel } from "@/app/warningLabel";
import {
  resultContextMatches,
  traderContextKey,
  type DeliveryProductId,
  type SupportedHubId,
} from "@/app/context";
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
import { selectScenarioRouteEconomics } from "@/app/model/scenarioRouteEconomics";
import { buildCommercialDiagnostics } from "@/app/model/commercialWarnings";
import { runtimeStoreStatus } from "@/app/model/dataPlaneStatus";
import { compositionFromProfile } from "@/app/experience/experienceProfile";
import {
  decisionActionAvailable,
  decisionComputeGate,
  decisionResultContextMismatch,
} from "@/app/model/decisionActionModel";
import type { ApiState } from "@/stores/api";

interface PortfolioDecisionModelParams {
  api: ApiState;
  contract: ContractDraft;
  gasDay: string;
  deliveryProduct: DeliveryProductId;
  hubId: SupportedHubId | null;
  selectedResourceId: string | null;
  selectedRouteId: string | null;
  t: TFunction;
}

export function usePortfolioDecisionModel({
  api,
  contract,
  gasDay,
  deliveryProduct,
  hubId,
  selectedResourceId,
  selectedRouteId,
  t,
}: PortfolioDecisionModelParams) {
  const lastAutoOptimizerSignatureRef = useRef<string | null>(null);
  const [strategyResultContextKey, setStrategyResultContextKey] = useState<string | null>(null);
  const currentContextKey = useMemo(
    () => traderContextKey({ gasDay, deliveryProduct, hubId }),
    [deliveryProduct, gasDay, hubId],
  );
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
    () => api.normalizedMarkets.filter(
      (observation) =>
        marketMatchesTradingContext(observation, gasDay, deliveryProduct) &&
        (!hubId || observation.hub.toUpperCase() === hubId),
    ),
    [api.normalizedMarkets, deliveryProduct, gasDay, hubId],
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
      selectedResourceId,
    ),
    [contextMarkets, contract, liveMark, portfolioResources, selectedResourceId],
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
  // Three states, not two: a status read that has not answered is not a disconnection, and the
  // copy below may not claim one it has no evidence for.
  const runtimeStore = runtimeStoreStatus(api.runtimeDb);
  const runtimeDbReady = runtimeStore === "ready";
  const optionBlockers = api.resourcePoolOptions?.blockers ?? [];
  // Two gates, one rule (`app/model/decisionActionModel.ts`): the identity's *declared*
  // capability plus the action's actual inputs, and no run of the same action in flight. The
  // profile is the composition `/api/me` returned for this identity; an absent profile fails
  // closed rather than being read as permission. Nothing here is an authority check - the
  // backend re-authorises each request - but it is what keeps a platform administrator from
  // being offered (or automatically issuing) a commercial run the backend will refuse.
  const composition = useMemo(
    () => compositionFromProfile(api.currentUser?.experience),
    [api.currentUser],
  );
  const poolInputReady =
    runtimeDbReady && hasPortfolioResources && saleOptions.length > 0 && optionBlockers.length === 0;
  const poolOptimizeGate = decisionComputeGate("optimize_pool", {
    profileAvailable: composition.available,
    capabilities: composition.effectiveCapabilities,
    inputReady: poolInputReady,
  });
  const routeCompareGate = decisionComputeGate("compare_routes", {
    profileAvailable: composition.available,
    capabilities: composition.effectiveCapabilities,
    inputReady: hasPortfolioResources && saleOptions.length > 0,
  });
  const canRunPoolOptimizer = decisionActionAvailable(poolOptimizeGate, api.poolOptimizeAction);
  const canCompareRoutes = decisionActionAvailable(routeCompareGate, api.routeCompareAction);
  // Each result carries its own provenance lane, so one action's run cannot relabel the
  // other's payload and a failed retry cannot erase a context change.
  const optimizerContextMismatch = decisionResultContextMismatch(
    api.poolOptimizeAction,
    api.resourcePoolResult !== null,
    currentContextKey,
  );
  const routeRecommendationContextMismatch = decisionResultContextMismatch(
    api.routeCompareAction,
    api.routeRecommendation !== null,
    currentContextKey,
  );
  // The Scenario panel's economics may only be derived from results that are current for the
  // context on screen: a payload provenanced to another context is withheld from the selector
  // (it reads "unavailable" and the panel states the mismatch) rather than presented as the
  // economics of the context the trader is standing in.
  const scenarioRouteEconomics = useMemo(
    () => selectScenarioRouteEconomics({
      carriedRouteId: selectedRouteId,
      selectedResourceId,
      routeRecommendation: routeRecommendationContextMismatch ? null : api.routeRecommendation,
      resourcePoolResult: optimizerContextMismatch ? null : api.resourcePoolResult,
      portfolioResources,
      saleOptionById,
    }),
    [
      api.resourcePoolResult,
      api.routeRecommendation,
      optimizerContextMismatch,
      portfolioResources,
      routeRecommendationContextMismatch,
      saleOptionById,
      selectedResourceId,
      selectedRouteId,
    ],
  );
  const strategyContextMismatch =
    api.strategyResult !== null &&
    !resultContextMatches(strategyResultContextKey, { gasDay, deliveryProduct, hubId });
  const poolInputBlockers = useMemo(() => {
    const blockers: string[] = [];
    if (runtimeStore === "unknown") blockers.push(t("home.blocker_runtime_unknown"));
    else if (!runtimeDbReady) blockers.push(t("home.blocker_runtime_db"));
    blockers.push(...(api.resourcePoolOptions?.blockers ?? []));
    return blockers;
  }, [api.resourcePoolOptions, runtimeDbReady, runtimeStore, t]);
  const commercialDiagnostics = useMemo(
    () => buildCommercialDiagnostics({
      poolInputBlockers,
      options: api.resourcePoolOptions,
      optimizer: api.resourcePoolResult,
      recommendation: api.routeRecommendation,
    }),
    [api.resourcePoolOptions, api.resourcePoolResult, api.routeRecommendation, poolInputBlockers],
  );
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
    // The automatic run is the same governed act as the header's: it happens only when the
    // identity's declared capability and the pool's inputs allow it. An identity the backend
    // refuses for commercial data is never sent a request on the user's behalf, so it never
    // logs a 403 for an action nobody chose.
    if (!canRunPoolOptimizer || api.loading) return;
    if (lastAutoOptimizerSignatureRef.current === autoOptimizerSignature) return;
    lastAutoOptimizerSignatureRef.current = autoOptimizerSignature;
    void api.optimizeResourcePool(resourcePoolOptimizationRequest, currentContextKey);
  }, [
    api.loading,
    api.optimizeResourcePool,
    autoOptimizerSignature,
    canRunPoolOptimizer,
    currentContextKey,
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

    reviewWarnings.forEach((warning) => add(t("home.evidence_warning"), warningLabel(warning, t)));
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
    () => resolveNetworkGeometryState(runtimeStore, api.nodes, api.edges),
    [api.edges, api.nodes, runtimeStore],
  );

  function optimizeResourcePoolForCurrentContext() {
    // Refused here for the same reason the control is disabled: an unavailable action must not
    // issue a request, and a second click while one is in flight is the same question.
    if (!canRunPoolOptimizer) return;
    void api.optimizeResourcePool(resourcePoolOptimizationRequest, currentContextKey);
  }

  function recommendRouteAllocationForCurrentContext() {
    if (!canCompareRoutes) return;
    void api.recommendRouteAllocation(routeRecommendationRequest, currentContextKey);
  }

  function evaluateStrategyForCurrentContext(overrides?: {
    risk_control?: Record<string, unknown>;
    bar_minutes?: number;
  }) {
    setStrategyResultContextKey(currentContextKey);
    void api.evaluateStrategyLab({
      ...strategyScenario,
      risk_control: {
        ...(strategyScenario.risk_control ?? {}),
        ...(overrides?.risk_control ?? {}),
      },
      existing_shadow_pnl_gbp: api.strategySummary?.cumulative_pnl_gbp ?? 0,
      components: overrides?.bar_minutes
        ? strategyScenario.components.map((component) => ({
            ...component,
            target_bar_minutes: overrides.bar_minutes,
          }))
        : strategyScenario.components,
    });
  }

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
    strategySummary: api.strategySummary,
    strategyRuns: api.strategyRuns,
    selectedAllocation,
    poolAllocations,
    optimizerContextMismatch,
    routeRecommendationContextMismatch,
    /** Either result displayed by the Scenario panel is stale for the current context. */
    resultsContextMismatch: optimizerContextMismatch || routeRecommendationContextMismatch,
    strategyContextMismatch,
    optimizeResourcePoolForCurrentContext,
    recommendRouteAllocationForCurrentContext,
    evaluateStrategyForCurrentContext,
    firstPoolAllocation,
    decisionPnl,
    decisionMargin,
    salePrice,
    purchasePrice,
    routeCharge,
    scenarioRouteEconomics,
    firstStrategyTarget,
    activeWarning,
    latestCapacityRows,
    reviewWarnings,
    runtimeDbReady,
    canRunPoolOptimizer,
    canCompareRoutes,
    poolOptimizeGate,
    routeCompareGate,
    /** The two governed computes' own lifecycle, rendered next to the action and its result. */
    poolOptimizeAction: api.poolOptimizeAction,
    routeCompareAction: api.routeCompareAction,
    poolInputBlockers,
    commercialDiagnostics,
    resourcePoolMapPaths,
    highlightedRoute,
    reviewEvidenceItems,
    networkGeometryState,
  };
}
