import { create } from "zustand";
import {
  api,
  AnalysisRequestDTO,
  AnalysisResultDTO,
  ApiMeta,
  CapacityObsDTO,
  CredentialProviderDTO,
  EdgeDTO,
  FlowObsDTO,
  FxRateDTO,
  GlossaryTermDTO,
  GlossaryContextDTO,
  LngObsDTO,
  IntradayOpportunityDTO,
  MarketQuoteDTO,
  MarketSpreadDTO,
  MonitoringAlertDTO,
  MonitoringAnalysisDTO,
  MonitoringSummaryDTO,
  NodeDTO,
  NormalizedMarketObsDTO,
  PipelineHealthDTO,
  PortfolioLiveSummaryDTO,
  PortfolioOptimizationRequestDTO,
  PortfolioOptimizationResultDTO,
  PortfolioPnlSnapshotDTO,
  ResourcePoolOptionsDTO,
  ReviewDecisionDTO,
  ReviewDecisionInputDTO,
  RouteRecommendationRequestDTO,
  RouteRecommendationResultDTO,
  RouteCandidateDTO,
  RouteEligibilityDTO,
  RuntimeDbStatusDTO,
  ScreenOrderObservationDTO,
  SourceSystemDTO,
  StrategyLabRequestDTO,
  StrategyLabResultDTO,
  StrategyRunDTO,
  StrategySummaryDTO,
  StorageObsDTO,
  TsoAccessPointDTO,
  TsoTariffDTO,
  UpstreamContractDTO,
  UpstreamContractInputDTO,
  openEventStream,
} from "@/api/client";

let decisionStreamClosers: Array<() => void> = [];
let marketRefreshSequence = 0;

function timestampMs(value: string): number {
  const parsed = Date.parse(value);
  return Number.isNaN(parsed) ? 0 : parsed;
}

function latestTimestamp(values: Array<string | null | undefined>): string | null {
  const latestTimestampMs = values.reduce<number>(
    (latest, value) => Math.max(latest, value ? timestampMs(value) : 0),
    0,
  );
  return latestTimestampMs > 0 ? new Date(latestTimestampMs).toISOString() : null;
}

function closeDecisionStreams() {
  decisionStreamClosers.forEach((close) => close());
  decisionStreamClosers = [];
}

function mergeMarketQuotes(
  current: MarketQuoteDTO[],
  incoming: MarketQuoteDTO[],
): MarketQuoteDTO[] {
  const byId = new Map(current.map((quote) => [quote.quote_id, quote]));
  incoming.forEach((quote) => {
    const existing = byId.get(quote.quote_id);
    if (!existing || timestampMs(quote.observed_at_utc) >= timestampMs(existing.observed_at_utc)) {
      byId.set(quote.quote_id, quote);
    }
  });
  return Array.from(byId.values())
    .sort((left, right) => timestampMs(right.observed_at_utc) - timestampMs(left.observed_at_utc))
    .slice(0, 500);
}

function mergeIntradayOpportunities(
  current: IntradayOpportunityDTO[],
  incoming: IntradayOpportunityDTO[],
): IntradayOpportunityDTO[] {
  const byId = new Map(current.map((item) => [item.opportunity_id, item]));
  incoming.forEach((item) => {
    const existing = byId.get(item.opportunity_id);
    if (!existing || timestampMs(item.detected_at_utc) >= timestampMs(existing.detected_at_utc)) {
      byId.set(item.opportunity_id, item);
    }
  });
  return Array.from(byId.values())
    .sort((left, right) => timestampMs(right.detected_at_utc) - timestampMs(left.detected_at_utc))
    .slice(0, 100);
}

function latestMarketObservedAt(
  normalizedMarkets: NormalizedMarketObsDTO[],
  marketQuotes: MarketQuoteDTO[],
  fxRates: FxRateDTO[],
): string | null {
  const timestamps = [
    ...normalizedMarkets.map((row) => row.observed_at_utc),
    ...marketQuotes.map((row) => row.observed_at_utc),
    ...fxRates.map((row) => row.observed_at_utc),
  ].filter((value): value is string => Boolean(value));
  return latestTimestamp(timestamps);
}

