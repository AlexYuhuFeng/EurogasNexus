import { create } from "zustand";
import {
  api,
  AnalysisRequestDTO,
  AnalysisResultDTO,
  ApiMeta,
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
  RouteCandidateDTO,
  RouteEligibilityDTO,
  RuntimeDbStatusDTO,
  SourceSystemDTO,
  StrategyLabRequestDTO,
  StrategyLabResultDTO,
  StorageObsDTO,
} from "@/api/client";

interface ApiState {
  nodes: NodeDTO[];
  edges: EdgeDTO[];
  sources: SourceSystemDTO[];
  markets: MarketObsDTO[];
  fxRates: FxRateDTO[];
  flows: FlowObsDTO[];
  storage: StorageObsDTO[];
  lng: LngObsDTO[];
  routes: RouteEligibilityDTO[];
  routeCandidates: RouteCandidateDTO[];
  routeOptions: EasingtonOptionsResultDTO | null;
  livePnl: LivePnlResultDTO | null;
  strategyResult: StrategyLabResultDTO | null;
  glossaryTerms: GlossaryTermDTO[];
  glossaryContext: GlossaryContextDTO | null;
  analysisResult: AnalysisResultDTO | null;
  credentialProviders: CredentialProviderDTO[];
  runtimeDb: RuntimeDbStatusDTO | null;
  meta: ApiMeta | null;
  loading: boolean;
  error: string | null;
  credentialMessage: string | null;
  dataStatus: "runtime" | "delayed" | "mocked" | "partial" | "unavailable";
  fetchWorkspace: () => Promise<void>;
  saveProviderCredential: (providerId: string, apiKey: string, label: string) => Promise<void>;
  compareEasingtonOptions: (contract: EasingtonContractRequest) => Promise<void>;
  markEasingtonLivePnl: (contract: EasingtonContractRequest, marks: LiveMarketMarkDTO[]) => Promise<void>;
  evaluateStrategyLab: (scenario: StrategyLabRequestDTO) => Promise<void>;
  fetchGlossaryContext: (term: string) => Promise<void>;
  askAnalysis: (body: AnalysisRequestDTO) => Promise<void>;
  generatePortfolioReport: (body: AnalysisRequestDTO) => Promise<void>;
}

export const useApiStore = create<ApiState>((set) => ({
  nodes: [],
  edges: [],
  sources: [],
  markets: [],
  fxRates: [],
  flows: [],
  storage: [],
  lng: [],
  routes: [],
  routeCandidates: [],
  routeOptions: null,
  livePnl: null,
  strategyResult: null,
  glossaryTerms: [],
  glossaryContext: null,
  analysisResult: null,
  credentialProviders: [],
  runtimeDb: null,
  meta: null,
  loading: false,
  error: null,
  credentialMessage: null,
  dataStatus: "mocked",

  fetchWorkspace: async () => {
    set({ loading: true, error: null });
    try {
      const [
        nodes,
        edges,
        sources,
        markets,
        fxRates,
        flows,
        storage,
        lng,
        routes,
        routeCandidates,
        glossaryTerms,
        runtimeDb,
        credentialProviders,
      ] = await Promise.all([
        api.nodes(),
        api.edges(),
        api.sources(),
        api.marketObservations(),
        api.fxRates(),
        api.flowObservations(),
        api.storageObservations(),
        api.lngObservations(),
        api.routeEligibility(),
        api.routeCandidates(),
        api.glossary("en"),
        api.runtimeDb(),
        api.credentialProviders(),
      ]);
      set({
        nodes: nodes.data,
        edges: edges.data,
        sources: sources.data,
        markets: markets.data,
        fxRates: fxRates.data,
        flows: flows.data,
        storage: storage.data,
        lng: lng.data,
        routes: routes.data,
        routeCandidates: routeCandidates.data.route_candidates,
        glossaryTerms: glossaryTerms.data,
        runtimeDb: runtimeDb.data,
        credentialProviders: credentialProviders.data,
        meta: nodes.meta,
        dataStatus: nodes.meta.source_references.includes("runtime-postgresql") ? "runtime" : "mocked",
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

  fetchGlossaryContext: async (term) => {
    set({ loading: true, error: null });
    try {
      const result = await api.glossaryContext(term);
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
