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

export interface RouteCandidateDTO {
  route_id: string; route_name: string; start_point_name: string; target_point_name: string;
  business_model: string; route_legs: Array<Record<string, unknown>>;
  required_entry_point_name: string | null; required_exit_point_name: string | null;
  required_tso_access: string[]; source_systems: string[];
}

export interface EasingtonContractRequest {
  contract_id: string; gas_year: string; delivery_quantity_mwh_per_day: number;
  contract_price_gbp_mwh: number; nbp_sale_price_gbp_mwh: number;
  physical_exit_sale_price_gbp_mwh: number; physical_exit_point_name: string;
  delivery_tolerance_pct: number; nomination_tolerance_pct: number;
  tolerance_risk_allowance_gbp_mwh: number; settlement_frequency: string;
  upstream_payment_lag_days: number; screen_sale_cash_lag_days: number;
  annual_financing_rate_pct: number; owned_entry_capacity_mwh_per_day?: number | null;
  owned_exit_capacity_mwh_per_day?: number | null; allowed_exit_points: string[];
  eligible_sale_modes: string[];
}

export interface EasingtonOptionPnlDTO {
  option_id: string; label: string; business_model: string; sale_price_gbp_mwh: number;
  contract_cost_gbp_mwh: number; entry_capacity_charge_gbp_mwh: number;
  exit_capacity_charge_gbp_mwh: number; commodity_charge_gbp_mwh: number;
  tolerance_risk_allowance_gbp_mwh: number; early_cash_value_gbp_mwh: number;
  total_charges_gbp_mwh: number; net_margin_gbp_mwh: number; net_pnl_gbp_per_day: number;
  source_refs: string[]; route_legs: Array<Record<string, unknown>>;
  tariff_status_summary: Record<string, number>; warnings: string[];
  human_review_required: boolean;
}

export interface EasingtonOptionsResultDTO {
  contract_id: string; gas_year: string; delivery_point_name: string;
  delivery_quantity_mwh_per_day: number; delivery_tolerance_pct: number;
  nomination_tolerance_pct: number; delivery_tolerance_mwh: number;
  nomination_tolerance_mwh: number; options: EasingtonOptionPnlDTO[];
  missing_inputs: string[]; warnings: string[]; source_refs: string[];
  research_only: boolean; human_review_required: boolean;
}

export interface LiveMarketMarkDTO {
  venue: string; hub: string; product: string; bid_gbp_mwh?: number | null;
  ask_gbp_mwh?: number | null; last_gbp_mwh?: number | null;
  mark_time_utc: string; source_system: string;
}

export interface LivePnlResultDTO extends EasingtonOptionsResultDTO {
  live_marks: Array<{
    option_id: string; venue: string; hub: string; product: string; status: string;
    mark_price_gbp_mwh: number | null; live_net_margin_gbp_mwh: number | null;
    live_net_pnl_gbp_per_day: number | null;
    signal: { suggestion_type: string; suggested_action: string; rationale: string[]; warnings: string[] };
  }>;
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

  sources: () => get<SourceSystemDTO[]>("/sources"),

  marketObservations: () => get<MarketObsDTO[]>("/market/observations"),

  screenOrders: () => get<ScreenOrderObservationDTO[]>("/portfolio/screen-orders"),

  pnlSnapshots: () => get<PortfolioPnlSnapshotDTO[]>("/portfolio/pnl-snapshots"),

  portfolioLiveSummary: () => get<PortfolioLiveSummaryDTO>("/portfolio/live-summary"),

  flowObservations: () => get<FlowObsDTO[]>("/physical/flows"),

  storageObservations: () => get<StorageObsDTO[]>("/storage/observations"),

  lngObservations: () => get<LngObsDTO[]>("/lng/observations"),

  fxRates: () => get<FxRateDTO[]>("/market/fx"),

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

  routeCandidates: () => get<{ route_candidates: RouteCandidateDTO[] }>("/route-cost/route-candidates"),

  compareEasingtonOptions: (body: EasingtonContractRequest) =>
    post<EasingtonOptionsResultDTO>("/route-cost/uk/easington/options", body),

  markEasingtonLivePnl: (contract: EasingtonContractRequest, marks: LiveMarketMarkDTO[]) =>
    post<LivePnlResultDTO>("/route-cost/uk/easington/live-pnl", { contract, marks }),

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
