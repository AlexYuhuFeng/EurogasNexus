/** Typed API client for /api. All data flows through backend API only. */

const DEFAULT_BROWSER_BASE = "/api";
const DEFAULT_DESKTOP_BASE = "http://127.0.0.1:8000/api";
const REFERENCE_NETWORK_READ_LIMIT = "2000";
export const API_BASE_STORAGE_KEY = "eurogas.settings.api_base_url";
export const API_TOKEN_STORAGE_KEY = "eurogas.settings.api_token";
export const PRINCIPAL_STORAGE_KEY = "eurogas.settings.operator_principal";
const envBase = import.meta.env.VITE_EUROGAS_API_BASE_URL as string | undefined;
const isDesktopShell =
  "__TAURI_INTERNALS__" in window ||
  window.location.protocol === "tauri:" ||
  window.location.hostname === "tauri.localhost";

let desktopSessionToken = "";
let currentCsrfToken = "";

export function setDesktopSessionToken(token: string, csrfToken = ""): void {
  desktopSessionToken = token.trim();
  currentCsrfToken = csrfToken.trim();
}

export function clearDesktopSession(): void {
  desktopSessionToken = "";
  currentCsrfToken = "";
}

export function configuredApiToken(): string {
  try {
    return (localStorage.getItem(API_TOKEN_STORAGE_KEY) ?? "").trim();
  } catch {
    return "";
  }
}

export function configuredOperatorPrincipal(): string {
  try {
    return (localStorage.getItem(PRINCIPAL_STORAGE_KEY) ?? "").trim();
  } catch {
    return "";
  }
}

export function saveApiAuth(token: string, principal: string): void {
  const normalizedToken = token.trim();
  const normalizedPrincipal = principal.trim();
  try {
    if (normalizedToken) {
      localStorage.setItem(API_TOKEN_STORAGE_KEY, normalizedToken);
    } else {
      localStorage.removeItem(API_TOKEN_STORAGE_KEY);
    }
    if (normalizedPrincipal) {
      localStorage.setItem(PRINCIPAL_STORAGE_KEY, normalizedPrincipal);
    } else {
      localStorage.removeItem(PRINCIPAL_STORAGE_KEY);
    }
  } catch {
    // storage unavailable: auth simply stays unconfigured
  }
}

export function authHeaders(): Record<string, string> {
  const headers: Record<string, string> = {};
  const token = desktopSessionToken || configuredApiToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const principal = configuredOperatorPrincipal();
  if (principal) headers["X-Eurogas-Principal"] = principal;
  if (currentCsrfToken) headers["X-Eurogas-CSRF"] = currentCsrfToken;
  return headers;
}

function requestInit(init: RequestInit = {}): RequestInit {
  return {
    ...init,
    credentials: "include",
    headers: { ...authHeaders(), ...(init.headers as Record<string, string> | undefined) },
  };
}

export function defaultApiBaseUrl(): string {
  return (envBase?.trim() || (isDesktopShell ? DEFAULT_DESKTOP_BASE : DEFAULT_BROWSER_BASE)).replace(/\/$/, "");
}

export function normalizeApiBaseUrl(value: string): string {
  const trimmed = value.trim().replace(/\/$/, "");
  if (trimmed === "/api") return trimmed;

  let parsed: URL;
  try {
    parsed = new URL(trimmed);
  } catch {
    throw new Error("Backend API URL must be /api or an absolute URL ending in /api.");
  }
  const loopback = parsed.hostname === "127.0.0.1" || parsed.hostname === "localhost";
  if (parsed.protocol !== "https:" && !(loopback && parsed.protocol === "http:")) {
    throw new Error("Remote backend API URLs must use HTTPS.");
  }
  if (!parsed.pathname.replace(/\/$/, "").endsWith("/api")) {
    throw new Error("Backend API URL must end in /api.");
  }
  parsed.search = "";
  parsed.hash = "";
  return parsed.toString().replace(/\/$/, "");
}

export function configuredApiBaseUrl(): string {
  const fallback = defaultApiBaseUrl();
  try {
    const stored = localStorage.getItem(API_BASE_STORAGE_KEY);
    return stored ? normalizeApiBaseUrl(stored) : fallback;
  } catch {
    return fallback;
  }
}

export function saveApiBaseUrl(value: string): string {
  const normalized = normalizeApiBaseUrl(value);
  localStorage.setItem(API_BASE_STORAGE_KEY, normalized);
  return normalized;
}

export function clearApiBaseUrl(): string {
  localStorage.removeItem(API_BASE_STORAGE_KEY);
  return defaultApiBaseUrl();
}

interface DesktopDeploymentConfig {
  schema_version: number;
  role: "Client";
  api_base_url: string;
}

export async function hydrateApiBaseUrlFromDesktopDeployment(): Promise<string> {
  if (!isDesktopShell || localStorage.getItem(API_BASE_STORAGE_KEY)) {
    return configuredApiBaseUrl();
  }
  try {
    const { invoke } = await import("@tauri-apps/api/core");
    const config = await invoke<DesktopDeploymentConfig | null>("read_deployment_config");
    return config?.api_base_url ? saveApiBaseUrl(config.api_base_url) : configuredApiBaseUrl();
  } catch {
    return configuredApiBaseUrl();
  }
}

function apiUrl(path: string): string {
  return apiUrlForBase(configuredApiBaseUrl(), path);
}

function apiUrlForBase(base: string, path: string): string {
  return new URL(`${base}${path}`, window.location.origin).toString();
}

export interface EventStreamHandle {
  close: () => void;
}

export function openEventStream(
  path: string,
  handlers: Record<string, (data: unknown) => void>,
  onStatus?: (status: "open" | "error") => void,
): EventStreamHandle {
  // Native EventSource cannot set Authorization headers, so the public API
  // token travels as the documented `api_key` query parameter on SSE only.
  const url = new URL(apiUrl(path), window.location.origin);
  const token = configuredApiToken();
  if (token) url.searchParams.set("api_key", token);
  const source = new EventSource(url.toString(), { withCredentials: true });
  source.onopen = () => onStatus?.("open");
  source.onerror = () => onStatus?.("error");
  for (const [event, handler] of Object.entries(handlers)) {
    source.addEventListener(event, (message: MessageEvent) => {
      let data: unknown = message.data;
      try {
        data = JSON.parse(message.data as string);
      } catch {
        // keep raw text for non-JSON events
      }
      handler(data);
    });
  }
  return { close: () => source.close() };
}

export interface ApiMeta {
  research_only: boolean;
  human_review_required: boolean;
  source_references: string[];
  warnings: string[];
  source_posture_summary?: SourcePostureSummaryDTO;
}

