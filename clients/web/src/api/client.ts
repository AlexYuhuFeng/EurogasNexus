/** Typed API client for /api. All data flows through backend API only. */

import { HOST_COMMANDS, resolveHostKind, tryHostCommand } from "@/app/host/hostCapabilities";

const DEFAULT_BROWSER_BASE = "/api";
const DEFAULT_DESKTOP_BASE = "http://127.0.0.1:8000/api";
const REFERENCE_NETWORK_READ_LIMIT = "2000";
export const API_BASE_STORAGE_KEY = "eurogas.settings.api_base_url";
export const API_TOKEN_STORAGE_KEY = "eurogas.settings.api_token";
export const PRINCIPAL_STORAGE_KEY = "eurogas.settings.operator_principal";
const envBase = import.meta.env.VITE_EUROGAS_API_BASE_URL as string | undefined;
// Platform detection has exactly one owner: the Architecture V2 HostCapabilities
// boundary (`clients/web/src/app/host/hostCapabilities.ts`). This module only reads
// the resolved kind, so the marker checks cannot drift between call sites.
const isDesktopShell = resolveHostKind() === "desktop";

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

/**
 * Drop every client-held credential: the stored API token, the stored operator
 * principal and the in-memory desktop session/CSRF token. Preferences without
 * secrets (theme, language, map tiles, API base URL) are deliberately kept.
 */
export function clearStoredAuth(): void {
  clearDesktopSession();
  try {
    localStorage.removeItem(API_TOKEN_STORAGE_KEY);
    localStorage.removeItem(PRINCIPAL_STORAGE_KEY);
  } catch {
    // storage unavailable: nothing stored can survive this call
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

export interface ApiRequestOptions {
  signal?: AbortSignal;
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
  // Best effort through the host boundary: a browser, or a shell that predates the
  // command, simply keeps the configured base URL.
  const config = await tryHostCommand<DesktopDeploymentConfig>(
    HOST_COMMANDS.readDeploymentConfig,
  );
  return config?.api_base_url ? saveApiBaseUrl(config.api_base_url) : configuredApiBaseUrl();
}

export function desktopShellDetected(): boolean {
  /** Whether the workspace runs inside the Tauri desktop shell. */

  return isDesktopShell;
}

export async function notifyDesktopClientReady(): Promise<void> {
  /**
   * Tell the desktop shell that identity resolution finished, so it can reveal
   * the main window. The shell keeps its splashscreen until then, which keeps
   * the terminal hidden from an unauthenticated visitor during startup.
   *
   * Browser deployments and shells without the command are ignored: the Web
   * workspace must stay usable when the native side is absent. The call goes
   * through the single HostCapabilities boundary, which owns the command allowlist.
   */

  if (!isDesktopShell) return;
  await tryHostCommand(HOST_COMMANDS.notifyClientReady);
}

export async function clearDesktopSessionData(): Promise<void> {
  /**
   * Ask the desktop shell to drop its WebView cookies, caches and local storage
   * after a sign-out, so a shared workstation does not keep the previous
   * operator's session material. The caller revokes the backend session and
   * clears the client-stored credentials first; browser deployments are a no-op.
   */

  if (!isDesktopShell) return;
  await tryHostCommand(HOST_COMMANDS.clearSessionData);
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
  /**
   * Where the payload came from. Optional because not every envelope carries it: the research
   * compute routes return the engine's own `source_references` inside `data` and a meta without
   * them, so a surface reads provenance where the payload actually has it rather than assuming a
   * field the response may not contain.
   */
  source_references?: string[];
  warnings?: string[];
  /**
   * Inputs the read needed and did not have - a missing runtime DB URL, a missing table. A surface
   * uses this to keep two statements apart: the read established nothing, and the read established
   * an empty result. Which one it was decides what the page is allowed to say.
   */
  missing_inputs?: string[];
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
    // The backend error envelope carries a machine code and a human message; the
    // code is surfaced first so the UI can localise it, the message stays visible
    // as the explanation. Auth failures report the code under `error`.
    const structured = detail as { message?: unknown; code?: unknown; error?: unknown };
    const message = typeof structured.message === "string" ? structured.message : "";
    const code =
      typeof structured.code === "string"
        ? structured.code
        : typeof structured.error === "string"
          ? structured.error
          : "";
    if (code && message) return `${code} — ${message}`;
    if (code) return code;
    if (message) return message;
  }
  return fallback;
}

/**
 * An HTTP error envelope: the status plus the machine-readable ``detail`` body.
 *
 * The message stays byte-identical to the previous plain ``Error`` (callers and
 * the identity gate classify it by its ``API <status>:`` prefix), while the raw
 * ``detail`` is retained so a governed surface can render the backend's own
 * structured issues instead of re-parsing the flattened message.
 */
export class ApiError extends Error {
  readonly status: number;
  readonly detail: unknown;
  /**
   * The whole error body, envelope included.
   *
   * The backend writes the stable code, family, severity, recoverability, message key,
   * action key and correlation id at the **top level** of the body and passes the
   * endpoint's own `detail` through unchanged beside them. Keeping the complete body is
   * what lets a surface explain a failure through the product error taxonomy instead of
   * reporting every one of them as a generic error (`describeFailure` in
   * `app/experience/errorPresentation.ts` reads this field first).
   */
  readonly body: unknown;

  constructor(message: string, status: number, detail: unknown, body: unknown = null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
    this.body = body;
  }
}

/** Structured failure of one transport call: status plus the parsed detail body. */
export interface ApiFailureDTO {
  status: number;
  detail: unknown;
  /** The whole error body, envelope included (see `ApiError.body`). */
  body: unknown;
  message: string;
}

/**
 * Outcome of a governed request that is expected to fail closed.
 *
 * Resolves instead of throwing for HTTP error responses so the caller keeps the
 * structured envelope (issues, codes, available formats). Transport-level
 * failures (abort, timeout, no response) still reject, because those are not
 * server answers.
 */
export type ApiOutcomeDTO<T> = { ok: true; data: T } | { ok: false; failure: ApiFailureDTO };

export async function apiOutcome<T>(
  operation: () => Promise<ApiResponse<T>>,
): Promise<ApiOutcomeDTO<T>> {
  try {
    return { ok: true, data: (await operation()).data };
  } catch (error) {
    if (error instanceof ApiError) {
      return {
        ok: false,
        failure: {
          status: error.status,
          detail: error.detail,
          body: error.body,
          message: error.message,
        },
      };
    }
    throw error;
  }
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
      throw new ApiError(`API ${res.status}: invalid JSON response.`, res.status, null);
    }
  }
  if (!res.ok) {
    const detail = errorDetail(payload, res.statusText || "request failed");
    throw new ApiError(
      `API ${res.status}: ${detail}`,
      res.status,
      payload && typeof payload === "object" && "detail" in payload
        ? (payload as { detail: unknown }).detail
        : payload,
      // The envelope travels whole: the taxonomy fields sit beside `detail`, and a
      // surface that only kept `detail` would report every failure as generic.
      payload,
    );
  }
  if (!looksJson || payload === null) {
    throw new ApiError(
      `API ${res.status}: expected JSON but received ${contentType || "an unknown content type"}.`,
      res.status,
      null,
    );
  }
  return payload as T;
}

export async function testApiBaseUrl(value: string): Promise<HealthDTO> {
  const normalized = normalizeApiBaseUrl(value);
  return parseResponse<HealthDTO>(
    await fetch(apiUrlForBase(normalized, "/health"), requestInit()),
  );
}