export interface ApiState {
  nodes: NodeDTO[];
  edges: EdgeDTO[];
  sources: SourceSystemDTO[];
  normalizedMarkets: NormalizedMarketObsDTO[];
  marketSpreads: MarketSpreadDTO[];
  marketQuotes: MarketQuoteDTO[];
  intradayOpportunities: IntradayOpportunityDTO[];
  screenOrders: ScreenOrderObservationDTO[];
  pnlSnapshots: PortfolioPnlSnapshotDTO[];
  portfolioSummary: PortfolioLiveSummaryDTO | null;
  fxRates: FxRateDTO[];
  flows: FlowObsDTO[];
  capacity: CapacityObsDTO[];
  storage: StorageObsDTO[];
  lng: LngObsDTO[];
  tsoAccess: TsoAccessPointDTO[];
  routes: RouteEligibilityDTO[];
  routeCandidates: RouteCandidateDTO[];
  tsoTariffs: TsoTariffDTO[];
  upstreamContracts: UpstreamContractDTO[];
  resourcePoolOptions: ResourcePoolOptionsDTO | null;
  routeRecommendation: RouteRecommendationResultDTO | null;
  resourcePoolResult: PortfolioOptimizationResultDTO | null;
  strategyResult: StrategyLabResultDTO | null;
  strategyRuns: StrategyRunDTO[];
  strategySummary: StrategySummaryDTO | null;
  reviewDecisions: ReviewDecisionDTO[];
  reviewMessage: string | null;
  glossaryTerms: GlossaryTermDTO[];
  glossaryContext: GlossaryContextDTO | null;
  analysisResult: AnalysisResultDTO | null;
  credentialProviders: CredentialProviderDTO[];
  monitoringAlerts: MonitoringAlertDTO[];
  monitoringSummary: MonitoringSummaryDTO;
  monitoringAnalysisByAlert: Record<string, MonitoringAnalysisDTO>;
  monitoringBusyAlertId: string | null;
  runtimeDb: RuntimeDbStatusDTO | null;
  pipelineHealth: PipelineHealthDTO | null;
  endpointMeta: Record<string, ApiMeta>;
  endpointErrors: Record<string, string>;
  meta: ApiMeta | null;
  marketLastUpdatedAtUtc: string | null;
  loading: boolean;
  streamingActive: boolean;
  error: string | null;
  credentialMessage: string | null;
  contractSaveMessage: string | null;
  dataStatus: "runtime" | "delayed" | "partial" | "unavailable";
  fetchWorkspace: () => Promise<void>;
  retryFailedWorkspaceEndpoints: () => Promise<void>;
  refreshMarketData: () => Promise<void>;
  subscribeDecisionStreams: () => void;
  refreshMonitoring: () => Promise<void>;
  saveProviderCredential: (providerId: string, apiKey: string, label: string) => Promise<void>;
  testProviderConnection: (providerId: string) => Promise<void>;
  acknowledgeMonitoringAlert: (alertId: string) => Promise<void>;
  analyzeMonitoringAlert: (
    alertId: string,
    question: string,
    language: "en" | "zh-CN",
  ) => Promise<void>;
  saveDraftContract: (contract: UpstreamContractInputDTO) => Promise<void>;
  recordReviewDecision: (body: ReviewDecisionInputDTO) => Promise<void>;
  recommendRouteAllocation: (request: RouteRecommendationRequestDTO) => Promise<void>;
  optimizeResourcePool: (request: PortfolioOptimizationRequestDTO) => Promise<void>;
  evaluateStrategyLab: (scenario: StrategyLabRequestDTO) => Promise<void>;
  fetchStrategySummary: () => Promise<void>;
  fetchStrategyRuns: () => Promise<void>;
  fetchGlossaryContext: (
    term: string,
    params?: { lang?: string; duration_start_utc?: string; duration_end_utc?: string },
  ) => Promise<void>;
  askAnalysis: (body: AnalysisRequestDTO) => Promise<void>;
  generatePortfolioReport: (body: AnalysisRequestDTO) => Promise<void>;
}

