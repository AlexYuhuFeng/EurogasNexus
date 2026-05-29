import { create } from "zustand";
import {
  api,
  ApiMeta,
  CredentialProviderDTO,
  EdgeDTO,
  FlowObsDTO,
  LngObsDTO,
  MarketObsDTO,
  NodeDTO,
  RouteEligibilityDTO,
  RuntimeDbStatusDTO,
  SourceSystemDTO,
  StorageObsDTO,
} from "@/api/client";

interface ApiState {
  nodes: NodeDTO[];
  edges: EdgeDTO[];
  sources: SourceSystemDTO[];
  markets: MarketObsDTO[];
  flows: FlowObsDTO[];
  storage: StorageObsDTO[];
  lng: LngObsDTO[];
  routes: RouteEligibilityDTO[];
  credentialProviders: CredentialProviderDTO[];
  runtimeDb: RuntimeDbStatusDTO | null;
  meta: ApiMeta | null;
  loading: boolean;
  error: string | null;
  credentialMessage: string | null;
  dataStatus: "runtime" | "delayed" | "mocked" | "partial" | "unavailable";
  fetchWorkspace: () => Promise<void>;
  saveProviderCredential: (providerId: string, apiKey: string, label: string) => Promise<void>;
}

export const useApiStore = create<ApiState>((set) => ({
  nodes: [],
  edges: [],
  sources: [],
  markets: [],
  flows: [],
  storage: [],
  lng: [],
  routes: [],
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
        flows,
        storage,
        lng,
        routes,
        runtimeDb,
        credentialProviders,
      ] = await Promise.all([
        api.nodes(),
        api.edges(),
        api.sources(),
        api.marketObservations(),
        api.flowObservations(),
        api.storageObservations(),
        api.lngObservations(),
        api.routeEligibility(),
        api.runtimeDb(),
        api.credentialProviders(),
      ]);
      set({
        nodes: nodes.data,
        edges: edges.data,
        sources: sources.data,
        markets: markets.data,
        flows: flows.data,
        storage: storage.data,
        lng: lng.data,
        routes: routes.data,
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
}));