async function get<T>(
  path: string,
  params?: Record<string, string>,
  options: ApiRequestOptions = {},
): Promise<ApiResponse<T>> {
  const url = new URL(apiUrl(path));
  if (params) {
    Object.entries(params).forEach(([k, v]) => { if (v) url.searchParams.set(k, v); });
  }
  const res = await fetch(url.toString(), requestInit({ signal: options.signal }));
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

async function post<T>(path: string, body: unknown, options: ApiRequestOptions = {}): Promise<ApiResponse<T>> {
  const res = await fetch(apiUrl(path), requestInit({
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal: options.signal,
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

/**
 * Architecture V2 Wave 5 projection contract.
 *
 * A projection is a coherent, server-composed read model: one `as_of_utc`, one
 * `time_basis`, and per-slice freshness and entitlement. The client renders it
 * instead of joining several low-level endpoints with mixed timestamps.
 */
export interface ProjectionFreshnessDTO {
  state: string;
  basis: string | null;
  evaluated_at_utc: string | null;
  last_observed_at_utc: string | null;
  expected_within_minutes: number | null;
  expectation_source: string | null;
  measured: unknown;
  derived_from: string | null;
}

export interface ProjectionEntitlementDTO {
  row_filter_applied: boolean;
  filtered_out: number;
  reason: string;
}

export interface ProjectionSliceDTO<Row> {
  available: boolean;
  source_references: string[];
  row_count: number;
  rows: Row[] | null;
  payload: Record<string, unknown> | null;
  freshness: ProjectionFreshnessDTO;
  entitlement: ProjectionEntitlementDTO | null;
  context_filter: { applied: string[]; rule: string } | null;
  limits: { row_limit: number; truncated: boolean } | null;
  warnings: string[];
  notes: string[];
}

export interface MarketContextProjectionDTO {
  projection: string;
  projection_version: string;
  as_of_utc: string;
  time_basis: Record<string, unknown>;
  active_context: Record<string, unknown>;
  slices: {
    market_observations: ProjectionSliceDTO<MarketObsDTO>;
    normalized_quotes: ProjectionSliceDTO<NormalizedMarketObsDTO>;
    quotes: ProjectionSliceDTO<MarketQuoteDTO>;
    intraday_opportunities: ProjectionSliceDTO<IntradayOpportunityDTO>;
    spreads: ProjectionSliceDTO<MarketSpreadDTO>;
    monitoring: ProjectionSliceDTO<MonitoringAlertDTO>;
    data_sources: ProjectionSliceDTO<SourceSystemDTO>;
  };
  warnings: string[];
  research_only: boolean;
  human_review_required: boolean;
}

export interface MarketContextQuery {
  gasDay?: string;
  product?: string;
  hub?: string;
}

/**
 * Architecture V2 portfolio projection: the coherent portfolio read model. The
 * `summary` slice carries a payload rather than rows, because the summary is an
 * aggregate and not a row set.
 */
export interface PortfolioSnapshotProjectionDTO {
  projection: string;
  projection_version: string;
  as_of_utc: string;
  time_basis: Record<string, unknown>;
  active_context: Record<string, unknown>;
  slices: {
    summary: ProjectionSliceDTO<never>;
    screen_orders: ProjectionSliceDTO<ScreenOrderObservationDTO>;
    pnl_snapshots: ProjectionSliceDTO<PortfolioPnlSnapshotDTO>;
    contracts: ProjectionSliceDTO<UpstreamContractDTO>;
    resources: ProjectionSliceDTO<Record<string, unknown>>;
    data_sources: ProjectionSliceDTO<SourceSystemDTO>;
  };
  warnings: string[];
  research_only: boolean;
  human_review_required: boolean;
}

export interface PortfolioSnapshotQuery {
  gasDay?: string;
  portfolioId?: string;
  product?: string;
  hub?: string;
  orderLimit?: number;
  snapshotLimit?: number;
  contractLimit?: number;
}

/**
 * One resolved (or explicitly unresolved) piece of review evidence.
 *
 * Evidence a resolver could not produce is reported as `available: false` with a stable
 * `unavailable_reason` - never as an empty artifact, because "we could not retrieve it"
 * and "it holds nothing" are different answers.
 */
export interface ReviewEvidenceEntryDTO {
  entity_type: string;
  entity_id: string;
  available: boolean;
  resolver: string | null;
  artifact: Record<string, unknown> | null;
  unavailable_reason: string | null;
  warnings: string[];
}

/**
 * Architecture V2 review projection: the decisions of the current review target, the
 * evidence each of them was decided on, and the monitoring posture - one as-of, one
 * time basis, per-slice freshness.
 */
export interface ReviewContextProjectionDTO {
  projection: string;
  projection_version: string;
  as_of_utc: string;
  time_basis: Record<string, unknown>;
  active_context: Record<string, unknown>;
  review_target: { entity_type?: string | null; entity_id?: string | null };
  slices: {
    decisions: ProjectionSliceDTO<ReviewDecisionDTO>;
    evidence: ProjectionSliceDTO<ReviewEvidenceEntryDTO>;
    monitoring: ProjectionSliceDTO<never>;
  };
  warnings: string[];
  research_only: boolean;
  human_review_required: boolean;
}

export interface ReviewContextQuery {
  entityType?: string;
  entityId?: string;
  gasDay?: string;
  product?: string;
  hub?: string;
  decisionLimit?: number;
  evidenceLimit?: number;
}

export interface ReviewDecisionDTO {
  decision_id: string; entity_type: string; entity_id: string;
  actor: string; decision: string; note: string | null; created_at_utc: string;
}

export interface ReviewDecisionInputDTO {
  entity_type:
    | "intraday_opportunity"
    | "strategy_run"
    | "generated_report"
    | "agent_review_pack";
  entity_id: string;
  /**
   * Deprecated: the platform records the authenticated identity as the actor (W0-03 C13) and
   * never uses this field. It is accepted only for compatibility, and a value that disagrees
   * with the identity comes back as an `ACTOR_CLAIM_IGNORED` envelope warning.
   */
  actor?: string;
  decision: "accepted" | "rejected" | "needs_attention";
  note?: string | null;
}

export interface DecisionCaseAssumptionDTO {
  key: string; value: string; source: string; note: string;
}

export interface DecisionCaseAlternativeDTO {
  alternative_id: string; label: string; description: string;
  economics_ref: string; warnings: string[];
}

export interface DecisionCaseEvidenceDTO {
  kind: string; ref: string; label: string; as_of_utc: string; snapshot_id: string;
}

export interface DecisionCaseRecordDTO {
  outcome: "accepted" | "rejected" | "needs_attention";
  actor: string; note: string; evidence_refs: string[]; recorded_at_utc: string;
}

/**
 * One evidence reference in a decision pack (`GET /api/decision-cases/{case_id}`, `pack.evidence`).
 *
 * `snapshot_resolvable` is *measured* by the route and three-valued, and the three values say three
 * different things: `true` the cited snapshot is on record, `false` the reference cites a snapshot
 * that is not on record (a hole a reviewer has to see), and `null` the reference cites no snapshot
 * at all, so nothing is claimed either way.
 */
export interface DecisionPackEvidenceDTO {
  kind: string; ref: string; label: string; as_of_utc: string;
  /** The snapshot the reference cites, or null when it cites none. */
  snapshot_id: string | null;
  snapshot_resolvable: boolean | null;
}

/** One audit event the pack cites against its case (`pack.audit.events`). */
export interface DecisionPackAuditEventDTO {
  event_id: string; action: string; principal: string;
  outcome: string; severity: string;
  /** The instant the act was recorded; null when the trail row carries none. */
  event_ts_utc: string | null;
  detail: string;
}

/** The case context as the pack composed it (`pack.context`). */
export interface DecisionPackContextDTO {
  gas_day: string | null; delivery_product: string | null; hub_id: string | null;
  portfolio_ref: string | null; snapshot_id: string | null;
  reproducible: boolean | null; created_by: string | null; created_at_utc: string | null;
}

/** The audit trail the pack carries for its own case (`pack.audit`). */
export interface DecisionPackAuditDTO {
  /** The resource the acts were recorded against: `decision_case:<case_id>`. */
  resource: string;
  events: DecisionPackAuditEventDTO[];
  /** Where the trail is readable in full, e.g. `/api/audit`. */
  read_surface: string;
}

/**
 * The decision pack beside a case's own fields (`GET /api/decision-cases/{case_id}`).
 *
 * One governance artefact a reviewer can sign: the context, the evidence with each snapshot's
 * resolvability measured, assumptions, alternatives, AI findings, warnings, the human decision with
 * its actor, the acts recorded against the case, and a canonical content hash over all of it. The
 * platform holds no signature, so `signable` states whether the case has the two things that make it
 * decidable at all (evidence and a recorded decision) and `signature_note` says so where a reader
 * looks for one.
 */
export interface DecisionPackDTO {
  /** The pack shape this payload was composed under, e.g. `decision-pack-1`. */
  pack_version: string;
  case_id: string; objective: string; status: string;
  context: DecisionPackContextDTO;
  evidence: DecisionPackEvidenceDTO[];
  assumptions: DecisionCaseAssumptionDTO[];
  alternatives: DecisionCaseAlternativeDTO[];
  ai_findings: string[]; warnings: string[];
  /** The human decision - the newest of `history` - or null while none has been recorded. */
  decision: DecisionCaseRecordDTO | null;
  /** Every record the case carries, oldest first: the same array as `DecisionCaseDTO.records`. */
  history: DecisionCaseRecordDTO[];
  audit: DecisionPackAuditDTO;
  /** False while there is no recorded decision or no evidence; the signature itself is a human act. */
  signable: boolean;
  /**
   * Blocker codes in two vocabularies: the pack's own `DECISION_PACK_*` codes and the case's own
   * codes. A surface renders every one of them rather than only the ones it recognises.
   */
  blockers: string[];
  signature_note: string;
  content_hash: string;
  content_hash_basis: string;
}

/** Full decision-case payload (`GET /api/decision-cases/{case_id}`). */
export interface DecisionCaseDTO {
  case_id: string; objective: string; status: string;
  created_by: string; created_at_utc: string;
  gas_day: string; delivery_product: string; hub_id: string;
  portfolio_ref: string; snapshot_id: string; reproducible: boolean;
  assumptions: DecisionCaseAssumptionDTO[];
  alternatives: DecisionCaseAlternativeDTO[];
  evidence: DecisionCaseEvidenceDTO[];
  ai_findings: string[]; warnings: string[];
  records: DecisionCaseRecordDTO[];
  /** Whether the case may accept a decision yet, with the blockers when it may not. */
  decidable: boolean; blockers: string[];
  /**
   * The case's decision pack, composed for the reviewer who signs it.
   *
   * Optional on purpose: a deployment whose single-case read predates the pack answers without this
   * field, and a surface says the pack is not in the read rather than rendering an empty one.
   */
  pack?: DecisionPackDTO;
}

/** Compact list row (`GET /api/decision-cases`). */
export interface DecisionCaseSummaryDTO {
  case_id: string; objective: string; status: string;
  gas_day: string; delivery_product: string; hub_id: string;
  evidence_count: number; alternative_count: number; assumption_count: number;
  record_count: number; reproducible: boolean;
  last_record: { outcome: string; actor: string; recorded_at_utc: string } | null;
}

export interface DecisionCaseCreateInputDTO {
  objective: string;
  gas_day?: string; delivery_product?: string; hub_id?: string;
  portfolio_ref?: string; snapshot_id?: string;
}

export interface DecisionCaseEvidenceInputDTO {
  kind:
    | "MARKET_CONTEXT"
    | "PORTFOLIO_SNAPSHOT"
    | "SCENARIO"
    | "OPTIMIZATION"
    | "ROUTE_RECOMMENDATION"
    | "BACKTEST"
    | "STRATEGY_RUN"
    | "RESEARCH_DATASET"
    | "AGENT_RUN"
    | "AI_ANALYSIS"
    | "REVIEW_CONTEXT"
    | "MANUAL";
  ref: string; label?: string; as_of_utc?: string; snapshot_id?: string;
}

export interface DecisionCaseDecisionInputDTO {
  outcome: "accepted" | "rejected" | "needs_attention";
  note?: string;
}

/**
 * Unified job record (`GET /api/jobs`). Architecture V2 converges ingestion,
 * dataset builds, optimisation, backtests, reporting and agent work on this one
 * lifecycle, so a surface can show what the deployment is actually running.
 */
export interface JobDTO {
  job_id: string;
  kind:
    | "INGESTION"
    | "DATASET_BUILD"
    | "OPTIMISATION"
    | "BACKTEST"
    | "REPORT"
    | "AGENT_RUN"
    | "SNAPSHOT";
  job_version: string;
  status:
    | "QUEUED"
    | "RUNNING"
    | "WAITING_FOR_INPUT"
    | "SUCCEEDED"
    | "FAILED"
    | "CANCELLED"
    | "EXPIRED";
  principal: string;
  scope_refs: string[];
  snapshot_id: string;
  input_hash: string;
  progress: number;
  created_at_utc: string;
  started_at_utc: string | null;
  finished_at_utc: string | null;
  duration_seconds: number | null;
  output_refs: string[];
  error_code: string;
  error_message: string;
  retryable: boolean;
  cancellable: boolean;
  correlation_id: string | null;
  provenance: string[];
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
  total_realized_pnl_gbp: number | null; total_unrealized_pnl_gbp: number | null;
  total_indicative_pnl_gbp: number | null; total_cash_value_gbp: number | null;
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

/**
 * One `/analysis/query` or `/reports/portfolio` request.
 *
 * No selection or filter field is declared here. The analysis pipeline reads no term,
 * asset, contract, strategy, section or portfolio selection, and the platform refuses a
 * non-empty one (`422 analysis_selection_not_supported`) rather than returning a run over
 * the whole entitled snapshot as if it had been narrowed. Evidence references belong in
 * `question`, which is the prompt the platform records and the provider receives.
 */
export interface AnalysisRequestDTO {
  question: string; task?: string; provider_id?: string; model?: string;
  invoke_provider?: boolean; duration_start_utc?: string | null;
  duration_end_utc?: string | null; language?: string;
  analysis_snapshot_id?: string | null;
}

/**
 * One Data Product catalogue entry (Architecture V2 Wave 4).
 *
 * The catalogue is the platform's declared read model: what a product is, which case it
 * answers, its time basis, the source families behind it, and - per principal - whether this
 * caller may see its values. `provenance` is present only when the caller is entitled **and**
 * the deployment could measure it: a restricted product carries none because the values are
 * withheld, and an entitled product carries none when the deployment has no runtime database
 * to measure with. Both read as "nothing to show" rather than as a zero, which is a
 * measurement - the two are told apart by `restricted` and by the catalogue's own
 * `runtime_available` flag, never by the absence alone.
 */
export interface DataProductDTO {
  product_id: string;
  business_name: string;
  description: string;
  domain: string;
  availability: { state: string; note: string };
  time_basis: {
    basis: string;
    gas_day_calendar: string | null;
    freshness_expectation_minutes: number | null;
  };
  source_families: string[];
  simulated_families: string[];
  entitlement_families: string[];
  served_by: Array<{ kind: string; reference: string; description: string }>;
  provenance_tables: string[];
  restricted: boolean;
  entitlement: {
    status: string;
    reason: string;
    required_family_count: number;
    granted_family_count: number;
    restricted_family_count: number;
    note: string;
  };
  provenance: {
    as_of_utc: string | null;
    row_count: number;
    freshness: { status: string; expectation_minutes: number | null; last_observed_at_utc: string | null };
    confidence: string;
    quality_flags: string[];
  } | null;
  human_review_required: boolean;
}

export interface DataProductCatalogueDTO {
  catalogue_version: string;
  generated_at_utc: string;
  runtime_available: boolean;
  products: DataProductDTO[];
  entitlement_summary: {
    total_products: number;
    allowed_products: number;
    restricted_products: number;
  };
}

export interface AnalysisResultDTO {
  analysis_id: string; task: string; provider_id: string; provider_status: string;
  answer_en: string; answer_zh_cn: string; citations: string[];
  sections: Array<{ section_id: string; title: string; content: string; citations: string[]; warnings: string[] }>;
  missing_inputs: string[]; warnings: string[]; snapshot_id: string;
  /**
   * The Analysis Snapshot the run cited (Architecture V2 Wave 4). Absent from the payload
   * when the caller cited nothing, which is why it is optional rather than nullable: a run
   * that cites no reference does not carry a null one.
   */
  analysis_snapshot_id?: string;
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
  row_count: number | null;
  column_count: number | null;
  coverage: number | null;
  temporal_integrity: string;
  status: string;
  created_at_utc: string;
}

export interface ResearchDatasetDetailDTO {
  spec_hash: string;
  ontology_version: string;
  content_hash?: string | null;
  dataset_snapshot_id: string;
  dataset_spec_id: string;
  source_cutoff_utc: string;
  row_count: number | null;
  column_count: number | null;
  coverage: number | null;
  temporal_integrity: string;
  status: string;
  entitlement_envelope: Record<string, unknown>;
  artifact_ref: string | null;
  metadata: Record<string, unknown>;
}

export interface ResearchDatasetQualityDTO {
  dataset_snapshot_id: string;
  quality_report: Record<string, unknown>;
  leakage_issues: Array<Record<string, unknown>>;
  warnings: string[];
}

export interface ResearchDatasetExportDTO {
  dataset_snapshot_id: string;
  format: "parquet" | "csv";
  artifact_ref: string | null;
  /** Registered artifact identity and digest of the referenced file. */
  artifact_id?: string | null;
  artifact_sha256?: string | null;
  /** Formats the backend has registered for this snapshot. Server-reported only. */
  available_formats?: string[];
  entitlement_policy: string;
}

/** One structured dataset-registry/validation issue: ``{field, code, message}``. */
export interface ResearchDatasetIssueDTO {
  field: string;
  code: string;
  message: string;
}

export interface ResearchDatasetValidationDTO {
  ok: boolean;
  issues: ResearchDatasetIssueDTO[];
  spec_hash: string;
  registry_resolution: string;
}

/**
 * Build reply: the snapshot metadata the materialize route returns. It carries
 * no artifact list, so available formats stay "not reported" until a server
 * answer names them.
 */
export interface ResearchDatasetBuildDTO extends Record<string, unknown> {
  dataset_snapshot_id: string;
  dataset_spec_id: string;
  dataset_spec_version: string;
  spec_hash?: string;
  row_count: number | null;
  column_count: number | null;
  artifact_ref?: string | null;
  entitlement_envelope?: Record<string, unknown>;
}

/**
 * The two research computes the Routes task runs (slice D).
 *
 * Both engines answer with the research contract: the figure, the assumptions it rests on, the
 * inputs it lacked, its warnings, and provenance that names `operator-input` - these are the
 * caller's own numbers, not market data. The provenance and the as-of travel inside `data` here,
 * which is why the surface reads them from the payload rather than from the envelope's meta.
 */
export interface RouteCostComponentDTO {
  component_type: string;
  amount: number;
  unit: string;
  currency: string;
  description: string;
}

export interface RouteCostRequestDTO {
  route_name: string;
  from_node_id: string;
  to_node_id: string;
  components: RouteCostComponentDTO[];
  route_km?: number | null;
}

export interface RouteCostOutcomeDTO {
  route_name: string;
  from_node_id: string;
  to_node_id: string;
  total_cost_eur_mwh: number;
  total_cost_boe: number;
  components: RouteCostComponentDTO[];
  route_km: number | null;
  research_only: boolean;
  human_review_required: boolean;
  assumptions: string[];
  missing_inputs: string[];
  warnings: string[];
  source_references: string[];
  lineage: string[];
  generated_at_utc: string;
}

export interface NetbackRequestDTO {
  route_name: string;
  from_market: string;
  to_market: string;
  market_price_eur_mwh: number;
  route_cost_eur_mwh: number;
  fx_rate: number;
  fx_pair: string;
}

export interface NetbackOutcomeDTO {
  route_name: string;
  from_market: string;
  to_market: string;
  market_price_eur_mwh: number;
  route_cost_eur_mwh: number;
  netback_eur_mwh: number;
  netback_local_mwh: number;
  fx_rate: number;
  fx_pair: string;
  research_only: boolean;
  human_review_required: boolean;
  assumptions: string[];
  missing_inputs: string[];
  warnings: string[];
  source_references: string[];
  lineage: string[];
  generated_at_utc: string;
}

/**
 * The desk's optimisation assessments (register C14/D8).
 *
 * `POST /api/optimization/nomination-window` and `POST /api/optimization/storage-dispatch` are
 * deterministic *assessment* engines: they evaluate instructions and return accepted or adjusted
 * quantities, and they never submit a nomination, a booking or a trade. Every answer is enveloped
 * with `meta.run_id` - the persisted input/output snapshot `GET /api/optimization/runs/{run_id}`
 * re-reads - or with `run_id: null` when the deployment has no runtime database, which the surface
 * states rather than hiding.
 */
export type OptimizationDecisionContextDTO = "SANDBOX_SCENARIO" | "RUNTIME_DECISION";

export interface NominationInstructionInputDTO {
  submitted_at: string;
  requested_quantity_mwh: number;
}

export interface NominationWindowInputDTO {
  window_id: string;
  opens_at: string;
  closes_at: string;
  maximum_change_mwh?: number | null;
  maximum_change_pct?: number | null;
}

export interface NominationWindowRequestDTO {
  initial_quantity_mwh: number;
  instructions: NominationInstructionInputDTO[];
  windows: NominationWindowInputDTO[];
  gas_day?: string | null;
  decision_context: OptimizationDecisionContextDTO;
}

export interface NominationDecisionDTO {
  submitted_at: string;
  requested_quantity_mwh: number;
  accepted_quantity_mwh: number;
  window_id: string | null;
  accepted: boolean;
  reason: string;
}

export interface NominationScheduleResultDTO {
  status: string;
  final_quantity_mwh: number;
  decisions: NominationDecisionDTO[];
  warnings: string[];
  human_review_required: boolean;
}

/**
 * One declared nomination window, resolved onto a gas day -
 * `GET /api/optimization/nomination-windows`.
 *
 * The masters declare a *clock* (a time of day), not an instant: the route resolves the declared
 * times against the gas-day calendar and serves the resulting UTC instants, so a surface shows the
 * same deadline the nomination engine matches an instruction against instead of resolving the
 * calendar a second time in the browser.
 */
export interface NominationWindowOccurrenceDTO {
  window_id: string;
  name: string;
  country: string;
  /** The declared clock time, as the master states it (`HH:MM:SS`). */
  opens_at: string;
  closes_at: string;
  /** The deadline the route resolved for this gas day - the instant a board renders. */
  opens_at_utc: string;
  closes_at_utc: string;
  /**
   * Whether the close falls on a later UTC date than the open. The route serves this as
   * `closes_after_utc_midnight` (the frozen contract draft named the field `wraps_utc_midnight`);
   * it is optional here because the board states the declared `closes_at_utc` instant itself and
   * must not need a flag to state a deadline.
   */
  closes_after_utc_midnight?: boolean;
  /**
   * The same daily rule's occurrence on the *following* gas day, resolved by the route.
   *
   * The masters are daily rules, so once the requested gas day's window has closed this is the
   * instant a desk is actually waiting for. The route resolves it on the calendar rather than
   * letting a surface add a day to a clock, which is why the board renders these three fields
   * instead of computing them.
   */
  next_gas_day?: string;
  next_opens_at_utc?: string;
  next_closes_at_utc?: string;
  /** The declared change limit. Null when the master declares none - never rendered as zero. */
  maximum_change_mwh: number | null;
  maximum_change_pct: number | null;
  valid_from_utc: string;
  valid_to_utc: string | null;
  source_system: string | null;
  source_reference: string | null;
}

/**
 * The nomination-window read's data block (`GET /api/optimization/nomination-windows`).
 *
 * `windows` alone cannot be read as a schedule: the route answers an unconfigured runtime database
 * with an empty list *plus a stated reason* (`meta.missing_inputs`, a `runtime-db-not-configured`
 * source), and answers a configured deployment that declares no master with an empty list and the
 * `NOMINATION_WINDOWS_MISSING` warning. `window_masters_declared` is the route's own count of what
 * it declared, so a surface can tell a measured zero from an unread input.
 */
export interface NominationWindowReadDTO {
  gas_day: string;
  calendar: string;
  gas_day_start_utc: string;
  gas_day_end_utc: string;
  /** How the route read the declared clock times; `utc-clock-on-gas-day` today. */
  time_basis: string;
  assessed_at_utc: string;
  window_masters_declared: number;
  windows: NominationWindowOccurrenceDTO[];
}

export interface StorageFacilityInputDTO {
  initial_inventory_mwh: number;
  minimum_inventory_mwh: number;
  maximum_inventory_mwh: number;
  maximum_injection_mwh: number;
  maximum_withdrawal_mwh: number;
  injection_efficiency?: number;
  withdrawal_efficiency?: number;
  injection_cost_gbp_mwh?: number;
  withdrawal_cost_gbp_mwh?: number;
  terminal_inventory_mwh?: number | null;
}

export interface StoragePeriodInputDTO {
  period_id: string;
  market_price_gbp_mwh: number;
}

export interface StorageDispatchRequestDTO {
  facility?: StorageFacilityInputDTO | null;
  periods: StoragePeriodInputDTO[];
  inventory_step_mwh?: number;
  facility_id?: string | null;
  gas_day?: string | null;
  max_periods?: number;
  decision_context: OptimizationDecisionContextDTO;
}

export interface StorageDecisionDTO {
  period_id: string;
  injection_mwh: number;
  withdrawal_mwh: number;
  ending_inventory_mwh: number;
  cashflow_gbp: number;
}

export interface StorageDispatchResultDTO {
  status: string;
  objective_value_gbp: number;
  decisions: StorageDecisionDTO[];
  terminal_inventory_mwh: number;
  warnings: string[];
  human_review_required: boolean;
}

/**
 * One persisted optimisation run - what was decided, from which inputs.
 *
 * `source_refs` and `warnings` are the run's own, `created_at_utc` is its as-of, and the two
 * snapshots are the evidence: the request the engine received and the result it produced.
 */
export interface OptimizationRunDTO {
  run_id: string;
  optimization_type: string;
  decision_context: string;
  status: string;
  input_snapshot: Record<string, unknown>;
  output_snapshot: Record<string, unknown>;
  source_refs: string[];
  warnings: string[];
  created_at_utc: string;
  research_only: boolean;
  human_review_required: boolean;
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

export interface CapabilityDTO {
  capability_id: string;
  name: string;
  domain: string;
  description: string;
  determinism_class: string;
  side_effect_class: string;
  action_policy: string;
  capability_version: string;
  input_schema: Record<string, unknown>;
  output_schema: Record<string, unknown>;
  required_permissions: string[];
  entitlement_policy: string;
}

export interface AgentRunDTO {
  agent_run_id: string;
  principal_id: string;
  user_objective: string;
  agent_profile: string;
  model_provider: string;
  model_id: string;
  status: string;
  current_stage: string;
  artifacts_created: string[];
  created_at: string;
  completed_at: string | null;
}

/**
 * One Analysis Snapshot descriptor (Architecture V2 Wave 4).
 *
 * Only the fields a caller needs to identify a reference are declared: the id it cites, when
 * the snapshot was taken and against which gas day, and who recorded it. The version blocks
 * the descriptor also carries are lineage detail for the platform, not for a picker.
 */
export interface AnalysisSnapshotDTO {
  snapshot_id: string;
  as_of_utc: string;
  gas_day: string;
  gas_day_calendar?: string;
  time_basis?: string;
  created_at_utc?: string;
  created_by?: string;
}

export interface AgentRunDetailDTO extends AgentRunDTO {
  research_plan_id: string | null;
  evidence_dependencies: string[];
  warnings: string[];
  blockers: string[];
  final_output_reference: string | null;
  /** Presence/identity summary only; the replay read carries the artifact bodies. */
  artifact_chain?: AgentArtifactChainSummaryDTO;
  /** Review artifact kind a human decision is recorded against. */
  review_entity_type?: string;
}

/** Ordered CR-15 governed research artifact chain, exactly as persisted. */
export type AgentArtifactType =
  | "research_plan"
  | "findings"
  | "strategy_ir"
  | "validation"
  | "challenge_report"
  | "review_pack";

/** Frozen run inputs one persisted agent run was produced from. */
export interface AgentFixtureDTO {
  fixture_id: string;
  fixture_kind: string;
  evidence_refs: string[];
  tool_invocation_ids: string[];
  deterministic_model: { model_provider: string; model_id: string };
}

/** Deterministic replay identity of one artifact or chain. */
export interface AgentReplayIdentityDTO {
  replay_id: string;
  content_hash: string;
  deterministic: boolean;
}

/** Which persisted artifacts, invocations and sources produced an artifact. */
export interface AgentArtifactLineageDTO {
  upstream_artifact_ids: string[];
  producing_invocation_ids: string[];
  source_families: string[];
  series_ids: string[];
  snapshot_ids: string[];
  source_references: string[];
  evidence_dependencies: string[];
}

/** Entitlement state observed while producing an artifact (fails closed). */
export interface AgentArtifactRightsDTO {
  entitlement_state: string;
  entitlement_states: string[];
  principal_id: string;
  evaluated_invocation_ids: string[];
  policy_boundary: string;
}

export interface AgentArtifactTimestampsDTO {
  created_at: string | null;
  run_started_at: string | null;
  run_completed_at: string | null;
}

export interface AgentArtifactChainSummaryDTO {
  order: string[];
  present: string[];
  missing: string[];
  complete: boolean;
  artifact_ids: Record<string, string[]>;
  /** Returned by the replay read only; the detail read carries the summary alone. */
  chain_hash?: string;
}

export interface AgentEvidenceRequirementDTO {
  series_id: string;
  required?: boolean;
  max_source_age_seconds?: number | null;
  temporal_integrity_min?: string | null;
  unit?: string | null;
}

export interface AgentResearchPlanStepDTO {
  analysis_id: string;
  analysis_type: string;
  input_series: string[];
  parameters: Record<string, unknown>;
}

/** Persisted research plan row as returned in the plan artifact payload. */
export interface AgentResearchPlanPayloadDTO {
  research_plan_id: string;
  agent_run_id: string | null;
  objective: string;
  question: string;
  market_scope: string[];
  entities: string[];
  product: string;
  horizon: string;
  hypotheses_to_test: string[];
  required_evidence: AgentEvidenceRequirementDTO[];
  analyses: AgentResearchPlanStepDTO[];
  data_quality_requirements: Record<string, unknown>;
  statistical_requirements: Record<string, unknown>;
  strategy_generation_allowed: boolean;
  stopping_conditions: string[];
  status: string;
  created_by: string;
  created_at: string;
}

/** One persisted research finding row. */
export interface AgentResearchFindingPayloadDTO {
  finding_id: string;
  research_plan_id: string | null;
  agent_run_id: string | null;
  question: string;
  statistic: string;
  value: string | null;
  unit: string | null;
  sample: string;
  period: string;
  methodology: string;
  evidence: string[];
  limitations: string[];
  quality_state: string;
  created_at: string;
}

export interface AgentStrategyIRConditionDTO {
  feature_id: string;
  operator: string;
  value: number;
  unit: string;
}

export interface AgentStrategyIRComponentDTO {
  component_id: string;
  component_type: string;
  weight: number;
  conditions: AgentStrategyIRConditionDTO[];
}

export interface AgentStrategyIRParameterDTO {
  parameter_id: string;
  name?: string;
  parameter_type: string;
  unit?: string | null;
  default_value?: unknown;
  min_value?: number | null;
  max_value?: number | null;
  allowed_values?: string[];
  optimization_allowed?: boolean;
  sensitivity_allowed?: boolean;
}

/** Persisted StrategyIR specification (the reviewed strategy artifact). */
export interface AgentStrategyIRPayloadDTO {
  schema_version?: string;
  hypothesis: string;
  universe: {
    origin_hub: string;
    destination_hub: string;
    product: string;
    currency: string;
  };
  components: AgentStrategyIRComponentDTO[];
  parameters: AgentStrategyIRParameterDTO[];
  sizing: {
    method: string;
    max_pct: number;
    max_quantity_mwh_per_day?: number | null;
  };
  risk_controls: Record<string, unknown>;
  economic_assumptions: Record<string, unknown>;
  data_requirements: Record<string, unknown>;
  evaluation_windows?: Array<Record<string, unknown>>;
}

export interface AgentPlanValidationIssueDTO {
  code: string;
  detail: string;
  evidence?: string | null;
}

export interface AgentStrategyIRValidationIssueDTO {
  code: string;
  detail: string;
  field?: string | null;
}

export interface AgentStrategyIRValidationDTO {
  ok: boolean;
  issues: AgentStrategyIRValidationIssueDTO[];
}

/** Persisted plan validation plus the recomputed StrategyIR validation view. */
export interface AgentValidationPayloadDTO {
  plan_id: string | null;
  plan_status: string | null;
  plan_validation_issues: AgentPlanValidationIssueDTO[];
  plan_validation_source: string;
  strategy_ir_validation: AgentStrategyIRValidationDTO | null;
  strategy_ir_validation_source: string;
  feature_catalog_id: string;
  run_blockers: string[];
  run_warnings: string[];
}

export interface AgentChallengeItemDTO {
  challenge: string;
  severity: string;
  evidence: Record<string, unknown>;
  result: string;
  recommended_follow_up?: string;
}

/** Persisted challenge report row. */
export interface AgentChallengeReportPayloadDTO {
  challenge_report_id: string;
  agent_run_id: string | null;
  strategy_version_id: string | null;
  backtest_run_id: string | null;
  items: AgentChallengeItemDTO[];
  overall_result: string;
  recommended_follow_up: string;
  created_at: string;
}

/** Human decisions recorded against the review pack through /review/decisions. */
export interface AgentReviewPackConfirmationDTO {
  entity_type: string;
  entity_id: string;
  decisions: ReviewDecisionDTO[];
}

/** Persisted review pack row plus its recorded human confirmation. */
export interface AgentReviewPackPayloadDTO {
  review_pack_id: string;
  agent_run_id: string | null;
  objective: string;
  research_plan: Record<string, unknown>;
  key_findings: unknown[];
  strategy_specification: Record<string, unknown> | null;
  backtest: Record<string, unknown> | null;
  robustness: Record<string, unknown>;
  challenge_report: Record<string, unknown> | null;
  data_provenance: string[];
  warnings: string[];
  known_limitations: string[];
  alternative_hypotheses: string[];
  status: string;
  created_at: string;
  human_confirmation?: AgentReviewPackConfirmationDTO;
}

interface AgentArtifactEnvelopeBaseDTO {
  operation_id: string;
  stage: string;
  present: boolean;
  artifact_id: string | null;
  artifact_ids: string[];
  agent_run_id: string;
  fixture: AgentFixtureDTO;
  replay_identity: AgentReplayIdentityDTO;
  lineage: AgentArtifactLineageDTO;
  rights: AgentArtifactRightsDTO;
  timestamps: AgentArtifactTimestampsDTO;
  /** Persisted null: no reasoning text is stored or returned for any artifact. */
  hidden_chain_of_thought: null;
}

/**
 * One chain artifact with its payload narrowed by artifact kind.
 *
 * The discriminated union lets a renderer switch on ``artifact_type`` and read a
 * typed payload; an absent artifact keeps ``payload: null`` instead of failing.
 */
export type AgentArtifactEnvelopeDTO =
  | (AgentArtifactEnvelopeBaseDTO & {
      artifact_type: "research_plan";
      payload: AgentResearchPlanPayloadDTO | null;
    })
  | (AgentArtifactEnvelopeBaseDTO & {
      artifact_type: "findings";
      payload: AgentResearchFindingPayloadDTO[] | null;
    })
  | (AgentArtifactEnvelopeBaseDTO & {
      artifact_type: "strategy_ir";
      payload: AgentStrategyIRPayloadDTO | null;
    })
  | (AgentArtifactEnvelopeBaseDTO & {
      artifact_type: "validation";
      payload: AgentValidationPayloadDTO | null;
    })
  | (AgentArtifactEnvelopeBaseDTO & {
      artifact_type: "challenge_report";
      payload: AgentChallengeReportPayloadDTO | null;
    })
  | (AgentArtifactEnvelopeBaseDTO & {
      artifact_type: "review_pack";
      payload: AgentReviewPackPayloadDTO | null;
    });

export type AgentArtifactsDTO = Record<AgentArtifactType, AgentArtifactEnvelopeDTO>;

export interface AgentReplayDTO extends AgentRunDetailDTO {
  started_at: string;
  review_entity_type: string;
  fixture: AgentFixtureDTO;
  artifact_chain: AgentArtifactChainSummaryDTO;
  artifacts: AgentArtifactsDTO;
  tool_invocations: unknown[];
  hidden_chain_of_thought: null;
}

export const api = {
  health: async () =>
    parseResponse<HealthDTO>(await fetch(apiUrl("/health"), requestInit())),

  nodes: (params?: { country?: string; node_type?: string }, options?: ApiRequestOptions) =>
    get<NodeDTO[]>("/reference-network/nodes", {
      limit: REFERENCE_NETWORK_READ_LIMIT,
      ...params,
    }, options),

  edges: (params?: { from_node_id?: string; to_node_id?: string }, options?: ApiRequestOptions) =>
    get<EdgeDTO[]>("/reference-network/edges", {
      limit: REFERENCE_NETWORK_READ_LIMIT,
      ...params,
    }, options),

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
  }, options?: ApiRequestOptions) => get<TsoAccessPointDTO[]>("/reference-network/tso-access", {
    limit: REFERENCE_NETWORK_READ_LIMIT,
    ...params,
  }, options),

  sources: (options?: ApiRequestOptions) => get<SourceSystemWire[]>("/sources", undefined, options).then(normalizeSourcesResponse),

  marketObservations: () => get<MarketObsDTO[]>("/market/observations"),

  normalizedMarketObservations: (options?: ApiRequestOptions) =>
    get<NormalizedMarketObsDTO[]>("/market/normalized", { limit: "500" }, options),

  marketSpreads: (options?: ApiRequestOptions) => get<MarketSpreadDTO[]>("/market/spreads", undefined, options),

  /**
   * Architecture V2 market projection: one coherent read model (observations,
   * normalized quotes, quotes, opportunities, spreads, monitoring, data sources)
   * on a single as-of and time basis, so the client stops joining several
   * endpoints with mixed timestamps.
   *
   * Query names are translated to the route's snake_case parameters here: a
   * camelCase parameter the route does not declare would be ignored silently,
   * which would drop a caller's filter without any error.
   */
  marketContext: (query?: MarketContextQuery, options?: ApiRequestOptions) => {
    const params: Record<string, string> = {};
    if (query?.gasDay) params.gas_day = query.gasDay;
    if (query?.product) params.delivery_product = query.product;
    if (query?.hub) params.hub = query.hub;
    return get<MarketContextProjectionDTO>("/projections/market-context", params, options);
  },

  /**
   * Architecture V2 portfolio projection: one coherent read model (summary, screen
   * orders, PnL snapshots, upstream contracts, resource-pool follow-up, data
   * sources) on a single as-of, replacing the client's join of
   * `/portfolio/live-summary`, `/portfolio/screen-orders` and
   * `/portfolio/pnl-snapshots`.
   *
   * `GET /portfolio/live-summary` is deliberately not declared here any more. The
   * projection's `summary` slice is the same `summarize_portfolio` result - narrowed by the
   * caller's entitlement, which the route does not do - on one as-of with the orders it
   * summarises. A second client read would answer the same question from a different instant,
   * so the route stays for the SDK and the CLI while the client has exactly one answer.
   */
  portfolioSnapshot: (query?: PortfolioSnapshotQuery, options?: ApiRequestOptions) => {
    const params: Record<string, string> = {};
    if (query?.gasDay) params.gas_day = query.gasDay;
    if (query?.portfolioId) params.portfolio_id = query.portfolioId;
    if (query?.product) params.delivery_product = query.product;
    if (query?.hub) params.hub = query.hub;
    if (query?.orderLimit !== undefined) params.order_limit = String(query.orderLimit);
    if (query?.snapshotLimit !== undefined) params.snapshot_limit = String(query.snapshotLimit);
    if (query?.contractLimit !== undefined) params.contract_limit = String(query.contractLimit);
    return get<PortfolioSnapshotProjectionDTO>(
      "/projections/portfolio-snapshot",
      params,
      options,
    );
  },

  /**
   * Architecture V2 review projection: the decisions, their resolved evidence and the
   * monitoring posture on one as-of. The review surface reads it when it opens rather
   * than putting evidence resolution on every workspace load.
   */
  reviewContext: (query?: ReviewContextQuery, options?: ApiRequestOptions) => {
    const params: Record<string, string> = {};
    if (query?.entityType) params.entity_type = query.entityType;
    if (query?.entityId) params.entity_id = query.entityId;
    if (query?.gasDay) params.gas_day = query.gasDay;
    if (query?.product) params.delivery_product = query.product;
    if (query?.hub) params.hub = query.hub;
    if (query?.decisionLimit !== undefined) params.decision_limit = String(query.decisionLimit);
    if (query?.evidenceLimit !== undefined) params.evidence_limit = String(query.evidenceLimit);
    return get<ReviewContextProjectionDTO>("/projections/review-context", params, options);
  },

  reviewDecisions: (params?: { entity_type?: string; entity_id?: string; limit?: string }, options?: ApiRequestOptions) =>
    get<ReviewDecisionDTO[]>("/review/decisions", params, options),

  /**
   * Architecture V2 Decision Cases: the container that turns analysis into
   * reviewable, human-owned decision evidence. A Decision Record is evidence and
   * rationale, never approval to execute anything.
   */
  decisionCases: (params?: { status?: string; limit?: string }, options?: ApiRequestOptions) =>
    get<DecisionCaseSummaryDTO[]>("/decision-cases", params, options),

  decisionCase: (caseId: string, options?: ApiRequestOptions) =>
    get<DecisionCaseDTO>(`/decision-cases/${encodeURIComponent(caseId)}`, undefined, options),

  createDecisionCase: (body: DecisionCaseCreateInputDTO) =>
    post<DecisionCaseDTO>("/decision-cases", body),

  attachDecisionCaseEvidence: (caseId: string, body: DecisionCaseEvidenceInputDTO) =>
    post<DecisionCaseDTO>(`/decision-cases/${encodeURIComponent(caseId)}/evidence`, body),

  /**
   * Record a human decision on a case.
   *
   * A refusal here is a governed outcome, not an exception: 409 ``case_not_decidable`` carries the
   * blockers, so the caller explains why a case cannot be decided yet instead of showing a generic
   * failure. This is the only decision call the client declares - a throwing twin posting to the
   * same route sat beside it with no caller, and two names for one act is how a surface ends up
   * handling the same refusal two different ways.
   */
  recordDecisionCaseDecisionOutcome: (
    caseId: string,
    body: DecisionCaseDecisionInputDTO,
  ) => apiOutcome(() => post<DecisionCaseDTO>(`/decision-cases/${encodeURIComponent(caseId)}/decisions`, body)),

  reopenDecisionCase: (caseId: string) =>
    post<DecisionCaseDTO>(`/decision-cases/${encodeURIComponent(caseId)}/reopen`, {}),

  /**
   * Architecture V2 unified jobs. Read-only except cancellation; a finished or
   * non-cancellable job answers 409 rather than pretending to have stopped it.
   */
  jobs: (
    params?: { status?: string; kind?: string; principal?: string; limit?: string },
    options?: ApiRequestOptions,
  ) => get<JobDTO[]>("/jobs", params, options),

  job: (jobId: string, options?: ApiRequestOptions) =>
    get<JobDTO>(`/jobs/${encodeURIComponent(jobId)}`, undefined, options),

  cancelJob: (jobId: string) => post<JobDTO>(`/jobs/${encodeURIComponent(jobId)}/cancel`, {}),

  recordReviewDecision: (body: ReviewDecisionInputDTO) =>
    post<ReviewDecisionDTO>("/review/decisions", body),

  /**
   * Record one review decision while keeping a governed refusal inspectable.
   *
   * Browser sessions are cookie-authenticated, so the mutation rides the shared
   * ``X-Eurogas-CSRF`` header already carried by :func:`authHeaders`. A refusal
   * resolves as a failure instead of throwing, because the caller has to explain
   * the exact status: 422 unknown review artifact kind, 403 identity refused.
   */
  recordReviewDecisionOutcome: (body: ReviewDecisionInputDTO) =>
    apiOutcome(() => post<ReviewDecisionDTO>("/review/decisions", body)),

  pipelineHealth: (options?: ApiRequestOptions) => get<PipelineHealthDTO>("/runtime/pipeline-health", undefined, options),

  marketQuotes: (options?: ApiRequestOptions) => get<MarketQuoteDTO[]>("/market/quotes", { limit: "500" }, options),

  intradayOpportunities: (options?: ApiRequestOptions) =>
    get<IntradayOpportunityDTO[]>("/market/opportunities", { limit: "100" }, options),

  screenOrders: (options?: ApiRequestOptions) => get<ScreenOrderObservationDTO[]>("/portfolio/screen-orders", undefined, options),

  pnlSnapshots: (options?: ApiRequestOptions) => get<PortfolioPnlSnapshotDTO[]>("/portfolio/pnl-snapshots", undefined, options),

  flowObservations: (options?: ApiRequestOptions) => get<FlowObsDTO[]>("/physical/flows", undefined, options),

  capacityObservations: (options?: ApiRequestOptions) => get<CapacityObsDTO[]>("/physical/capacity", undefined, options),

  storageObservations: (options?: ApiRequestOptions) => get<StorageObsDTO[]>("/storage/observations", undefined, options),

  lngObservations: (options?: ApiRequestOptions) => get<LngObsDTO[]>("/lng/observations", undefined, options),

  fxRates: (options?: ApiRequestOptions) => get<FxRateDTO[]>("/market/fx", undefined, options),

  credentialProviders: (options?: ApiRequestOptions) => get<CredentialProviderDTO[]>("/credentials/providers", undefined, options),

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

  monitoringAlerts: (options?: ApiRequestOptions) =>
    get<MonitoringAlertDTO[]>("/monitoring/alerts", { limit: "100" }, options),

  monitoringSummary: (options?: ApiRequestOptions) => get<MonitoringSummaryDTO>("/monitoring/summary", undefined, options),

  acknowledgeMonitoringAlert: (alertId: string) =>
    post<MonitoringAlertDTO>(`/monitoring/alerts/${encodeURIComponent(alertId)}/acknowledge`, {}),

  analyzeMonitoringAlert: (
    alertId: string,
    body: { question: string; language: "en" | "zh-CN"; model: "deepseek-v4-flash" },
  ) => post<MonitoringAnalysisDTO>(
    `/monitoring/alerts/${encodeURIComponent(alertId)}/analysis`,
    body,
  ),

  routeEligibility: (options?: ApiRequestOptions) => get<RouteEligibilityDTO[]>("/contracts/routes", undefined, options),

  routeCandidates: (options?: ApiRequestOptions) => get<{ route_candidates: RouteCandidateDTO[] }>("/route-cost/route-candidates", undefined, options),

  tsoTariffs: (options?: ApiRequestOptions) => get<TsoTariffsResultDTO>("/route-cost/tso-tariffs", undefined, options),

  upstreamContracts: (options?: ApiRequestOptions) => get<UpstreamContractDTO[]>("/route-cost/upstream-contracts", undefined, options),

  saveUpstreamContract: (body: UpstreamContractInputDTO) =>
    post<UpstreamContractDTO>("/route-cost/upstream-contracts", body),

  resourcePoolOptions: (options?: ApiRequestOptions) => get<ResourcePoolOptionsDTO>("/route-cost/resource-pool/options", undefined, options),

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

  runtimeDb: (options?: ApiRequestOptions) => get<RuntimeDbStatusDTO>("/runtime/db", undefined, options),
  runtimeDependencies: (options?: ApiRequestOptions) => get<RuntimeDependenciesDTO>("/runtime/dependencies", undefined, options),
  runtimeRelease: (options?: ApiRequestOptions) => get<RuntimeReleaseDTO>("/runtime/release", undefined, options),
  researchFeatures: (options?: ApiRequestOptions) => get<ResearchFeatureDTO[]>("/research/features", undefined, options),
  researchTargets: (options?: ApiRequestOptions) => get<ResearchTargetDTO[]>("/research/targets", undefined, options),
  researchDatasets: (options?: ApiRequestOptions) => get<ResearchDatasetDTO[]>("/research/datasets", undefined, options),
  researchCapabilities: () => get<ResearchCapabilityDTO[]>("/research/capabilities"),
  researchDataset: (datasetSnapshotId: string, options?: ApiRequestOptions) =>
    get<ResearchDatasetDetailDTO>(`/research/datasets/${encodeURIComponent(datasetSnapshotId)}`, undefined, options),
  researchDatasetQuality: (datasetSnapshotId: string, options?: ApiRequestOptions) =>
    get<ResearchDatasetQualityDTO>(`/research/datasets/${encodeURIComponent(datasetSnapshotId)}/quality`, undefined, options),
  exportResearchDataset: (
    datasetSnapshotId: string,
    body: { format: "parquet" | "csv" },
    options?: ApiRequestOptions,
  ) =>
    post<ResearchDatasetExportDTO>(
      `/research/datasets/${encodeURIComponent(datasetSnapshotId)}/export`,
      body,
      options,
    ),
  capabilities: (params?: { domain?: string }) =>
    get<CapabilityDTO[]>("/capabilities", params),
  searchCapabilities: (q: string) => get<CapabilityDTO[]>("/capabilities/search", { q }),
  capability: (capabilityId: string) =>
    get<CapabilityDTO>(`/capabilities/${encodeURIComponent(capabilityId)}`),
  /**
   * Invoke one registered capability (Architecture V2 Wave 7 / CR-15).
   *
   * `human_confirmation` answers a capability whose declared `action_policy` is
   * `HUMAN_CONFIRMATION`; the runtime refuses such a capability without it, and the flag buys no
   * authority - permissions, data scopes and argument validation are evaluated either way. The
   * response is a `CapabilityResult`: a refusal comes back as `status: "BLOCKED"` with a stable
   * failure code, so the surface renders what stopped it rather than an error string.
   */
  invokeCapability: (
    capabilityId: string,
    argumentsBody: Record<string, unknown>,
    confirmation?: { humanConfirmation: boolean; confirmationNote?: string },
  ) =>
    post<Record<string, unknown>>(`/capabilities/${encodeURIComponent(capabilityId)}/invoke`, {
      arguments: argumentsBody,
      human_confirmation: confirmation?.humanConfirmation ?? false,
      confirmation_note: confirmation?.confirmationNote ?? "",
    }),
  agentProfiles: () => get<Record<string, unknown>[]>("/agent/profiles"),
  /**
   * The declared Data Product catalogue with this caller's entitlement verdict
   * (Architecture V2 Wave 4).
   *
   * A deployment without a runtime database still serves the declared contract and reports
   * freshness as `UNKNOWN` rather than a fabricated zero, so the surface renders what it
   * receives instead of assuming a measured value is always present.
   */
  /**
   * Queue one MANUAL ingestion run for a source (Architecture V2 Wave 4/8 operator path).
   *
   * The route queues the run and returns it; the dataops worker executes it. The platform's own
   * guards (credential state, circuit breaker, certification) still decide whether the run will
   * produce data, so the surface discloses what it sees instead of pre-empting the platform.
   */
  requestSourceRun: (sourceId: string, reason: string, options?: ApiRequestOptions) =>
    post<Record<string, unknown>>(
      `/sources/${encodeURIComponent(sourceId)}/run`,
      { reason },
      options,
    ),
  dataProducts: (options?: ApiRequestOptions) =>
    get<DataProductCatalogueDTO>("/data-products", undefined, options),
  /**
   * Record an Analysis Snapshot from the Active Context (Architecture V2 Wave 4).
   *
   * The route is GOVERNED and refuses the write without a runtime database, because a snapshot
   * is persisted evidence rather than a derived read. Context keys outside the declared subset
   * are refused with `active_context_key_unsupported` instead of being dropped, so the caller
   * learns which dimension the platform cannot express.
   */
  createAnalysisSnapshot: (
    body: { as_of_utc: string; active_context: Record<string, string> },
    options?: ApiRequestOptions,
  ) => post<AnalysisSnapshotDTO>("/analysis-snapshots", body, options),
  /**
   * Recent Analysis Snapshots, newest first (Architecture V2 Wave 4).
   *
   * A snapshot descriptor is lineage metadata: it names the version set a run can cite as its
   * reproducibility reference. A deployment without a runtime database returns an empty list
   * with a warning rather than an error, so the surface can say "none recorded" honestly
   * instead of showing a failure.
   */
  analysisSnapshots: (params?: { limit?: number }, options?: ApiRequestOptions) =>
    get<AnalysisSnapshotDTO[]>(
      "/analysis-snapshots",
      params ? { limit: String(params.limit) } : undefined,
      options,
    ),
  agentRuns: (params?: { limit?: number }) =>
    get<AgentRunDTO[]>("/agent/runs", params ? { limit: String(params.limit) } : undefined),
  agentRun: (agentRunId: string) =>
    get<AgentRunDetailDTO>(`/agent/runs/${encodeURIComponent(agentRunId)}`),
  agentReplay: (agentRunId: string) =>
    get<AgentReplayDTO>(`/agent/runs/${encodeURIComponent(agentRunId)}/replay`),
  runAgentResearch: (body: { objective: string; agent_profile?: string; strategy_generation_allowed?: boolean }) =>
    post<Record<string, unknown>>("/agent/research", body),
  validateResearchDataset: (spec: Record<string, unknown>, options?: ApiRequestOptions) =>
    post<ResearchDatasetValidationDTO>("/research/datasets/validate", { dataset_spec: spec }, options),
  buildResearchDataset: (spec: Record<string, unknown>, options?: ApiRequestOptions) =>
    post<ResearchDatasetBuildDTO>(
      "/research/datasets",
      { dataset_spec: spec, materialize: true },
      options,
    ),

  glossary: (lang: string = "en", params?: { category?: string; q?: string }, options?: ApiRequestOptions) =>
    get<GlossaryTermDTO[]>("/glossary", { lang, ...(params ?? {}) }, options),

  glossaryContext: (
    term: string,
    params?: { lang?: string; duration_start_utc?: string; duration_end_utc?: string },
  ) =>
    get<GlossaryContextDTO>(`/glossary/${encodeURIComponent(term)}/context`, params),

  analysisQuery: (body: AnalysisRequestDTO) => post<AnalysisResultDTO>("/analysis/query", body),

  portfolioReport: (body: AnalysisRequestDTO) => post<AnalysisResultDTO>("/reports/portfolio", body),

  routeCost: (body: RouteCostRequestDTO) => post<RouteCostOutcomeDTO>("/research/route-cost", body),
  netback: (body: NetbackRequestDTO) => post<NetbackOutcomeDTO>("/research/netback", body),

  /**
   * The two desk assessments, and the run record that makes them checkable (register C14/D8).
   *
   * Assessment only: `nomination-window` evaluates instructions against window rules and returns
   * accepted or adjusted quantities, and `storage-dispatch` returns a per-period inject/withdraw
   * plan. Neither submits a nomination, a booking or a trade - the platform has no execution
   * semantics by design.
   */
  optimizeNominationWindow: (body: NominationWindowRequestDTO) =>
    post<NominationScheduleResultDTO>("/optimization/nomination-window", body),
  optimizeStorageDispatch: (body: StorageDispatchRequestDTO) =>
    post<StorageDispatchResultDTO>("/optimization/storage-dispatch", body),
  optimizationRun: (runId: string, options?: ApiRequestOptions) =>
    get<OptimizationRunDTO>(`/optimization/runs/${encodeURIComponent(runId)}`, undefined, options),

  /**
   * The declared nomination windows for one gas day - the desk's clock.
   *
   * A read of the deployment's own declaration, not an optimization: the query parameter is
   * optional, and omitting it asks for the gas day containing the current UTC instant. The route
   * reports an unconfigured runtime database as an unread input rather than as an empty schedule,
   * so the caller keeps the whole envelope and reads the posture from `meta`.
   */
  nominationWindows: (gasDay?: string, options?: ApiRequestOptions) =>
    get<NominationWindowReadDTO>(
      "/optimization/nomination-windows",
      gasDay ? { gas_day: gasDay } : undefined,
      options,
    ),

  me: (options?: ApiRequestOptions) => get<CurrentUserDTO>("/me", undefined, options),
  authStatus: () => get<AuthStatusDTO>("/auth/status"),
  /** Development-only credential login; the backend sets the session cookie. */
  login: (username: string, password: string) =>
    post<DevLoginIdentityDTO>("/dev/auth/login", { username, password }),
  logout: (options?: ApiRequestOptions) => post<{ logged_out: boolean }>("/auth/logout", {}, options),
  desktopOidcToken: (body: DesktopOidcTokenInputDTO) =>
    post<DesktopOidcTokenDTO>("/auth/oidc/desktop/token", body),
  startDesktopOidcLogin: (body: DesktopOidcLoginInputDTO) =>
    post<DesktopOidcLoginDTO>("/auth/oidc/desktop/login", body),
  accessUsers: () => get<AccessUserDTO[]>("/access/users"),
  patchAccessUser: (principalId: string, body: AccessUserPatchInputDTO) =>
    patch<AccessUserDTO>(`/access/users/${encodeURIComponent(principalId)}`, body),
  accessRoles: () => get<Record<string, string[]>>("/access/roles"),
  accessDataScopes: () => get<DataScopeCatalogueDTO>("/access/data-scopes"),
  accessApiKeys: () => get<AccessApiKeyDTO[]>("/access/api-keys"),
  createAccessApiKey: (body: AccessApiKeyCreateInputDTO) =>
    post<AccessApiKeyDTO & { api_key: string }>("/access/api-keys", body),
  revokeAccessApiKey: (keyId: string) =>
    post<{ key_id: string; revoked: boolean }>(`/access/api-keys/${encodeURIComponent(keyId)}/revoke`, {}),
  auditEvents: (params?: { actor?: string; action?: string; resource?: string; outcome?: string; limit?: string }) =>
    get<AuditEventDTO[]>("/audit", params),
  ssoProfile: () => get<Record<string, unknown>>("/access/sso"),
};


/**
 * Architecture V2 composition contract returned by `GET /api/me`.
 *
 * It carries capability *names* the authenticated identity already holds,
 * functional assignments and the work modes it may compose. It is composition
 * only: the client MUST NOT treat it as a permission check, and the backend
 * re-authorises every request.
 */
export interface ExperienceProfileDTO {
  principal_id: string;
  role: string;
  roles: string[];
  functional_assignments: string[];
  available_work_modes: string[];
  default_work_mode: string | null;
  effective_capabilities: string[];
  commercial_capabilities: string[];
  scope_refs: string[];
  data_entitlement_refs: string[];
  unsupported_scope_kinds: string[];
  work_mode_grants_authority: boolean;
}

export interface CurrentUserDTO {
  principal_id: string; name: string; display_name?: string; principal_type: string;
  role: string; roles: string[]; email: string | null;
  identity_source: string; status: string; data_scopes: string[];
  permissions: string[]; auth_method: string; csrf_token: string | null;
  experience?: ExperienceProfileDTO;
}

export interface AuthStatusDTO {
  oidc_configured: boolean; session_cookie: boolean;
  /** Presence-only descriptor of the configured OIDC profile; never a secret. */
  profile: string | Record<string, unknown> | null;
  /** True only when the deployment advertises development credential login. */
  dev_login: boolean;
}

export interface DevCredentialLoginInputDTO {
  username: string; password: string;
}

/**
 * Successful `POST /api/dev/auth/login` payload. Development deployments only -
 * the credential is validated by the backend and the session cookie it returns
 * is what carries authority, never this response.
 */
export interface DevLoginIdentityDTO {
  authenticated: boolean; principal_id: string; display_name: string;
  role: string; permissions: string[];
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

/**
 * The data-scope families this deployment declares (`GET /api/access/data-scopes`).
 *
 * It is a catalogue, not a policy: an entitlement may name any of these, and a value outside it is
 * one nothing recognises. Typed as itself rather than as an open record so a surface that offers
 * scopes is offering the deployment's own declaration.
 */
export interface DataScopeCatalogueDTO {
  public_baseline: string[];
  commercial: string[];
  wildcard: string;
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