export interface ApiResponse<T> {
  data: T;
  meta: ApiMeta;
}

export interface HealthDTO {
  status: string;
  version: string;
  profile: string;
}

function errorDetail(payload: unknown, fallback: string): string {
  if (!payload || typeof payload !== "object" || !("detail" in payload)) return fallback;
  const detail = (payload as { detail: unknown }).detail;
  if (typeof detail === "string") return detail;
  if (detail && typeof detail === "object") {
    const structured = detail as { message?: unknown; code?: unknown };
    if (typeof structured.message === "string") return structured.message;
    if (typeof structured.code === "string") return structured.code;
  }
  return fallback;
}

async function parseResponse<T>(res: Response): Promise<T> {
  const body = await res.text();
  const contentType = res.headers.get("content-type") ?? "";
  const looksJson = contentType.includes("json") || body.trimStart().startsWith("{") || body.trimStart().startsWith("[");
  let payload: unknown = null;
  if (looksJson && body) {
    try {
      payload = JSON.parse(body);
    } catch {
      throw new Error(`API ${res.status}: invalid JSON response.`);
    }
  }
  if (!res.ok) {
    const detail = errorDetail(payload, res.statusText || "request failed");
    throw new Error(`API ${res.status}: ${detail}`);
  }
  if (!looksJson || payload === null) {
    throw new Error(`API ${res.status}: expected JSON but received ${contentType || "an unknown content type"}.`);
  }
  return payload as T;
}

export async function testApiBaseUrl(value: string): Promise<HealthDTO> {
  const normalized = normalizeApiBaseUrl(value);
  return parseResponse<HealthDTO>(
    await fetch(apiUrlForBase(normalized, "/health"), requestInit()),
  );
}

async function get<T>(path: string, params?: Record<string, string>): Promise<ApiResponse<T>> {
  const url = new URL(apiUrl(path));
  if (params) {
    Object.entries(params).forEach(([k, v]) => { if (v) url.searchParams.set(k, v); });
  }
  const res = await fetch(url.toString(), requestInit());
  return parseResponse<ApiResponse<T>>(res);
}

async function patch<T>(path: string, body: unknown): Promise<ApiResponse<T>> {
  const response = await fetch(apiUrl(path), requestInit({
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  }));
  return parseResponse<ApiResponse<T>>(response);
}

async function put<T>(path: string, body: unknown): Promise<ApiResponse<T>> {
  const response = await fetch(apiUrl(path), requestInit({
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  }));
  return parseResponse<ApiResponse<T>>(response);
}

async function post<T>(path: string, body: unknown): Promise<ApiResponse<T>> {
  const res = await fetch(apiUrl(path), requestInit({
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  }));
  return parseResponse<ApiResponse<T>>(res);
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
  operational_status: string; workflow_ready: boolean;
  effective_source_system: string; effective_record_count: number;
  effective_last_success_at_utc: string | null;
  entitlement_scope: string; freshness_expectation_minutes: number;
  credential_requirements: string[]; credential_provider_id: string | null;
  credential_state: string; credential_status: string | null;
  credential_last_tested_at_utc: string | null; credential_last_test_status: string | null;
  preview_substitute_source_system: string | null;
  preview_substitute_status: string | null;
  preview_substitute_record_count: number;
  last_success_at_utc: string | null; last_failure_at_utc: string | null;
  last_ingestion_status: string | null; last_ingestion_message: string | null;
  diagnostics: string[]; export_restrictions: string[];
  certification_stage: string; certification_allows_live: boolean;
  scheduler_enabled: boolean; circuit_state: string | null;
  next_run_at_utc: string | null; consecutive_failures: number;
  freshness_state: string | null; freshness_status?: string | null;
  source_age_seconds: number | null;
  certification_state: string | null; entitlement_state: string | null;
  adapter_version: string | null;
}

export interface SourceCategoryPostureDTO {
  category: string;
  category_label: string;
  registered_sources: number;
  active_sources: number;
  workflow_ready_sources: number;
  sources_needing_attention: number;
  missing_credentials: number;
  preview_substitutes_active: number;
  runtime_records: number;
  next_action: string;
}

export interface SourcePostureSummaryDTO {
  totals: {
    registered_sources: number;
    active_sources: number;
    workflow_ready_sources: number;
    sources_needing_attention: number;
    missing_credentials: number;
    preview_substitutes_active: number;
    runtime_records: number;
  };
  categories: SourceCategoryPostureDTO[];
}

type SourceSystemWire = Partial<SourceSystemDTO> & {
  source_id?: string;
  source_system?: string;
  datasets?: unknown;
  credential_requirements?: unknown;
  diagnostics?: unknown;
  export_restrictions?: unknown;
  certification_stage?: unknown;
  certification_allows_live?: unknown;
};