const DEFAULT_STRATEGY_ID = "nbp-sap-icis-ocm-window";

function withoutLegacyFlag<T extends object>(body: T): T {
  const payload = { ...body } as Record<string, unknown>;
  delete payload["research" + "_only"];
  return payload as T;
}

// ---------------------------------------------------------------------------
// Independent endpoint loading (audit item: "29 个请求 Promise.all，任一 503
// 拖垮整个工作区"). Each endpoint loads with its own retry; failures are
// recorded per endpoint and can be retried without reloading the workspace.
// ---------------------------------------------------------------------------

type LoaderOutcome<T> = { ok: true; value: T } | { ok: false; error: string };

async function loadEndpointWithRetry<T>(
  loader: () => Promise<T>,
  retries = 1,
): Promise<LoaderOutcome<T>> {
  for (let attempt = 0; ; attempt += 1) {
    try {
      return { ok: true, value: await loader() };
    } catch (error) {
      if (attempt >= retries) return { ok: false, error: String(error) };
      await new Promise((resolve) => setTimeout(resolve, 250 * (attempt + 1)));
    }
  }
}

/** endpointMeta key -> loader. Keys keep the historical endpointMeta names. */
const WORKSPACE_LOADERS: Array<[string, () => Promise<{ data: unknown; meta: ApiMeta }>]> = [
  ["referenceNodes", api.nodes],
  ["referenceEdges", api.edges],
  ["sources", api.sources],
  ["normalizedMarkets", api.normalizedMarketObservations],
  ["marketSpreads", api.marketSpreads],
  ["marketQuotes", api.marketQuotes],
  ["intradayOpportunities", api.intradayOpportunities],
  ["screenOrders", api.screenOrders],
  ["pnlSnapshots", api.pnlSnapshots],
  ["portfolioSummary", api.portfolioLiveSummary],
  ["fxRates", api.fxRates],
  ["flows", api.flowObservations],
  ["capacity", api.capacityObservations],
  ["storage", api.storageObservations],
  ["lng", api.lngObservations],
  ["tsoAccess", api.tsoAccess],
  ["routes", api.routeEligibility],
  ["routeCandidates", api.routeCandidates],
  ["tsoTariffs", api.tsoTariffs],
  ["upstreamContracts", api.upstreamContracts],
  ["resourcePoolOptions", api.resourcePoolOptions],
  ["glossaryTerms", () => api.glossary("en")],
  ["runtimeDb", api.runtimeDb],
  ["credentialProviders", api.credentialProviders],
  ["monitoringAlerts", api.monitoringAlerts],
  ["monitoringSummary", api.monitoringSummary],
  ["reviewDecisions", api.reviewDecisions],
  ["pipelineHealth", api.pipelineHealth],
];

/** endpointMeta key -> ApiState slice key. */
const WORKSPACE_STATE_KEYS: Record<string, keyof ApiState> = {
  referenceNodes: "nodes",
  referenceEdges: "edges",
  sources: "sources",
  normalizedMarkets: "normalizedMarkets",
  marketSpreads: "marketSpreads",
  marketQuotes: "marketQuotes",
  intradayOpportunities: "intradayOpportunities",
  screenOrders: "screenOrders",
  pnlSnapshots: "pnlSnapshots",
  portfolioSummary: "portfolioSummary",
  fxRates: "fxRates",
  flows: "flows",
  capacity: "capacity",
  storage: "storage",
  lng: "lng",
  tsoAccess: "tsoAccess",
  routes: "routes",
  routeCandidates: "routeCandidates",
  tsoTariffs: "tsoTariffs",
  upstreamContracts: "upstreamContracts",
  resourcePoolOptions: "resourcePoolOptions",
  glossaryTerms: "glossaryTerms",
  runtimeDb: "runtimeDb",
  credentialProviders: "credentialProviders",
  monitoringAlerts: "monitoringAlerts",
  monitoringSummary: "monitoringSummary",
  reviewDecisions: "reviewDecisions",
  pipelineHealth: "pipelineHealth",
};

