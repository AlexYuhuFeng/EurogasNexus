/** Typed API client for /api. All data flows through backend API only. */

const DEFAULT_BROWSER_BASE = "/api";
const DEFAULT_DESKTOP_BASE = "http://127.0.0.1:8000/api";
const envBase = import.meta.env.VITE_EUROGAS_API_BASE_URL as string | undefined;
const isDesktopShell =
  "__TAURI_INTERNALS__" in window ||
  window.location.protocol === "tauri:" ||
  window.location.hostname === "tauri.localhost";
const BASE = (envBase?.trim() || (isDesktopShell ? DEFAULT_DESKTOP_BASE : DEFAULT_BROWSER_BASE)).replace(/\/$/, "");

function apiUrl(path: string): string {
  return new URL(`${BASE}${path}`, window.location.origin).toString();
}

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
  const url = new URL(apiUrl(path));
  if (params) {
    Object.entries(params).forEach(([k, v]) => { if (v) url.searchParams.set(k, v); });
  }
  const res = await fetch(url.toString());
  if (!res.ok) throw new Error(`API ${res.status}: ${res.statusText}`);
  return res.json();
}

async function post<T>(path: string, body: unknown): Promise<ApiResponse<T>> {
  const res = await fetch(apiUrl(path), {
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
  source_system?: string | null; source_dataset?: string | null;
  source_reference?: string | null; source_record_id?: string | null;
  data_quality?: string | null;
  metadata_json?: Record<string, unknown> | null;
}

export interface EdgeDTO {
  id: string; from_node_id: string; to_node_id: string;
  edge_type: string; length_km: number | null;
  source_system?: string | null; source_dataset?: string | null;
  source_reference?: string | null; source_record_id?: string | null;
  data_quality?: string | null;
  metadata_json?: Record<string, unknown> | null;
}

export interface FacilityDTO {
  id: string; name: string; facility_type: string; country: string;
  lat: number; lon: number; capacity_boe_d: number | null;
  source_system?: string | null; source_dataset?: string | null;
  source_reference?: string | null; source_record_id?: string | null;
  data_quality?: string | null;
  metadata_json?: Record<string, unknown> | null;
}

export interface MarketHubDTO {
  id: string; name: string; hub_code: string; country: string;
  description: string | null;
  source_system?: string | null; source_dataset?: string | null;
  source_reference?: string | null; source_record_id?: string | null;
  data_quality?: string | null;
  metadata_json?: Record<string, unknown> | null;
}

export interface TsoAccessPointDTO {
  access_id: string; point_id: string | null; point_key: string; point_name: string;
  country: string; operator_key: string; operator_name: string; tso_eic_code: string | null;
  direction: string; adjacent_country: string | null; adjacent_operator_key: string | null;
  connected_operators: string | null; booking_platform: string | null;
  booking_platform_url: string | null; annual_contracts_available: boolean;
  monthly_contracts_available: boolean; daily_contracts_available: boolean;
  day_ahead_contracts_available: boolean; is_cam_relevant: boolean; is_cmp_relevant: boolean;
  last_update_utc: string | null; source_system: string; source_dataset: string;
  source_reference: string; source_record_id: string; data_quality: string;
  metadata_json?: Record<string, unknown> | null;
}

export interface SourceSystemDTO {
  source_id: string; source_system: string; datasets: string[];
  status: string; description: string; live_record_count: number;
  category: string; category_label: string; connectivity_status: string;
  entitlement_scope: string; freshness_expectation_minutes: number;
  credential_requirements: string[]; credential_provider_id: string | null;
  credential_state: string; credential_status: string | null;
  credential_last_tested_at_utc: string | null; credential_last_test_status: string | null;
  last_success_at_utc: string | null; last_failure_at_utc: string | null;
  last_ingestion_status: string | null; last_ingestion_message: string | null;
  diagnostics: string[]; export_restrictions: string[];
}

type SourceSystemWire = Partial<SourceSystemDTO> & {
  source_id?: string;
  source_system?: string;
  datasets?: unknown;
  credential_requirements?: unknown;
  diagnostics?: unknown;
  export_restrictions?: unknown;
};

const SOURCE_CATEGORY_BY_SYSTEM: Record<string, string> = {
  ARGUS: "price",
  BBL: "tariff",
  CNMCENAGAS: "tariff",
  DEEPSEEK: "ai",
  ECB: "fx",
  EEX: "price",
  ENTSOG: "infrastructure",
  FLUXYSBELGIUM: "tariff",
  GERMANTSO: "tariff",
  GIE: "infrastructure",
  GTS: "tariff",
  ICE_OCM: "price",
  ICIS: "price",
  IUK: "tariff",
  KPLER: "price",
  NATRAN: "tariff",
  NATIONALGASNTS: "tariff",
  NATIONAL_GAS_NTS: "tariff",
  PLATTS: "price",
  TRAYPORT: "price",
  WEATHER: "weather",
};

const SOURCE_CATEGORY_LABELS: Record<string, string> = {
  ai: "LLM",
  fx: "FX",
  infrastructure: "Infrastructure",
  price: "Prices",
  tariff: "TSO Tariffs",
  weather: "Weather",
};

function sourceSystemKey(value: string): string {
  return value.trim().toUpperCase().replace(/[\s-]+/g, "_");
}

function asStringArray(value: unknown): string[] {
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === "string" && item.trim().length > 0)
    : [];
}

function normalizeSourceSystem(raw: SourceSystemWire): SourceSystemDTO {
  const sourceSystem = raw.source_system?.trim() || "Unknown";
  const sourceKey = sourceSystemKey(sourceSystem);
  const category = raw.category || SOURCE_CATEGORY_BY_SYSTEM[sourceKey] || "price";
  const credentialRequirements = asStringArray(raw.credential_requirements);
  const credentialRequired = credentialRequirements.length > 0;
  const liveRecordCount = Number(raw.live_record_count ?? 0);
  const status = raw.status || (liveRecordCount > 0 ? "active" : "registered");
  const credentialState = raw.credential_state || (credentialRequired ? "missing" : "not_required");
  const connectivityStatus = raw.connectivity_status ||
    (credentialState === "missing"
      ? "needs_credential"
      : liveRecordCount > 0
        ? "active"
        : status);
  const diagnostics = asStringArray(raw.diagnostics);

  return {
    source_id: raw.source_id || `src-${sourceKey.toLowerCase().replace(/_/g, "-")}`,
    source_system: sourceSystem,
    datasets: asStringArray(raw.datasets),
    status: connectivityStatus,
    description: raw.description || `${sourceSystem} data source.`,
    live_record_count: liveRecordCount,
    category,
    category_label: raw.category_label || SOURCE_CATEGORY_LABELS[category] || category,
    connectivity_status: connectivityStatus,
    entitlement_scope: raw.entitlement_scope || (credentialRequired ? "licensed" : "public"),
    freshness_expectation_minutes: Number(raw.freshness_expectation_minutes ?? 0),
    credential_requirements: credentialRequirements,
    credential_provider_id: raw.credential_provider_id ?? (credentialRequired ? sourceSystem : null),
    credential_state: credentialState,
    credential_status: raw.credential_status ?? null,
    credential_last_tested_at_utc: raw.credential_last_tested_at_utc ?? null,
    credential_last_test_status: raw.credential_last_test_status ?? null,
    last_success_at_utc: raw.last_success_at_utc ?? null,
    last_failure_at_utc: raw.last_failure_at_utc ?? null,
    last_ingestion_status: raw.last_ingestion_status ?? null,
    last_ingestion_message: raw.last_ingestion_message ?? null,
    diagnostics: diagnostics.length > 0
      ? diagnostics
      : liveRecordCount > 0
        ? ["live_records_available"]
        : credentialState === "missing"
          ? ["credential_missing"]
          : ["no_records_in_runtime_db"],
    export_restrictions: asStringArray(raw.export_restrictions),
  };
}

function normalizeSourcesResponse(
  response: ApiResponse<SourceSystemWire[]>,
): ApiResponse<SourceSystemDTO[]> {
  return {
    ...response,
    data: response.data.map(normalizeSourceSystem),
  };
}

export interface MarketObsDTO {
  observation_id: string; market_venue: string; product: string;
  price: number; unit: string; currency: string;
  period_start_utc: string; period_end_utc: string;
  source_system?: string; freshness?: string;
}

export interface ScreenOrderObservationDTO {
  order_observation_id: string; provider_id: string; venue: string;
  account_label: string; external_order_id: string; side: string; order_type: string;
  hub: string; product: string; contract_code: string;
  delivery_start_utc: string; delivery_end_utc: string;
  price: number; currency: string; unit: string; quantity_mwh: number;
  filled_quantity_mwh: number; remaining_quantity_mwh: number; status: string;
  observed_at_utc: string; source_system: string; source_reference: string;
  linked_strategy_id?: string | null; linked_resource_id?: string | null;
  research_only: boolean; human_review_required: boolean;
}

export interface PortfolioPnlSnapshotDTO {
  pnl_snapshot_id: string; portfolio_id: string; resource_id?: string | null;
  strategy_id?: string | null; valuation_time_utc: string;
  realized_pnl_gbp: number; unrealized_pnl_gbp: number; indicative_pnl_gbp: number;
  cash_value_gbp: number; market_value_gbp: number; quantity_mwh: number;
  valuation_basis: string; source_system: string; source_reference: string;
  warnings: string[]; research_only: boolean; human_review_required: boolean;
}

export interface PortfolioLiveSummaryDTO {
  portfolio_id: string; latest_valuation_time_utc?: string | null;
  total_realized_pnl_gbp: number; total_unrealized_pnl_gbp: number;
  total_indicative_pnl_gbp: number; total_cash_value_gbp: number;
  open_order_count: number; filled_order_count: number; warnings: string[];
  research_only: boolean; human_review_required: boolean;
}

export interface FxRateDTO {
  pair: string; base_currency?: string; quote_currency?: string; rate: number;
  rate_type?: string; value_date?: string; observed_at_utc: string;
  source_system?: string; source_reference?: string; freshness?: string;
}

export interface FlowObsDTO {
  observation_id: string; point_id: string; point_name: string; direction: string;
  flow_mcm_d: number; period_start_utc: string; period_end_utc: string;
  observed_at_utc?: string; source_system?: string; source_reference?: string; freshness?: string;
}

export interface CapacityObsDTO {
  observation_id: string; point_id: string; point_name: string; direction: string;
  capacity_type: string; capacity_mcm_d: number; original_value?: number | null;
  original_unit?: string | null; period_start_utc: string; period_end_utc: string;
  observed_at_utc?: string; source_system?: string; source_reference?: string; freshness?: string;
}

export interface StorageObsDTO {
  observation_id: string; facility_id: string; facility_name: string;
  country?: string; inventory_twh: number | null; working_capacity_twh?: number | null;
  fill_pct: number | null; injection_twh_d?: number | null; withdrawal_twh_d?: number | null;
  period_start_utc?: string; period_end_utc?: string; observed_at_utc?: string;
  source_system?: string; source_reference?: string; freshness?: string;
}

export interface LngObsDTO {
  observation_id: string; terminal_id: string; terminal_name: string;
  country?: string; inventory_twh: number | null; send_out_twh_d: number | null;
  dtmi_pct?: number | null; period_start_utc?: string; period_end_utc?: string; observed_at_utc?: string;
  source_system?: string; source_reference?: string; freshness?: string;
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

export interface RouteCandidateDTO {
  route_id: string; route_name: string; start_point_name: string; target_point_name: string;
  business_model: string; route_legs: Array<Record<string, unknown>>;
  required_entry_point_name: string | null; required_exit_point_name: string | null;
  required_tso_access: string[]; source_systems: string[];
}


export interface TsoTariffDTO {
  tariff_id: string; document_id: string; country: string; tso: string; market_area: string;
  gas_year: string; point_id: string; source_point_name: string; direction: string;
  capacity_product: string; firmness: string; tariff_value: number; currency: string; unit: string;
  effective_from: string; effective_to?: string | null; tariff_status: string;
  source_table: string; source_page?: number | null; source_refs: string[]; manual_review_required: boolean;
}

export interface TsoTariffsResultDTO {
  scope: string; data_source: string; tariffs: TsoTariffDTO[];
}

export interface UpstreamContractDTO {
  contract_id: string; contract_name: string; resource_type: string; delivery_point_name: string;
  gas_year: string; delivery_quantity_mwh_per_day: number; contract_price_gbp_mwh: number;
  settlement_frequency: string; upstream_payment_lag_days: number; screen_sale_cash_lag_days: number;
  delivery_tolerance_pct: number; nomination_tolerance_pct: number;
  tolerance_risk_allowance_gbp_mwh?: number | null; annual_financing_rate_pct: number;
  owned_entry_capacity_mwh_per_day?: number | null; owned_exit_capacity_mwh_per_day?: number | null;
  allowed_exit_points: string[]; eligible_sale_modes: string[]; updated_at_utc?: string;
}
export interface RouteRecommendationRequestDTO {
  request_id: string; source_point_id: string; target_point_id?: string | null;
  required_quantity_mwh_per_day: number; gas_year: string;
  capacity_product: string; firmness: string; company_accessible_tsos?: string[] | null;
  candidates: Array<Record<string, unknown>>;
}

export interface RouteRecommendationResultDTO {
  request_id: string; status: string; total_requested_mwh_per_day: number;
  total_allocated_mwh_per_day: number; unallocated_mwh_per_day: number;
  allocations: Array<{
    route_id: string; route_name: string; destination_market?: string | null;
    allocated_mwh_per_day: number; route_cost?: number | null;
    currency?: string | null; unit?: string | null; sale_price?: number | null;
    netback?: number | null; rationale: string[];
  }>;
  excluded_routes: Array<Record<string, unknown>>;
  warnings: string[]; assumptions: string[];
  research_only: boolean; human_review_required: boolean;
}

export interface PortfolioResourceDTO {
  resource_id: string; resource_name: string; resource_type: string; delivery_mode: string;
  location_point_name: string; available_quantity_mwh_per_day: number;
  contract_cost_gbp_mwh: number; variable_cost_gbp_mwh?: number;
  delivery_tolerance_pct?: number | null; nomination_tolerance_pct?: number | null;
  tolerance_risk_allowance_gbp_mwh?: number; upstream_payment_lag_days?: number;
  settlement_frequency?: string; required_tso_access?: string[];
  accessible_tsos?: string[] | null; pricing_method?: string; source_refs?: string[];
}

export interface PortfolioSaleOptionDTO {
  option_id: string; label: string; delivery_mode: string; target_point_name: string;
  sale_price_gbp_mwh: number; route_cost_gbp_mwh?: number;
  capacity_limit_mwh_per_day?: number | null; screen_sale_cash_lag_days?: number;
  required_tso_access?: string[]; source_refs?: string[];
}

export interface PortfolioOptimizationRequestDTO {
  portfolio_id: string; resources: PortfolioResourceDTO[]; sale_options: PortfolioSaleOptionDTO[];
  annual_financing_rate_pct?: number; objective?: string; research_only?: boolean;
}

export interface PortfolioOptimizationResultDTO {
  portfolio_id: string; status: string; total_allocated_mwh_per_day: number;
  total_unallocated_mwh_per_day: number; total_net_pnl_gbp_per_day: number;
  allocations: Array<{
    resource_id: string; option_id: string; allocated_quantity_mwh_per_day: number;
    gross_sale_price_gbp_mwh: number; total_cost_gbp_mwh: number;
    early_cash_value_gbp_mwh: number; net_margin_gbp_mwh: number;
    net_pnl_gbp_per_day: number; warnings: string[];
  }>;
  missing_inputs: string[]; warnings: string[]; source_refs: string[];
  research_only: boolean; human_review_required: boolean;
}

export interface ResourcePoolOptionsDTO {
  scope: string; data_source: string;
  portfolio_resources: PortfolioResourceDTO[];
  sale_options: Array<PortfolioSaleOptionDTO & {
    sale_price_currency?: string; sale_price_unit?: string;
    route_cost_currency?: string; route_cost_unit?: string;
  }>;
  blockers: string[]; warnings: string[];
}

export interface StrategyPriceObservationDTO {
  observation_id: string; source_system: string; venue: string; hub: string; product: string;
  price_name: string; price_gbp_mwh: number; observed_at_utc: string;
  delivery_start_utc: string; delivery_end_utc: string; bar_minutes?: number | null;
  price_type?: string; source_reference?: string;
}

export interface StrategyResourceContextDTO {
  resource_id: string; resource_name: string; available_quantity_mwh_per_day: number;
  all_in_cost_gbp_mwh: number; delivery_tolerance_pct?: number | null;
  nomination_tolerance_pct?: number | null; booked_entry_capacity_mwh_per_day?: number | null;
  balancing_allowance_gbp_mwh?: number; required_tso_access: string[];
  company_accessible_tsos?: string[] | null;
}

export interface StrategyComponentDTO {
  component_id: string; component_type: string; weight?: number;
  day_ahead_price_names?: string[]; intraday_price_names?: string[];
  positive_spread_threshold_gbp_mwh?: number; negative_spread_threshold_gbp_mwh?: number;
  time_window_start?: string | null; time_window_end?: string | null;
  target_bar_minutes?: number | null;
}

export interface StrategyLabRequestDTO {
  strategy_id: string; strategy_name: string; run_mode: string;
  resource_contexts: StrategyResourceContextDTO[];
  price_observations: StrategyPriceObservationDTO[];
  components: StrategyComponentDTO[];
  risk_control?: Record<string, unknown>;
  existing_shadow_pnl_gbp?: number;
  research_only?: boolean;
}

export interface StrategyAllocationTargetDTO {
  market_bucket: string; target_allocation_pct: number; target_quantity_mwh_per_day: number;
  reference_price_gbp_mwh: number | null; expected_margin_gbp_mwh: number | null;
  rationale: string[];
}

export interface StrategyLabResultDTO {
  strategy_id: string; strategy_name: string; run_mode: string; status: string;
  weighted_score: number; day_ahead_average_gbp_mwh: number | null;
  intraday_average_gbp_mwh: number | null;
  intraday_vs_day_ahead_spread_gbp_mwh: number | null;
  allocation_targets: StrategyAllocationTargetDTO[];
  missing_inputs: string[]; warnings: string[]; source_refs: string[];
  candidate_action_for_review: string; research_only: boolean; human_review_required: boolean;
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
  term_id: string; term: string; category: string; definition: string;
  definition_en: string; definition_zh_cn: string;
  aliases: string[]; related_terms: string[]; source_refs: string[];
}

export interface GlossaryContextDTO {
  term: string; context_type: string; description: string;
  description_en?: string | null; description_zh_cn?: string | null;
  requested_duration?: Record<string, unknown> | null;
  entity_summary?: Record<string, unknown> | null;
  matched_entities: Array<Record<string, unknown>>;
  capacity: Record<string, unknown> | null; capacity_usage: Record<string, unknown> | null;
  metrics: Array<Record<string, unknown>>;
  related_prices: Array<Record<string, unknown>>; related_routes: Array<Record<string, unknown>>;
  related_contracts: Array<Record<string, unknown>>;
  live_market_marks: Array<Record<string, unknown>>;
  context_sections: Array<{
    section_id: string; title: string; items: Array<Record<string, unknown>>;
    metrics?: Array<Record<string, unknown>>; warnings: string[];
  }>;
  related_sources: string[]; data_quality: Record<string, unknown>; warnings: string[];
  research_only: boolean; human_review_required: boolean;
}

export interface AnalysisRequestDTO {
  question: string; task?: string; provider_id?: string; model?: string;
  invoke_provider?: boolean; selected_terms?: string[]; selected_assets?: string[];
  selected_contracts?: string[]; duration_start_utc?: string | null;
  duration_end_utc?: string | null; include_sections?: string[]; language?: string;
}

export interface AnalysisResultDTO {
  analysis_id: string; task: string; provider_id: string; provider_status: string;
  answer_en: string; answer_zh_cn: string; citations: string[];
  sections: Array<{ section_id: string; title: string; content: string; citations: string[]; warnings: string[] }>;
  missing_inputs: string[]; warnings: string[]; snapshot_id: string;
  created_at_utc: string; research_only: boolean; human_review_required: boolean;
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

  tsoAccess: (params?: {
    point_id?: string; country?: string; operator_key?: string; direction?: string;
  }) => get<TsoAccessPointDTO[]>("/reference-network/tso-access", params),

  sources: () => get<SourceSystemWire[]>("/sources").then(normalizeSourcesResponse),

  marketObservations: () => get<MarketObsDTO[]>("/market/observations"),

  screenOrders: () => get<ScreenOrderObservationDTO[]>("/portfolio/screen-orders"),

  pnlSnapshots: () => get<PortfolioPnlSnapshotDTO[]>("/portfolio/pnl-snapshots"),

  portfolioLiveSummary: () => get<PortfolioLiveSummaryDTO>("/portfolio/live-summary"),

  flowObservations: () => get<FlowObsDTO[]>("/physical/flows"),

  capacityObservations: () => get<CapacityObsDTO[]>("/physical/capacity"),

  storageObservations: () => get<StorageObsDTO[]>("/storage/observations"),

  lngObservations: () => get<LngObsDTO[]>("/lng/observations"),

  fxRates: () => get<FxRateDTO[]>("/market/fx"),

  credentialProviders: () => get<CredentialProviderDTO[]>("/credentials/providers"),

  saveCredential: (providerId: string, body: { api_key: string; label: string }) =>
    fetch(apiUrl(`/credentials/${providerId}`), {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }).then(async (res) => {
      if (!res.ok) throw new Error(`API ${res.status}: ${res.statusText}`);
      return res.json() as Promise<ApiResponse<CredentialProviderDTO>>;
    }),

  routeEligibility: () => get<RouteEligibilityDTO[]>("/contracts/routes"),

  routeCandidates: () => get<{ route_candidates: RouteCandidateDTO[] }>("/route-cost/route-candidates"),

  tsoTariffs: () => get<TsoTariffsResultDTO>("/route-cost/tso-tariffs"),

  upstreamContracts: () => get<UpstreamContractDTO[]>("/route-cost/upstream-contracts"),

  resourcePoolOptions: () => get<ResourcePoolOptionsDTO>("/route-cost/resource-pool/options"),

  recommendRouteAllocation: (body: RouteRecommendationRequestDTO) =>
    post<RouteRecommendationResultDTO>("/route-cost/recommend", body),

  optimizeResourcePool: (body: PortfolioOptimizationRequestDTO) =>
    post<PortfolioOptimizationResultDTO>("/route-cost/resource-pool/optimize", body),

  evaluateStrategyLab: (body: StrategyLabRequestDTO) =>
    post<StrategyLabResultDTO>("/strategy-lab/evaluate", body),

  capacityContracts: () => get<CapacityContractDTO[]>("/contracts/capacity"),

  runtimeDb: () => get<RuntimeDbStatusDTO>("/runtime/db"),

  glossary: (lang: string = "en", params?: { category?: string; q?: string }) =>
    get<GlossaryTermDTO[]>("/glossary", { lang, ...(params ?? {}) }),

  glossaryContext: (
    term: string,
    params?: { lang?: string; duration_start_utc?: string; duration_end_utc?: string },
  ) =>
    get<GlossaryContextDTO>(`/glossary/${encodeURIComponent(term)}/context`, params),

  analysisQuery: (body: AnalysisRequestDTO) => post<AnalysisResultDTO>("/analysis/query", body),

  portfolioReport: (body: AnalysisRequestDTO) => post<AnalysisResultDTO>("/reports/portfolio", body),

  routeCost: (body: unknown) => post<unknown>("/research/route-cost", body),
  netback: (body: unknown) => post<unknown>("/research/netback", body),
};