const SOURCE_CATEGORY_BY_SYSTEM: Record<string, string> = {
  ARGUS: "price",
  BBL: "tariff",
  CNMCENAGAS: "tariff",
  DEEPSEEK: "ai",
  ECB: "fx",
  EEX: "price",
  EEX_SIM: "price",
  ENTSOG: "infrastructure",
  FLUXYSBELGIUM: "tariff",
  GERMANTSO: "tariff",
  GIE: "infrastructure",
  GTS: "tariff",
  ICE_OCM: "price",
  ICE_OCM_SIM: "price",
  ICIS: "price",
  ICIS_SIM: "price",
  IUK: "tariff",
  KPLER: "price",
  NATRAN: "tariff",
  NATIONALGASNTS: "tariff",
  NATIONAL_GAS_NTS: "tariff",
  PLATTS: "price",
  TRAYPORT: "price",
  TRAYPORT_SIM: "price",
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

const SIMULATED_PRICE_SOURCE_SYSTEMS = ["EEX_Sim", "ICE_OCM_Sim", "Trayport_Sim", "ICIS_Sim"];

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
  const previewSubstituteStatus = raw.preview_substitute_status ?? null;
  const previewSubstituteRecordCount = Number(raw.preview_substitute_record_count ?? 0);
  const operationalStatus = raw.operational_status ||
    (connectivityStatus === "active"
      ? "active"
      : previewSubstituteStatus === "active" && previewSubstituteRecordCount > 0
        ? "active_simulated"
        : connectivityStatus);
  const workflowReady = raw.workflow_ready ?? ["active", "active_simulated"].includes(operationalStatus);

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
    operational_status: operationalStatus,
    workflow_ready: workflowReady,
    effective_source_system: raw.effective_source_system ??
      (operationalStatus === "active_simulated"
        ? raw.preview_substitute_source_system ?? sourceSystem
        : sourceSystem),
    effective_record_count: Number(raw.effective_record_count ??
      (operationalStatus === "active_simulated" ? previewSubstituteRecordCount : liveRecordCount)),
    effective_last_success_at_utc: raw.effective_last_success_at_utc ?? raw.last_success_at_utc ?? null,
    entitlement_scope: raw.entitlement_scope || (credentialRequired ? "licensed" : "public"),
    freshness_expectation_minutes: Number(raw.freshness_expectation_minutes ?? 0),
    credential_requirements: credentialRequirements,
    credential_provider_id: raw.credential_provider_id ?? (credentialRequired ? sourceSystem : null),
    credential_state: credentialState,
    credential_status: raw.credential_status ?? null,
    credential_last_tested_at_utc: raw.credential_last_tested_at_utc ?? null,
    credential_last_test_status: raw.credential_last_test_status ?? null,
    preview_substitute_source_system: raw.preview_substitute_source_system ?? null,
    preview_substitute_status: previewSubstituteStatus,
    preview_substitute_record_count: previewSubstituteRecordCount,
    last_success_at_utc: raw.last_success_at_utc ?? null,
    last_failure_at_utc: raw.last_failure_at_utc ?? null,
    last_ingestion_status: raw.last_ingestion_status ?? null,
    last_ingestion_message: raw.last_ingestion_message ?? null,
    certification_stage:
      typeof raw.certification_stage === "string" && raw.certification_stage.trim()
        ? raw.certification_stage.trim()
        : "unverified",
    certification_allows_live: Boolean(raw.certification_allows_live),
    diagnostics: diagnostics.length > 0
      ? diagnostics
      : liveRecordCount > 0
        ? ["live_records_available"]
        : credentialState === "missing"
          ? ["credential_missing"]
          : ["no_records_in_runtime_db"],
    export_restrictions: asStringArray(raw.export_restrictions),
    scheduler_enabled: Boolean(raw.scheduler_enabled),
    circuit_state: typeof raw.circuit_state === "string" ? raw.circuit_state : null,
    next_run_at_utc: typeof raw.next_run_at_utc === "string" ? raw.next_run_at_utc : null,
    consecutive_failures: Number(raw.consecutive_failures ?? 0),
    freshness_state: typeof raw.freshness_state === "string" ? raw.freshness_state : null,
    source_age_seconds: typeof raw.source_age_seconds === "number" ? raw.source_age_seconds : null,
    certification_state: typeof raw.certification_state === "string" ? raw.certification_state : null,
    entitlement_state: typeof raw.entitlement_state === "string" ? raw.entitlement_state : null,
    adapter_version: typeof raw.adapter_version === "string" ? raw.adapter_version : null,
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
  observed_at_utc?: string; source_system?: string; source_reference?: string;
  source_record_id?: string | null; metadata_json?: Record<string, unknown>;
  freshness?: string; quality_score?: number; research_only?: boolean;
}

export interface NormalizedMarketObsDTO extends MarketObsDTO {
  hub: string;
  tenor: string;
  is_gas_price: boolean;
  price_gbp_mwh: number | null;
}

export interface MarketSpreadDTO {
  spread_id: string; name: string; from_venue: string; to_venue: string;
  from_hub: string; to_hub: string; spread_eur_mwh: number; period: string;
}

export interface ReviewDecisionDTO {
  decision_id: string; entity_type: string; entity_id: string;
  actor: string; decision: string; note: string | null; created_at_utc: string;
}

export interface ReviewDecisionInputDTO {
  entity_type: "intraday_opportunity" | "strategy_run" | "generated_report";
  entity_id: string; actor: string;
  decision: "accepted" | "rejected" | "needs_attention";
  note?: string | null;
}

export interface PipelineHealthSourceDTO {
  source_name: string; status: string;
  started_at_utc: string; finished_at_utc: string | null;
  consecutive_failures: number;
}

export interface PipelineHealthDTO {
  generated_at_utc: string;
  sources: PipelineHealthSourceDTO[];
  quote_freshness: Record<string, {
    count_recent_5m: number;
    latest_observed_at_utc: string | null;
  }>;
  latest_opportunity_detected_at_utc: string | null;
  open_alerts: number;
}

export interface MarketQuoteDTO {
  quote_id: string; source_system: string; source_record_id?: string | null;
  venue: string; instrument_id: string; hub: string; product: string;
  delivery_start_utc: string; delivery_end_utc: string;
  bid_price?: number | null; ask_price?: number | null; last_price?: number | null;
  bid_quantity_mwh?: number | null; ask_quantity_mwh?: number | null;
  currency: string; unit: string; observed_at_utc: string; received_at_utc: string;
  source_reference: string; freshness: string; quality_score: number;
  simulated: boolean; metadata_json?: Record<string, unknown>;
}

export interface IntradayOpportunityDTO {
  opportunity_id: string; scan_id: string; opportunity_type: string; status: string;
  buy_quote_id: string; sell_quote_id: string; route_id: string; route_name: string;
  buy_venue: string; sell_venue: string; buy_hub: string; sell_hub: string;
  product: string; delivery_start_utc: string; delivery_end_utc: string;
  comparison_currency: string; comparison_unit: string;
  buy_ask: number; sell_bid: number; gross_spread: number;
  route_cost?: number | null; trading_cost: number; risk_buffer: number;
  net_margin?: number | null; max_quantity_mwh?: number | null;
  indicative_net_value?: number | null; quote_age_seconds: number;
  confidence_score: number; cost_components: Array<Record<string, unknown>>;
  source_refs: string[]; assumptions: string[]; missing_inputs: string[]; warnings: string[];
  detected_at_utc: string; valid_until_utc: string; simulated: boolean;
  human_review_required: boolean;
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
  dtmi_twh?: number | null; period_start_utc?: string; period_end_utc?: string; observed_at_utc?: string;
  source_system?: string; source_reference?: string; freshness?: string;
}