function deriveWorkspaceSlice(key: string, response: { data: unknown }): unknown {
  if (key === "routeCandidates") {
    return (response.data as { route_candidates: unknown }).route_candidates;
  }
  if (key === "tsoTariffs") {
    return (response.data as { tariffs: unknown }).tariffs;
  }
  return response.data;
}

const DEFAULT_MONITORING_SUMMARY = {
  open_count: 0,
  acknowledged_count: 0,
  critical_count: 0,
  warning_count: 0,
  info_count: 0,
  llm_pending_count: 0,
  simulated_count: 0,
};

export const useApiStore = create<ApiState>((set, get) => ({
  nodes: [],
  edges: [],
  sources: [],
  normalizedMarkets: [],
  marketSpreads: [],
  marketQuotes: [],
  intradayOpportunities: [],
  screenOrders: [],
  pnlSnapshots: [],
  portfolioSummary: null,
  fxRates: [],
  flows: [],
  capacity: [],
  storage: [],
  lng: [],
  tsoAccess: [],
  routes: [],
  routeCandidates: [],
  tsoTariffs: [],
  upstreamContracts: [],
  resourcePoolOptions: null,
  routeRecommendation: null,
  resourcePoolResult: null,
  strategyResult: null,
  strategyRuns: [],
  strategySummary: null,
  reviewDecisions: [],
  reviewMessage: null,
  glossaryTerms: [],
  glossaryContext: null,
  analysisResult: null,
  credentialProviders: [],
  monitoringAlerts: [],
  monitoringSummary: {
    open_count: 0,
    acknowledged_count: 0,
    critical_count: 0,
    warning_count: 0,
    info_count: 0,
    llm_pending_count: 0,
    simulated_count: 0,
  },
  monitoringAnalysisByAlert: {},
  monitoringBusyAlertId: null,
  runtimeDb: null,
  pipelineHealth: null,
  endpointMeta: {},
  endpointErrors: {},
  meta: null,
  marketLastUpdatedAtUtc: null,
  loading: false,
  streamingActive: false,
  error: null,
  credentialMessage: null,
  contractSaveMessage: null,
  dataStatus: "unavailable",

  fetchWorkspace: async () => {
    set({ loading: true, error: null });
    const outcomes = await Promise.all(
      WORKSPACE_LOADERS.map(async ([key, loader]) => ({
        key,
        outcome: await loadEndpointWithRetry(loader),
      })),
    );
    const endpointErrors: Record<string, string> = {};
    const endpointMeta: Record<string, ApiMeta> = {};
    const slices: Record<string, unknown> = {};
    for (const { key, outcome } of outcomes) {
      if (outcome.ok) {
        endpointMeta[key] = outcome.value.meta;
        slices[key] = deriveWorkspaceSlice(key, outcome.value);
      } else {
        endpointErrors[key] = outcome.error;
      }
    }
    const sourceRefs = Object.values(endpointMeta).flatMap((item) => item.source_references ?? []);
    const hasRuntime = sourceRefs.some((source) => source === "runtime-postgresql");
    const hasDbMissing = sourceRefs.some((source) => source === "runtime-db-not-configured");
    const runtimeDb = slices.runtimeDb as RuntimeDbStatusDTO | undefined;
    const allFailed = Object.keys(endpointErrors).length === WORKSPACE_LOADERS.length;
    const resolvedStatus =
      !runtimeDb || !runtimeDb.database_url_present || !runtimeDb.connectivity.ok
        ? "unavailable"
        : hasRuntime && hasDbMissing
          ? "partial"
          : hasRuntime
            ? "runtime"
            : "partial";

    set({
      nodes: (slices.referenceNodes ?? []) as NodeDTO[],
      edges: (slices.referenceEdges ?? []) as EdgeDTO[],
      sources: (slices.sources ?? []) as SourceSystemDTO[],
      normalizedMarkets: (slices.normalizedMarkets ?? []) as NormalizedMarketObsDTO[],
      marketSpreads: (slices.marketSpreads ?? []) as MarketSpreadDTO[],
      marketQuotes: (slices.marketQuotes ?? []) as MarketQuoteDTO[],
      intradayOpportunities: (slices.intradayOpportunities ?? []) as IntradayOpportunityDTO[],
      screenOrders: (slices.screenOrders ?? []) as ScreenOrderObservationDTO[],
      pnlSnapshots: (slices.pnlSnapshots ?? []) as PortfolioPnlSnapshotDTO[],
      portfolioSummary: (slices.portfolioSummary ?? null) as PortfolioLiveSummaryDTO | null,
      fxRates: (slices.fxRates ?? []) as FxRateDTO[],
      flows: (slices.flows ?? []) as FlowObsDTO[],
      capacity: (slices.capacity ?? []) as CapacityObsDTO[],
      storage: (slices.storage ?? []) as StorageObsDTO[],
      lng: (slices.lng ?? []) as LngObsDTO[],
      tsoAccess: (slices.tsoAccess ?? []) as TsoAccessPointDTO[],
      routes: (slices.routes ?? []) as RouteEligibilityDTO[],
      routeCandidates: (slices.routeCandidates ?? []) as RouteCandidateDTO[],
      tsoTariffs: (slices.tsoTariffs ?? []) as TsoTariffDTO[],
      upstreamContracts: (slices.upstreamContracts ?? []) as UpstreamContractDTO[],
      resourcePoolOptions: (slices.resourcePoolOptions ?? null) as ResourcePoolOptionsDTO | null,
      glossaryTerms: (slices.glossaryTerms ?? []) as GlossaryTermDTO[],
      runtimeDb: (slices.runtimeDb ?? null) as RuntimeDbStatusDTO | null,
      credentialProviders: (slices.credentialProviders ?? []) as CredentialProviderDTO[],
      monitoringAlerts: (slices.monitoringAlerts ?? []) as MonitoringAlertDTO[],
      monitoringSummary: (slices.monitoringSummary ?? DEFAULT_MONITORING_SUMMARY) as MonitoringSummaryDTO,
      reviewDecisions: (slices.reviewDecisions ?? []) as ReviewDecisionDTO[],
      pipelineHealth: (slices.pipelineHealth ?? null) as PipelineHealthDTO | null,
      endpointMeta,
      endpointErrors,
      meta: endpointMeta.referenceNodes ?? null,
      marketLastUpdatedAtUtc: latestMarketObservedAt(
        (slices.normalizedMarkets ?? []) as NormalizedMarketObsDTO[],
        (slices.marketQuotes ?? []) as MarketQuoteDTO[],
        (slices.fxRates ?? []) as FxRateDTO[],
      ),
      dataStatus: resolvedStatus,
      loading: false,
      error: allFailed
        ? `All workspace endpoints failed: ${Object.keys(endpointErrors).join(", ")}`
        : null,
    });
    void get().fetchStrategySummary();
    void get().fetchStrategyRuns();
    get().subscribeDecisionStreams();
  },

  retryFailedWorkspaceEndpoints: async () => {
    const failedKeys = Object.keys(get().endpointErrors);
    if (failedKeys.length === 0) return;
    const loaderByKey = new Map(WORKSPACE_LOADERS);
    const outcomes = await Promise.all(
      failedKeys.map(async (key) => ({
        key,
        outcome: await loadEndpointWithRetry(loaderByKey.get(key) as () => Promise<{ data: unknown; meta: ApiMeta }>),
      })),
    );
    set((state) => {
      const endpointErrors = { ...state.endpointErrors };
      const endpointMeta = { ...state.endpointMeta };
      const patch: Partial<ApiState> = {};
      for (const { key, outcome } of outcomes) {
        if (outcome.ok) {
          delete endpointErrors[key];
          endpointMeta[key] = outcome.value.meta;
          const stateKey = WORKSPACE_STATE_KEYS[key];
          if (stateKey) {
            (patch as Record<string, unknown>)[stateKey] = deriveWorkspaceSlice(key, outcome.value);
          }
        }
      }
      return {
        ...patch,
        endpointErrors,
        endpointMeta,
        error: Object.keys(endpointErrors).length === 0 ? null : state.error,
        loading: false,
      };
    });
  },

  refreshMarketData: async () => {
    const refreshSequence = ++marketRefreshSequence;
    // Market board data must not wait on the slower /api/sources diagnostic
    // endpoint. Update source posture in the background after live prices land.
    void api.sources()
      .then((sources) => {
        if (refreshSequence !== marketRefreshSequence) return;
        set((state) => ({
          sources: sources.data,
          endpointMeta: {
            ...state.endpointMeta,
            sources: sources.meta,
          },
        }));
      })
      .catch(() => undefined);
    const [normalizedResult, spreadResult, quoteResult, opportunityResult, fxResult] =
      await Promise.all([
        loadEndpointWithRetry(api.normalizedMarketObservations, 0),
        loadEndpointWithRetry(api.marketSpreads, 0),
        loadEndpointWithRetry(api.marketQuotes, 0),
        loadEndpointWithRetry(api.intradayOpportunities, 0),
        loadEndpointWithRetry(api.fxRates, 0),
      ]);
    if (refreshSequence !== marketRefreshSequence) return;

    set((state) => {
      const endpointMeta = { ...state.endpointMeta };
      const endpointErrors = { ...state.endpointErrors };
      const recordOutcome = (
        key: string,
        outcome: LoaderOutcome<{ data: unknown; meta: ApiMeta }>,
      ) => {
        if (outcome.ok) {
          endpointMeta[key] = outcome.value.meta;
          delete endpointErrors[key];
        } else {
          endpointErrors[key] = outcome.error;
        }
      };
      recordOutcome("normalizedMarkets", normalizedResult);
      recordOutcome("marketSpreads", spreadResult);
      recordOutcome("marketQuotes", quoteResult);
      recordOutcome("intradayOpportunities", opportunityResult);
      recordOutcome("fxRates", fxResult);

      const normalizedMarkets = normalizedResult.ok
        ? normalizedResult.value.data
        : state.normalizedMarkets;
      const marketSpreads = spreadResult.ok
        ? spreadResult.value.data
        : state.marketSpreads;
      const marketQuotes = quoteResult.ok
        ? mergeMarketQuotes(state.marketQuotes, quoteResult.value.data)
        : state.marketQuotes;
      const intradayOpportunities = opportunityResult.ok
        ? mergeIntradayOpportunities(
          state.intradayOpportunities,
          opportunityResult.value.data,
        )
        : state.intradayOpportunities;
      const fxRates = fxResult.ok ? fxResult.value.data : state.fxRates;
      const failedMarketEndpoints = [
        "normalizedMarkets",
        "marketSpreads",
        "marketQuotes",
        "intradayOpportunities",
        "fxRates",
      ].filter((key) => endpointErrors[key]);

      return {
        normalizedMarkets,
        marketSpreads,
        marketQuotes,
        intradayOpportunities,
        fxRates,
        endpointMeta,
        endpointErrors,
        meta: normalizedResult.ok ? normalizedResult.value.meta : state.meta,
        marketLastUpdatedAtUtc: latestMarketObservedAt(
          normalizedMarkets,
          marketQuotes,
          fxRates,
        ),
        error: failedMarketEndpoints.length > 0
          ? `Market refresh partial: ${failedMarketEndpoints.join(", ")}`
          : null,
      };
    });
  },

  subscribeDecisionStreams: () => {
    closeDecisionStreams();
    const onStatus = (status: "open" | "error") =>
      set({ streamingActive: status === "open" });

    decisionStreamClosers.push(
      openEventStream(
        "/stream/quotes",
        {
          quotes: (payload) => {
            const quote = payload as MarketQuoteDTO;
            if (!quote || typeof quote !== "object" || !("quote_id" in quote)) return;
            set((state) => ({
              marketQuotes: mergeMarketQuotes(state.marketQuotes, [quote]),
              marketLastUpdatedAtUtc: latestTimestamp([
                state.marketLastUpdatedAtUtc,
                quote.observed_at_utc,
              ]),
            }));
          },
        },
        onStatus,
      ).close,
    );

    decisionStreamClosers.push(
      openEventStream("/stream/opportunities", {
        opportunities: (payload) => {
          const opportunity = payload as IntradayOpportunityDTO;
          if (
            !opportunity ||
            typeof opportunity !== "object" ||
            !("opportunity_id" in opportunity)
          ) {
            return;
          }
          set((state) => ({
            intradayOpportunities: mergeIntradayOpportunities(
              state.intradayOpportunities,
              [opportunity],
            ),
          }));
        },
      }).close,
    );

    decisionStreamClosers.push(
      openEventStream("/stream/alerts", {
        alerts: (payload) => {
          const alert = payload as MonitoringAlertDTO;
          if (!alert || typeof alert !== "object" || !("alert_id" in alert)) return;
          set((state) => ({
            monitoringAlerts: [
              alert,
              ...state.monitoringAlerts.filter((item) => item.alert_id !== alert.alert_id),
            ],
          }));
        },
      }).close,
    );
  },

  refreshMonitoring: async () => {
    try {
      const [alerts, summary, health] = await Promise.all([
        api.monitoringAlerts(),
        api.monitoringSummary(),
        api.pipelineHealth(),
      ]);
      set((state) => ({
        monitoringAlerts: alerts.data,
        monitoringSummary: summary.data,
        pipelineHealth: health.data,
        endpointMeta: {
          ...state.endpointMeta,
          monitoringAlerts: alerts.meta,
          monitoringSummary: summary.meta,
          pipelineHealth: health.meta,
        },
      }));
    } catch (e) {
      set({ error: String(e) });
    }
  },

  saveProviderCredential: async (providerId, apiKey, label) => {
    set({ credentialMessage: null });
    try {
      await api.saveCredential(providerId, { api_key: apiKey, label });
      const credentialProviders = await api.credentialProviders();
      set({
        credentialProviders: credentialProviders.data,
        credentialMessage: `${providerId} credential saved.`,
      });
    } catch (e) {
      set({ credentialMessage: String(e) });
    }
  },

  testProviderConnection: async (providerId) => {
    set({ credentialMessage: null });
    try {
      const result = await api.testCredentialConnection(providerId);
      const credentialProviders = await api.credentialProviders();
      set({
        credentialProviders: credentialProviders.data,
        credentialMessage: result.data.connection_status === "success"
          ? `${providerId} live connection passed.`
          : `${providerId} live connection failed: ${result.data.connection_error_code ?? result.data.connection_status}`,
      });
    } catch (e) {
      set({ credentialMessage: String(e) });
      throw e;
    }
  },

  acknowledgeMonitoringAlert: async (alertId) => {
    set({ monitoringBusyAlertId: alertId });
    try {
      await api.acknowledgeMonitoringAlert(alertId);
      const [alerts, summary] = await Promise.all([
        api.monitoringAlerts(),
        api.monitoringSummary(),
      ]);
      set({
        monitoringAlerts: alerts.data,
        monitoringSummary: summary.data,
        monitoringBusyAlertId: null,
      });
    } catch (e) {
      set({ error: String(e), monitoringBusyAlertId: null });
    }
  },

  analyzeMonitoringAlert: async (alertId, question, language) => {
    set({ monitoringBusyAlertId: alertId });
    try {
      const result = await api.analyzeMonitoringAlert(alertId, {
        question,
        language,
        model: "deepseek-v4-flash",
      });
      set((state) => ({
        monitoringAnalysisByAlert: {
          ...state.monitoringAnalysisByAlert,
          [alertId]: result.data,
        },
        monitoringBusyAlertId: null,
      }));
    } catch (e) {
      set({ error: String(e), monitoringBusyAlertId: null });
    }
  },

  saveDraftContract: async (contract) => {
    set({ contractSaveMessage: null, loading: true, error: null });
    try {
      const saved = await api.saveUpstreamContract(contract);
      const [upstreamContracts, resourcePoolOptions] = await Promise.all([
        api.upstreamContracts(),
        api.resourcePoolOptions(),
      ]);
      set({
        upstreamContracts: upstreamContracts.data,
        resourcePoolOptions: resourcePoolOptions.data,
        meta: saved.meta,
        contractSaveMessage: `${saved.data.contract_id} persisted for decision support.`,
        loading: false,
      });
    } catch (e) {
      set({ error: String(e), contractSaveMessage: String(e), loading: false });
    }
  },

  recordReviewDecision: async (body) => {
    set({ reviewMessage: null });
    try {
      const saved = await api.recordReviewDecision(body);
      const list = await api.reviewDecisions();
      set({
        reviewDecisions: list.data,
        reviewMessage: `${saved.data.decision_id} recorded for ${saved.data.entity_type}:${saved.data.entity_id}.`,
      });
    } catch (e) {
      set({ reviewMessage: String(e) });
    }
  },

  recommendRouteAllocation: async (request) => {
    set({ loading: true, error: null });
    try {
      const result = await api.recommendRouteAllocation(request);
      set({ routeRecommendation: result.data, meta: result.meta, loading: false });
    } catch (e) {
      set({ error: String(e), loading: false });
    }
  },

  optimizeResourcePool: async (request) => {
    set({ loading: true, error: null });
    try {
      const result = await api.optimizeResourcePool(withoutLegacyFlag(request));
      set({ resourcePoolResult: result.data, meta: result.meta, loading: false });
    } catch (e) {
      set({ error: String(e), loading: false });
    }
  },

  evaluateStrategyLab: async (scenario) => {
    set({ loading: true, error: null });
    try {
      const result = await api.evaluateStrategyLab(withoutLegacyFlag(scenario));
      set({ strategyResult: result.data, meta: result.meta, loading: false });
      void get().fetchStrategySummary();
      void get().fetchStrategyRuns();
    } catch (e) {
      set({ error: String(e), loading: false });
    }
  },

  fetchStrategySummary: async () => {
    try {
      const result = await api.strategySummary({ strategy_id: DEFAULT_STRATEGY_ID });
      set({ strategySummary: result.data });
    } catch (e) {
      set({ strategySummary: null, error: String(e) });
    }
  },

  fetchStrategyRuns: async () => {
    try {
      const result = await api.strategyRuns({ strategy_id: DEFAULT_STRATEGY_ID, limit: 20 });
      set({ strategyRuns: result.data });
    } catch (e) {
      set({ strategyRuns: [], error: String(e) });
    }
  },

  fetchGlossaryContext: async (term, params) => {
    set({ loading: true, error: null });
    try {
      const result = await api.glossaryContext(term, params);
      set({ glossaryContext: result.data, meta: result.meta, loading: false });
    } catch (e) {
      set({ error: String(e), loading: false });
    }
  },

  askAnalysis: async (body) => {
    set({ loading: true, error: null });
    try {
      const result = await api.analysisQuery(body);
      set({ analysisResult: result.data, meta: result.meta, loading: false });
    } catch (e) {
      set({ error: String(e), loading: false });
    }
  },

  generatePortfolioReport: async (body) => {
    set({ loading: true, error: null });
    try {
      const result = await api.portfolioReport(body);
      set({ analysisResult: result.data, meta: result.meta, loading: false });
    } catch (e) {
      set({ error: String(e), loading: false });
    }
  },
}));
