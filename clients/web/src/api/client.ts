/** Typed API client for /api/v1. All data flows through backend API only. */

const BASE = "/api/v1";

export interface ApiMeta {
  research_only: boolean;
  human_review_required: boolean;
  source_references: string[];
  warnings: string[];
}

export interface ApiResponse<T> {
  data: T;
  meta: ApiMeta;
}

async function get<T>(path: string, params?: Record<string, string>): Promise<ApiResponse<T>> {
  const url = new URL(`${BASE}${path}`, window.location.origin);
  if (params) {
    Object.entries(params).forEach(([k, v]) => { if (v) url.searchParams.set(k, v); });
  }
  const res = await fetch(url.toString());
  if (!res.ok) throw new Error(`API ${res.status}: ${res.statusText}`);
  return res.json();
}

async function post<T>(path: string, body: unknown): Promise<ApiResponse<T>> {
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`API ${res.status}: ${res.statusText}`);
  return res.json();
}

// --- Types ---

export interface NodeDTO {
  id: string; name: string; node_type: string; country: string;
  lat: number; lon: number; capacity_boe_d: number | null;
}

export interface EdgeDTO {
  id: string; from_node_id: string; to_node_id: string;
  edge_type: string; length_km: number | null;
}

export interface FacilityDTO {
  id: string; name: string; facility_type: string; country: string;
  lat: number; lon: number; capacity_boe_d: number | null;
}

export interface MarketHubDTO {
  id: string; name: string; hub_code: string; country: string;
  description: string | null;
}

export interface SourceSystemDTO {
  source_id: string; source_system: string; datasets: string[];
  status: string; description: string; live_record_count: number;
}

export interface MarketObsDTO {
  observation_id: string; market_venue: string; product: string;
  price: number; unit: string; currency: string;
  period_start_utc: string; period_end_utc: string;
  source_system?: string; freshness?: string;
}

export interface FlowObsDTO {
  observation_id: string; point_id: string; point_name: string; direction: string;
  flow_mcm_d: number; period_start_utc: string; period_end_utc: string;
  source_system?: string; freshness?: string;
}

export interface StorageObsDTO {
  observation_id: string; facility_id: string; facility_name: string;
  inventory_twh: number | null; fill_pct: number | null; source_system?: string; freshness?: string;
}

export interface LngObsDTO {
  observation_id: string; terminal_id: string; terminal_name: string;
  inventory_twh: number | null; send_out_twh_d: number | null; source_system?: string; freshness?: string;
}

export interface CredentialProviderDTO {
  provider_id: string; display_name: string; credential_required: boolean;
  configured: boolean; status: string; redacted_preview: string | null;
  last_tested_at_utc: string | null; last_test_status: string | null;
}

export interface RouteEligibilityDTO {
  route_id: string; from_node_id: string; to_node_id: string;
  eligibility: string; confidence: number; constraints: string[];
}

export interface CapacityContractDTO {
  contract_id: string; route_name: string; from_node_id: string; to_node_id: string;
  capacity_boe_d: number; unit: string; start_utc: string; end_utc: string; status: string;
}

export interface RuntimeDbStatusDTO {
  database_url_present: boolean;
  redacted_database_url: string | null;
  connectivity: { ok: boolean; error: string | null };
  alembic_revision: string | null;
  required_tables: string[];
  missing_tables: string[];
  warnings: string[];
}

export interface GlossaryTermDTO {
  term: string; definition: string;
}

// --- API functions ---

export const api = {
  nodes: (params?: { country?: string; node_type?: string }) =>
    get<NodeDTO[]>("/reference-network/nodes", params),

  edges: (params?: { from_node_id?: string; to_node_id?: string }) =>
    get<EdgeDTO[]>("/reference-network/edges", params),

  facilities: (params?: { facility_type?: string; country?: string }) =>
    get<FacilityDTO[]>("/reference-network/facilities", params),

  marketHubs: () => get<MarketHubDTO[]>("/reference-network/market-hubs"),

  sources: () => get<SourceSystemDTO[]>("/sources"),

  marketObservations: () => get<MarketObsDTO[]>("/market/observations"),

  flowObservations: () => get<FlowObsDTO[]>("/physical/flows"),

  storageObservations: () => get<StorageObsDTO[]>("/storage/observations"),

  lngObservations: () => get<LngObsDTO[]>("/lng/observations"),

  fxRates: () => get<{ pair: string; rate: number }[]>("/market/fx"),

  credentialProviders: () => get<CredentialProviderDTO[]>("/credentials/providers"),

  saveCredential: (providerId: string, body: { api_key: string; label: string }) =>
    fetch(`${BASE}/credentials/${providerId}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }).then(async (res) => {
      if (!res.ok) throw new Error(`API ${res.status}: ${res.statusText}`);
      return res.json() as Promise<ApiResponse<CredentialProviderDTO>>;
    }),

  routeEligibility: () => get<RouteEligibilityDTO[]>("/contracts/routes"),

  capacityContracts: () => get<CapacityContractDTO[]>("/contracts/capacity"),

  runtimeDb: () => get<RuntimeDbStatusDTO>("/runtime/db"),

  glossary: (lang: string = "en") =>
    get<GlossaryTermDTO[]>("/glossary", { lang }),

  routeCost: (body: unknown) => post<unknown>("/research/route-cost", body),
  netback: (body: unknown) => post<unknown>("/research/netback", body),
};