export interface CredentialProviderDTO {
  provider_id: string; display_name: string; credential_required: boolean;
  default_model?: string | null;
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

export interface MonitoringAlertDTO {
  alert_id: string; fingerprint: string; category: string; alert_type: string;
  severity: "info" | "warning" | "critical";
  status: "open" | "acknowledged" | "resolved";
  title_en: string; title_zh_cn: string; message_en: string; message_zh_cn: string;
  entity_type: string; entity_id: string; event_time_utc: string;
  detected_at_utc: string; updated_at_utc: string;
  acknowledged_at_utc: string | null; resolved_at_utc: string | null;
  occurrence_count: number; evidence_snapshot: Record<string, unknown>;
  source_refs: string[]; warnings: string[]; llm_provider_id: string;
  llm_status: string; llm_summary_en: string | null; llm_summary_zh_cn: string | null;
  llm_last_attempt_at_utc: string | null; simulated: boolean;
  human_review_required: boolean;
}

export interface MonitoringSummaryDTO {
  open_count: number; acknowledged_count: number; critical_count: number;
  warning_count: number; info_count: number; llm_pending_count: number;
  simulated_count: number;
}

export interface MonitoringAnalysisDTO {
  analysis_id: string | null; alert_id: string; provider_id: string;
  provider_status: string; answer: string | null; model: string; language: string;
  source_refs: string[]; warnings: string[]; human_review_required: boolean;
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
  variable_cost_gbp_mwh?: number; regas_fee_gbp_mwh?: number; fuel_loss_allowance_pct?: number;
  notes?: string | null;
  research_only?: boolean; human_review_required?: boolean;
}
export type UpstreamContractInputDTO = Omit<UpstreamContractDTO, "updated_at_utc" | "research_only" | "human_review_required"> & {
  notes?: string | null;
};
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
  fuel_loss_allowance_pct?: number; screen_sale_cash_lag_days?: number | null;
  delivery_tolerance_pct?: number | null; nomination_tolerance_pct?: number | null;
  tolerance_risk_allowance_gbp_mwh?: number; upstream_payment_lag_days?: number;
  settlement_frequency?: string; required_tso_access?: string[];
  accessible_tsos?: string[] | null; pricing_method?: string; source_refs?: string[];
}

export interface PortfolioSaleOptionDTO {
  option_id: string; label: string; delivery_mode: string; target_point_name: string;
  route_topology_kind?: "LOCAL_MARKET_DISPOSITION" | "NETWORK_ROUTE";
  sale_price_gbp_mwh: number; route_cost_gbp_mwh?: number;
  sale_price_source_system?: string | null; sale_price_source_reference?: string | null;
  sale_price_observed_at_utc?: string | null; sale_price_freshness?: string | null;
  sale_price_quality_score?: number | null; sale_price_simulated?: boolean;
  sale_price_source_family?: string | null;
  capacity_limit_mwh_per_day?: number | null; screen_sale_cash_lag_days?: number;
  required_tso_access?: string[]; source_refs?: string[];
  eligible_resource_ids?: string[];
}

export interface PortfolioOptimizationRequestDTO {
  portfolio_id: string; resources: PortfolioResourceDTO[]; sale_options: PortfolioSaleOptionDTO[];
  annual_financing_rate_pct?: number; objective?: string; research_only?: boolean;
}

export interface PortfolioOptimizationResultDTO {
  portfolio_id: string; status: string; algorithm: string; optimality: string;
  total_allocated_mwh_per_day: number;
  total_unallocated_mwh_per_day: number; total_net_pnl_gbp_per_day: number;
  allocations: Array<{
    resource_id: string; option_id: string; allocated_quantity_mwh_per_day: number;
    gross_sale_price_gbp_mwh: number; total_cost_gbp_mwh: number;
    early_cash_value_gbp_mwh: number; net_margin_gbp_mwh: number;
    net_pnl_gbp_per_day: number; warnings: string[];
  }>;
  missing_inputs: string[]; assumptions: string[]; warnings: string[]; source_refs: string[];
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
  run_id: string;
  strategy_id: string; strategy_name: string; run_mode: string; status: string;
  weighted_score: number; day_ahead_average_gbp_mwh: number | null;
  intraday_average_gbp_mwh: number | null;
  intraday_vs_day_ahead_spread_gbp_mwh: number | null;
  allocation_targets: StrategyAllocationTargetDTO[];
  missing_inputs: string[]; warnings: string[]; source_refs: string[];
  candidate_action_for_review: string;
  paper_pnl_gbp: number; cumulative_pnl_gbp: number; hit: boolean;
  research_only: boolean; human_review_required: boolean;
}

export interface StrategyRunDTO {
  run_id: string; strategy_id: string; strategy_name?: string | null;
  strategy_version_id?: string | null;
  run_type?: string | null;
  run_mode: string; status: string;
  requested_at_utc?: string | null;
  started_at_utc: string; finished_at_utc: string | null;
  completed_at_utc?: string | null;
  evaluation_start_utc?: string | null;
  evaluation_end_utc?: string | null;
  data_cutoff_utc?: string | null;
  dataset_snapshot_id?: string | null;
  manifest_json?: Record<string, unknown> | null;
  manifest_hash?: string | null;
  engine_version?: string | null;
  backtest_engine_version?: string | null;
  experiment_id?: string | null;
  application_version?: string | null;
  git_commit_sha?: string | null;
  strategy_schema_version?: string | null;
  run_schema_version?: string | null;
  deterministic_seed?: string | null;
  requested_by?: string | null;
  trigger_type?: string | null;
  correlation_request_id?: string | null;
  backtest_metrics?: BacktestMetricSetDTO | null;
  paper_pnl_gbp: number | null; cumulative_pnl_gbp: number | null; hit: boolean | null;
  weighted_score: number | null;
  day_ahead_average_gbp_mwh?: number | null;
  intraday_average_gbp_mwh?: number | null;
  intraday_vs_day_ahead_spread_gbp_mwh?: number | null;
  candidate_action_for_review?: string | null;
  allocation_targets: StrategyAllocationTargetDTO[];
  missing_inputs: string[]; warnings: string[]; source_refs: string[];
  research_only: boolean; human_review_required: boolean;
}

export interface StrategySummaryDTO {
  strategy_id: string | null; run_mode: string | null; run_count: number;
  total_paper_pnl_gbp: number; cumulative_pnl_gbp: number; hit_rate: number;
  max_drawdown_gbp: number; first_started_at_utc: string | null;
  last_started_at_utc: string | null; latest_status: string | null;
}

export interface StrategyRegistryParameterDTO {
  parameter_id: string; name: string; type: string; unit?: string | null;
  description?: string; min_value?: number | null; max_value?: number | null;
  allowed_values?: string[]; optimization_allowed?: boolean;
  sensitivity_allowed?: boolean;
}

export interface StrategyRegistryComponentDTO {
  component_id: string; component_type: string; role?: string; hubs?: string[];
  tenors?: string[]; price_basis?: string | null; resource_id?: string | null;
  parameter_refs?: string[]; required_evidence?: string[];
  extension_json?: Record<string, unknown>;
}

export interface StrategyVersionDefinitionDTO {
  components?: StrategyRegistryComponentDTO[];
  parameter_definitions?: StrategyRegistryParameterDTO[];
  parameter_values?: Record<string, unknown>;
  risk_controls?: Record<string, unknown>;
  economic_assumptions?: Record<string, unknown>;
  data_requirements?: Record<string, unknown>;
  evaluation_windows?: Record<string, unknown>[];
}

