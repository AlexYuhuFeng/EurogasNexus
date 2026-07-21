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
  MarketObsDTO,
  MarketQuoteDTO,
  MonitoringAlertDTO,
  MonitoringAnalysisDTO,
  MonitoringSummaryDTO,
  NodeDTO,
  PortfolioLiveSummaryDTO,
  PortfolioOptimizationRequestDTO,
  PortfolioOptimizationResultDTO,
  PortfolioPnlSnapshotDTO,
  ResourcePoolOptionsDTO,
  RouteRecommendationRequestDTO,
  RouteRecommendationResultDTO,
  RouteCandidateDTO,
  RouteEligibilityDTO,
  RuntimeDbStatusDTO,
  ScreenOrderObservationDTO,
  SourceSystemDTO,
  StrategyLabRequestDTO,
  StrategyLabResultDTO,
  StorageObsDTO,
  TsoAccessPointDTO,
  TsoTariffDTO,
  UpstreamContractDTO,
  UpstreamContractInputDTO,
} from "@/api/client";

export interface ApiState {
  nodes: NodeDTO[];
  edges: EdgeDTO[];
  sources: SourceSystemDTO[];
  markets: MarketObsDTO[];
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
  glossaryTerms: GlossaryTermDTO[];
  glossaryContext: GlossaryContextDTO | null;
  analysisResult: AnalysisResultDTO | null;
  credentialProviders: CredentialProviderDTO[];
  monitoringAlerts: MonitoringAlertDTO[];
  monitoringSummary: MonitoringSummaryDTO;
  monitoringAnalysisByAlert: Record<string, MonitoringAnalysisDTO>;
  monitoringBusyAlertId: string | null;
  runtimeDb: RuntimeDbStatusDTO | null;
  endpointMeta: Record<string, ApiMeta>;
  meta: ApiMeta | null;
  marketLastUpdatedAtUtc: string | null;
  loading: boolean;
  error: string | null;
  credentialMessage: string | null;
  contractSaveMessage: string | null;
  dataStatus: "runtime" | "delayed" | "partial" | "unavailable";
  fetchWorkspace: () => Promise<void>;
  refreshMarketData: () => Promise<void>;
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
  recommendRouteAllocation: (request: RouteRecommendationRequestDTO) => Promise<void>;
  optimizeResourcePool: (request: PortfolioOptimizationRequestDTO) => Promise<void>;
  evaluateStrategyLab: (scenario: StrategyLabRequestDTO) => Promise<void>;
  fetchGlossaryContext: (
    term: string,
    params?: { lang?: string; duration_start_utc?: string; duration_end_utc?: string },
  ) => Promise<void>;
  askAnalysis: (body: AnalysisRequestDTO) => Promise<void>;
  generatePortfolioReport: (body: AnalysisRequestDTO) => Promise<void>;
}

function withoutLegacyFlag<T extends object>(body: T): T {
  const payload = { ...body } as Record<string, unknown>;
  delete payload["research" + "_only"];
  return payload as T;
}

