import { create } from "zustand";
import {
  api,
  AnalysisRequestDTO,
  AnalysisResultDTO,
  ApiMeta,
  CapacityObsDTO,
  CredentialProviderDTO,
  EdgeDTO,
  EasingtonContractRequest,
  EasingtonOptionsResultDTO,
  FlowObsDTO,
  FxRateDTO,
  GlossaryTermDTO,
  GlossaryContextDTO,
  LiveMarketMarkDTO,
  LivePnlResultDTO,
  LngObsDTO,
  MarketObsDTO,
  NodeDTO,
  PortfolioLiveSummaryDTO,
  PortfolioPnlSnapshotDTO,
  RouteCandidateDTO,
  RouteEligibilityDTO,
  RuntimeDbStatusDTO,
  ScreenOrderObservationDTO,
  SourceSystemDTO,
  StrategyLabRequestDTO,
  StrategyLabResultDTO,
  StorageObsDTO,
  TsoAccessPointDTO,
  UkTariffDTO,
  UpstreamContractDTO,
} from "@/api/client";

interface ApiState {
  nodes: NodeDTO[];
  edges: EdgeDTO[];
  sources: SourceSystemDTO[];
  markets: MarketObsDTO[];
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
  ukTariffs: UkTariffDTO[];
  upstreamContracts: UpstreamContractDTO[];
  routeOptions: EasingtonOptionsResultDTO | null;
  livePnl: LivePnlResultDTO | null;
  strategyResult: StrategyLabResultDTO | null;
  glossaryTerms: GlossaryTermDTO[];
  glossaryContext: GlossaryContextDTO | null;
  analysisResult: AnalysisResultDTO | null;
  credentialProviders: CredentialProviderDTO[];
  runtimeDb: RuntimeDbStatusDTO | null;
  endpointMeta: Record<string, ApiMeta>;
  meta: ApiMeta | null;
  loading: boolean;
  error: string | null;
  credentialMessage: string | null;
  dataStatus: "runtime" | "delayed" | "partial" | "unavailable";
  fetchWorkspace: () => Promise<void>;
  saveProviderCredential: (providerId: string, apiKey: string, label: string) => Promise<void>;
  compareEasingtonOptions: (contract: EasingtonContractRequest) => Promise<void>;
  markEasingtonLivePnl: (contract: EasingtonContractRequest, marks: LiveMarketMarkDTO[]) => Promise<void>;
  evaluateStrategyLab: (scenario: StrategyLabRequestDTO) => Promise<void>;
  fetchGlossaryContext: (
    term: string,
    params?: { lang?: string; duration_start_utc?: string; duration_end_utc?: string },
  ) => Promise<void>;
  askAnalysis: (body: AnalysisRequestDTO) => Promise<void>;
  generatePortfolioReport: (body: AnalysisRequestDTO) => Promise<void>;
}

export const useApiStore = create<ApiState>((set) => ({
  nodes: [],
  edges: [],
  sources: [],
  markets: [],
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
  ukTariffs: [],
  upstreamContracts: [],
  routeOptions: null,
  livePnl: null,
  strategyResult: null,
  glossaryTerms: [],
  glossaryContext: null,
  analysisResult: null,
  credentialProviders: [],
  runtimeDb: null,
  endpointMeta: {},
  meta: null,
  loading: false,
  error: null,
  credentialMessage: null,
  dataStatus: "unavailable",

  fetchWorkspace: async () => {
    set({ loading: true, error: null });
    try {
      const [
        nodes,
        edges,
        sources,
        markets,
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
        ukTariffs,
        upstreamContracts,
        glossaryTerms,
        runtimeDb,
        credentialProviders,
      ] = await Promise.all([
        api.nodes(),
        api.edges(),
        api.sources(),
        api.marketObservations(),
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
        api.ukTariffs(),
        api.upstreamContracts(),
        api.glossary("en"),
        api.runtimeDb(),
        api.credentialProviders(),
      ]);
      const endpointMeta = {
        referenceNodes: nodes.meta,
        referenceEdges: edges.meta,
        sources: sources.meta,
        markets: markets.meta,
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
        ukTariffs: ukTariffs.meta,
        upstreamContracts: upstreamContracts.meta,
        glossaryTerms: glossaryTerms.meta,
        runtimeDb: runtimeDb.meta,
        credentialProviders: credentialProviders.meta,
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
        ukTariffs: ukTariffs.data.tariffs,
        upstreamContracts: upstreamContracts.data,
        glossaryTerms: glossaryTerms.data,
        runtimeDb: runtimeDb.data,
        credentialProviders: credentialProviders.data,
        endpointMeta,
        meta: nodes.meta,
        dataStatus: resolvedStatus,
        loading: false,
      });
    } catch (e) {
      set({ error: String(e), dataStatus: "unavailable", loading: false });
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

  compareEasingtonOptions: async (contract) => {
    set({ loading: true, error: null });
    try {
      const result = await api.compareEasingtonOptions(contract);
      set({ routeOptions: result.data, meta: result.meta, loading: false });
    } catch (e) {
      set({ error: String(e), loading: false });
    }
  },

  markEasingtonLivePnl: async (contract, marks) => {
    set({ loading: true, error: null });
    try {
      const result = await api.markEasingtonLivePnl(contract, marks);
      set({ livePnl: result.data, routeOptions: result.data, meta: result.meta, loading: false });
    } catch (e) {
      set({ error: String(e), loading: false });
    }
  },

  evaluateStrategyLab: async (scenario) => {
    set({ loading: true, error: null });
    try {
      const result = await api.evaluateStrategyLab(scenario);
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