export interface StrategyDTO {
  strategy_id: string; name: string; description: string;
  lifecycle_status: string; current_version_id: string | null;
  created_by: string; created_at_utc: string; updated_at_utc: string;
  retired_at_utc: string | null; tags: string[]; research_only: boolean;
}

export interface StrategyVersionDTO {
  strategy_version_id: string; strategy_id: string; version_number: number;
  schema_version: string; status: string; hypothesis: string;
  definition_json: Record<string, unknown>; parent_version_id: string | null;
  created_by: string; created_at_utc: string; frozen_at_utc: string | null;
  content_hash: string; research_only: boolean;
}

export interface StrategyCreateInputDTO {
  strategy_id?: string; name: string; description?: string; tags?: string[];
}

export interface StrategyMetadataUpdateInputDTO {
  name?: string | null; description?: string | null; tags?: string[] | null;
}

export interface StrategyVersionCreateInputDTO {
  hypothesis?: string; definition: StrategyVersionDefinitionDTO;
  strategy_name?: string | null;
  run_mode?: string;
  resource_contexts?: Record<string, unknown>[];
  price_observations?: Record<string, unknown>[];
  existing_shadow_pnl_gbp?: number;
}

export interface StrategyForkInputDTO {
  hypothesis?: string | null; definition?: StrategyVersionDefinitionDTO | null;
}

export interface StrategyRunCreateInputDTO {
  strategy_version_id: string;
  run_type?: string;
  deterministic_seed?: string | null;
  trigger_type?: string;
  correlation_request_id?: string | null;
  evaluation_period_start_utc?: string | null;
  evaluation_period_end_utc?: string | null;
  decision_schedule?: Record<string, unknown> | null;
  economic_assumptions?: Record<string, unknown> | null;
  parameter_values?: Record<string, unknown>;
  experiment_id?: string | null;
}

export interface BacktestMetricSetDTO {
  evaluation_count: number;
  candidate_decision_count: number;
  blocked_decision_count: number;
  skipped_decision_count: number;
  data_coverage: number;
  gross_indicative_pnl_gbp: number;
  modeled_costs_gbp: number;
  net_indicative_pnl_gbp: number;
  max_drawdown_gbp: number;
  peak_timestamp_utc?: string | null;
  trough_timestamp_utc?: string | null;
  recovery_timestamp_utc?: string | null;
  pnl_volatility_gbp?: number | null;
  worst_event_pnl_gbp?: number | null;
  best_event_pnl_gbp?: number | null;
  max_exposure_mwh_per_day: number;
  average_exposure_mwh_per_day: number;
  hit_ratio?: number | null;
  turnover?: number | null;
  average_margin_gbp_mwh?: number | null;
  average_modeled_cost_gbp_mwh?: number | null;
  sharpe_ratio?: number | null;
  sortino_ratio?: number | null;
  risk_metric_not_applicable_reasons?: string[];
  warning_counts?: Record<string, number>;
  temporal_integrity?: string;
}

export interface BacktestDecisionEventDTO {
  event_id: string; run_id: string; experiment_id?: string | null;
  decision_sequence: number; decision_time_utc: string;
  gas_day: string; gas_day_start_utc: string; gas_day_end_utc: string;
  outcome: string; candidate_action_for_review?: string | null;
  weighted_score?: number | null;
  day_ahead_average_gbp_mwh?: number | null;
  intraday_average_gbp_mwh?: number | null;
  intraday_vs_day_ahead_spread_gbp_mwh?: number | null;
  allocation_targets: Record<string, unknown>[];
  gross_indicative_pnl_gbp: number;
  modeled_costs_gbp: number;
  net_indicative_pnl_gbp: number;
  cumulative_net_indicative_pnl_gbp: number;
  ending_exposure_mwh_per_day: number;
  missing_inputs: string[]; warnings: string[];
  price_evidence_refs: string[]; fx_evidence_refs: string[];
  cost_evidence_refs: string[]; resource_evidence_refs: string[];
  cost_trace: Record<string, unknown>[];
  attribution: Record<string, unknown>[];
  research_only: boolean; human_review_required: boolean;
}

export interface BacktestSeriesPointDTO {
  series_point_id: string; run_id: string;
  decision_sequence: number; decision_time_utc: string; gas_day: string;
  gross_indicative_pnl_gbp: number; modeled_costs_gbp: number;
  net_indicative_pnl_gbp: number; cumulative_net_indicative_pnl_gbp: number;
  ending_exposure_mwh_per_day: number; drawdown_gbp?: number;
  research_only: boolean;
}

export interface BacktestAttributionDTO {
  attribution_id: string; run_id: string; event_id: string;
  decision_time_utc: string; dimension: string; key: string;
  gross_indicative_pnl_gbp: number; modeled_costs_gbp: number;
  net_indicative_pnl_gbp: number; quantity_mwh_per_day: number | null;
  source_refs: string[]; research_only: boolean;
}

export interface BacktestExperimentDTO {
  experiment_id: string; strategy_id: string;
  base_strategy_version_id: string; name: string; hypothesis: string;
  experiment_type: string; evaluation_period: Record<string, unknown>;
  run_ids: string[]; status: string; created_by: string;
  created_at_utc: string; updated_at_utc: string; research_only: boolean;
}

export interface ShadowMonitorDTO {
  shadow_monitor_id: string; strategy_id: string; strategy_version_id: string;
  baseline_run_id?: string | null; state: string;
  schedule: Record<string, unknown>; created_by: string;
  created_at_utc: string; activated_at_utc?: string | null;
  paused_at_utc?: string | null; retired_at_utc?: string | null;
  last_evaluation_at_utc?: string | null; next_evaluation_at_utc?: string | null;
  latest_evaluation_id?: string | null; consecutive_failures: number;
  health_state: string; cumulative_shadow_pnl_gbp: number;
  current_exposure_mwh_per_day: number; research_only: boolean;
}

export interface ShadowMonitorCreateInputDTO {
  strategy_version_id: string; baseline_run_id?: string | null;
  schedule: Record<string, unknown>; activate?: boolean;
}

export interface ShadowEvaluationDTO {
  shadow_evaluation_id: string; shadow_monitor_id: string;
  strategy_version_id: string; scheduled_for_utc: string;
  started_at_utc?: string | null; decision_time_utc?: string | null;
  completed_at_utc?: string | null; state: string;
  gas_day?: string | null; gas_day_start_utc?: string | null;
  gas_day_end_utc?: string | null; snapshot_id?: string | null;
  candidate_id?: string | null; price_evidence_refs: string[];
  fx_evidence_refs: string[]; resource_evidence_refs: string[];
  source_systems: string[]; freshness: Record<string, unknown>[];
  missing_inputs: string[]; warnings: string[];
  result?: Record<string, unknown> | null; failure_class?: string | null;
  retry_count: number; research_only: boolean; human_review_required: boolean;
  risk_checks?: ShadowRiskCheckDTO[];
  candidate?: Record<string, unknown> | null;
}