export const useApiStore = create<ApiState>((set) => ({
  nodes: [],
  edges: [],
  sources: [],
  markets: [],
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
  endpointMeta: {},
  meta: null,
  marketLastUpdatedAtUtc: null,
  loading: false,
  error: null,
  credentialMessage: null,
  contractSaveMessage: null,
  dataStatus: "unavailable",

  fetchWorkspace: async () => {
    set({ loading: true, error: null });
    try {
      const [
        nodes,
        edges,
        sources,
        markets,
        marketQuotes,
        intradayOpportunities,
        screenOrders,
        pnlSnapshots,
        portfolioSummary,
        fxRates,
        flows,
        capacity,
        storage,
        lng,
        tsoAccess,
        routes,
        routeCandidates,
        tsoTariffs,
        upstreamContracts,
        resourcePoolOptions,
        glossaryTerms,
        runtimeDb,
        credentialProviders,
        monitoringAlerts,
        monitoringSummary,
      ] = await Promise.all([
        api.nodes(),
        api.edges(),
        api.sources(),
        api.marketObservations(),
        api.marketQuotes(),
        api.intradayOpportunities(),
        api.screenOrders(),
        api.pnlSnapshots(),
        api.portfolioLiveSummary(),
        api.fxRates(),
        api.flowObservations(),
        api.capacityObservations(),
        api.storageObservations(),
        api.lngObservations(),
        api.tsoAccess(),
        api.routeEligibility(),
        api.routeCandidates(),
        api.tsoTariffs(),
        api.upstreamContracts(),
        api.resourcePoolOptions(),
        api.glossary("en"),
        api.runtimeDb(),
        api.credentialProviders(),
        api.monitoringAlerts(),
        api.monitoringSummary(),
      ]);
      const endpointMeta = {
        referenceNodes: nodes.meta,
        referenceEdges: edges.meta,
        sources: sources.meta,
        markets: markets.meta,
        marketQuotes: marketQuotes.meta,
        intradayOpportunities: intradayOpportunities.meta,
        screenOrders: screenOrders.meta,
        pnlSnapshots: pnlSnapshots.meta,
        portfolioSummary: portfolioSummary.meta,
        fxRates: fxRates.meta,
        flows: flows.meta,
        capacity: capacity.meta,
        storage: storage.meta,
        lng: lng.meta,
        tsoAccess: tsoAccess.meta,
        routes: routes.meta,
        routeCandidates: routeCandidates.meta,
        tsoTariffs: tsoTariffs.meta,
        upstreamContracts: upstreamContracts.meta,
        resourcePoolOptions: resourcePoolOptions.meta,
        glossaryTerms: glossaryTerms.meta,
        runtimeDb: runtimeDb.meta,
        credentialProviders: credentialProviders.meta,
        monitoringAlerts: monitoringAlerts.meta,
        monitoringSummary: monitoringSummary.meta,
      };
      const sourceRefs = Object.values(endpointMeta).flatMap((item) => item.source_references ?? []);
      const hasRuntime = sourceRefs.some((source) => source === "runtime-postgresql");
      const hasDbMissing = sourceRefs.some((source) => source === "runtime-db-not-configured");
      const resolvedStatus = !runtimeDb.data.database_url_present || !runtimeDb.data.connectivity.ok
        ? "unavailable"
        : hasRuntime && hasDbMissing
          ? "partial"
          : hasRuntime
            ? "runtime"
            : "partial";

      set({
        nodes: nodes.data,
        edges: edges.data,
        sources: sources.data,
        markets: markets.data,
        marketQuotes: marketQuotes.data,
        intradayOpportunities: intradayOpportunities.data,
        screenOrders: screenOrders.data,
        pnlSnapshots: pnlSnapshots.data,
        portfolioSummary: portfolioSummary.data,
        fxRates: fxRates.data,
        flows: flows.data,
        capacity: capacity.data,
        storage: storage.data,
        lng: lng.data,
        tsoAccess: tsoAccess.data,
        routes: routes.data,
        routeCandidates: routeCandidates.data.route_candidates,
        tsoTariffs: tsoTariffs.data.tariffs,
        upstreamContracts: upstreamContracts.data,
        resourcePoolOptions: resourcePoolOptions.data,
        glossaryTerms: glossaryTerms.data,
        runtimeDb: runtimeDb.data,
        credentialProviders: credentialProviders.data,
        monitoringAlerts: monitoringAlerts.data,
        monitoringSummary: monitoringSummary.data,
        endpointMeta,
        meta: nodes.meta,
        marketLastUpdatedAtUtc: new Date().toISOString(),
        dataStatus: resolvedStatus,
        loading: false,
      });
    } catch (e) {
      set({ error: String(e), dataStatus: "unavailable", loading: false });
    }
  },

  refreshMarketData: async () => {
    try {
      const [markets, marketQuotes, intradayOpportunities, fxRates, sources] = await Promise.all([
        api.marketObservations(),
        api.marketQuotes(),
        api.intradayOpportunities(),
        api.fxRates(),
        api.sources(),
      ]);
      set((state) => ({
        markets: markets.data,
        marketQuotes: marketQuotes.data,
        intradayOpportunities: intradayOpportunities.data,
        fxRates: fxRates.data,
        sources: sources.data,
        endpointMeta: {
          ...state.endpointMeta,
          markets: markets.meta,
          marketQuotes: marketQuotes.meta,
          intradayOpportunities: intradayOpportunities.meta,
          fxRates: fxRates.meta,
          sources: sources.meta,
        },
        meta: markets.meta,
        marketLastUpdatedAtUtc: new Date().toISOString(),
        error: null,
      }));
    } catch (e) {
      set({
        marketQuotes: [],
        intradayOpportunities: [],
        error: String(e),
      });
    }
  },

  refreshMonitoring: async () => {
    try {
      const [alerts, summary] = await Promise.all([
        api.monitoringAlerts(),
        api.monitoringSummary(),
      ]);
      set((state) => ({
        monitoringAlerts: alerts.data,
        monitoringSummary: summary.data,
        endpointMeta: {
          ...state.endpointMeta,
          monitoringAlerts: alerts.meta,
          monitoringSummary: summary.meta,
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
    } catch (e) {
      set({ error: String(e), loading: false });
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
