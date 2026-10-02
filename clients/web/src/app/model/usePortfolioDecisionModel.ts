import { useEffect, useMemo, useRef, useState } from "react";
import type { TFunction } from "i18next";
import { warningLabel } from "@/app/warningLabel";
import {
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
import {
  decisionInputIdentity,
  decisionProvenanceKey,
  decisionProvenanceMismatch,
} from "@/app/model/decisionResultProvenance";
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
  // Null when the draft's annual financing rate is unknown and no saved contract rate applies:
  // the optimiser action then has no valid input and is gated closed rather than run with an
  // invented 0% rate (`buildResourcePoolOptimizationRequest`).
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

  /**
   * The provenance key a run is stamped with: which act, the trading context, and the canonical
   * identity of the caller-known inputs the request was composed from
   * (`app/model/decisionResultProvenance.ts`). A saved-contract revision, a refreshed pool read,
   * a moved market mark or the financing input changes the key, so a result that lands afterwards
   * stays stale instead of being relabelled current; a draft field no request consumes changes
   * nothing. The two governed actions carry distinct keys because their requests consume
   * different inputs.
   */
  const optimizerProvenanceKey = useMemo(
    () =>
      resourcePoolOptimizationRequest === null
        ? null
        : decisionProvenanceKey(
            "optimize_pool",
            currentContextKey,
            decisionInputIdentity({
              request: resourcePoolOptimizationRequest,
              savedContracts: api.upstreamContracts,
              marketReads: saleOptions,
            }),
          ),
    [api.upstreamContracts, currentContextKey, resourcePoolOptimizationRequest, saleOptions],
  );
  const compareProvenanceKey = useMemo(
    () =>
      decisionProvenanceKey(
        "compare_routes",
        currentContextKey,
        decisionInputIdentity({
          request: routeRecommendationRequest,
          savedContracts: api.upstreamContracts,
          marketReads: saleOptions,
        }),
      ),
    [api.upstreamContracts, currentContextKey, routeRecommendationRequest, saleOptions],
  );
  /**
   * The strategy evaluation request as it will actually be sent (the scenario plus the shadow
   * PnL the run continues from). Its identity is built from this payload, so a contract
   * revision, pool read or market observation change invalidates a shown strategy result too.
  */
  function strategyEvaluationPayload(overrides?: {
    risk_control?: Record<string, unknown>;
    bar_minutes?: number;
  }) {
    return {
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
    };
  }
  /**
   * The current key is composed from the *default* payload (`strategyEvaluationPayload()`).
   *
   * An evaluation started with overrides sends a payload this key does not describe: it is
   * stamped with the identity of the payload actually sent, so a successful overridden run does
   * not match and is withheld as stale (`currentStrategyResult` null) rather than presented as
   * the default payload's result. That is the conservative posture, not an equivalence claim -
   * the overridden and default payloads are different requests - and no surface in this build
   * calls the evaluation with overrides.
   */
  const strategyProvenanceKey = useMemo(
    () =>
      decisionProvenanceKey(
        "strategy_evaluation",
        currentContextKey,
        decisionInputIdentity({
          request: strategyEvaluationPayload(),
          savedContracts: api.upstreamContracts,
        }),
      ),
    [api.strategySummary, api.upstreamContracts, currentContextKey, strategyScenario],
  );
  // Each result carries its own provenance lane, so one action's run cannot relabel the other's
  // payload and a failed retry cannot erase a context or input change. One rule decides
  // staleness (`decisionProvenanceMismatch`): a held result is current only while its key equals
  // the key of the inputs the caller now knows.
  const optimizerContextMismatch = decisionResultContextMismatch(
    api.poolOptimizeAction,
    api.resourcePoolResult !== null,
    optimizerProvenanceKey,
  );
  const routeRecommendationContextMismatch = decisionResultContextMismatch(
    api.routeCompareAction,
    api.routeRecommendation !== null,
    compareProvenanceKey,
  );
  const strategyContextMismatch = decisionProvenanceMismatch(
    api.strategyResult !== null,
    strategyResultContextKey,
    strategyProvenanceKey,
  );
  // The one derived posture every consumer reads: a payload whose provenance is not the caller's
  // current inputs is withheld from current metrics - never substituted with 0 - and the surface
  // states that it is stale. The scenario selector, the map's decision rail, the Portfolio PnL
  // strip, the Review evidence pack and the warning lists read these values, not the raw lanes.
  const currentResourcePoolResult = optimizerContextMismatch ? null : api.resourcePoolResult;
  const currentRouteRecommendation = routeRecommendationContextMismatch
    ? null
    : api.routeRecommendation;
  const currentStrategyResult = strategyContextMismatch ? null : api.strategyResult;

  const selectedAllocation = currentRouteRecommendation?.allocations[0] ?? null;
  const poolAllocations = currentResourcePoolResult?.allocations ?? [];
  const firstPoolAllocation = poolAllocations[0] ?? null;
  const firstPortfolioResource = portfolioResources[0] ?? null;
  const firstAllocationOption = firstPoolAllocation
    ? saleOptionById.get(firstPoolAllocation.option_id)
    : null;
  const rawDecisionPnl =
    currentResourcePoolResult?.total_net_pnl_gbp_per_day ??
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
  const firstStrategyTarget = currentStrategyResult?.allocation_targets[0];
  const activeWarning = [
    ...(currentStrategyResult?.warnings ?? []),
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
      currentResourcePoolResult,
      currentRouteRecommendation,
      currentStrategyResult,
      api.analysisResult,
      api.meta,
    ),
    [
      api.analysisResult,
      api.meta,
      currentResourcePoolResult,
      currentRouteRecommendation,
      currentStrategyResult,
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
    runtimeDbReady &&
    hasPortfolioResources &&
    saleOptions.length > 0 &&
    optionBlockers.length === 0 &&
    resourcePoolOptimizationRequest !== null;
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
  // The Scenario panel's economics may only be derived from results that are current for the
  // inputs on screen: a payload with another provenance is withheld from the selector (it reads
  // "unavailable" and the panel states the mismatch) rather than presented as this context's
  // economics.
  const scenarioRouteEconomics = useMemo(
    () => selectScenarioRouteEconomics({
      carriedRouteId: selectedRouteId,
      selectedResourceId,
      routeRecommendation: currentRouteRecommendation,
      resourcePoolResult: currentResourcePoolResult,
      portfolioResources,
      saleOptionById,
    }),
    [
      currentResourcePoolResult,
      currentRouteRecommendation,
      portfolioResources,
      saleOptionById,
      selectedResourceId,
      selectedRouteId,
    ],
  );
  const poolInputBlockers = useMemo(() => {
    const blockers: string[] = [];
    if (runtimeStore === "unknown") blockers.push(t("home.blocker_runtime_unknown"));
    else if (!runtimeDbReady) blockers.push(t("home.blocker_runtime_db"));
    blockers.push(...(api.resourcePoolOptions?.blockers ?? []));
    // One governed input is the draft's own financing-rate fallback: while neither the draft nor
    // a saved contract records a rate, the optimiser has no request to send and says so here
    // instead of calculating an early-cash term from a rate nobody entered.
    if (resourcePoolOptimizationRequest === null) blockers.push(t("scenario.financing_rate_unknown"));
    return blockers;
  }, [api.resourcePoolOptions, resourcePoolOptimizationRequest, runtimeDbReady, runtimeStore, t]);
  const commercialDiagnostics = useMemo(
    () => buildCommercialDiagnostics({
      poolInputBlockers,
      options: api.resourcePoolOptions,
      optimizer: currentResourcePoolResult,
      recommendation: currentRouteRecommendation,
    }),
    [
      api.resourcePoolOptions,
      currentResourcePoolResult,
      currentRouteRecommendation,
      poolInputBlockers,
    ],
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
      financingRate: resourcePoolOptimizationRequest?.annual_financing_rate_pct ?? null,
    }),
    [portfolioResources, resourcePoolOptimizationRequest, saleOptions],
  );

  useEffect(() => {
    // The automatic run is the same governed act as the header's: it happens only when the
    // identity's declared capability and the pool's inputs allow it. An identity the backend
    // refuses for commercial data is never sent a request on the user's behalf, so it never
    // logs a 403 for an action nobody chose.
    if (!canRunPoolOptimizer || api.loading || resourcePoolOptimizationRequest === null) return;
    // The key the run is requested under, not the trading context alone: if this changes while
    // the run is in flight, the answer is committed with the old key and reads stale.
    if (optimizerProvenanceKey === null) return;
    if (lastAutoOptimizerSignatureRef.current === autoOptimizerSignature) return;
    lastAutoOptimizerSignatureRef.current = autoOptimizerSignature;
    void api.optimizeResourcePool(resourcePoolOptimizationRequest, optimizerProvenanceKey);
  }, [
    api.loading,
    api.optimizeResourcePool,
    autoOptimizerSignature,
    canRunPoolOptimizer,
    optimizerProvenanceKey,
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
    (currentResourcePoolResult?.missing_inputs ?? []).forEach(
      (input) => add(t("home.evidence_missing_input"), input),
    );
    (currentRouteRecommendation?.assumptions ?? []).forEach(
      (assumption) => add(t("home.evidence_assumption"), assumption),
    );
    [
      ...(currentResourcePoolResult?.source_refs ?? []),
      ...(api.meta?.source_references ?? []),
      ...Object.values(api.endpointMeta).flatMap((item) => item.source_references ?? []),
    ].forEach((sourceRef) => add(t("home.evidence_source"), sourceRef));

    return items.slice(0, 6);
  }, [
    api.endpointMeta,
    api.meta,
    currentResourcePoolResult,
    currentRouteRecommendation,
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
    if (!canRunPoolOptimizer || resourcePoolOptimizationRequest === null) return;
    if (optimizerProvenanceKey === null) return;
    void api.optimizeResourcePool(resourcePoolOptimizationRequest, optimizerProvenanceKey);
  }

  function recommendRouteAllocationForCurrentContext() {
    if (!canCompareRoutes) return;
    void api.recommendRouteAllocation(routeRecommendationRequest, compareProvenanceKey);
  }

  function evaluateStrategyForCurrentContext(overrides?: {
    risk_control?: Record<string, unknown>;
    bar_minutes?: number;
  }) {
    // `overrides` are stamped with the identity of the payload actually sent; that differs from
    // the model's default-payload current key, so an overridden run is withheld as stale by the
    // rule above instead of being relabelled current (no equivalence is claimed).
    const payload = strategyEvaluationPayload(overrides);
    const provenanceKey = decisionProvenanceKey(
      "strategy_evaluation",
      currentContextKey,
      decisionInputIdentity({
        request: payload,
        savedContracts: api.upstreamContracts,
      }),
    );
    void api.evaluateStrategyLab(payload).then((completed) => {
      // Stamped only by a run that actually produced a result: a refused or failed evaluation
      // leaves the previous result and its own provenance key in place.
      if (completed) setStrategyResultContextKey(provenanceKey);
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
    /** Either governed result the surfaces display is stale for the current inputs. */
    resultsContextMismatch: optimizerContextMismatch || routeRecommendationContextMismatch,
    strategyContextMismatch,
    /**
     * The one provenance gate every consumer reads: each is null while the held payload was not
     * computed from the inputs the caller now knows, so stale economics are withheld rather than
     * relabelled current or replaced with 0.
     */
    currentResourcePoolResult,
    currentRouteRecommendation,
    currentStrategyResult,
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