export interface ShadowRiskCheckDTO {
  risk_check_id: string; shadow_evaluation_id: string;
  control_id: string; observed_value?: number | null;
  limit_value?: number | null; state: string; severity: string; explanation: string;
}

export interface ShadowAlertDTO {
  alert_id: string; shadow_monitor_id: string;
  shadow_evaluation_id?: string | null; alert_type: string; severity: string;
  state: string; fingerprint: string; summary: string; evidence_refs: string[];
  first_seen_at_utc: string; last_seen_at_utc: string;
  occurrence_count: number; acknowledged_at_utc?: string | null;
  acknowledged_by?: string | null; resolved_at_utc?: string | null;
  research_only: boolean;
}

export interface ShadowDriftDTO {
  drift_snapshot_id: string; shadow_monitor_id: string;
  baseline_run_id?: string | null; observation_window: Record<string, unknown>;
  state: string; metrics: Record<string, unknown>[]; sample_size: number;
  explanation: string; created_at_utc: string;
}

export interface ShadowRuntimeStatusDTO {
  scheduler: string; last_heartbeat_at_utc?: string | null;
  active_monitors: number; pending_evaluations: number;
  failed_evaluations_24h: number; duplicate_claims_prevented: number;
}

export interface BacktestExperimentCreateInputDTO {
  experiment_id?: string; strategy_id: string;
  base_strategy_version_id: string; name: string; hypothesis?: string;
  experiment_type?: string;
  evaluation_period_start_utc: string; evaluation_period_end_utc: string;
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

export interface ResearchFeatureDTO {
  feature_id: string;
  content_hash: string;
  status: string;
  definition: {
    feature_id: string;
    name: string;
    description: string;
    category: string;
    input_dependencies: string[];
    output_unit: string;
    frequency: string;
    availability_class: string;
    transformation: string;
    transformation_version: string;
    missing_data_policy: string;
    point_in_time_policy: string;
    future_knowledge_policy: string;
  };
}

export interface ResearchTargetDTO {
  target_id: string;
  content_hash: string;
  status: string;
  definition: {
    target_id: string;
    name: string;
    description: string;
    target_type: string;
    entity_type: string;
    entity_id: string;
    metric: string;
    horizon: string;
    target_window: string;
    unit: string;
    aggregation: string;
    label_calculation: string;
    availability_delay: string;
  };
}

export interface ResearchDatasetDTO {
  dataset_snapshot_id: string;
  dataset_spec_id: string;
  source_cutoff_utc: string;
  row_count: number;
  column_count: number;
  coverage: number;
  temporal_integrity: string;
  status: string;
  created_at_utc: string;
}

export interface ResearchCapabilityDTO {
  name: string;
  description: string;
  read_write_class: string;
  deterministic: boolean;
  side_effect_class: string;
  required_permission: string;
  required_entitlement?: string | null;
  provenance_behavior: string;
  timeout_seconds: number;
}

export const api = {
  health: async () =>
    parseResponse<HealthDTO>(await fetch(apiUrl("/health"), requestInit())),

  nodes: (params?: { country?: string; node_type?: string }) =>
    get<NodeDTO[]>("/reference-network/nodes", {
      limit: REFERENCE_NETWORK_READ_LIMIT,
      ...params,
    }),

  edges: (params?: { from_node_id?: string; to_node_id?: string }) =>
    get<EdgeDTO[]>("/reference-network/edges", {
      limit: REFERENCE_NETWORK_READ_LIMIT,
      ...params,
    }),

  facilities: (params?: { facility_type?: string; country?: string }) =>
    get<FacilityDTO[]>("/reference-network/facilities", {
      limit: REFERENCE_NETWORK_READ_LIMIT,
      ...params,
    }),

  marketHubs: () => get<MarketHubDTO[]>("/reference-network/market-hubs", {
    limit: REFERENCE_NETWORK_READ_LIMIT,
  }),

  tsoAccess: (params?: {
    point_id?: string; country?: string; operator_key?: string; direction?: string;
  }) => get<TsoAccessPointDTO[]>("/reference-network/tso-access", {
    limit: REFERENCE_NETWORK_READ_LIMIT,
    ...params,
  }),

  sources: () => get<SourceSystemWire[]>("/sources").then(normalizeSourcesResponse),

  marketObservations: () => get<MarketObsDTO[]>("/market/observations"),

  normalizedMarketObservations: () =>
    get<NormalizedMarketObsDTO[]>("/market/normalized", { limit: "500" }),

  marketSpreads: () => get<MarketSpreadDTO[]>("/market/spreads"),

  reviewDecisions: (params?: { entity_type?: string; entity_id?: string; limit?: string }) =>
    get<ReviewDecisionDTO[]>("/review/decisions", params),

  recordReviewDecision: (body: ReviewDecisionInputDTO) =>
    post<ReviewDecisionDTO>("/review/decisions", body),

  pipelineHealth: () => get<PipelineHealthDTO>("/runtime/pipeline-health"),

  marketQuotes: () => get<MarketQuoteDTO[]>("/market/quotes", { limit: "500" }),

  intradayOpportunities: () =>
    get<IntradayOpportunityDTO[]>("/market/opportunities", { limit: "100" }),

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
    fetch(apiUrl(`/credentials/${providerId}`), requestInit({
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    })).then((res) => parseResponse<ApiResponse<CredentialProviderDTO>>(res)),

  testCredentialConnection: (providerId: string) =>
    post<CredentialProviderDTO & { connection_status: string; connection_error_code: string | null }>(
      `/credentials/${providerId}/connection-test`,
      {},
    ),

  monitoringAlerts: () =>
    get<MonitoringAlertDTO[]>("/monitoring/alerts", { limit: "100" }),

  monitoringSummary: () => get<MonitoringSummaryDTO>("/monitoring/summary"),

  acknowledgeMonitoringAlert: (alertId: string) =>
    post<MonitoringAlertDTO>(`/monitoring/alerts/${encodeURIComponent(alertId)}/acknowledge`, {}),

  analyzeMonitoringAlert: (
    alertId: string,
    body: { question: string; language: "en" | "zh-CN"; model: "deepseek-v4-flash" },
  ) => post<MonitoringAnalysisDTO>(
    `/monitoring/alerts/${encodeURIComponent(alertId)}/analysis`,
    body,
  ),

  routeEligibility: () => get<RouteEligibilityDTO[]>("/contracts/routes"),

  routeCandidates: () => get<{ route_candidates: RouteCandidateDTO[] }>("/route-cost/route-candidates"),

  tsoTariffs: () => get<TsoTariffsResultDTO>("/route-cost/tso-tariffs"),

  upstreamContracts: () => get<UpstreamContractDTO[]>("/route-cost/upstream-contracts"),

  saveUpstreamContract: (body: UpstreamContractInputDTO) =>
    post<UpstreamContractDTO>("/route-cost/upstream-contracts", body),

  resourcePoolOptions: () => get<ResourcePoolOptionsDTO>("/route-cost/resource-pool/options"),

  recommendRouteAllocation: (body: RouteRecommendationRequestDTO) =>
    post<RouteRecommendationResultDTO>("/route-cost/recommend", body),

  optimizeResourcePool: (body: PortfolioOptimizationRequestDTO) =>
    post<PortfolioOptimizationResultDTO>("/route-cost/resource-pool/optimize", body),

  evaluateStrategyLab: (body: StrategyLabRequestDTO) =>
    post<StrategyLabResultDTO>("/strategy-lab/evaluate", body),

  strategyRuns: (params?: { strategy_id?: string; run_mode?: string; limit?: number }) =>
    get<StrategyRunDTO[]>("/strategy-lab/runs", {
      ...(params?.strategy_id ? { strategy_id: params.strategy_id } : {}),
      ...(params?.run_mode ? { run_mode: params.run_mode } : {}),
      ...(params?.limit ? { limit: String(params.limit) } : {}),
    }),

  strategyRun: (runId: string) =>
    get<StrategyRunDTO>(`/strategy-lab/runs/${encodeURIComponent(runId)}`),

  strategySummary: (params?: { strategy_id?: string; run_mode?: string }) =>
    get<StrategySummaryDTO>("/strategy-lab/summary", {
      ...(params?.strategy_id ? { strategy_id: params.strategy_id } : {}),
      ...(params?.run_mode ? { run_mode: params.run_mode } : {}),
    }),

  strategies: () => get<StrategyDTO[]>("/strategies"),

  strategy: (strategyId: string) =>
    get<StrategyDTO>(`/strategies/${encodeURIComponent(strategyId)}`),

  createStrategy: (body: StrategyCreateInputDTO) => post<StrategyDTO>("/strategies", body),

  updateStrategyMetadata: (strategyId: string, body: StrategyMetadataUpdateInputDTO) =>
    patch<StrategyDTO>(`/strategies/${encodeURIComponent(strategyId)}/metadata`, body),

  strategyVersions: (strategyId: string) =>
    get<StrategyVersionDTO[]>(`/strategies/${encodeURIComponent(strategyId)}/versions`),

  createStrategyVersion: (strategyId: string, body: StrategyVersionCreateInputDTO) =>
    post<StrategyVersionDTO>(`/strategies/${encodeURIComponent(strategyId)}/versions`, body),

  strategyVersion: (versionId: string) =>
    get<StrategyVersionDTO>(`/strategy-versions/${encodeURIComponent(versionId)}`),

  updateStrategyVersionDraft: (versionId: string, body: StrategyVersionCreateInputDTO) =>
    put<StrategyVersionDTO>(`/strategy-versions/${encodeURIComponent(versionId)}/draft`, body),

  freezeStrategyVersion: (versionId: string) =>
    post<StrategyVersionDTO>(`/strategy-versions/${encodeURIComponent(versionId)}/freeze`, {}),

  forkStrategyVersion: (versionId: string, body?: StrategyForkInputDTO) =>
    post<StrategyVersionDTO>(`/strategy-versions/${encodeURIComponent(versionId)}/fork`, body ?? {}),

  createStrategyRun: (body: StrategyRunCreateInputDTO) =>
    post<StrategyRunDTO>("/strategy-runs", body),

  strategyRegistryRuns: (params?: {
    strategy_id?: string; strategy_version_id?: string; run_type?: string; limit?: number;
  }) =>
    get<StrategyRunDTO[]>("/strategy-runs", {
      ...(params?.strategy_id ? { strategy_id: params.strategy_id } : {}),
      ...(params?.strategy_version_id ? { strategy_version_id: params.strategy_version_id } : {}),
      ...(params?.run_type ? { run_type: params.run_type } : {}),
      ...(params?.limit ? { limit: String(params.limit) } : {}),
    }),

  strategyRegistryRun: (runId: string) =>
    get<StrategyRunDTO>(`/strategy-runs/${encodeURIComponent(runId)}`),

  strategyRunEvents: (runId: string) =>
    get<BacktestDecisionEventDTO[]>(`/strategy-runs/${encodeURIComponent(runId)}/events`),

  strategyRunSeries: (runId: string) =>
    get<BacktestSeriesPointDTO[]>(`/strategy-runs/${encodeURIComponent(runId)}/series`),

  strategyRunAttribution: (runId: string) =>
    get<BacktestAttributionDTO[]>(`/strategy-runs/${encodeURIComponent(runId)}/attribution`),

  createBacktestExperiment: (body: BacktestExperimentCreateInputDTO) =>
    post<BacktestExperimentDTO>("/backtest-experiments", body),

  backtestExperiments: () => get<BacktestExperimentDTO[]>("/backtest-experiments"),

  backtestExperiment: (experimentId: string) =>
    get<BacktestExperimentDTO>(`/backtest-experiments/${encodeURIComponent(experimentId)}`),

  createShadowMonitor: (body: ShadowMonitorCreateInputDTO) =>
    post<ShadowMonitorDTO>("/shadow-monitors", body),

  shadowMonitors: () => get<ShadowMonitorDTO[]>("/shadow-monitors"),

  shadowMonitor: (monitorId: string) =>
    get<ShadowMonitorDTO>(`/shadow-monitors/${encodeURIComponent(monitorId)}`),

  pauseShadowMonitor: (monitorId: string) =>
    post<ShadowMonitorDTO>(`/shadow-monitors/${encodeURIComponent(monitorId)}/pause`, {}),

  resumeShadowMonitor: (monitorId: string) =>
    post<ShadowMonitorDTO>(`/shadow-monitors/${encodeURIComponent(monitorId)}/resume`, {}),

  retireShadowMonitor: (monitorId: string) =>
    post<ShadowMonitorDTO>(`/shadow-monitors/${encodeURIComponent(monitorId)}/retire`, {}),

  shadowEvaluations: (monitorId: string) =>
    get<ShadowEvaluationDTO[]>(`/shadow-monitors/${encodeURIComponent(monitorId)}/evaluations`),

  shadowEvaluation: (evaluationId: string) =>
    get<ShadowEvaluationDTO>(`/shadow-evaluations/${encodeURIComponent(evaluationId)}`),

  shadowDrift: (monitorId: string) =>
    get<ShadowDriftDTO[]>(`/shadow-monitors/${encodeURIComponent(monitorId)}/drift`),

  shadowAlerts: (params?: { state?: string; severity?: string; monitor_id?: string }) =>
    get<ShadowAlertDTO[]>("/shadow-alerts", {
      ...(params?.state ? { state: params.state } : {}),
      ...(params?.severity ? { severity: params.severity } : {}),
      ...(params?.monitor_id ? { monitor_id: params.monitor_id } : {}),
    }),

  acknowledgeShadowAlert: (alertId: string) =>
    post<ShadowAlertDTO>(`/shadow-alerts/${encodeURIComponent(alertId)}/acknowledge`, { actor: "operator" }),

  shadowRuntimeStatus: () => get<ShadowRuntimeStatusDTO>("/shadow-runtime/status"),

  capacityContracts: () => get<CapacityContractDTO[]>("/contracts/capacity"),

  runtimeDb: () => get<RuntimeDbStatusDTO>("/runtime/db"),
  runtimeDependencies: () => get<RuntimeDependenciesDTO>("/runtime/dependencies"),
  runtimeRelease: () => get<RuntimeReleaseDTO>("/runtime/release"),
  researchFeatures: () => get<ResearchFeatureDTO[]>("/research/features"),
  researchTargets: () => get<ResearchTargetDTO[]>("/research/targets"),
  researchDatasets: () => get<ResearchDatasetDTO[]>("/research/datasets"),
  researchCapabilities: () => get<ResearchCapabilityDTO[]>("/research/capabilities"),
  validateResearchDataset: (spec: Record<string, unknown>) =>
    post<{ ok: boolean; issues: string[]; spec_hash: string }>("/research/datasets/validate", { dataset_spec: spec }),
  buildResearchDataset: (spec: Record<string, unknown>) =>
    post<Record<string, unknown>>("/research/datasets", { dataset_spec: spec, materialize: true }),

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

  me: () => get<CurrentUserDTO>("/me"),
  authStatus: () => get<AuthStatusDTO>("/auth/status"),
  logout: () => post<{ logged_out: boolean }>("/auth/logout", {}),
  desktopOidcToken: (body: DesktopOidcTokenInputDTO) =>
    post<DesktopOidcTokenDTO>("/auth/oidc/desktop/token", body),
  startDesktopOidcLogin: (body: DesktopOidcLoginInputDTO) =>
    post<DesktopOidcLoginDTO>("/auth/oidc/desktop/login", body),
  accessUsers: () => get<AccessUserDTO[]>("/access/users"),
  patchAccessUser: (principalId: string, body: AccessUserPatchInputDTO) =>
    patch<AccessUserDTO>(`/access/users/${encodeURIComponent(principalId)}`, body),
  accessRoles: () => get<Record<string, string[]>>("/access/roles"),
  accessDataScopes: () => get<Record<string, string[]>>("/access/data-scopes"),
  accessApiKeys: () => get<AccessApiKeyDTO[]>("/access/api-keys"),
  createAccessApiKey: (body: AccessApiKeyCreateInputDTO) =>
    post<AccessApiKeyDTO & { api_key: string }>("/access/api-keys", body),
  revokeAccessApiKey: (keyId: string) =>
    post<{ key_id: string; revoked: boolean }>(`/access/api-keys/${encodeURIComponent(keyId)}/revoke`, {}),
  auditEvents: (params?: { actor?: string; action?: string; resource?: string; outcome?: string; limit?: string }) =>
    get<AuditEventDTO[]>("/audit", params),
  ssoProfile: () => get<Record<string, unknown>>("/access/sso"),
};


export interface CurrentUserDTO {
  principal_id: string; name: string; display_name?: string; principal_type: string;
  role: string; roles: string[]; email: string | null;
  identity_source: string; status: string; data_scopes: string[];
  permissions: string[]; auth_method: string; csrf_token: string | null;
}

export interface AuthStatusDTO {
  oidc_configured: boolean; session_cookie: boolean;
  profile: Record<string, unknown> | null;
}

export interface DesktopOidcLoginInputDTO {
  code_challenge: string; code_verifier: string; redirect_uri: string;
}

export interface DesktopOidcLoginDTO {
  state: string; authorization_url: string;
}

export interface DesktopOidcTokenInputDTO {
  code: string; state: string; code_verifier: string; redirect_uri: string;
}

export interface DesktopOidcTokenDTO {
  access_token: string; token_type: string; principal_id: string;
  principal_name: string; expires_in_seconds: number;
}

export interface AccessUserDTO {
  principal_id: string; principal_type: string; name: string; display_name: string;
  role: string; roles: string[]; email: string | null; identity_source: string;
  status: string; data_scopes: string[]; created_at_utc: string; updated_at_utc: string;
  last_login_at_utc: string | null; keys: AccessApiKeyDTO[];
}

export interface AccessUserPatchInputDTO {
  status?: string; roles?: string[]; data_scopes?: string[]; email?: string | null;
}

export interface AccessApiKeyDTO {
  key_id: string; principal_id: string; key_prefix: string; display_name: string;
  expires_at_utc: string | null; last_used_at_utc: string | null;
  created_at_utc: string; revoked_at_utc: string | null;
  scopes: string[]; created_by: string | null;
}

export interface AccessApiKeyCreateInputDTO {
  principal_id: string; display_name?: string; expires_at_utc?: string | null;
  scopes?: string[];
}

export interface AuditEventDTO {
  event_id: string; event_type: string; severity: string; principal: string;
  action: string; resource: string; outcome: string; detail: string;
  event_ts_utc: string; source_system: string; permission?: string | null;
  correlation_id?: string | null; client_type?: string | null;
}

export interface RuntimeDependencyStateDTO {
  state: string; detail?: string; checked_at_utc?: string;
  last_heartbeat_at_utc?: string; age_seconds?: number;
  missing_tables?: string[]; configured?: boolean;
}

export interface RuntimeReleaseDTO {
  application_version: string;
  release_channel: "preview" | "rc" | "stable";
  git_sha: string | null;
  git_ref: string | null;
  build_run_id: string | null;
  build_timestamp: string | null;
  api_contract_version: string;
  database_schema_revision: string;
  minimum_supported_client: string;
  minimum_supported_server: string;
  backtest_engine_version: string;
  strategy_schema_version: string;
  strategy_run_schema_version: string;
  solver_version: string;
}

export interface RuntimeDependenciesDTO {
  generated_at_utc: string;
  database: RuntimeDependencyStateDTO;
  schedulers: Record<string, RuntimeDependencyStateDTO>;
  oidc: RuntimeDependencyStateDTO;
  llm: RuntimeDependencyStateDTO;
  streaming: RuntimeDependencyStateDTO;
}
