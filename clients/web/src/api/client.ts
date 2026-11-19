/** Typed API client for /api. All data flows through backend API only. */

import { HOST_COMMANDS, resolveHostKind, tryHostCommand } from "@/app/host/hostCapabilities";
import type {
  FxForwardDTO,
  InstrumentCatalogueDTO,
  NormaliseRequestDTO,
  NormaliseResponseDTO,
} from "./comparablePrices";
import type { EvaluationDTO, InterpretationDTO, SpreadBoardDTO, StrategySpecDTO } from "./spreads";
import type { PromptMarketDTO, StrategyTrackDTO } from "./strategyTracks";

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

/**
 * The desktop app's backend session, held in memory only. The desktop WebView's origin is
 * cross-site to the API on every platform (Windows, macOS, Linux), so the browser's
 * SameSite session cookie is never sent; the app presents the same opaque session in
 * `X-Eurogas-Session` instead (the native-app pattern, RFC 8252).
 */
export function setDesktopSessionToken(token: string, csrfToken = ""): void {
  desktopSessionToken = token.trim();
  currentCsrfToken = csrfToken.trim();
}

/** The CSRF token for cookie-authenticated mutations; leaves a desktop session untouched. */
export function setCsrfToken(csrfToken: string): void {
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
  // A desktop session is an interactive login: its own header, never confused with the
  // deployment API token an SDK or a configured workstation sends as a bearer.
  if (desktopSessionToken) headers["X-Eurogas-Session"] = desktopSessionToken;
  else {
    const token = configuredApiToken();
    if (token) headers["Authorization"] = `Bearer ${token}`;
  }
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

/**
 * Server-sent events over fetch, for credentials that must stay in headers. Reconnects after
 * a dropped connection (as EventSource does) until closed.
 */
function openHeaderEventStream(
  path: string,
  handlers: Record<string, (data: unknown) => void>,
  onStatus?: (status: "open" | "error") => void,
): EventStreamHandle {
  const controller = new AbortController();
  let closed = false;
  let retry: ReturnType<typeof setTimeout> | undefined;
  const connect = async () => {
    try {
      const response = await fetch(apiUrl(path), requestInit({ signal: controller.signal, headers: { Accept: "text/event-stream" } }));
      if (!response.ok || !response.body) throw new Error(`stream ${response.status}`);
      onStatus?.("open");
      // Loaded on first use: only desktop sessions read streams this way.
      const { dispatchSseBlock } = await import("./sse");
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      for (;;) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        let boundary = buffer.search(/\r?\n\r?\n/);
        while (boundary !== -1) {
          dispatchSseBlock(buffer.slice(0, boundary), handlers);
          buffer = buffer.slice(buffer.slice(boundary).match(/^\r?\n\r?\n/)![0].length + boundary);
          boundary = buffer.search(/\r?\n\r?\n/);
        }
      }
      throw new Error("stream ended");
    } catch {
      if (closed) return;
      onStatus?.("error");
      retry = setTimeout(() => void connect(), 5000);
    }
  };
  void connect();
  return {
    close: () => {
      closed = true;
      if (retry) clearTimeout(retry);
      controller.abort();
    },
  };
}

export function openEventStream(
  path: string,
  handlers: Record<string, (data: unknown) => void>,
  onStatus?: (status: "open" | "error") => void,
): EventStreamHandle {
  // A desktop session must travel in a header and never in a URL (URLs are logged), and
  // EventSource cannot set headers: read the stream with fetch instead.
  if (desktopSessionToken) return openHeaderEventStream(path, handlers, onStatus);
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

export interface ApiResponse<T, M = ApiMeta> {
  data: T;
  meta: M;
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

async function get<T, M = ApiMeta>(
  path: string,
  params?: Record<string, string> | URLSearchParams,
  options: ApiRequestOptions = {},
): Promise<ApiResponse<T, M>> {
  const url = new URL(apiUrl(path));
  if (params instanceof URLSearchParams) {
    params.forEach((value, key) => url.searchParams.append(key, value));
  } else if (params) {
    Object.entries(params).forEach(([k, v]) => { if (v) url.searchParams.set(k, v); });
  }
  const res = await fetch(url.toString(), requestInit({ signal: options.signal }));
  return parseResponse<ApiResponse<T, M>>(res);
}

export type ReportFormat = "csv" | "xlsx" | "pdf";

/**
 * Download a report read as CSV, Excel or PDF (`format=`) with the caller's credentials, and
 * save it under the file name the server chose. Every format holds the same rows.
 */
export async function downloadReport(
  path: string,
  params: Record<string, string> = {},
  format: ReportFormat = "csv",
): Promise<void> {
  const url = new URL(apiUrl(path));
  Object.entries({ ...params, format }).forEach(([k, v]) => { if (v) url.searchParams.set(k, v); });
  const response = await fetch(url.toString(), requestInit());
  if (!response.ok) throw new Error(`export failed (${response.status})`);
  const disposition = response.headers.get("content-disposition") ?? "";
  const name = /filename="([^"]+)"/.exec(disposition)?.[1] ?? `eurogas-nexus-report.${format}`;
  const link = document.createElement("a");
  link.href = URL.createObjectURL(await response.blob());
  link.download = name;
  link.click();
  URL.revokeObjectURL(link.href);
}

/** A stored market report's self-contained HTML, read with the caller's credentials. */
export async function fetchReportHtml(reportId: string): Promise<string> {
  const response = await fetch(apiUrl(`/reports/market/${encodeURIComponent(reportId)}/html`), requestInit());
  if (!response.ok) throw new Error(`report ${response.status}`);
  return response.text();
}

/**
 * Send a contract PDF to intake and get back a draft for review; nothing is stored.
 * The body is the file itself, so no form-data parser is needed on the server.
 */
export async function intakeContractPdf(file: File): Promise<ContractIntakeDTO> {
  const url = new URL(apiUrl("/contracts/intake"));
  url.searchParams.set("file_name", file.name);
  const response = await fetch(url.toString(), requestInit({
    method: "POST",
    headers: { "Content-Type": "application/pdf" },
    body: file,
  }));
  const parsed = await parseResponse<ApiResponse<ContractIntakeDTO>>(response);
  return parsed.data;
}

/** CSV download, kept for callers that offer only CSV. */
export function downloadReportCsv(path: string, params: Record<string, string> = {}): Promise<void> {
  return downloadReport(path, params, "csv");
}

/**
 * Told before every write (POST/PUT/PATCH/DELETE): the read cache marks its answers stale
 * (app/data/readCache.ts, wired by the shell). A listener, so this module imports nothing more.
 */
const apiWriteListeners = new Set<() => void>();

export function onApiWrite(listener: () => void): () => void {
  apiWriteListeners.add(listener);
  return () => {
    apiWriteListeners.delete(listener);
  };
}

function notifyApiWrite(): void {
  for (const listener of apiWriteListeners) listener();
}

async function patch<T>(path: string, body: unknown): Promise<ApiResponse<T>> {
  // A write may change what any read answers: kept answers are refreshed on next view.
  notifyApiWrite();
  const response = await fetch(apiUrl(path), requestInit({
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  }));
  return parseResponse<ApiResponse<T>>(response);
}

async function del<T>(path: string): Promise<ApiResponse<T>> {
  // A write may change what any read answers: kept answers are refreshed on next view.
  notifyApiWrite();
  const response = await fetch(apiUrl(path), requestInit({ method: "DELETE" }));
  return parseResponse<ApiResponse<T>>(response);
}

async function put<T>(path: string, body: unknown): Promise<ApiResponse<T>> {
  // A write may change what any read answers: kept answers are refreshed on next view.
  notifyApiWrite();
  const response = await fetch(apiUrl(path), requestInit({
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  }));
  return parseResponse<ApiResponse<T>>(response);
}

async function deleteWithBody<T>(path: string, body: unknown): Promise<ApiResponse<T>> {
  // A write may change what any read answers: kept answers are refreshed on next view.
  notifyApiWrite();
  const response = await fetch(apiUrl(path), requestInit({
    method: "DELETE",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  }));
  return parseResponse<ApiResponse<T>>(response);
}

async function post<T, M = ApiMeta>(path: string, body: unknown, options: ApiRequestOptions = {}): Promise<ApiResponse<T, M>> {
  // A write may change what any read answers: kept answers are refreshed on next view.
  notifyApiWrite();
  const res = await fetch(apiUrl(path), requestInit({
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal: options.signal,
  }));
  return parseResponse<ApiResponse<T, M>>(res);
}

/**
 * A read sent as POST because its question does not fit a query string (a list of prices to
 * convert). It changes nothing on the server, so kept answers stay valid: no write notice.
 */
async function postRead<T, M = ApiMeta>(path: string, body: unknown, options: ApiRequestOptions = {}): Promise<ApiResponse<T, M>> {
  const res = await fetch(apiUrl(path), requestInit({
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal: options.signal,
  }));
  return parseResponse<ApiResponse<T, M>>(res);
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
  status: string; description: string;
  /** Rows held for this source; null when the server could not count them (unknown, not 0). */
  live_record_count: number | null;
  category: string; category_label: string; connectivity_status: string;
  /** How the data arrives: a connector, an operator's file import, a vendor template or a model service (#33). */
  integration?: "api" | "file_import" | "template" | "model_service" | "manual_register";
  operational_status: string; workflow_ready: boolean;
  effective_source_system: string; effective_record_count: number | null;
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
  /** FRESH-01: per dataset, what the manifest expects, the last receipt, the next expected
   * update and the state (current, late, stale, never; manual for a register or an import). */
  freshness_contract?: SourceFreshnessContractDTO[];
  /** ONT-02: provider identifiers this source delivered that resolve to nothing, with counts. */
  unresolved_identifiers?: UnresolvedIdentifierDTO[];
  /** The configured model endpoint of a model service (#33); never a key. */
  model_service?: { provider_name: string; model: string; host: string } | null;
  /** Public-source approval (ENTSOG, GIE): class, state and the terms an administrator accepts. */
  approval?: SourceApprovalDTO;
}

/** The approval classes of the registry (`domain/ingestion/source_approval.py`). */
export type SourceApprovalClass =
  | "approval" | "approval_and_key" | "no_approval" | "key_only" | "licensed"
  | "register" | "simulated" | "model";

export type SourceApprovalState =
  | "not_required" | "not_approved" | "approved_waiting_for_key" | "approved" | "running" | "failing";

export interface SourceApprovalDTO {
  required: boolean;
  class?: SourceApprovalClass;
  state: SourceApprovalState;
  state_words?: string;
  /** Stable reason code (`source_not_approved`, `credential_missing`, a validation failure). */
  reason: string | null;
  action?: string;
  approved_by?: string | null;
  approved_at_utc?: string | null;
  terms?: {
    provider: string; summary: string; attribution: string; terms_url: string;
    reference: string; version: string;
  } | null;
}

export interface SourceApprovalResultDTO {
  source_id: string; source_system: string; state: SourceApprovalState | "approved";
  changed: boolean; stage: string; failure?: string | null;
  approval: { approved_by: string | null; approved_at_utc: string | null; reason: string | null };
}

export interface SourceFreshnessContractDTO {
  source_id: string;
  dataset: string;
  expected: {
    integration: string; schedule_type: string; interval_minutes: number | null;
    daily_at: string | null; timezone: string; calendar: string;
    normal_max_age_minutes: number; stale_after_minutes: number; publication: string;
    period_late_hours: number | null; period_stale_hours: number | null;
  };
  last_received_at_utc: string | null;
  last_period_at_utc: string | null;
  next_expected_at_utc: string | null;
  next_expected_basis: string;
  /** The scheduler's next run has passed without a run (the scheduler is not running). */
  next_expected_overdue?: boolean;
  state: "current" | "late" | "stale" | "never" | "manual";
  /** Why the gate holds this dataset back (`source_not_approved` ...), and where to act. */
  blocked_reason?: string | null;
  blocked_action?: string | null;
}

export interface UnresolvedIdentifierDTO {
  entity_type: string;
  identifier: string;
  reason: string;
  count: number;
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
  runtime_records: number | null;
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
    runtime_records: number | null;
    /** ONT-02: distinct provider identifiers quarantined across sources. */
    unresolved_identifiers?: number;
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

/**
 * A source's record count as sent: null is the server saying it could not count (the read
 * failed), kept unknown rather than read as 0; an absent field (an older server) is 0.
 */
function parseRecordCount(value: unknown): number | null {
  if (value === null) return null;
  const count = Number(value ?? 0);
  return Number.isFinite(count) ? count : null;
}

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
  // null is the server saying the count read failed: keep it unknown, never 0.
  const liveRecordCount = parseRecordCount(raw.live_record_count);
  const hasLiveRecords = (liveRecordCount ?? 0) > 0;
  const status = raw.status || (hasLiveRecords ? "active" : "registered");
  const credentialState = raw.credential_state || (credentialRequired ? "missing" : "not_required");
  const connectivityStatus = raw.connectivity_status ||
    (credentialState === "missing"
      ? "needs_credential"
      : hasLiveRecords
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
    effective_record_count: raw.effective_record_count !== undefined
      ? parseRecordCount(raw.effective_record_count)
      : operationalStatus === "active_simulated" ? previewSubstituteRecordCount : liveRecordCount,
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
      : hasLiveRecords
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
    // Carried through as the server sent them (they were dropped before, so the detail panel
    // never showed the freshness contract).
    ...(Array.isArray(raw.freshness_contract) ? { freshness_contract: raw.freshness_contract } : {}),
    ...(Array.isArray(raw.unresolved_identifiers) ? { unresolved_identifiers: raw.unresolved_identifiers } : {}),
    ...(raw.model_service !== undefined ? { model_service: raw.model_service } : {}),
    ...(raw.approval && typeof raw.approval === "object" ? { approval: raw.approval } : {}),
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
  price_name?: string;
  hub: string;
  tenor: string;
  is_gas_price: boolean;
  price_gbp_mwh: number | null;
  /**
   * Backend-owned exact source-price evidence. These are the original domain
   * `normalized_view._source_price_fields` names plus the exact/provenance pair
   * (`price_gbp_mwh_exact`, `price_gbp_mwh_provenance`); `price_gbp_mwh` above is
   * the existing numeric normalized field. The web client renders these strings
   * verbatim and never parses them into a float or performs FX arithmetic.
   */
  price_gbp_mwh_exact?: string | null;
  price_gbp_mwh_provenance?: string | null;
  source_price_status?: string | null;
  source_price_exact?: string | null;
  source_price_raw?: string | null;
  source_price_volume_mwh_exact?: string | null;
  source_price_volume_raw?: string | null;
  source_price_volume_status?: string | null;
  source_price_provenance?: string | null;
  source_price_issue?: string | null;
  source_price_issue_detail?: string | null;
  source_price_source_system?: string | null;
  source_price_source_reference?: string | null;
  source_price_source_dataset?: string | null;
  price_float_provenance?: string | null;
  price_semantics?: string | null;
  executable_quote?: boolean | null;
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
  /** Decision deadline (#58), UTC; null when none was set. */
  decision_due_at_utc?: string | null; deadline_state?: string;
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
  /** Who opened the case and when (absent from servers before the situational strip). */
  created_by?: string; created_at_utc?: string;
  evidence_count: number; alternative_count: number; assumption_count: number;
  record_count: number; reproducible: boolean;
  decision_due_at_utc?: string | null; deadline_state?: string;
  last_record: { outcome: string; actor: string; recorded_at_utc: string } | null;
}

export interface DecisionCaseCreateInputDTO {
  objective: string;
  gas_day?: string; delivery_product?: string; hub_id?: string;
  portfolio_ref?: string; snapshot_id?: string;
  /** ISO-8601 with an explicit offset; the API refuses a naive time. */
  decision_due_at_utc?: string | null;
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
  /** What the figure is and leaves out (NUM-05). */
  method?: RiskMethodNoteDTO;
}

export interface PortfolioLiveSummaryDTO {
  portfolio_id: string; latest_valuation_time_utc?: string | null;
  total_realized_pnl_gbp: number | null; total_unrealized_pnl_gbp: number | null;
  total_indicative_pnl_gbp: number | null; total_cash_value_gbp: number | null;
  open_order_count: number; filled_order_count: number; warnings: string[];
  research_only: boolean; human_review_required: boolean;
  method?: RiskMethodNoteDTO;
}

/**
 * The method note behind a risk figure (``domain/risk/method_notes.py``, NUM-05): what it
 * is, what it includes and leaves out, and its inputs' as-of times. ``i18n`` holds the keys
 * (``risk.method.<key>.*``) to translate the English text; ``params`` fills the summary.
 */
export interface RiskMethodNoteDTO {
  key: string;
  summary: string;
  includes: string[];
  excludes: string[];
  params: Record<string, string | number | null>;
  inputs_as_of: Record<string, string | null>;
  i18n: { summary: string; includes: string[]; excludes: string[] };
  review_status: string;
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

/**
 * One exact native-rate payload from the backend `entsog-native-units-v1`
 * normalizer. Every numeric token stays a string: the web client renders the
 * backend's exact decimal, it never converts or re-rounds it.
 */
export interface NativeRateDTO {
  value_text: string;
  unit_text: string;
  native_value: string;
  normalized_unit: string;
  quantity_kind: "energy" | "volume";
  rate_basis: "day" | "hour";
  energy_kwh_per_day: string | null;
  volume_mcm_per_day: string | null;
  normalizer_version: "entsog-native-units-v1";
}

interface NativePhysicalObservationBaseDTO {
  observation_id: string;
  source_record_id: string;
  point_id: string;
  point_name: string;
  direction: string;
  period_start_utc: string;
  period_end_utc: string;
  observed_at_utc: string | null;
  source_system: "ENTSOG";
  operator_key: string | null;
  flow_status: string | null;
  period_type: string | null;
  source_reference: string;
  research_only: boolean;
  quantity_basis: "native";
  normalizer_version: "entsog-native-units-v1";
  native_rate_json: NativeRateDTO;
  raw_archive_id: string | null;
  payload_sha256: string | null;
  received_at_utc: string | null;
}

/** One projected native-unit ENTSOG physical flow observation. */
export interface NativeFlowObsDTO extends NativePhysicalObservationBaseDTO {
  kind: string;
}

/** One projected native-unit ENTSOG physical capacity observation. */
export interface NativeCapacityObsDTO extends NativePhysicalObservationBaseDTO {
  capacity_type: string;
}

export interface NativePhysicalFetchOptions {
  /** Optional ENTSOG point identifier; surrounding whitespace is trimmed. */
  pointId?: string;
  /**
   * Inclusive lower bound. ISO 8601 with an explicit timezone (`Z` or `+-HH:MM`).
   * Must be supplied together with `toUtc`.
   */
  fromUtc?: string;
  /**
   * Exclusive upper bound. ISO 8601 with an explicit timezone (`Z` or `+-HH:MM`).
   * Must be supplied together with `fromUtc` and be later than it.
   */
  toUtc?: string;
  /** Page size, an integer from 1 to 2000. Defaults to 200. */
  limit?: number;
  signal?: AbortSignal;
}

const NATIVE_PHYSICAL_TIMESTAMP_PATTERN =
  /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.(\d{1,9}))?(Z|[+-]\d{2}:\d{2})$/;

/**
 * Parse a strict, timezone-aware ISO 8601 timestamp into an exact epoch instant.
 *
 * The backend expects aware datetimes and rejects naive ones, so the pattern
 * makes a `Z` or `+-HH:MM` zone mandatory. Calendar fields are checked here
 * instead of through `Date.parse`, which silently normalizes impossible dates
 * such as 2026-02-30. No clock/default is consulted: a range is only ever the
 * pair the caller supplied.
 *
 * The instant is integer epoch microseconds, not a JS number: modern epoch
 * milliseconds cannot distinguish a one-microsecond window, while the backend
 * compares Python datetimes at microsecond resolution. `datetime.fromisoformat`
 * truncates digits beyond six, so the fraction is padded/truncated to exactly
 * six digits before it is folded into the instant.
 */
function parseNativePhysicalTimestamp(
  value: unknown,
  label: "fromUtc" | "toUtc",
): { text: string; instant: bigint } {
  if (typeof value !== "string") {
    throw new Error(`${label} must be a string.`);
  }
  const match = NATIVE_PHYSICAL_TIMESTAMP_PATTERN.exec(value);
  if (!match) {
    throw new Error(
      `${label} must be an ISO 8601 timestamp with an explicit timezone (Z or +-HH:MM).`,
    );
  }

  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  const hour = Number(match[4]);
  const minute = Number(match[5]);
  const second = Number(match[6]);
  const fraction = match[7] ?? "";
  const zone = match[8] ?? "";
  const leapYear = (year % 4 === 0 && year % 100 !== 0) || year % 400 === 0;
  const daysInMonth =
    month === 2
      ? leapYear
        ? 29
        : 28
      : [4, 6, 9, 11].includes(month)
        ? 30
        : 31;
  if (
    year < 1 ||
    month < 1 ||
    month > 12 ||
    day < 1 ||
    day > daysInMonth ||
    hour > 23 ||
    minute > 59 ||
    second > 59
  ) {
    throw new Error(`${label} must be a valid calendar date and time.`);
  }

  let offsetMinutes = 0;
  if (zone !== "Z") {
    const offsetHour = Number(zone.slice(1, 3));
    const offsetMinute = Number(zone.slice(4, 6));
    if (offsetHour > 23 || offsetMinute > 59) {
      throw new Error(`${label} must use a valid explicit timezone offset.`);
    }
    offsetMinutes = (zone[0] === "-" ? -1 : 1) * (offsetHour * 60 + offsetMinute);
  }

  const instant = new Date(0);
  instant.setUTCFullYear(year, month - 1, day);
  instant.setUTCHours(hour, minute, second, 0);
  // Match the backend exactly: the first six fraction digits are microseconds,
  // any 7th-9th digits are truncated, and fewer digits are right-padded.
  const fractionMicros = BigInt((fraction + "000000").slice(0, 6));
  return {
    text: value,
    instant:
      BigInt(instant.getTime()) * 1000n +
      fractionMicros -
      BigInt(offsetMinutes) * 60n * 1_000_000n,
  };
}

function nativePhysicalQuery(options: NativePhysicalFetchOptions): URLSearchParams {
  if (!options || typeof options !== "object" || Array.isArray(options)) {
    throw new Error("Native physical options are required.");
  }

  const rawPointId = options.pointId;
  let pointId: string | undefined;
  if (rawPointId !== undefined) {
    if (typeof rawPointId !== "string") {
      throw new Error("pointId must be a string.");
    }
    pointId = rawPointId.trim();
    if (!pointId) {
      throw new Error("pointId must be non-blank.");
    }
    if (pointId.length > 128) {
      throw new Error("pointId must be at most 128 characters.");
    }
  }

  const rawLimit: unknown = options.limit === undefined ? 200 : options.limit;
  if (
    typeof rawLimit !== "number" ||
    !Number.isInteger(rawLimit) ||
    rawLimit < 1 ||
    rawLimit > 2000
  ) {
    throw new Error("limit must be an integer between 1 and 2000.");
  }

  const rawFromUtc: unknown = options.fromUtc;
  const rawToUtc: unknown = options.toUtc;
  const hasFromUtc = rawFromUtc !== undefined;
  const hasToUtc = rawToUtc !== undefined;
  if (hasFromUtc !== hasToUtc) {
    throw new Error("fromUtc and toUtc must be provided together.");
  }
  let fromUtc: string | undefined;
  let toUtc: string | undefined;
  if (hasFromUtc && hasToUtc) {
    const from = parseNativePhysicalTimestamp(rawFromUtc, "fromUtc");
    const to = parseNativePhysicalTimestamp(rawToUtc, "toUtc");
    if (from.instant >= to.instant) {
      throw new Error("fromUtc must be earlier than toUtc.");
    }
    fromUtc = from.text;
    toUtc = to.text;
  }

  const params = new URLSearchParams();
  params.set("quantity_basis", "native");
  if (pointId !== undefined) params.set("point_id", pointId);
  params.set("limit", String(rawLimit));
  if (fromUtc !== undefined && toUtc !== undefined) {
    // Forward the validated text verbatim: an explicit offset is preserved, and
    // URLSearchParams encodes the `+` sign rather than decoding it as a space.
    params.set("from_utc", fromUtc);
    params.set("to_utc", toUtc);
  }
  return params;
}

/**
 * Fetch projected native-unit ENTSOG physical flows through the shared API
 * transport, preserving the envelope's complete meta.
 */
export async function fetchNativeFlows(
  options: NativePhysicalFetchOptions = {},
): Promise<ApiResponse<NativeFlowObsDTO[]>> {
  const params = nativePhysicalQuery(options);
  return get<NativeFlowObsDTO[]>(
    "/physical/flows",
    params,
    options.signal ? { signal: options.signal } : {},
  );
}

/**
 * Fetch projected native-unit ENTSOG physical capacities through the shared API
 * transport, preserving the envelope's complete meta.
 */
export async function fetchNativeCapacity(
  options: NativePhysicalFetchOptions = {},
): Promise<ApiResponse<NativeCapacityObsDTO[]>> {
  const params = nativePhysicalQuery(options);
  return get<NativeCapacityObsDTO[]>(
    "/physical/capacity",
    params,
    options.signal ? { signal: options.signal } : {},
  );
}

export interface PriceConversionDTO {
  value: number;
  from_unit: string;
  converted: Record<string, number | null>;
  fx: Record<string, { rate: number; source?: string | null; fixing?: string; value_dates?: string[] }>;
  fx_fixing: {
    fixing_id: string; source_system: string; label: string; licensed: boolean;
    fixings_used: number; averaged: boolean;
  };
  factors: Record<string, number>;
}

/** The units authority's factors (``GET /api/analysis/ontology`` → ``units``). */
export interface UnitsReferenceDTO {
  /** MWh in one unit (energy) and m3 in one unit (volume). */
  energy_in_mwh: Record<string, number>;
  volume_in_m3: Record<string, number>;
  price_units: Record<string, { currency: string; divisor: number; unit: string }>;
  price_aliases: Record<string, string>;
  volume_to_energy: {
    gcv_kwh_per_m3: number;
    reference_conditions: string;
    valid_range_kwh_per_m3: [number, number];
    basis: string;
  };
  gas_day_calendar: string;
}

export interface OntologyDTO {
  entities: string[];
  relationships: string[];
  guardrails: string[];
  units?: UnitsReferenceDTO;
}

/** One fact an answer-bar question rests on: the line, its topic, source and as-of. */
export interface AskLineDTO {
  topic: string;
  text: string;
  source: string;
  as_of: string | null;
  simulated: boolean;
}

/** ``POST /api/analysis/ask``: the checked answer (or none) and the facts it rests on. */
export interface AskAnswerDTO {
  question: string;
  topics: string[];
  answer: string | null;
  /** "model": the checked model text is shown; "facts": only the fact lines. */
  basis: "model" | "facts";
  /** used; off (no model for this caller or deployment); refused (failed the checks); failed. */
  ai: "used" | "off" | "refused" | "failed";
  lines: AskLineDTO[];
  sources: string[];
  simulated: boolean;
  as_of: string;
  warnings: string[];
}

export interface StorageTrajectoryDTO {
  code: string; as_of_gas_day: string; fill_pct: number; inventory_twh: number;
  working_capacity_twh: number; target_pct: number; deviation_pp: number;
  effective_target_pct: number; target_inventory_twh: number; gap_twh: number;
  window_open: string; deadline: string; days_to_window_open: number; days_to_deadline: number;
  required_net_injection_to_window_twh_d: number | null;
  required_net_injection_to_deadline_twh_d: number | null;
  recent_net_injection_twh_d: number | null; pace_days_used: number;
  projected_fill_at_deadline_pct: number | null;
  status: "target_met" | "on_track" | "behind" | "unreachable" | "withdrawal_season";
  limitations: string[];
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
  label?: string | null;
  /** Whether the backend actually implements a live connection test for this provider. */
  connection_test_supported?: boolean;
  /** GIE-only: how the credential was resolved (env | file | credential_store | missing | ...). */
  credential_source_kind?: string;
  /** GIE-only: stable diagnostic codes, never secret content. */
  credential_diagnostics?: string[];
  /** GIE-only: declared backend support flags (connection_test, agsi, alsi). */
  support_flags?: string[];
  /** Where the key a backend call would use comes from (#38); never the key itself. */
  effective_source?: "env" | "file" | "credential_store" | "disabled" | "missing";
  /** The variable that set it, when it came from the environment or a key file. */
  effective_variable?: string | null;
  effective_source_detail?: string;
  /** Environment variables (and key-file variable) that can carry this provider's key. */
  credential_env_vars?: string[];
  /** False when a key can be stored but no connector reads it yet. */
  connector_implemented?: boolean;
  credential_note?: string;
  /** GIE-only: the existing certification gate state, reported separately from connectivity. */
  certification?: { stage: string; allows_live: boolean; reason: string } | null;
}

export interface GieConnectionProductDTO {
  product: string; ok: boolean; error_code: string | null; http_status: number | null;
  record_count: number; normalized_rows: number; provider_last_page: number | null;
  page_size: number | null; complete: boolean | null; bounded_partial: boolean;
  response_date: string | null;
}

export interface GieConnectionTestDTO {
  ok: boolean; error_code: string | null; products: GieConnectionProductDTO[];
  tested_at_utc: string; bounded?: boolean; market_data_persisted?: boolean;
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

/** "Why?" for one object (``POST /api/analysis/explain``). */
export type ExplainSubject = "alert" | "outage" | "credit" | "mandate" | "pnl";
export interface ExplanationDTO {
  subject: ExplainSubject;
  object_id: string;
  title: string;
  text: string;
  lines: string[];
  sources: string[];
  basis: "rule" | "model";
  simulated: boolean;
  warnings: string[];
  as_of: string;
}

/** Market reports (``/api/reports/...``): the catalogue, a plan, a stored report. */
export type ReportKind = "daily" | "weekly" | "monthly" | "situation" | "ask";
export type ReportAudience = "internal" | "shareable";

export interface ReportSectionTypeDTO {
  key: string;
  title: string;
  group: string;
  data_source: string;
  charts: string[];
  internal_only: boolean;
  params: string[];
  description: string;
}

export interface ReportCatalogueDTO {
  template_version: string;
  kinds: ReportKind[];
  daily_variants: ("morning" | "eod")[];
  audiences: ReportAudience[];
  groups: string[];
  sections: ReportSectionTypeDTO[];
  default_sections: Record<ReportKind, string[]>;
  pdf: string;
  /** Known hub codes (what a typed hub must resolve to). */
  hubs?: string[];
  /** What this user's form may offer, read before Generate (null: the store could not be read). */
  availability?: ReportAvailabilityDTO | null;
}

export interface ReportAvailabilityDTO {
  can_generate: boolean;
  reason: string | null;
  sections: Record<string, { state: "ok" | "not_held" | "unavailable"; reason: string | null; action?: string | null }>;
  audiences: Record<ReportAudience, { allowed: boolean; reason: string | null }>;
  period: { max_days: number; latest_end: string };
  ai: { available: boolean; reason: string | null };
  languages: ("en" | "zh-CN")[];
}

export interface ReportPlanDTO {
  kind: ReportKind;
  audience: ReportAudience;
  variant: "morning" | "eod" | null;
  sections: string[];
  hubs: string[];
  countries: string[];
  period_start: string | null;
  period_end: string | null;
  alert_id: string | null;
  outage_id: string | null;
  question: string | null;
  notes: string[];
}

export interface ReportPlanProposalDTO {
  question: string;
  answerable: boolean;
  message: string | null;
  missing: string[];
  basis: "model" | "rules";
  model_refusal: string | null;
  plan: ReportPlanDTO | null;
  notes: string[];
}

export interface ReportRequestDTO {
  kind: ReportKind;
  variant?: "morning" | "eod";
  audience: ReportAudience;
  sections?: string[];
  hubs?: string[];
  countries?: string[];
  period_start?: string;
  period_end?: string;
  alert_id?: string;
  outage_id?: string;
  question?: string;
  /** Print the data annex; omitted: the kind's default (weekly and monthly). */
  annex?: boolean;
  /** Optional reporting currency and energy unit; prices keep their native unit. */
  currency?: "EUR" | "GBP" | "USD";
  energy_unit?: "MWh" | "th" | "MMBtu";
  language?: "en" | "zh-CN";
  use_model?: boolean;
}

/** A scheduled report (``/api/reports/schedules``): generated on the worker for its roles. */
export interface ReportScheduleDTO {
  schedule_id?: string;
  name?: string;
  kind: "daily" | "weekly";
  variant?: "morning" | "eod" | null;
  sections?: string[];
  language: "en" | "zh-CN";
  at_utc: string;
  weekday?: number | null;
  roles: string[];
  email: boolean;
  enabled?: boolean;
}

export interface ReportSummaryDTO {
  report_id: string;
  kind: ReportKind;
  variant: string | null;
  title: string;
  audience: ReportAudience;
  headline: string;
  period_start: string | null;
  period_end: string | null;
  as_of: string | null;
  created_at: string | null;
  generated_by_type: string;
  simulated: boolean;
  licensed_families: string[];
  model_use: { attempted?: number; passed?: number };
  /** An asked report's question. */
  question?: string | null;
  generated_by?: string;
  edited_by?: "model" | "rule";
}

export interface ReportMetadataDTO {
  report_id: string;
  title: string;
  kind: ReportKind;
  audience: ReportAudience;
  headline: string;
  key_points: string[];
  as_of: string;
  simulated: boolean;
  sections: { key: string; title: string; status: string; commentary_basis: string; simulated: boolean; forecast: boolean }[];
  omitted: { key: string; title: string; reason: string; action: string | null }[];
  licensed: { sources?: string[] };
  model_use: { attempted?: number; passed?: number };
  snapshot_sha256: string;
  html_sha256: string;
  pdf: string;
  issue?: number;
  standfirst?: string | null;
  answer?: { text: string; fact_ids: string[]; basis: "model" | "rule" } | null;
  findings?: { fact_ids: string[]; text: string; implication: string | null; why: string; basis?: string }[];
  editorial?: { basis: "model" | "rule"; model: string | null; directive: string | null; temperature?: number | null; elements?: Record<string, { ok: boolean; detail: string }> };
}

/** A morning brief or end-of-day draft (``POST /api/analysis/brief``). */
export interface DeskBriefDTO {
  kind: "morning" | "eod";
  title: string;
  lead: string | null;
  lead_basis: "model" | "none";
  sections: { key: string; heading: string; lines: string[]; sources: string[] }[];
  text: string;
  simulated: boolean;
  warnings: string[];
  as_of: string;
}

/** Freshness-contract state of one figure (``application/freshness_contract.py``). */
export type FigureStateDTO = "current" | "late" | "stale" | "never" | "manual";

/** One Today figure: value, native unit, as-of time, state and simulated flag. */
export interface TodayFigureDTO {
  key: string;
  label: string;
  value: number | null;
  unit: string;
  as_of: string | null;
  state: FigureStateDTO;
  simulated: boolean;
  source: string | null;
  method?: RiskMethodNoteDTO;
  [extra: string]: unknown;
}

/** An explicit empty state: why there is nothing and what would fill it. */
export interface TodayEmptyDTO {
  code: string;
  reason: string;
  action: string;
}

export interface TodayPriceDTO extends TodayFigureDTO {
  hub: string;
  product: string;
  tenor: string;
  close_day: string;
  day_change: number | null;
  day_change_vs: string | null;
}

export interface TodayWhyDTO {
  subject: ExplainSubject;
  id: string;
}

/** A close on Today's market row: the hub's own quotation, its day change and 30 closes. */
export interface TodayMarketFigureDTO extends TodayFigureDTO {
  hub: string;
  product: string;
  tenor: "day-ahead" | "month-ahead";
  close_day: string;
  day_change: number | null;
  series: { day: string; value: number }[];
}

/** A front-month spread against TTF in EUR/MWh, with the route cost or why it is not given. */
export interface TodaySpreadDTO extends TodayFigureDTO {
  pair: string;
  product: string;
  fx: { base: string; quote: string; rate: number; [extra: string]: unknown } | null;
  route_cost: {
    value: number | null;
    unit: string;
    verdict: "in_the_money" | "out_of_the_money" | null;
    via?: string[];
    reason?: string;
  };
}

/** Design basis 2, E.2 row 1: my market. */
export interface TodayMarketDTO {
  hubs: {
    hub: string;
    day_ahead: TodayMarketFigureDTO | null;
    front_month: TodayMarketFigureDTO | null;
    empty: TodayEmptyDTO | null;
  }[];
  spreads: (TodaySpreadDTO | { pair: string; empty: TodayEmptyDTO })[];
  series_days: number;
}

/** Design basis 2, E.2 row 3: what needs me, ranked server-side, at most five. */
export interface TodayNeedsMeItemDTO {
  /** "strategy": a tracked strategy's changed, still actionable paper signal. */
  kind: "opportunity" | "outage" | "limit" | "strategy";
  id: string;
  title: string;
  title_zh?: string | null;
  simulated: boolean;
  as_of: string | null;
  lane?: "must_act" | "could_act";
  headline?: { value: string | null; unit: string | null } | null;
  period?: string | null;
  target?: { mode: string; task: string; params?: Record<string, string> };
  hub?: string;
  touches_book?: boolean;
  size?: { value: number | null; unit: string | null };
  status?: string | null;
  utilisation_pct?: number | null;
  /** Since when an outage is out (or from when planned); none for a standing limit state. */
  since_utc?: string | null;
  why?: TodayWhyDTO | null;
}

/** A day's quantity in the hub's desk unit (NBP th/d; continental MWh/d with its MW). */
export interface GasDayQuantityDTO {
  value: number;
  unit: "th/d" | "MWh/d";
  mwh: number;
  mw?: number;
}

export interface GasDayTargetDTO {
  mode: string;
  task: string;
  params: Record<string, string>;
}

export interface GasDayLineDTO {
  ref: string;
  direction: "in" | "out";
  kind: string;
  label: string;
  point: string | null;
  /** nominated, contract_quantity, booked, booked_today, scheduled, slot. */
  basis: string;
  book_id: string;
  quantity: GasDayQuantityDTO;
  simulated: boolean;
  prompt_trade: boolean;
  target: GasDayTargetDTO;
}

export interface GasDayCutoffDTO {
  key: "nomination" | "last_renomination" | "gas_day_end" | "window";
  name: string | null;
  at_utc: string;
  /** held: a declared window; assumption: the network-code default; calendar: the gas day. */
  basis: "held" | "assumption" | "calendar";
  source: string;
  passed: boolean;
}

export interface GasDayCostDTO {
  value: number | null;
  currency: string;
  basis: "balanced" | "assumption" | "missing";
  reason?: string;
  rate?: number;
  rate_unit?: string;
  side?: "long_discount" | "short_premium";
  assumption_set?: string;
  assumption_version?: number;
}

export interface GasDayHubDTO {
  hub: string;
  state: "long" | "short" | "balanced";
  in: GasDayQuantityDTO;
  out: GasDayQuantityDTO;
  net: GasDayQuantityDTO;
  lines: GasDayLineDTO[];
  done_today: { trades: number; bought: GasDayQuantityDTO; sold: GasDayQuantityDTO; target: GasDayTargetDTO };
  delegated: { ref: string; label: string; direction: "in" | "out"; quantity: GasDayQuantityDTO; trader: string; trader_name: string; delegation_id: string | null; book: string }[];
  cutoffs: GasDayCutoffDTO[];
  cost_of_nothing: GasDayCostDTO;
  books: string[];
  simulated: boolean;
}

/** Today row 6, "My gas day" (`application/gas_day.py`): appended, so rows keep their positions. */
export interface TodayGasDayRowDTO {
  key: "gas_day";
  title: string;
  scope: { kind: "mandate" | "all_books"; mandates: { id: string; name: string; hubs: string[] }[]; books: string[] | null } | null;
  days: { gas_day: string; which: "today" | "tomorrow"; hours: number; hubs: GasDayHubDTO[] }[];
  simulated: boolean;
  populated: boolean;
  empty: TodayEmptyDTO | null;
}

export interface TodayNeedsMeRowDTO {
  key: "needs_me";
  title: string;
  populated: boolean;
  empty: TodayEmptyDTO | null;
  items: TodayNeedsMeItemDTO[];
  more: number;
  /** One sentence when nothing qualifies; the row is then not shown. */
  quiet: string | null;
}

export interface TodayKeyFiguresRowDTO {
  key: "key_figures";
  title: string;
  populated: boolean;
  /** Design basis 2, E.2 row 1 (the focus hubs' DA and front month, the spreads). */
  market?: TodayMarketDTO;
  prices: (TodayPriceDTO | { key: string; hub: string; empty: TodayEmptyDTO })[];
  prices_empty: TodayEmptyDTO | null;
  position: { today: TodayFigureDTO; front_month: TodayFigureDTO } | null;
  position_empty: TodayEmptyDTO | null;
  tightest_limit:
    | (TodayFigureDTO & {
        kind: "credit" | "mandate";
        name: string;
        status: string;
        utilisation_pct: number;
        why: TodayWhyDTO;
        counts: { breach: number; watch: number; expired: number; shown: number };
      })
    | null;
  limit_empty: TodayEmptyDTO | null;
}

export interface TodayChangesRowDTO {
  key: "changes";
  title: string;
  populated: boolean;
  empty: TodayEmptyDTO | null;
  alerts: {
    counts: { open: number; critical: number; warning: number };
    items: {
      alert_id: string;
      severity: "warning" | "critical";
      category: string;
      title: string;
      title_zh: string;
      as_of: string | null;
      simulated: boolean;
      why: TodayWhyDTO;
    }[];
    more: number;
    listed_elsewhere: number;
  };
  outages: {
    counts: { active: number; scheduled: number; total: number };
    horizon_days: number;
    as_of: string | null;
    state: FigureStateDTO;
    items: {
      event_id: string;
      facility: string;
      zone: string | null;
      status: string;
      start_utc: string;
      end_utc: string | null;
      unavailable: number | null;
      unit: string | null;
      as_of: string | null;
      simulated: boolean;
      /** Every operator that published the event (newer servers). */
      operators?: string[];
      message_count?: number;
      why: TodayWhyDTO;
    }[];
    more: number;
  };
}

export interface TodayBookRowDTO {
  key: "book";
  title: string;
  populated: boolean;
  empty: TodayEmptyDTO | null;
  horizon_months?: number;
  hubs: {
    hub: string;
    position_today: TodayFigureDTO;
    position_front_month: TodayFigureDTO;
    net_open_mwh: number;
    /** In the hub's quotation (NBP GBp/th); the book's per-MWh value travels with it. */
    mark: (TodayFigureDTO & { same_as: string | null; value_mwh?: number; unit_mwh?: string }) | null;
    day_pnl_change: TodayFigureDTO | { empty: TodayEmptyDTO };
  }[];
}

export interface TodayFundamentalsRowDTO {
  key: "fundamentals";
  title: string;
  populated: boolean;
  empty: TodayEmptyDTO | null;
  storage:
    | {
        latest: TodayFigureDTO;
        inventory_twh: number;
        unit: string;
        series: { day: string; inventory_twh: number; fill_pct: number | null }[];
        /** About four months of fill against the same gas days a year earlier. */
        season?: { day: string; fill_pct: number | null; previous_year_fill_pct: number | null }[];
        /** The EU filling target: met at any point between window_open and deadline ("MM-DD"). */
        target?: { pct: number; window_open: string; deadline: string };
      }
    | { empty: TodayEmptyDTO };
  balance:
    | {
        latest: TodayFigureDTO;
        unit: string;
        series: {
          day: string;
          call_gwh: number;
          norway_gwh: number;
          lng_gwh: number;
          storage_net_withdrawal_gwh: number;
        }[];
        call_7d_avg_gwh?: number | null;
        lng_gwh?: number | null;
        lng_vs_yesterday_gwh?: number | null;
      }
    | { empty: TodayEmptyDTO };
  /** The storage fundamentals read for the EU (CP-04), as Today shows it. */
  storage_europe?: { region: unknown; countries: unknown[]; focus_countries: string[]; simulated: boolean } | { empty: TodayEmptyDTO };
}

/** A measure as the opportunity engine carries it: decimal text, never a float. */
export interface OpportunityMeasureDTO {
  value: string | null;
  unit: string;
  currency?: string | null;
}

/** One row of `GET /api/opportunities` (CP-08): the claim and its figures, ranked by the server. */
export interface OpportunityRowDTO {
  opportunity_id: string;
  key: string;
  type: string;
  type_code: string;
  lane: "must_act" | "could_act" | "market";
  state: "new" | "actionable" | "indicative" | "watch" | "blocked" | "expired" | "converted";
  claim: string;
  headline: { value: string | null; unit: string };
  value: { amount: string | null; currency: string } | null;
  volume: { value: string | null; unit: string } | null;
  period: string;
  quality: { class: string; label: string };
  simulated: boolean;
  book_ids: string[];
  expires_at_utc: string;
  deadline_utc: string | null;
  version: number;
  first_seen_utc: string;
  last_evaluated_utc: string;
  reasons: string[];
  blocked: { code: string; subject: string; text: string; fix: string } | null;
  rank: { position: number; reason: string } | null;
  user_state: { state: string; reason: string | null; at_version: number; changed_since: boolean } | Record<string, never> | null;
  /** What it is about, in words ("Haldor supply (Easington)", "TTF → THE"). */
  subject: string;
  period_start: string | null;
  period_end: string | null;
  /** One item per subject: its months (largest first) and their totals. */
  group?: OpportunityGroupDTO;
}

export interface OpportunityGroupMemberDTO {
  opportunity_id: string;
  period: string;
  period_start: string | null;
  headline: { value: string | null; unit: string };
  value: { amount: string | null; currency: string } | null;
  volume: { value: string | null; unit: string } | null;
  state: OpportunityRowDTO["state"];
  deadline_utc: string | null;
  expires_at_utc: string;
}

export interface OpportunityGroupDTO {
  count: number;
  members: OpportunityGroupMemberDTO[];
  total_value: { amount: string | null; currency: string } | null;
  total_volume: { value: string | null; unit: string } | null;
}

export interface OpportunityBucketDTO {
  total: number;
  offset: number;
  items: OpportunityRowDTO[];
  next_cursor: string | null;
}

/** What the engine needs before it can find anything (B.7 "Empty on day one"). */
export interface OpportunityReadinessDTO {
  book: { ready: boolean; contracts: number; approved_hedge_bands: number; missing: string | null };
  prices: {
    ready: boolean;
    licensed_quote_sources: string[];
    settlement_sources: string[];
    firm_marks: number;
    /** On a demo desk: the simulated market it may read (labelled simulated). */
    simulated_sources?: string[];
    missing: string | null;
  };
  published_costs: {
    ready: boolean;
    transport_tariffs: number;
    /** On a demo desk: the demo's simulated tariffs (labelled simulated). */
    simulated_transport_tariffs?: number;
    terminal_terms: number;
    missing: string | null;
  };
  assumptions: { ready: boolean; approved_versions: number; missing: string | null };
  types_now: string[];
}

export interface OpportunityListDTO {
  as_of_utc: string | null;
  evaluation: {
    evaluation_id: string;
    status: string;
    finished_at_utc: string;
    demo_desk: boolean;
    /** "schedule" (inputs changed) or "on_demand" (a person asked). */
    trigger?: string;
    next: { pending_inputs: string[]; last_scheduled_utc: string | null; not_before_utc: string | null } | string;
  } | null;
  lanes: Partial<Record<"must_act" | "could_act" | "market", OpportunityBucketDTO>>;
  groups: Partial<Record<"watching" | "blocked", OpportunityBucketDTO>>;
  confirming: number;
  hidden_by_you: number;
  per_lane_shown: number;
  simulated: boolean;
  banner: string | null;
  readiness: OpportunityReadinessDTO;
}

export interface OpportunityLegDTO {
  kind: "term" | "subtotal" | "conversion" | "result" | "volume" | "value";
  label_key: string;
  label: string;
  quantity: OpportunityMeasureDTO | null;
  rate: OpportunityMeasureDTO | null;
  fx: OpportunityMeasureDTO | null;
  contribution: OpportunityMeasureDTO | null;
  subtotal: OpportunityMeasureDTO | null;
  input_class: string | null;
  source_family: string | null;
  source_ref: string;
  as_of_utc: string | null;
  input_keys: string[];
  note: string;
}

/** The frozen object of one version: what the arithmetic was when it was evaluated. */
export interface OpportunityObjectDTO {
  type: string;
  lane: string;
  claim: { key: string; fields: Record<string, unknown>; text: string };
  legs: OpportunityLegDTO[];
  assumptions: {
    key: string;
    value: OpportunityMeasureDTO;
    origin: string;
    set_by: string;
    set_at_utc: string;
    input_key: string | null;
    range_low: string | null;
    range_high: string | null;
  }[];
  falsifiers: { key: string; text: string }[];
  sensitivity: { driver: string; kind: string; value: OpportunityMeasureDTO; text: string }[];
  checks: { kind: string; result: "pass" | "fail" | "not_assessed"; figure: string; reference: string }[];
  quality: {
    class: string;
    label: string;
    simulated: boolean;
    inputs: {
      key: string;
      kind: string;
      class: string;
      label: string;
      source_family: string | null;
      source_ref: string;
      as_of_utc: string | null;
      value: string | null;
      unit: string;
    }[];
  };
}

/** `GET /api/opportunities/{id}`: the row, its frozen object, snapshot, versions and case. */
export interface OpportunityDetailDTO extends OpportunityRowDTO {
  object: OpportunityObjectDTO | null;
  snapshot: Record<string, unknown> | null;
  versions: { version: number; state: string; snapshot_id: string; recorded_at_utc: string }[];
  case: { case_id: string; converted_by: string; converted_at_utc: string } | null;
  ended_reason: string | null;
  next_steps: ("open_as_case" | "watch" | "dismiss")[];
}

/** One of the firm's own marks (`/api/market/firm-marks`): always "firm's mark", never a market price. */
export interface FirmMarkDTO {
  mark_id: string;
  hub: string;
  period: string;
  value: number;
  unit: string;
  currency: string;
  input_class: "firm_mark";
  class_label: string;
  entered_by: string;
  entered_at_utc: string;
  note: string;
}

/** ``GET /api/desk/today`` (UX-05): the four rows of the Today screen, computed once. */
export interface DeskTodayDTO {
  as_of: string;
  gas_day: string;
  front_month: string;
  simulated: boolean;
  /** Every figure simulated: the page says so once and drops the per-figure marker. */
  all_simulated?: boolean;
  simulated_notice: string | null;
  rows: [TodayKeyFiguresRowDTO, TodayChangesRowDTO, TodayBookRowDTO, TodayFundamentalsRowDTO, TodayNeedsMeRowDTO?, TodayGasDayRowDTO?];
  /** My hubs: the user's list, else the book's, then the board's (at most four). */
  focus_hubs?: string[];
  /** Every late or stale figure by name (FRESH-02), instead of a page-wide "N feeds stale". */
  stale_figures: { key: string; label: string; state: FigureStateDTO; as_of: string | null }[];
  warnings: string[];
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
  // Currency of contract_price_gbp_mwh (the name predates it); absent from older servers = GBP.
  contract_price_currency?: "GBP" | "EUR" | "USD";
  settlement_frequency: string; upstream_payment_lag_days: number; screen_sale_cash_lag_days: number;
  delivery_tolerance_pct: number; nomination_tolerance_pct: number;
  tolerance_risk_allowance_gbp_mwh?: number | null; annual_financing_rate_pct: number;
  /** Funding segments (#14); [] when the contract is funded at its single rate. */
  financing_tranches?: Array<{ lender: string; principal: number; annual_rate_pct: number; day_count: "ACT/365F" | "ACT/360" }>;
  owned_entry_capacity_mwh_per_day?: number | null; owned_exit_capacity_mwh_per_day?: number | null;
  allowed_exit_points: string[]; eligible_sale_modes: string[]; updated_at_utc?: string;
  variable_cost_gbp_mwh?: number; regas_fee_gbp_mwh?: number; fuel_loss_allowance_pct?: number;
  notes?: string | null;
  // The operator-declared payment terms the stored row carries: the strict canonical
  // `contract-payment-terms/v1` document, or `null` for "not stated". Optional because a
  // response from a deployment that predates the carrier carries no field at all, which is
  // "unknown", never "nothing declared"; the model that decides that is
  // `app/model/contractPaymentTerms.ts`.
  payment_terms?: PaymentTermsDTO | null;
  research_only?: boolean; human_review_required?: boolean;
  // Opaque stale-edit token of the stored row (GET and write response). It
  // covers every persisted field of the contract, is not the captured revision
  // number, and is sent back as `expected_edit_token` when this row is edited.
  // A create-only save omits it.
  edit_token?: string;
  /** Lifecycle: set once the contract is retired (it then leaves positions and risk). */
  retired_at_utc?: string | null;
  retired_by?: string | null;
  /** Display name of the person who retired it (the list with retired contracts). */
  retired_by_name?: string | null;
  retire_reason?: string | null;
  /**
   * Contract kind (docs/product/CONTRACT_TYPES.md): SUPPLY_GSA, UPSTREAM_TENDER, LNG_MSPA,
   * LNG_CARGO (and kinds named but not entered here). Absent from older servers = SUPPLY_GSA.
   */
  contract_kind?: string;
  /** False while a migrated row's kind is inferred and not yet confirmed by a person. */
  contract_kind_reviewed?: boolean;
  /** The kind's typed terms (with their `schema` label), or null. */
  kind_terms?: Record<string, unknown> | null;
  /** Terms the product does not model yet, kept verbatim. */
  unmodelled_terms?: string | null;
  /** A confirmation's master agreement (an LNG cargo's MSPA). */
  master_contract_id?: string | null;
  /** The one figure that matters for the kind (native units), from the server. */
  headline?: { key: string; value: number; min?: number; max?: number; unit: string; term?: string; window?: string[] } | null;
  // Additive write metadata: how the governed upsert classified this write and
  // which captured economic revision is newest afterwards. Capture-time evidence,
  // not a revision history or an edit-conflict protocol.
  write_outcome?: "created" | "economics_updated" | "metadata_updated" | "unchanged";
  latest_revision?: {
    contract_revision_id: string; contract_id: string; revision_number: number;
    capture_origin: string; content_hash: string; recorded_at_utc: string; recorded_by: string;
  } | null;
}

/**
 * One declared date specification of a payment-schedule item (read-only transport).
 *
 * Exactly one shape applies, discriminated by `kind`: an operator-stated final payable date,
 * or a rule anchored to a reviewed event that has **not** been resolved into a date. This is
 * the decoded stored declaration, not a calculation: the client neither resolves an anchor
 * nor derives an amount or date from these fields.
 */
export type PaymentDateSpecificationDTO =
  | {
      kind: "EXPLICIT_DATE";
      final_payable_date: string;
      source_reference: string;
    }
  | {
      kind: "ANCHORED_RULE";
      anchor_event: string;
      anchor_offset_days: number;
      offset_day_kind: string;
      business_day_convention: string;
      calendar_reference: string | null;
      source_reference: string;
    };

/** One declared payable line of a stored payment schedule (read-only transport). */
export interface PaymentScheduleItemDTO {
  item_id: string;
  cash_flow_category: string;
  flow_direction: "INFLOW" | "OUTFLOW";
  source_reference: string;
  date_specification: PaymentDateSpecificationDTO;
}

/**
 * The stored `contract-payment-terms/v1` declaration a contract read may carry.
 *
 * Field names, enum spellings and the single date shape are the backend domain model's, not a
 * client taxonomy: the client decodes this document strictly before rendering it and defines
 * no parallel vocabulary or calculator.
 */
export interface PaymentTermsDTO {
  schema_version: string;
  quantity_basis_reference: string;
  items: PaymentScheduleItemDTO[];
}

export type UpstreamContractInputDTO = Omit<
  UpstreamContractDTO,
  | "updated_at_utc"
  | "research_only"
  | "human_review_required"
  | "write_outcome"
  | "latest_revision"
  | "edit_token"
  // Declared payment terms are read-only in this client: omission preserves the stored
  // declaration (the write route reads presence from `model_fields_set`), so no save builder
  // may set or clear them until an explicit editing workflow is reviewed.
  | "payment_terms"
  | "headline"
  | "contract_kind_reviewed"
> & {
  notes?: string | null;
  /**
   * The edit token read for the stored contract this save updates, or null for
   * a create-only save. Omitting or nulling it never overwrites an existing
   * identity: the backend answers 409 `contract_edit_conflict`.
   */
  expected_edit_token?: string | null;
};

/** A contract's price for one delivery month (`GET /api/contracts/{id}/price`). */
export interface ContractPriceDTO {
  contract_id: string;
  month: string;
  price_terms: Record<string, unknown> | null;
  note: string | null;
  result: {
    value: number | null;
    unit: string;
    currency: string | null;
    input_class: string;
    words: string;
    inputs: Array<{ index: string; weight: number; value: number; unit: string; read_value: number; read_unit: string; input_class: string; source_ref: string; as_of: string | null; window: [string, string]; observations: number }>;
    missing: string[];
    notes: string[];
  } | null;
}

/** A typed contract's write: the server derives the base columns from `kind_terms`. */
export interface TypedContractInputDTO {
  contract_id: string;
  contract_name: string;
  contract_kind: string;
  kind_terms?: Record<string, unknown> | null;
  master_contract_id?: string | null;
  unmodelled_terms?: string | null;
  notes?: string | null;
  expected_edit_token?: string | null;
}

/**
 * One captured immutable economic revision of an upstream contract (transport
 * only). `snapshot` is the stored canonical document: exact decimal strings and
 * null-versus-zero exactly as captured. This is capture-time evidence, not a
 * complete history and not payment terms; do not derive dates or amounts here.
 */
export interface UpstreamContractRevisionDTO {
  scope?: string; data_source?: string;
  contract_revision_id: string; contract_id: string; revision_number: number;
  schema_version: string; capture_origin: string; content_hash: string;
  recorded_at_utc: string; recorded_by: string;
  display_metadata: { contract_name: string; operator_notes: string | null };
  snapshot: Record<string, unknown>;
}

/** One bounded, ordered page of a contract's captured revisions, oldest first. */
export interface UpstreamContractRevisionListDTO {
  scope: string; data_source: string; contract_id: string;
  revision_count: number; returned_count: number; has_more: boolean;
  limit: number; offset: number;
  revisions: UpstreamContractRevisionDTO[];
}

/**
 * One candidate in a route-comparison request.
 *
 * `manual_cost` is an explicit value or null for unknown. It is never defaulted
 * to zero. A `*_gbp_mwh` value is already GBP/MWh and travels with that identity.
 */
export interface RouteRecommendationCandidateDTO {
  route_id: string;
  route_name: string;
  destination_market?: string | null;
  sale_price?: number | null;
  price_currency?: string | null;
  price_unit?: string | null;
  required_tso_access?: string[];
  available_capacity_mwh_per_day?: number | null;
  capacity_status?: string | null;
  manual_cost?: number | null;
  cost_currency?: string | null;
  cost_unit?: string | null;
  /** Source-option date carried as evidence; the request-level date governs. */
  tariff_applicability_date?: string | null;
  /** Caller provenance only; the backend echoes it as unverified input. */
  source_refs?: string[];
}

export interface RouteRecommendationRequestDTO {
  request_id: string; source_point_id: string; target_point_id?: string | null;
  required_quantity_mwh_per_day: number; gas_year: string;
  /**
   * Explicit delivery gas day the selected tariffs must cover, or null.
   * The Web builder carries the caller's current canonical gas day here; null
   * is "not assessed" and is never replaced with a clock or metadata instant.
   */
  tariff_applicability_date?: string | null;
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
    netback?: number | null;
    /** Backend tariff references plus caller refs prefixed `unverified_input:`. */
    source_refs?: string[];
    /** Caller refs exactly as supplied; unverified and non-binding. */
    unverified_input_source_refs?: string[];
    rationale: string[];
  }>;
  excluded_routes: Array<Record<string, unknown>>;
  warnings: string[]; assumptions: string[];
  /** The explicit date the tariffs were selected for, or null when not assessed. */
  tariff_applicability_date?: string | null;
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
  /**
   * The interconnection path the route was priced along (domain/route_cost/route_adjacency.py):
   * "proven" with the crossings and the node ids hub -> point(s) -> hub, "local", or why the
   * route is not connected.
   */
  route_adjacency?: {
    status: "proven" | "local" | "no_proven_connection" | "endpoint_not_in_network";
    crossings?: Array<{ from_hub: string; to_hub: string; points: string[]; point_names: string[]; pipeline_operator: string | null }>;
    path_node_ids?: string[];
    detail?: string;
  } | null;
  sale_price_gbp_mwh: number; route_cost_gbp_mwh?: number | null;
  /** The backend-normalized identity of `sale_price_gbp_mwh` (GBP/MWh). */
  sale_price_currency?: string | null; sale_price_unit?: string | null;
  /** The backend-normalized identity of `route_cost_gbp_mwh` (GBP/MWh). */
  route_cost_currency?: string | null; route_cost_unit?: string | null;
  sale_price_source_system?: string | null; sale_price_source_reference?: string | null;
  sale_price_observed_at_utc?: string | null; sale_price_freshness?: string | null;
  sale_price_quality_score?: number | null; sale_price_simulated?: boolean;
  sale_price_source_family?: string | null;
  capacity_limit_mwh_per_day?: number | null;
  /** KNOWN | NOT_REQUIRED | UNKNOWN; missing state must not be read as NOT_REQUIRED. */
  capacity_status?: "KNOWN" | "NOT_REQUIRED" | "UNKNOWN" | string | null;
  /** The date the backend selected this option's tariff for, or null if unassessed. */
  tariff_applicability_date?: string | null;
  /** Tariff/document provenance the backend actually used for the route cost. */
  route_cost_source_refs?: string[];
  screen_sale_cash_lag_days?: number | null;
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
    // The financing rate that slice used (its contract's own, else the scenario default) (#14).
    financing_rate_pct?: number | null; financing_rate_source?: "contract" | "contract_tranches" | "scenario_default" | null;
    financing_day_count?: "ACT/365F" | "ACT/360" | null;
    /** Per funding segment when the contract is funded by several lenders (#14). */
    financing_tranches?: Array<{
      lender: string; principal: number; share: number; annual_rate_pct: number;
      day_count: "ACT/365F" | "ACT/360"; lag_days: number; early_cash_value_gbp_mwh: number;
    }>;
    net_pnl_gbp_per_day: number; warnings: string[];
  }>;
  missing_inputs: string[]; assumptions: string[]; warnings: string[]; source_refs: string[];
  research_only: boolean; human_review_required: boolean;
}

export interface ResourcePoolOptionsDTO {
  scope: string; data_source: string;
  /** The explicit gas day the composition selected tariffs for, or null. */
  tariff_applicability_date?: string | null;
  portfolio_resources: PortfolioResourceDTO[];
  sale_options: PortfolioSaleOptionDTO[];
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

export type StrategyVisibility = "PRIVATE" | "PUBLIC" | "GROUPS";

export interface StrategyDTO {
  owner_principal_id?: string | null; visibility?: StrategyVisibility;
  shared_group_ids?: string[]; can_manage?: boolean;
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
  /** Honest evidence diagnostics; never presented as fresh observed coverage. */
  distinct_admitted_price_refs?: number;
  events_reusing_admitted_price_refs?: number;
  events_with_simulated_evidence?: number;
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
  /** Desk detail, when the term has it. */
  unit?: string; formula?: string; example?: string; where_in_app?: string[];
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

export type PreferenceKey =
  | "language"
  | "theme"
  | "market_view"
  | "market_board_layout"
  | "pnl_colors"
  // Times shown in: device | utc | market (app/time/timeFormat.ts).
  | "time_zone"
  // The secondary value beside a native figure and totals across currencies
  // (app/time/valueFormat.ts, design basis G2): an ECB currency and MWh | th | MMBtu | GJ.
  | "reporting_currency"
  | "energy_unit"
  // The situational strip (docs/product/ROLE_FIRST_REDESIGN.md §5): thresholds, focus hubs,
  // the quiet line, and the items this person hid (personal only).
  | "strip_outage_gwh_d"
  | "strip_outage_share_pct"
  | "strip_price_move_pct"
  | "strip_quiet_line"
  | "strip_focus_hubs"
  | "strip_hidden";

export interface PreferencesDTO {
  personal: Partial<Record<PreferenceKey, string>>;
  organisation_defaults: Partial<Record<PreferenceKey, string>> & { enabled_languages?: string[] };
  effective: Record<PreferenceKey, string> & { enabled_languages: string[] };
  updated_at_utc: string | null;
}

export type OrganisationSettingsDTO = Partial<Record<PreferenceKey, string>> & { enabled_languages?: string[] };

export interface PositionLadderRowDTO {
  hub: string;
  month: string;
  physical_mwh: number;
  financial_mwh: number;
  net_mwh: number;
  hedge_ratio: number | null;
  /** Price the month is marked at, in the hub's unit; null when nothing marks it. */
  mark?: number | null;
  /** "quoted", "derived" (from a quarter, season or year), "front" (prompt) or "flat". */
  mark_method?: string | null;
  /** The unit of `mark`: the hub's currency per MWh. */
  mark_unit?: string;
  /** The same mark as the desk quotes the hub (NBP in GBp/th), for display. */
  mark_quote?: number | null;
  mark_quote_unit?: string;
}

/** A market-data licence the firm holds; licensed data scopes are granted against it. */
export interface MarketDataLicenceInput {
  vendor: string;
  source_family: string;
  licence_type: "ENTERPRISE" | "SITE" | "NAMED_USER";
  licensed_use: "DISPLAY" | "NON_DISPLAY" | "DISPLAY_AND_NON_DISPLAY";
  valid_from: string;
  valid_to?: string | null;
  offices?: string[];
  seats?: number | null;
  contract_reference?: string;
  notes?: string;
}

export interface MarketDataLicenceDTO extends MarketDataLicenceInput {
  licence_id: string;
  active: boolean;
  holders: { principal_id: string; display_name: string; office: string | null }[];
  seats_used: number | null;
  updated_by: string;
  updated_at_utc: string;
}

export interface NweBalanceDayDTO {
  day: string;
  call_gwh: number;
  norway_gwh: number;
  norway_outage_gwh?: number;
  lng_gwh: number;
  storage_net_withdrawal_gwh: number;
  /** Forecast days: the part of the storage draw taken from the facilities in `inventory_twh`. */
  inventory_draw_gwh?: number | null;
  inventory_twh?: number | null;
  fill_pct?: number | null;
  methods?: Record<string, string>;
  flags?: string[];
}

export interface MapLocationDTO {
  lon: number;
  lat: number;
  ref_id?: string;
  ref_kind?: "node" | "facility";
  match?: "eic" | "name" | "feed";
  coordinate_quality?: string;
  country?: string | null;
}

export interface MapOutageDTO {
  event_id: string;
  facility_name: string;
  asset_type: string;
  event_type: string;
  status: "active" | "scheduled";
  start_utc: string;
  end_utc: string | null;
  balancing_zone: string;
  unit: string;
  technical_capacity: number | null;
  unavailable_capacity: number | null;
  unavailable_gwh_d: number | null;
  unavailable_share: number | null;
  description: string;
  market_participant: string;
  source_system: string;
  location: MapLocationDTO;
}

export interface MapPointFlowDTO {
  point_id: string;
  point_name: string;
  direction: string;
  /** The closed gas day shown (its calendar date); the open day is never shown. */
  gas_day?: string | null;
  gas_day_start_utc: string | null;
  gas_day_end_utc?: string | null;
  value: number | null;
  unit: string;
  gwh_d: number | null;
  source_system: string;
  /** ENTSOG operator whose report is shown; direction is relative to its system. */
  operator_key?: string | null;
  location: MapLocationDTO;
}

export interface MapContractDTO {
  contract_id: string;
  contract_name: string;
  resource_type: string;
  delivery_point: string;
  gas_year: string;
  delivery_mwh_d: number;
  entry_capacity_mwh_d: number | null;
  book_id: string | null;
  location: MapLocationDTO;
}

export interface MapCargoDTO {
  cargo_id: string;
  vessel_name: string;
  vessel_imo: string | null;
  status: "loading" | "laden" | "discharging" | "delivered" | "ballast";
  load_port: string;
  departed_at_utc: string | null;
  destination_terminal: string | null;
  eta_utc: string | null;
  position_at_utc: string | null;
  volume_m3: number | null;
  energy_gwh: number | null;
  own: boolean;
  book_id: string | null;
  source_system: string;
  origin: MapLocationDTO | null;
  position: MapLocationDTO | null;
  destination: MapLocationDTO | null;
  track: Array<[number, number]>;
  /** When the vessel was at each track point (ISO, null when not reported); newer servers. */
  track_times?: Array<string | null>;
}

export interface MapRegasSlotDTO {
  slot_id: string;
  terminal_name: string;
  window_start_utc: string;
  window_end_utc: string;
  active: boolean;
  send_out_gwh_d: number | null;
  energy_gwh: number | null;
  cargo_id: string | null;
  book_id: string | null;
  location: MapLocationDTO;
}

export interface MapUnlocatedPointDTO {
  point_key: string;
  point_name: string;
  countries: string[];
  operators: string[];
  reason: string;
}

export interface MapSituationDTO {
  as_of_utc: string;
  outages: MapOutageDTO[];
  flows: MapPointFlowDTO[];
  /** How the flow shown at each point was chosen (closed gas day, one operator). */
  flow_rule?: string;
  contracts: MapContractDTO[];
  cargoes: MapCargoDTO[];
  regas_slots: MapRegasSlotDTO[];
  /** `network_points` and `flows` on newer servers: points with no published position. */
  unlocated: Record<"outages" | "contracts" | "cargoes" | "regas_slots", number> &
    Partial<Record<"network_points" | "flows", number>>;
  /** Network points the reference knows but no source places (newer servers). */
  unlocated_network_points?: MapUnlocatedPointDTO[];
  /** Outages no source places, with why (newer servers). */
  unlocated_outages?: Array<{ event_id: string; facility_name: string; facility_id: string; market_participant?: string | null; reason: string }>;
  /** Outages at a facility GIE identifies but no accepted source positions (newer servers). */
  known_facility_outages?: Array<{
    facility_eic: string;
    facility_name: string | null;
    country: string | null;
    operator: string | null;
    /** `no_published_position`, or `outside_reference_network` (no reference point in that country). */
    reason: string;
    outages: number;
    event_ids: string[];
    /** Sites of a virtual storage group the reviewed alias table tied to it (newer servers). */
    sites?: string[];
  }>;
  /** Counts of everything the caller may see, placed on the map or not. */
  totals?: Record<"outages_active" | "outages_scheduled" | "contracts" | "cargoes" | "regas_slots", number> &
    Partial<Record<"network_points", number>>;
  positions_included: boolean;
  /**
   * The market LNG vessel feed: whether the caller holds the licensed vessel-feed entitlement
   * (Kpler or an AIS provider), how many market cargoes are visible, how many simulated.
   */
  vessel_feed?: { entitled: boolean | null; market_cargoes: number; simulated: number; families: string[] };
  /** The "Our book" view's relevance classes (design basis 2, J.5); newer servers. */
  book_relevance?: BookRelevanceDTO | null;
}

/** Why an object is on the "Our book" view: a reason key and its values. */
export interface BookReasonDTO {
  key: string;
  [field: string]: string | number | null | undefined;
}

export interface BookRelevanceItemDTO {
  kind: "point" | "hub" | "capacity" | "storage" | "cargo" | "terminal";
  ref: string;
  name: string;
  location: { lon: number; lat: number } | null;
  reasons: BookReasonDTO[];
}

export interface BookPriceDTO {
  price: number;
  currency: string;
  unit: string;
  simulated: boolean;
  observed_at_utc?: string | null;
}

export interface BookReachableDTO {
  from_hub: string;
  to_hub: string;
  crossings_count: number;
  via: string[];
  path_node_ids: string[];
  crossings: Array<{ point_key: string; name: string; node_id: string | null; pipeline: string | null; firm_technical_gwh_d: number | null }>;
  contracts: string[];
  indicative: true;
  price_from: BookPriceDTO | null;
  price_to: BookPriceDTO | null;
  tariff_gbp_mwh: number | null;
  tariff_status: "held" | "missing" | "fx_missing" | "not_assessed";
  missing: string[];
  missing_legs?: string[];
  spread_gbp_mwh: number | null;
  net_gbp_mwh: number | null;
  simulated: boolean;
  /** We hold capacity at a crossing on the way. */
  with_held_capacity?: boolean;
}

export interface BookOpportunityPathDTO {
  opportunity_id: string;
  type: string;
  type_code: string;
  state: string;
  /** "pop": actionable or indicative, drawn emphasised; "outline": watch, a thin outline. */
  emphasis: "pop" | "outline";
  claim: string;
  headline: { value: string | null; unit: string };
  period: string;
  simulated: boolean;
  from_hub: string;
  to_hub: string;
  path_node_ids: string[];
  via: string[];
  /** The record stated the crossing its evaluator priced (else the default one is drawn). */
  route_stated?: boolean;
  /** on_book: starts or ends at one of our hubs; adjacent: a crossing away; other. */
  relation?: "on_book" | "adjacent" | "other";
  /** The record also states the way the volume goes now (re-route, locational alternative). */
  proposal?: BookProposalDTO | null;
  /** When the window to act closes (the record's deadline, else its expiry). */
  window_closes_utc?: string | null;
  /** Why the core holds it back (a blocked record): the blocker's own words and its fix. */
  blocked?: { code: string; subject: string; text: string; fix?: string } | null;
}

/** One side of a now-against-proposed reading: the record's own texts, null = not stated. */
export interface BookProposalSideDTO {
  to_hub: string | null;
  via: string[];
  tariff: string | null;
  capacity: string | null;
  margin: string | null;
  period: string;
  input_class: { class: string; label: string };
}

export interface BookProposalDTO {
  /** The current path's nodes; one node when the volume is sold where it is delivered. */
  current_path_node_ids: string[];
  current_route_stated: boolean;
  now: BookProposalSideDTO;
  proposed: BookProposalSideDTO;
  benefit: { via: string | null; headline: { value: string | null; unit: string }; avoids_outage: string | null };
  /** The inputs it rests on: label, source family and reference, as-of time, input class. */
  evidence: Array<{ label: string; source_family: string | null; source_ref: string | null; as_of_utc: string | null; input_class: string | null }>;
}

/** The gas-year window of a contract and the days delivered. */
export interface BookContractPeriodDTO {
  label: string;
  start: string;
  end: string;
  elapsed_days: number;
  total_days: number;
}

/** An outage or restriction touching the book, with how much of ours it touches. */
export interface BookDisruptionDTO {
  event_id: string;
  facility_name: string | null;
  status: "active" | "scheduled" | string | null;
  start_utc: string | null;
  end_utc: string | null;
  unavailable_gwh_d: number | null;
  simulated: boolean;
  /** "point": at its located point; "zone": no source positions it, placed at its zone's hub. */
  placement: "point" | "zone";
  hub: string | null;
  location: { lon: number; lat: number };
  touches: "ours" | "reachable" | "opportunity";
  contracts: string[];
  /** Delivery of the contracts touched (what is exposed), MWh/d. */
  affected_mwh_d: number;
  /** Active and touching our own contracts: the one mark on the map that pulses. */
  pulse: boolean;
}

export interface BookArrivalDTO {
  cargo_id: string;
  vessel: string;
  terminal: string | null;
  eta_utc: string | null;
  simulated: boolean;
}

export interface BookContractPathDTO {
  contract_id: string;
  contract: string;
  from_hub: string;
  to_hub: string;
  mwh_d: number | null;
  path_node_ids: string[];
  period?: BookContractPeriodDTO | null;
}

export interface BookRelevanceDTO {
  rule: string;
  ours: BookRelevanceItemDTO[];
  contract_paths: BookContractPathDTO[];
  reachable: BookReachableDTO[];
  /** The caller's live opportunities with a path between two hubs (opportunity core). */
  opportunities: BookOpportunityPathDTO[];
  /** Expected LNG arrivals at terminals where we hold slots (newer servers). */
  arrivals?: BookArrivalDTO[];
  outages_touching: string[];
  /** Outages touching the book with what of ours they touch (newer servers). */
  disruptions?: BookDisruptionDTO[];
  /** Contract id -> its gas-year window and days delivered (newer servers). */
  contract_periods?: Record<string, BookContractPeriodDTO | null>;
}

/** North-west Europe balance: measured history and the component forecast. */
/** One entity of `GET /api/fundamentals/storage` (a region or a country). */
export interface StorageEntityDTO {
  code: string;
  name: string;
  simulated: boolean;
  sources: string[];
  /** The last gas day held. */
  as_of: string;
  received_at_utc: string | null;
  fill_pct: number | null;
  stock_twh: number | null;
  working_capacity_twh: number | null;
  day_change_pts: number | null;
  day_change_twh: number | null;
  week_change_pts: number | null;
  week_change_twh: number | null;
  injection_twh_d: number | null;
  withdrawal_twh_d: number | null;
  net_withdrawal_7d_twh_d: number | null;
  vs_last_year: { day: string; fill_pct: number | null; diff_pts: number | null };
  history: { mode: "none" | "lines" | "band"; years: string[]; label: string; history_from: string };
  vs_average: {
    years: number;
    label: string | null;
    mean_pct: number | null;
    low_pct: number | null;
    high_pct: number | null;
    diff_pts: number | null;
    range_position: number | null;
    outside: "below" | "above" | null;
  };
  target: { pct: number; window_open: string; deadline: string; gap_pts: number | null; days_to_target_at_7d_rate: number | null } | null;
  spark: { day: string; fill_pct: number | null }[];
  /** Only for the entities asked for in `season`. */
  season?: {
    axis: string[];
    gas_year: string;
    this_year: (number | null)[];
    last_year: { gas_year: string; values: (number | null)[] } | null;
    lines: { gas_year: string; values: (number | null)[] }[];
    band: { years: string[]; label: string; low: (number | null)[]; high: (number | null)[]; mean: (number | null)[] } | null;
  };
  /** The region only: what it is. */
  definition?: string;
}

/** One entity of `GET /api/fundamentals/lng`: send-out (GWh/d, 7-day mean) against history. */
export interface LngEntityDTO {
  code: string;
  name: string;
  simulated: boolean;
  sources: string[];
  as_of: string;
  send_out_7d_gwh_d: number | null;
  send_out_day_gwh_d: number | null;
  inventory_twh: number | null;
  inventory_pct_of_dtmi: number | null;
  vs_last_year: { day: string; send_out_7d_gwh_d: number | null; diff_gwh_d: number | null };
  history: StorageEntityDTO["history"];
  vs_average: {
    years: number;
    mean_gwh_d: number | null;
    low_gwh_d: number | null;
    high_gwh_d: number | null;
    diff_gwh_d: number | null;
    range_position: number | null;
    outside: "below" | "above" | null;
  };
  spark: { day: string; send_out_7d_gwh_d: number | null }[];
  season?: StorageEntityDTO["season"];
}

export interface FundamentalsLngDTO {
  region: LngEntityDTO | null;
  countries: LngEntityDTO[];
  missing: { code: string; name: string; reason: string }[];
  simulated: boolean;
  unit: string;
  method: string;
}

/** One series of `GET /api/fundamentals/flows`: energy landed (GWh/d, 7-day mean) against history. */
export interface FlowEntityDTO {
  code: string;
  name: string;
  scope: "norway" | "uk_terminal" | null;
  simulated: boolean;
  as_of: string;
  flow_7d_gwh_d: number | null;
  flow_day_gwh_d: number | null;
  vs_last_year: { day: string; flow_7d_gwh_d: number | null; diff_gwh_d: number | null };
  history: StorageEntityDTO["history"];
  vs_average: LngEntityDTO["vs_average"];
  spark: { day: string; flow_7d_gwh_d: number | null }[];
  season?: StorageEntityDTO["season"];
}

export interface FundamentalsFlowsDTO {
  totals: FlowEntityDTO[];
  landings: FlowEntityDTO[];
  simulated: boolean;
  unit: string;
  method?: string;
  warnings: string[];
}

export interface FundamentalsStorageDTO {
  region: StorageEntityDTO | null;
  countries: StorageEntityDTO[];
  missing: { code: string; name: string; reason: string }[];
  reconciliation: {
    day: string;
    region_stock_twh: number;
    countries_stock_twh: number;
    countries_counted: number;
    countries_expected: number;
    difference_twh: number;
    complete: boolean;
  } | null;
  simulated: boolean;
  unit: string;
  method: string;
  warnings: string[];
}

export interface NweBalanceDTO {
  region: string[];
  unit: string;
  history: NweBalanceDayDTO[];
  forecast: NweBalanceDayDTO[];
  norway_outages: number;
  assumptions: Record<string, unknown>;
}

/** One delivery day of the gas-for-power view for a bidding zone. */
export interface GasForPowerDayDTO {
  day: string;
  power_price: number | null;
  /** "day_ahead" (auction) or "market_index" (GB within-day reference). */
  power_price_basis?: string | null;
  residual_load_mw: number | null;
  implied_gas_burn_gwh: number | null;
  burn_basis: string[];
  gas_hub: string | null;
  gas_price: number | null;
  carbon_market: string | null;
  carbon_price: number | null;
  coal_price_per_mwh: number | null;
  clean_spark_spread: number | null;
  clean_dark_spread: number | null;
  fuel_switch_gas_price: number | null;
  currency: string;
}

/** One live or upcoming gas facility outage from a REMIT urgent market message. */
export interface OutageEventDTO {
  event_id: string;
  version: number | null;
  facility_id: string;
  facility_name: string;
  asset_type: string;
  event_type: string;
  status: string;
  start_utc: string;
  end_utc: string | null;
  published_at_utc: string | null;
  balancing_zone: string;
  unit: string;
  unavailable_capacity: number | null;
  capacity_impact_mcm_d: number;
  description: string;
  market_participant: string;
  /** The daily figure through the unit authority; null where the message has none. */
  unavailable_gwh_d?: number | null;
  /** How the daily figure was made (`per_day`, `per_hour_x_24h`, `unconverted:<reason>`). */
  daily_basis?: string;
  direction?: string;
  source_system?: string;
  source_reference?: string;
  attribution?: string;
  /** With `grouped=true`: every message of the event, its operators and how many. */
  messages?: string[];
  operators?: string[];
  message_count?: number;
}

export interface LadderRollupDTO {
  group: string;
  level: string;
  physical_mwh: number;
  financial_mwh: number;
  net_mwh: number;
  hedge_ratio: number | null;
  mark_to_market: number | null;
  legs: number;
}

export interface TradingBookDTO {
  book_id: string;
  name: string;
  legal_entity: string;
  region: string;
  business: string;
  base_currency: string;
  commodities: string[];
  active: boolean;
  contracts: number;
  orders: number;
}

/** Exposure to one counterparty against its approved credit line. */
export interface CreditExposureRowDTO {
  counterparty_id: string;
  counterparty: string;
  legal_entity: string | null;
  rating: string | null;
  currency: string;
  limit: number;
  replacement_exposure: number;
  receivable_exposure: number;
  collateral: number;
  net_exposure: number;
  headroom: number;
  utilisation_pct: number | null;
  remaining_mwh: number;
  legs: number;
  unvalued_legs: number;
  /** Evergreen contracts counted only to the end of the current gas year. */
  open_ended_legs?: number;
  valid_until: string | null;
  status: "ok" | "watch" | "breach" | "expired" | "incomplete";
  method?: RiskMethodNoteDTO;
}

/** One trader's open positions against their mandate. */
export interface MandateUsageRowDTO {
  mandate_id: string;
  trader: string;
  name: string;
  books: string;
  hubs: string;
  max_net_mwh_per_month: number | null;
  largest_net_mwh: number;
  largest_at: string;
  utilisation_pct: number | null;
  max_tenor_months: number | null;
  furthest_month: string;
  legs: number;
  breaches: string;
  valid_until: string | null;
  status: "ok" | "watch" | "breach" | "expired";
  hedge_policy: string;
  hedge_ratio_range: string | null;
  hedge_room_mwh: number | null;
  instruments: string;
  method?: RiskMethodNoteDTO;
}

export interface CreditLineInput {
  name: string;
  aliases: string[];
  legal_entity?: string | null;
  limit_amount: number;
  currency: string;
  collateral_amount: number;
  rating?: string | null;
  contract_ids: string[];
  receivable_days: number;
  valid_until?: string | null;
}

export interface MandateInput {
  trader: string;
  display_name: string;
  book_ids: string[];
  hubs: string[];
  max_net_mwh_per_month?: number | null;
  max_tenor_months?: number | null;
  physical_allowed: boolean;
  financial_allowed: boolean;
  valid_until?: string | null;
  min_hedge_ratio_pct?: number | null;
  max_hedge_ratio_pct?: number | null;
  instruments?: string[];
}

export interface SellDownInput {
  hub: string;
  da_price: number;
  wd_expected_price: number;
  short_penalty_per_mwh: number;
  long_discount_per_mwh: number;
  lot_mwh: number;
}

export interface DailyBalanceDayDTO {
  gas_day: string;
  supply: number;
  exchange_bought: number;
  exchange_sold: number;
  bilateral_bought: number;
  bilateral_sold: number;
  /** Supply plus purchases minus sales: positive is gas still to sell, negative to buy. */
  residual_mwh: number;
  state: "long" | "short" | "balanced";
  cash_out_cost: number | null;
}

export interface DailyBalanceDTO {
  hub: string;
  currency: string;
  delivery_ratio: number;
  contracts: string[];
  days: DailyBalanceDayDTO[];
}

export interface HedgeApprovalMonthDTO {
  month: string;
  contract_mwh: number;
  hedged_mwh: number;
  hedge_pct: number;
  room_mwh: number | null;
}

export interface HedgeApprovalRowDTO {
  contract_id: string;
  contract_name: string;
  min_hedge_ratio_pct: number | null;
  max_hedge_ratio_pct: number | null;
  approval_ref: string | null;
  valid_until: string | null;
  hedge_range: string | null;
  months: HedgeApprovalMonthDTO[];
  breaches: string[];
  status: "ok" | "breach" | "expired";
  linked_trades: number;
  contract_found: boolean;
  notes: string | null;
  updated_by: string;
}

export interface HedgeApprovalInput {
  min_hedge_ratio_pct: number | null;
  max_hedge_ratio_pct: number | null;
  approval_ref: string | null;
  valid_until: string | null;
  notes: string | null;
}

export interface SellDownPlanDTO {
  hub: string;
  contracts: string[];
  dcq_mwh: number;
  expected_supply_mwh: number;
  supply_stdev_mwh: number;
  volatility_basis: string;
  lots_day_ahead: number;
  sell_day_ahead_mwh: number;
  keep_within_day_mwh: number;
  critical_ratio: number;
  probability_short_pct: number;
  expected_cost_vs_perfect: number;
  sell_all_cost_vs_perfect: number;
  cost_over_per_mwh: number;
  cost_under_per_mwh: number;
  reasons: string[];
}

/** A bilateral supply contract's allocations against nominations and DCQ. */
export interface DeliveryPerformanceRowDTO {
  contract_id: string;
  contract: string;
  hub: string;
  tso: string;
  dcq_mwh_d: number;
  days: number;
  missing_days: number;
  nominated_mwh: number;
  allocated_mwh: number;
  net_deviation_mwh: number;
  imbalance_mwh: number;
  mean_abs_deviation_mwh_d: number | null;
  max_shortfall_mwh_d: number;
  short_days: number;
  long_days: number;
  outside_swing_days: number;
  mean_allocated_mwh_d: number | null;
  stdev_allocated_mwh_d: number | null;
  cv_pct: number | null;
  trend_7d_vs_dcq_pct: number | null;
  flags: string;
  status: "ok" | "watch";
}

export interface DeliveryDayDTO {
  gas_day: string;
  dcq_mwh: number;
  nominated_mwh: number | null;
  allocated_mwh: number | null;
  deviation_mwh: number | null;
  /** Beyond the contract's nomination tolerance that day, as the table counts it. */
  outside_tolerance: "short" | "long" | null;
}

export interface DeliveryPerformanceDTO {
  rows: DeliveryPerformanceRowDTO[];
  series: DeliveryDayDTO[];
  days: number;
}

export interface LngTerminalTermsDTO {
  terminal_id: string;
  name: string;
  country: string | null;
  hub: string;
  currency: string;
  regas_tariff_per_mwh: number;
  entry_tariff_per_mwh: number;
  fuel_retention_pct: number;
  port_costs_per_cargo: number;
  other_per_mwh: number;
  extra_sailing_days: number;
  source_note: string;
  capacity_basis?: "spot" | "long_term";
  variable_regas_per_mwh?: number | null;
  regime?: "regulated_indexed" | "regulated" | "auction" | "negotiated";
  fixed_per_cargo?: number;
  by_cargo_class?: Record<string, number> | null;
  source_url?: string | null;
  source_sha256?: string | null;
  effective_from?: string | null;
  retrieved_at_utc?: string | null;
  updated_by?: string;
  updated_at_utc?: string | null;
}

export type LngTerminalTermsInput = Omit<
  LngTerminalTermsDTO,
  "terminal_id" | "currency" | "updated_by" | "updated_at_utc" | "by_cargo_class" | "source_sha256" | "retrieved_at_utc"
>;

export interface SupportReportDTO {
  report_id: string;
  reporter: string;
  /** The reporter's display name. */
  reporter_name?: string | null;
  /** The IT desk member working it, by name. */
  assignee_name?: string | null;
  reporter_role: string;
  severity: "P1" | "P2" | "P3" | "P4";
  category: string;
  summary: string;
  description: string;
  page: string | null;
  client_context: Record<string, unknown> | null;
  server_context: Record<string, unknown> | null;
  status: "open" | "acknowledged" | "resolved";
  assignee: string | null;
  resolution: string | null;
  created_at_utc: string;
  updated_at_utc: string;
}

export interface SupportReportInput {
  severity: string;
  category: string;
  summary: string;
  description: string;
  page?: string | null;
  client_context?: Record<string, unknown> | null;
}

export interface NotificationChannelDTO {
  channel_id: string;
  name: string;
  kind: "email";
  recipients: string | null;
  categories: string[];
  min_severity: string;
  enabled: boolean;
  updated_by: string;
  updated_at_utc: string;
  last_delivery: { status: string; detail: string; at_utc: string } | null;
}

export interface NotificationChannelInput {
  name: string;
  kind: "email";
  recipients: string;
  categories: string[];
  min_severity: string;
  enabled: boolean;
}

export interface TariffPublicationDTO {
  publication_id: string;
  tso: string;
  country: string | null;
  gas_year: string;
  status: "expected" | "indicative" | "final";
  url: string | null;
  published_on: string | null;
  last_checked_at_utc: string | null;
  changed_at_utc: string | null;
  reviewed_at_utc: string | null;
  reviewed_by: string | null;
  note: string | null;
  state: string;
  severity: "ok" | "watch" | "breach";
  final_due: string | null;
  message: string;
}

/** One contract term read from a PDF, with the page and words it came from. */
export interface ContractIntakeTermDTO {
  field: string;
  value: string | number;
  unit: string;
  page: number;
  evidence: string;
  note: string;
}

export interface ContractIntakeDTO {
  file_name: string;
  pages: number;
  text_pages: number;
  ocr_pages: number;
  record: Record<string, unknown>;
  terms: ContractIntakeTermDTO[];
  warnings: string[];
  sha256: string;
}

export interface TradingBooksDTO {
  books: TradingBookDTO[];
  hierarchy: Record<string, Record<string, Record<string, string[]>>>;
  unassigned: { contracts: number; orders: number };
}

export interface TradingBookInput {
  name: string;
  legal_entity: string;
  region: string;
  business: string;
  base_currency?: string;
  commodities?: string[];
  active?: boolean;
  contract_ids?: string[];
  order_ids?: string[];
}

export interface ForwardCurvePointDTO {
  hub: string;
  month: string;
  price: number;
  method: string;
  source: string;
  warning: string | null;
}

export interface PositionLadderDTO {
  rows: PositionLadderRowDTO[];
  totals: { physical_mwh: number; financial_mwh: number; net_mwh: number; gross_tenor_mwh?: number };
  /** Per hub: net and gross (sum of |net| over months) MWh (#53). */
  tenor_exposure?: { hub: string; net_mwh: number; gross_mwh: number; months_held: number }[];
  /** Hubs long in one delivery month and short in another; hub-net VaR is withheld for them. */
  offsetting_hubs?: string[];
  /** Tenor shock scenario, when shocks were requested. */
  scenario?: {
    pnl: number;
    contributions: { hub: string; month: string; net_mwh: number; shock_per_mwh: number; pnl: number }[];
    unshocked: string[];
    excluded_no_fx: string[];
  } | null;
  mark_to_market: number | null;
  unpriced_rows: number;
  var_95_1d: number | null;
  var_observations: number;
  horizon: { start: string; end: string };
  legs: { physical: number; financial: number };
  curve?: ForwardCurvePointDTO[];
  reporting_currency?: string | null;
  group_by?: string;
  rollup?: LadderRollupDTO[];
  /** Method notes keyed by the figure's field: mark_to_market, var_95_1d, tenor_exposure, scenario. */
  methods?: Record<string, RiskMethodNoteDTO>;
  warnings: string[];
}

export interface SpreadSeriesDTO {
  hub: string;
  tenor: string;
  source_system: string;
  currency: string;
  unit: string;
  first: string;
  last: string;
  days: number;
  simulated: boolean;
}

export interface SpreadLegInputDTO {
  hub: string;
  tenor: string;
  source_system?: string | null;
  weight: number;
}

export interface SpreadRuleInputDTO {
  kind: "zscore" | "threshold";
  lookback: number;
  entry_z: number;
  exit_z: number;
  low?: number | null;
  high?: number | null;
  volume_mwh_per_day: number;
  cost_per_mwh: number;
}

export interface SpreadPointDTO {
  date: string;
  legs: number[];
  spread: number;
  zscore: number | null;
  position: number;
  pnl: number;
  cumulative_pnl: number;
}

export interface SpreadTradeDTO {
  opened: string;
  closed: string | null;
  direction: "long" | "short";
  entry_spread: number;
  exit_spread: number | null;
  pnl: number;
}

export interface SpreadAnalysisDTO {
  labels: string[];
  weights: number[];
  rule: Record<string, unknown>;
  unit: string;
  points: SpreadPointDTO[];
  statistics: Record<string, number | null>;
  trades: SpreadTradeDTO[];
  metrics: Record<string, number | null>;
  limitations: string[];
  analysis_hash: string;
}

/**
 * The shared dated cash valuation (`POST /api/research/cash-valuation`).
 *
 * One typed transport for the sandbox-only adaptation of
 * `domain/research/cash_valuation.py`. Every financial value - signed amounts, FX rates and
 * discount factors - is an **exact decimal string on the wire in both directions**. The client
 * never converts one to `number`, never parses one and never does cash arithmetic: a value that
 * went through a binary float (or through JavaScript's 53-bit integer range) could not be
 * re-stated exactly, which is the whole contract the route exists to keep. A repair of a value
 * beyond safe integer precision is exactly what this boundary must not do, so the fields are
 * `string` and the response is read, not recomputed.
 *
 * The business context entries are caller-supplied canonical `concept:value` strings. The
 * backend echoes them without resolving, looking up, inferring or entitling them
 * (`meta.references_verified` is always `false`), which is why the DTOs carry no entity types:
 * nothing here is a resolved entity reference.
 *
 * `decision_context` is deliberately absent from the request DTO. The sandbox gate reads the
 * raw JSON body and refuses a `RUNTIME_DECISION` claim before validation; this request model
 * forbids even a `SANDBOX_SCENARIO` claim as an unknown field,
 * so the only way to honour "SANDBOX_SCENARIO, never runtime-decision" is to send no context
 * claim at all - the route itself is the sandbox, and the response states the context.
 */
export const CASH_VALUATION_LEG_CATEGORIES = [
  "cargo_purchase",
  "cargo_sale",
  "shipping",
  "transport",
  "regas",
  "storage",
  "fuel",
  "demurrage",
  "boil_off",
  "other",
] as const;

/** The cash-flow leg vocabulary `CashFlowLegCategory` declares. */
export type CashValuationLegCategoryDTO = (typeof CASH_VALUATION_LEG_CATEGORIES)[number];

/** One valued leg as the engine serialized it: Decimals are exact strings, dates are ISO dates. */
export interface CashValuationLegValuationDTO {
  leg_id: string;
  category: CashValuationLegCategoryDTO;
  payment_date: string;
  currency: string;
  signed_amount: string;
  cash_amount_reporting_ccy: string;
  present_value_reporting_ccy: string;
  discount_factor: string;
  discount_curve_reference: string;
  discount_source_reference: string;
  discount_as_of: string;
  source_reference: string;
  fx_rate_reporting_per_leg: string;
  fx_source_reference: string;
  fx_as_of: string | null;
  description: string;
}

export interface LngEconomicsOnlyEnergyStageDTO {
  stage_id: string;
  /** `cargo_transfer`, `shipping`, `storage`, `regasification` or `other`. */
  kind: string;
  input_energy_mwh: string;
  output_energy_mwh: string;
  consumed_energy_mwh: string;
  physical_loss_energy_mwh: string;
  source_references: string[];
}

/** The exact ordered energy balance the backend composed from the declared stages. */
export interface LngEconomicsEnergyBalanceDTO {
  model_version: string;
  purchased_energy_mwh: string;
  delivered_energy_mwh: string;
  energy_basis_reference: string;
  energy_unit: string;
  total_consumed_energy_mwh: string;
  physical_loss_energy_mwh: string;
  total_reduction_energy_mwh: string;
  stage_count: number;
  stages: LngEconomicsOnlyEnergyStageDTO[];
  warnings: string[];
  source_references: string[];
  research_only: boolean;
  human_review_required: boolean;
}

/** The embedded shared cash valuation, with every Decimal serialized as an exact string. */
export interface LngEconomicsCashValuationDTO {
  model_version: string;
  contract_id: string;
  cargo_id: string;
  terminal_id: string;
  resource_id: string;
  valuation_date: string;
  reporting_currency: string;
  leg_valuations: CashValuationLegValuationDTO[];
  total_undiscounted_cash_reporting_ccy: string;
  net_present_value_reporting_ccy: string;
  assumptions: string[];
  warnings: string[];
  source_references: string[];
  lineage: string[];
  research_only: boolean;
  human_review_required: boolean;
}

/** One economics-only result as the route serialized it. */
export interface LngEconomicsOnlyResultDTO {
  research_only: boolean;
  human_review_required: boolean;
  model_version: string;
  action: string;
  contract_id: string;
  cargo_id: string;
  terminal_id: string;
  resource_id: string;
  valuation_date: string;
  reporting_currency: string;
  energy_basis_reference: string;
  energy_unit: string;
  purchased_energy_mwh: string;
  delivered_energy_mwh: string;
  total_consumed_energy_mwh: string;
  physical_loss_energy_mwh: string;
  total_reduction_energy_mwh: string;
  purchase_basis: string;
  purchase_included_cost_items: string[];
  cost_scope_statement: string;
  purchase_unit_price_eur_per_mwh: string;
  sale_unit_price_eur_per_mwh: string;
  unit_netback_eur_per_purchased_mwh: string;
  sale_basis_eur_per_delivered_mwh: string;
  purchase_outlay_eur: string;
  sale_proceeds_eur: string;
  total_downstream_costs_eur: string;
  cargo_margin_eur: string;
  margin_reconciliation_gap_eur: string;
  margin_reconciliation_tolerance_eur: string;
  net_present_value_eur: string;
  total_undiscounted_cash_eur: string;
  cash_valuation: LngEconomicsCashValuationDTO;
  energy_balance: LngEconomicsEnergyBalanceDTO;
  physical_readiness: string;
  readiness_assessed: boolean;
  assumptions: string[];
  warnings: string[];
  source_references: string[];
  lineage: string[];
}

/**
 * The sandbox envelope of the LNG economics-only route.
 *
 * Caller-supplied and unverified, no customer approval, no physical readiness assessment and
 * `SANDBOX_SCENARIO` as the only decision context this route can carry. A profitable result is
 * never delivery feasibility, terminal/slot/storage rights or nomination authority.
 */
export interface LngEconomicsOnlyMetaDTO extends ApiMeta {
  decision_context: "SANDBOX_SCENARIO";
  caller_supplied: true;
  references_verified: false;
  physical_readiness: string;
  readiness_assessed: boolean;
  customer_approval: false;
  source_references: string[];
  warnings: string[];
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

  normalizedMarketObservations: (options?: ApiRequestOptions, limit = 500) =>
    get<NormalizedMarketObsDTO[]>("/market/normalized", { limit: String(limit) }, options),

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

  /**
   * Backend price conversion with a named FX fix: ECB (default), WMR (WM/Reuters) or BFIX
   * (Bloomberg). Licensed fixes answer only for principals holding that data scope.
   */
  priceConversion: (
    value: number,
    fromUnit: string,
    fxSource: string = "ECB",
    options?: ApiRequestOptions,
  ) =>
    get<PriceConversionDTO>(
      "/market/price-conversion",
      { value: String(value), from_unit: fromUnit, fx_source: fxSource },
      options,
    ),

  interestRates: (benchmark?: string, options?: ApiRequestOptions) =>
    get<{ benchmarks: Record<string, { label: string; day_count: string; attribution: string }>; fixings: unknown[] }>(
      "/market/interest-rates",
      benchmark ? { benchmark } : undefined,
      options,
    ),

  /** The business ontology, with the units authority's conversion factors. */
  ontology: (options?: ApiRequestOptions) => get<OntologyDTO>("/analysis/ontology", undefined, options),

  /** A question from the answer bar, answered from the caller's Today facts. */
  ask: (question: string, language: "en" | "zh-CN", options?: ApiRequestOptions) =>
    post<AskAnswerDTO>("/analysis/ask", { question, language }, options),

  storageTargetTrajectory: (code: string, options?: ApiRequestOptions) =>
    get<StorageTrajectoryDTO | null>("/storage/target-trajectory", { code }, options),

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
    post<
      CredentialProviderDTO & {
        connection_status?: string;
        connection_error_code?: string | null;
        connection?: GieConnectionTestDTO;
      }
    >(`/credentials/${providerId}/connection-test`, {}),

  monitoringAlerts: (options?: ApiRequestOptions) =>
    get<MonitoringAlertDTO[]>("/monitoring/alerts", { limit: "100" }, options),

  monitoringSummary: (options?: ApiRequestOptions) => get<MonitoringSummaryDTO>("/monitoring/summary", undefined, options),

  explain: (subject: ExplainSubject, id: string, language: "en" | "zh-CN") =>
    post<ExplanationDTO>("/analysis/explain", { subject, id, language }),

  deskBrief: (kind: "morning" | "eod", language: "en" | "zh-CN") =>
    post<DeskBriefDTO>("/analysis/brief", { kind, language }),

  deskToday: (options?: ApiRequestOptions) => get<DeskTodayDTO>("/desk/today", undefined, options),

  opportunities: (options?: ApiRequestOptions) => get<OpportunityListDTO>("/opportunities", undefined, options),

  opportunity: (opportunityId: string, options?: ApiRequestOptions) =>
    get<OpportunityDetailDTO>(`/opportunities/${encodeURIComponent(opportunityId)}`, undefined, options),

  evaluateOpportunities: () => post<Record<string, unknown>>("/opportunities/evaluations", {}),

  setOpportunityState: (
    opportunityId: string,
    body: { action: "dismiss" | "restore" | "watch" | "unwatch"; reason?: string; note?: string },
  ) => put<Record<string, unknown>>(`/opportunities/${encodeURIComponent(opportunityId)}/state`, body),

  firmMarks: (options?: ApiRequestOptions) =>
    get<{ marks: FirmMarkDTO[]; statement: string }>("/market/firm-marks", undefined, options),

  putFirmMarks: (marks: { hub: string; period: string; value: number; unit: string; note?: string }[]) =>
    put<{ marks: FirmMarkDTO[] }>("/market/firm-marks", { marks }),

  openOpportunityCase: (opportunityId: string) =>
    post<{ case: { case_id: string } | null; evidence_ref: string }>(
      `/opportunities/${encodeURIComponent(opportunityId)}/case`,
      {},
    ),

  reportCatalogue: (language?: string, options?: ApiRequestOptions) =>
    get<ReportCatalogueDTO>("/reports/catalogue", language ? { language } : undefined, options),

  reportPlan: (question: string, audience: ReportAudience) =>
    post<ReportPlanProposalDTO>("/reports/plan", { question, audience }),

  generateReport: (body: ReportRequestDTO, options?: ApiRequestOptions) =>
    post<ReportMetadataDTO>("/reports/market", body, options),

  deleteReport: (reportId: string) =>
    del<{ deleted: string[] }>(`/reports/market/${encodeURIComponent(reportId)}`),

  deleteReports: (reportIds: string[]) =>
    post<{ deleted: string[]; refused: { report_id: string; code: string }[] }>(
      "/reports/market/bulk-delete", { report_ids: reportIds }),

  reportSchedules: (options?: ApiRequestOptions) =>
    get<{ schedules: ReportScheduleDTO[]; last_slots: Record<string, string> }>("/reports/schedules", undefined, options),

  saveReportSchedules: (schedules: ReportScheduleDTO[]) =>
    put<{ schedules: ReportScheduleDTO[] }>("/reports/schedules", { schedules }),

  renameReport: (reportId: string, title: string) =>
    patch<{ renamed: string[]; title: string }>(`/reports/market/${encodeURIComponent(reportId)}`, { title }),

  marketReports: (options?: ApiRequestOptions) =>
    get<ReportSummaryDTO[]>("/reports/market", { limit: "50" }, options),

  marketReport: (reportId: string) =>
    get<ReportMetadataDTO>(`/reports/market/${encodeURIComponent(reportId)}`),

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
  retiredUpstreamContracts: (options?: ApiRequestOptions) =>
    get<UpstreamContractDTO[]>("/route-cost/upstream-contracts", { include_retired: "true" }, options),
  /** Retire or reinstate a contract against the version the user looked at (audited). */
  setContractLifecycle: (contractId: string, action: "retire" | "reinstate", reason: string, editToken: string) =>
    post<UpstreamContractDTO>(
      `/route-cost/upstream-contracts/${encodeURIComponent(contractId)}/${action}`,
      { reason, expected_edit_token: editToken },
    ),

  contractPrice: (contractId: string, month: string, options?: ApiRequestOptions) =>
    get<ContractPriceDTO>(`/contracts/${encodeURIComponent(contractId)}/price`, { month }, options),
  saveUpstreamContract: (body: UpstreamContractInputDTO | TypedContractInputDTO) =>
    post<UpstreamContractDTO>("/route-cost/upstream-contracts", body),

  /**
   * One bounded page of a contract's captured economic revisions, oldest
   * first. The revisions are capture-time evidence: not a complete history
   * and not payment terms. No capture is created by reading, and no revision
   * is ever re-attributed; transport only, no client arithmetic.
   */
  upstreamContractRevisions: (
    contractId: string,
    params?: { limit?: number; offset?: number },
    options?: ApiRequestOptions,
  ) =>
    get<UpstreamContractRevisionListDTO>(
      `/route-cost/upstream-contracts/${encodeURIComponent(contractId)}/revisions`,
      {
        ...(params?.limit ? { limit: String(params.limit) } : {}),
        ...(params?.offset ? { offset: String(params.offset) } : {}),
      },
      options,
    ),

  /** One captured revision, scoped to its contract; a cross-contract id is a 404. */
  upstreamContractRevision: (
    contractId: string,
    contractRevisionId: string,
    options?: ApiRequestOptions,
  ) =>
    get<UpstreamContractRevisionDTO>(
      `/route-cost/upstream-contracts/${encodeURIComponent(contractId)}/revisions/${encodeURIComponent(contractRevisionId)}`,
      undefined,
      options,
    ),

  resourcePoolOptions: (options?: ApiRequestOptions) => get<ResourcePoolOptionsDTO>("/route-cost/resource-pool/options", undefined, options),

  recommendRouteAllocation: (body: RouteRecommendationRequestDTO, options?: ApiRequestOptions) =>
    post<RouteRecommendationResultDTO>("/route-cost/recommend", body, options),

  optimizeResourcePool: (body: PortfolioOptimizationRequestDTO, options?: ApiRequestOptions) =>
    post<PortfolioOptimizationResultDTO>("/route-cost/resource-pool/optimize", body, options),

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

  strategy: (strategyId: string) =>
    get<StrategyDTO>(`/strategies/${encodeURIComponent(strategyId)}`),

  strategyVersion: (versionId: string) =>
    get<StrategyVersionDTO>(`/strategy-versions/${encodeURIComponent(versionId)}`),

  capacityContracts: () => get<CapacityContractDTO[]>("/contracts/capacity"),

  runtimeDb: (options?: ApiRequestOptions) => get<RuntimeDbStatusDTO>("/runtime/db", undefined, options),
  runtimeDependencies: (options?: ApiRequestOptions) => get<RuntimeDependenciesDTO>("/runtime/dependencies", undefined, options),
  runtimeRelease: (options?: ApiRequestOptions) => get<RuntimeReleaseDTO>("/runtime/release", undefined, options),
  decisionHandoff: (caseId: string) =>
    get<Record<string, unknown>>(`/decision-cases/${encodeURIComponent(caseId)}/handoff`),
  fundamentalsFlows: (season: string[] = [], options?: ApiRequestOptions) =>
    get<FundamentalsFlowsDTO>("/fundamentals/flows", season.length ? { season: season.join(",") } : undefined, options),
  nweBalanceHistory: (historyDays: number, options?: ApiRequestOptions) =>
    get<NweBalanceDTO>("/market/nwe-balance", { days: "1", history_days: String(historyDays) }, options),
  fundamentalsLng: (season: string[] = [], options?: ApiRequestOptions) =>
    get<FundamentalsLngDTO>("/fundamentals/lng", season.length ? { season: season.join(",") } : undefined, options),
  fundamentalsStorage: (
    query: { region?: "eu" | "nwe"; season?: string[]; focus?: string[] } = {},
    options?: ApiRequestOptions,
  ) =>
    get<FundamentalsStorageDTO>(
      "/fundamentals/storage",
      {
        region: query.region ?? "eu",
        ...(query.season?.length ? { season: query.season.join(",") } : {}),
        ...(query.focus?.length ? { focus: query.focus.join(",") } : {}),
      },
      options,
    ),
  nweBalance: (days = 14, options?: ApiRequestOptions) =>
    get<NweBalanceDTO>("/market/nwe-balance", { days: String(days) }, options),
  gasForPower: (zone = "DE_LU", days = 14, options?: ApiRequestOptions) =>
    get<GasForPowerDayDTO[]>("/market/gas-for-power", { zone, days: String(days) }, options),
  mapSituation: (outageHorizonDays = 14, options?: ApiRequestOptions, historyDays = 0) =>
    get<MapSituationDTO>(
      "/portfolio/map-situation",
      historyDays > 0
        ? { outage_horizon_days: String(outageHorizonDays), history_days: String(historyDays) }
        : { outage_horizon_days: String(outageHorizonDays) },
      options,
    ),
  outages: (horizonDays = 90, options?: ApiRequestOptions, view: { grouped?: boolean; endedDays?: number } = {}) =>
    get<OutageEventDTO[]>(
      "/physical/outages",
      {
        horizon_days: String(horizonDays),
        ...(view.grouped ? { grouped: "true" } : {}),
        ...(view.endedDays ? { ended_days: String(view.endedDays) } : {}),
      },
      options,
    ),
  positionLadder: (
    months = 12,
    options?: ApiRequestOptions,
    view: { groupBy?: string; reportingCurrency?: string; shocks?: string[] } = {},
  ) => {
    const params = new URLSearchParams({ months: String(months) });
    if (view.groupBy && view.groupBy !== "hub") params.set("group_by", view.groupBy);
    if (view.reportingCurrency) params.set("reporting_currency", view.reportingCurrency);
    // Tenor shocks (#53), repeated: HUB:YYYY-MM:delta per MWh.
    for (const shock of view.shocks ?? []) params.append("shock", shock);
    return get<PositionLadderDTO>("/portfolio/position-ladder", params, options);
  },
  creditExposure: (options?: ApiRequestOptions) =>
    get<{ rows: CreditExposureRowDTO[]; as_of: string }>("/portfolio/credit-exposure", undefined, options),
  mandateUsage: (options?: ApiRequestOptions) =>
    get<{ rows: MandateUsageRowDTO[]; as_of: string }>("/portfolio/mandate-usage", undefined, options),
  saveCreditLine: (counterpartyId: string, body: CreditLineInput) =>
    put<{ key: string; created: boolean }>(`/portfolio/credit-lines/${encodeURIComponent(counterpartyId)}`, body),
  saveTraderMandate: (mandateId: string, body: MandateInput) =>
    put<{ key: string; created: boolean }>(`/portfolio/trader-mandates/${encodeURIComponent(mandateId)}`, body),
  deliveryPerformance: (days = 90, contractId?: string, options?: ApiRequestOptions) =>
    get<DeliveryPerformanceDTO>(
      "/contracts/delivery-performance",
      { days: String(days), ...(contractId ? { contract_id: contractId } : {}) },
      options,
    ),
  lngTerminalTerms: (options?: ApiRequestOptions) =>
    get<{ rows: LngTerminalTermsDTO[] }>("/portfolio/lng-terminal-terms", undefined, options),
  saveLngTerminalTerms: (terminalId: string, body: LngTerminalTermsInput) =>
    put<{ key: string; created: boolean }>(`/portfolio/lng-terminal-terms/${encodeURIComponent(terminalId)}`, body),
  lngTerminalTariffRegister: (options?: ApiRequestOptions) =>
    get<LngTerminalTariffRegisterDTO>("/lng/terminal-tariffs", undefined, options),
  reviewLngTerminalTariff: (tariffId: string) =>
    post<LngTerminalTariffDTO>(`/lng/terminal-tariffs/${encodeURIComponent(tariffId)}/review`, {}),
  recordLngTariffOperatorTerms: (operator: string, body: { permitted: boolean; reference: string }) =>
    put<LngTariffOperatorDTO>(`/lng/terminal-tariffs/operators/${encodeURIComponent(operator)}`, body),
  /** The firm's assumption sets the caller may read (organisation and visible books). */
  assumptionSets: (options?: ApiRequestOptions) =>
    get<{ sets: AssumptionSetSummaryDTO[] }>("/assumption-sets", undefined, options),
  freightRoutes: (options?: ApiRequestOptions) =>
    get<FreightRouteDTO[]>("/lng/freight-routes", undefined, options),
  saveFreightRoute: (routeId: string, body: Omit<FreightRouteDTO, "route_id" | "version" | "recorded_by" | "recorded_at_utc">) =>
    put<FreightRouteDTO>(`/lng/freight-routes/${encodeURIComponent(routeId)}`, body),
  cargoEconomics: (body: {
    arrival_month: string;
    product?: "spot" | "term" | "prompt" | "annual";
    cargoes: CargoInput[];
    terminal_ids?: string[];
    terminal_inputs?: Record<string, { entry_per_mwh?: number; gas_in_kind_pct?: number }>;
    /** The delivered spread by arrival month for the first FOB cargo (design C.4); 0 for none. */
    series_months?: number;
    series_terminal_id?: string;
    /** Henry Hub against the hub, daily, over this many days (design C.4); 0 for none. */
    history_days?: number;
    /** Terminals in several currencies rank in this currency at the arrival month's FX. */
    reporting_currency?: "EUR" | "GBP" | "USD";
    /** The assumption set to read; default the organisation's approved one. */
    assumption_set_id?: string;
  }, options?: ApiRequestOptions) => post<CargoEconomicsDTO>("/lng/cargo-economics", body, options),
  tariffPublications: (options?: ApiRequestOptions) =>
    get<{ rows: TariffPublicationDTO[] }>("/route-cost/tariff-publications", undefined, options),
  saveTariffPublication: (
    publicationId: string,
    body: { tso: string; country: string | null; gas_year: string; status: string; url: string | null; mark_reviewed: boolean },
  ) => put<TariffPublicationDTO>(`/route-cost/tariff-publications/${encodeURIComponent(publicationId)}`, body),
  reportProblem: (body: SupportReportInput) => post<SupportReportDTO>("/support/reports", body),
  supportReports: (status?: string, options?: ApiRequestOptions) =>
    get<{ rows: SupportReportDTO[]; scope: "all" | "mine" }>(
      "/support/reports",
      status ? { status } : undefined,
      options,
    ),
  updateSupportReport: (reportId: string, body: { status: string; assignee?: string | null; resolution?: string | null }) =>
    patch<SupportReportDTO>(`/support/reports/${encodeURIComponent(reportId)}`, body),
  notificationChannels: (options?: ApiRequestOptions) =>
    get<{ rows: NotificationChannelDTO[] }>("/settings/notification-channels", undefined, options),
  saveNotificationChannel: (channelId: string, body: NotificationChannelInput) =>
    put<NotificationChannelDTO>(`/settings/notification-channels/${encodeURIComponent(channelId)}`, body),
  testNotificationChannel: (channelId: string) =>
    post<{ sent: boolean; detail: string }>(`/settings/notification-channels/${encodeURIComponent(channelId)}/test`, {}),
  dailyBalance: (
    query: { hub: string; days?: number; short_premium_per_mwh?: number; long_discount_per_mwh?: number },
    options?: ApiRequestOptions,
  ) =>
    get<DailyBalanceDTO>(
      "/portfolio/daily-balance",
      Object.fromEntries(
        Object.entries(query)
          .filter(([, value]) => value !== undefined && value !== null && !Number.isNaN(value))
          .map(([key, value]) => [key, String(value)]),
      ),
      options,
    ),
  hedgeApprovals: (options?: ApiRequestOptions) =>
    get<{
      rows: HedgeApprovalRowDTO[];
      /** Contracts a band can be approved for: identity and hub, no commercial terms. */
      contracts: { contract_id: string; contract_name: string; hub: string }[];
    }>("/portfolio/hedge-approvals", undefined, options),
  saveHedgeApproval: (contractId: string, body: HedgeApprovalInput) =>
    put<{ key: string; created: boolean }>(`/portfolio/hedge-approvals/${encodeURIComponent(contractId)}`, body),
  sellDownPlan: (body: SellDownInput, options?: ApiRequestOptions) =>
    post<SellDownPlanDTO>("/portfolio/sell-down-plan", body, options),
  tradingBooks: (options?: ApiRequestOptions) => get<TradingBooksDTO>("/portfolio/books", undefined, options),
  saveTradingBook: (bookId: string, body: TradingBookInput) =>
    put<{ book_id: string; created: boolean; contracts_assigned: number; orders_assigned: number }>(
      `/portfolio/books/${encodeURIComponent(bookId)}`,
      body,
    ),
  myPreferences: (options?: ApiRequestOptions) => get<PreferencesDTO>("/me/preferences", undefined, options),
  /** Merge personal choices; `null` clears one back to the organisation default. */
  saveMyPreferences: (patch: Partial<Record<PreferenceKey, string | null>>) =>
    put<PreferencesDTO>("/me/preferences", patch),
  organisationSettings: () => get<OrganisationSettingsDTO>("/settings/organisation"),
  saveOrganisationSettings: (settings: OrganisationSettingsDTO) =>
    put<OrganisationSettingsDTO>("/settings/organisation", settings),
  spreadSeries: (options?: ApiRequestOptions) => get<SpreadSeriesDTO[]>("/research/spread-series", undefined, options),
  spreadAnalysis: (
    body: { legs: SpreadLegInputDTO[]; date_from?: string | null; date_to?: string | null; rule: SpreadRuleInputDTO },
    options?: ApiRequestOptions,
  ) => post<SpreadAnalysisDTO>("/research/spread-analysis", body, options),
  /** Research → Spreads: a description into a StrategySpec, with its questions. */
  spreadsInterpret: (body: { text: string; language: "en" | "zh-CN" }, options?: ApiRequestOptions) =>
    post<InterpretationDTO>("/research/spreads/interpret", body, options),
  /** Research → Spreads: a spec's checks and its result, every figure from the engine. */
  /** Research → Spreads: the desk's spread board (focus hubs first, then the majors). */
  spreadsBoard: (hubs: readonly string[] = [], options?: ApiRequestOptions) =>
    get<SpreadBoardDTO>("/research/spreads/board", hubs.length ? { hubs: hubs.join(",") } : undefined, options),
  spreadsEvaluate: (spec: StrategySpecDTO, options?: ApiRequestOptions) =>
    post<EvaluationDTO>("/research/spreads/evaluate", { spec }, options),
  /** Tracked strategies (paper shadow run): the caller's own. */
  strategyTracks: (options?: ApiRequestOptions) =>
    get<StrategyTrackDTO[]>("/research/strategy-tracks", undefined, options),
  strategyTrack: (trackId: string, options?: ApiRequestOptions) =>
    get<StrategyTrackDTO>(`/research/strategy-tracks/${encodeURIComponent(trackId)}`, undefined, options),
  createStrategyTrack: (
    body: { name: string; mode: "daily" | "intraday"; spec: StrategySpecDTO; rule?: Record<string, unknown> | null },
    options?: ApiRequestOptions,
  ) => post<StrategyTrackDTO>("/research/strategy-tracks", body, options),
  stopStrategyTrack: (trackId: string, options?: ApiRequestOptions) =>
    post<StrategyTrackDTO>(`/research/strategy-tracks/${encodeURIComponent(trackId)}/stop`, {}, options),
  /** Prices → Prompt: live WD/DA for one hub and today's post-trade performance. */
  promptMarket: (hub: string, options?: ApiRequestOptions) =>
    get<PromptMarketDTO>("/market/prompt", { hub }, options),
  /** Hub → product kind → tenor: the caller's entitled daily series (the instrument picker). */
  marketInstruments: (options?: ApiRequestOptions) =>
    get<InstrumentCatalogueDTO>("/market/instruments", undefined, options),
  /** A pair's rate for a delivery period: forward by interest parity, licensed, or spot. */
  fxForward: (
    query: { base: string; quote: string; product?: string; value_date?: string; as_of?: string },
    options?: ApiRequestOptions,
  ) =>
    get<FxForwardDTO>(
      "/market/fx-forward",
      Object.fromEntries(Object.entries(query).filter((entry): entry is [string, string] => typeof entry[1] === "string")),
      options,
    ),
  /** Prices into one unit, each with its normalisation record (server-side factors and FX). */
  normaliseMarket: (body: NormaliseRequestDTO, options?: ApiRequestOptions) =>
    postRead<NormaliseResponseDTO>("/market/normalise", body, options),
  capabilities: (params?: { domain?: string }) =>
    get<CapabilityDTO[]>("/capabilities", params),
  capability: (capabilityId: string) =>
    get<CapabilityDTO>(`/capabilities/${encodeURIComponent(capabilityId)}`),
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
  /**
   * Approve a public source (ENTSOG, GIE) for the firm: ADMIN only, checked on the server. The
   * administrator has read the provider's terms summary; the server records who, when and why,
   * audits it and runs the bounded live validation the ingestion gate requires.
   */
  approveSource: (sourceId: string, reason: string, acceptTerms: boolean, options?: ApiRequestOptions) =>
    post<SourceApprovalResultDTO>(
      `/sources/${encodeURIComponent(sourceId)}/approve`,
      { reason, accept_terms: acceptTerms },
      options,
    ),
  /**
   * Withdraw a public-source approval (ADMIN, audited). The caller confirmed it: reads stop at
   * the next scheduled run and the source reads "Not approved yet"; stored data is kept.
   */
  revokeSourceApproval: (sourceId: string, reason: string) =>
    deleteWithBody<{ source_id: string; state: string; changed: boolean }>(
      `/sources/${encodeURIComponent(sourceId)}/approve`,
      { reason, confirm: true },
    ),
  requestSourceRun: (sourceId: string, reason: string, options?: ApiRequestOptions) =>
    post<Record<string, unknown>>(
      `/sources/${encodeURIComponent(sourceId)}/run`,
      { reason },
      options,
    ),
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
  glossary: (lang: string = "en", params?: { category?: string; q?: string }, options?: ApiRequestOptions) =>
    get<GlossaryTermDTO[]>("/glossary", { lang, ...(params ?? {}) }, options),

  glossaryContext: (
    term: string,
    params?: { lang?: string; duration_start_utc?: string; duration_end_utc?: string },
  ) =>
    get<GlossaryContextDTO>(`/glossary/${encodeURIComponent(term)}/context`, params),

  analysisQuery: (body: AnalysisRequestDTO) => post<AnalysisResultDTO>("/analysis/query", body),

  portfolioReport: (body: AnalysisRequestDTO) => post<AnalysisResultDTO>("/reports/portfolio", body),

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
  /**
   * Development-only credential login. A browser gets the HttpOnly session cookie; the
   * desktop app asks for the session token in the body and keeps it in memory.
   */
  login: (username: string, password: string) =>
    post<DevLoginIdentityDTO>(
      "/dev/auth/login",
      isDesktopShell ? { username, password, client: "desktop" } : { username, password },
    ),
  /**
   * Local-account sign-in (firms without SSO). A temporary password answers
   * `password_change_required` with a single-use `change_token` instead of a session.
   */
  localLogin: (username: string, password: string) =>
    post<LocalLoginDTO>(
      "/auth/login",
      isDesktopShell ? { username, password, client: "desktop" } : { username, password },
    ),
  /** The forced password change after a temporary password; opens the session. */
  completePasswordChange: (changeToken: string, newPassword: string) =>
    post<LocalLoginDTO>(
      "/auth/password-change",
      isDesktopShell
        ? { change_token: changeToken, new_password: newPassword, client: "desktop" }
        : { change_token: changeToken, new_password: newPassword },
    ),
  /** A signed-in local-account user changes their own password (other sessions end). */
  changeOwnPassword: (currentPassword: string, newPassword: string) =>
    post<LocalLoginDTO>("/me/password", { current_password: currentPassword, new_password: newPassword }),
  logout: (options?: ApiRequestOptions) => post<{ logged_out: boolean }>("/auth/logout", {}, options),
  desktopOidcToken: (body: DesktopOidcTokenInputDTO) =>
    post<DesktopOidcTokenDTO>("/auth/oidc/desktop/token", body),
  startDesktopOidcLogin: (body: DesktopOidcLoginInputDTO) =>
    post<DesktopOidcLoginDTO>("/auth/oidc/desktop/login", body),
  accessUsers: () => get<AccessUserDTO[], ApiMeta & { account_options?: AccountOptionsDTO }>("/access/users"),
  createAccessUser: (body: AccessUserCreateInputDTO) =>
    post<AccessUserCreatedDTO>("/access/users", body),
  resetAccessUserPassword: (principalId: string) =>
    post<AccessUserCreatedDTO>(`/access/users/${encodeURIComponent(principalId)}/reset-password`, {}),
  deleteAccessUser: (principalId: string) =>
    del<{ principal_id: string; deleted: boolean }>(`/access/users/${encodeURIComponent(principalId)}`),
  patchAccessUser: (principalId: string, body: AccessUserPatchInputDTO) =>
    patch<AccessUserDTO>(`/access/users/${encodeURIComponent(principalId)}`, body),
  accessRoles: () => get<Record<string, string[]>>("/access/roles"),
  accessDataScopes: () => get<DataScopeCatalogueDTO>("/access/data-scopes"),
  marketDataLicences: () => get<MarketDataLicenceDTO[]>("/access/market-data-licences"),
  saveMarketDataLicence: (licenceId: string, body: MarketDataLicenceInput) =>
    put<MarketDataLicenceDTO>(`/access/market-data-licences/${encodeURIComponent(licenceId)}`, body),
  accessApiKeys: () => get<AccessApiKeyDTO[]>("/access/api-keys"),
  createAccessApiKey: (body: AccessApiKeyCreateInputDTO) =>
    post<AccessApiKeyDTO & { api_key: string }>("/access/api-keys", body),
  revokeAccessApiKey: (keyId: string) =>
    post<{ key_id: string; revoked: boolean }>(`/access/api-keys/${encodeURIComponent(keyId)}/revoke`, {}),
  auditEvents: (params?: {
    actor?: string; action?: string; resource?: string; outcome?: string; limit?: string;
    /** Window bounds, ISO-8601 with an offset, and the continuation cursor (#59). */
    start_utc?: string; end_utc?: string; cursor?: string;
  }) => get<AuditEventDTO[], ApiMeta & { continuation?: AuditContinuationDTO }>("/audit", params),
  ssoProfile: () => get<Record<string, unknown>>("/access/sso"),
  /** First-run setup (ADMIN): the welcome flow's pages and where it stands. */
  setup: (options?: ApiRequestOptions) => get<SetupViewDTO>("/setup", undefined, options),
  saveSetup: (status: "in_progress" | "completed" | "dismissed", step: string | null) =>
    put<SetupViewDTO>("/setup", { status, step }),
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
  /** Job functions an administrator declared; composition only, never a grant. */
  declared_job_functions?: string[];
  /** Declared functions the role cannot support: reported, not granted. */
  unsatisfied_job_functions?: string[];
  /** Persona landing page, when a job function is declared. */
  home?: { workspace: string; task: string } | null;
  office?: string | null;
  office_time_zone?: string | null;
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
  /** True when local accounts (user name and password) are offered. */
  local_login?: boolean;
}

/** `POST /api/auth/login` and `/api/auth/password-change`: a session, or the change step first. */
export interface LocalLoginDTO {
  authenticated: boolean;
  password_change_required: boolean;
  /** Present only with `password_change_required`: single-use, short-lived. */
  change_token?: string;
  principal_id?: string; display_name: string; role?: string; permissions?: string[];
  session_token?: string;
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
  /** Desktop logins only: the session to hold in memory and present as X-Eurogas-Session. */
  session_token?: string;
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
  /** Declared job functions and home office: composition only, never a grant. */
  job_functions?: string[]; office?: string | null;
  /** How the person signs in: a local password, company SSO, or an API key only. */
  account_kind?: "local" | "sso" | "service" | "key";
  /** The one state Admin -> Users shows. */
  account_state?: "ACTIVE" | "INVITED" | "DISABLED" | "LOCKED" | "PENDING";
  local_password?: LocalPasswordStateDTO | null;
  /** Whether the server would accept a delete (no sign-in, key, session or audited act). */
  deletable?: boolean;
}

/** Safe facts about a local password; never the hash. */
export interface LocalPasswordStateDTO {
  must_change_password: boolean;
  temporary_password_expires_at_utc: string | null;
  temporary_password_expired: boolean;
  locked_until_utc: string | null;
  failed_attempts: number;
  password_set_at_utc: string;
  demo_account: boolean;
}

/** How people may be added on this deployment (`GET /api/access/users` meta). */
export interface AccountOptionsDTO {
  local_accounts: boolean;
  local_accounts_setting: string;
  sso_invites: boolean;
  temporary_password_hours: number;
}

export interface AccessUserCreateInputDTO {
  kind: "local" | "sso";
  username?: string; display_name?: string; email?: string | null; subject?: string | null;
  roles?: string[]; data_scopes?: string[]; job_functions?: string[]; office?: string | null;
  groups?: string[];
}

/** A created (or reset) user; `one_time_password` is present once for a local account. */
export interface AccessUserCreatedDTO {
  user: AccessUserDTO;
  one_time_password?: string;
  warning?: string;
}

export interface AccessUserPatchInputDTO {
  status?: string; roles?: string[]; data_scopes?: string[]; email?: string | null;
  job_functions?: string[]; office?: string | null;
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

/** One entry of a first-run setup page: a registered source, or a product capability. */
export interface SetupItemDTO {
  item_id: string;
  source_id?: string;
  source_system?: string;
  category?: string;
  integration?: string;
  /**
   * How the product connects to it today: open, approval, approval_and_key, key, model,
   * licensed_key, licensed_import, licensed_none, register, template; for the book and people
   * pages: import, api_key, admin.
   */
  connection: string;
  credential_provider?: string | null;
  key_registration_url?: string | null;
  licence_family?: string | null;
  import_tools?: string[];
  tool?: string;
  datasets?: string[];
}

/** One operator of the public LNG terminal tariff register and whether the firm may read its documents (CP-11). */
export interface LngTariffOperatorDTO {
  operator: string;
  display_name: string;
  legal_url: string;
  finding: string;
  checked_on: string;
  permission_state: "needs_firm_terms" | "permitted";
  reference: string | null;
  recorded_by: string | null;
  recorded_at_utc: string | null;
}

/** One published figure in the register: a candidate until a second person reviews it. */
export interface LngTerminalTariffDTO {
  tariff_id: string;
  terminal_id: string;
  operator: string;
  terminal_name: string;
  product: string;
  charge_basis: string;
  amount: number | null;
  currency: string;
  unit: string | null;
  by_cargo_class: Record<string, number> | null;
  valid_from: string | null;
  valid_to: string | null;
  period_label: string | null;
  excludes: string[];
  source_url: string | null;
  document_title: string | null;
  retrieved_at_utc: string;
  review_status: "CANDIDATE" | "REVIEWED";
  recorded_by: string | null;
  reviewed_by: string | null;
  reviewed_at_utc: string | null;
}

export interface LngTerminalTariffRegisterDTO {
  operators: LngTariffOperatorDTO[];
  tariffs: LngTerminalTariffDTO[];
  counts: { reviewed: number; candidate: number; terminals: number };
}

/** One of the firm's assumption sets, without its values (`GET /api/assumption-sets`). */
export interface AssumptionSetSummaryDTO {
  set_id: string;
  name: string;
  scope: "organisation" | "book";
  book_id: string | null;
  approved_version: number | null;
}

/** One version of a voyage distance the firm holds (CP-12 `freight_route`). */
export interface FreightRouteDTO {
  route_id: string;
  version: number;
  load_port: string;
  discharge_port: string;
  discharge_terminal_id: string | null;
  routing: "direct" | "suez" | "panama" | "cape";
  distance_nm: number;
  canal: "none" | "suez" | "panama";
  source: string;
  recorded_by: string;
  recorded_at_utc: string | null;
}

export interface CargoLegDTO {
  key: string;
  label: string;
  amount: number | null;
  unit: string;
  input_class: string;
  source: string;
}

export interface CargoTerminalDTO {
  terminal_id: string;
  name: string;
  hub: string;
  currency: string;
  arrival_month: string;
  reason: string | null;
  cost_per_mwh: number | null;
  netback_per_mwh: number | null;
  margin_per_mwh: number | null;
  /** The margin in the reporting currency per MWh, when terminals in several currencies rank together. */
  margin_reporting_per_mwh?: number | null;
  margin_usd_mmbtu: number | null;
  margin_total: number | null;
  lifting_margin_per_mwh: number | null;
  margin_low_per_mwh: number | null;
  margin_high_per_mwh: number | null;
  regas_basis: string;
  grade: string;
  assumptions: number;
  excludes: string[];
  legs: CargoLegDTO[];
  /** USD per one unit of the hub currency used on this row, and where it came from. */
  fx_usd_per_unit?: number | null;
  fx_source?: string;
  /** The margin step by step, hub currency per MWh delivered (hub, gas in kind, entry, regas,
   * netback, FOB or DES, boil-off, freight, margin). */
  steps?: { key: string; amount: number | null; kind: "total" | "delta" }[];
  /** Henry Hub versus the hub (design C.4), FOB rows only: the delivered and netback views. */
  delivered_spread?: CargoDeliveredSpreadDTO | null;
}

export interface CargoDeliveredSpreadDTO {
  delivered_per_mwh: number | null;
  hub_per_mwh: number | null;
  arb_per_mwh: number | null;
  arb_total: number | null;
  sent_out_mwh: number | null;
  fob_netback_usd_mmbtu: number | null;
  fob_price_usd_mmbtu: number | null;
  lifting_price_usd_mmbtu: number | null;
  netback_margin_usd_mmbtu: number | null;
  netback_lifting_margin_usd_mmbtu: number | null;
  netback_total: number | null;
}

/** How a cargo's voyage was stated: a saved route, or the desk's own distance or days. */
export interface CargoVoyageDTO {
  basis: "saved_route" | "entered_distance" | "entered_days" | "standard" | "none";
  route_id: string | null;
  label?: string;
  source?: string;
  distance_nm?: number | null;
  speed_kn?: number | null;
  ballast?: "round" | "one_way";
}

export interface CargoResultDTO {
  cargo_id: string;
  label: string;
  term: "FOB" | "DES";
  blocked: string | null;
  q_load_mmbtu: number | null;
  q_del_mmbtu: number | null;
  q_del_mwh: number | null;
  fob_price_usd_mmbtu: number | null;
  lifting_price_usd_mmbtu: number | null;
  cost_usd_mmbtu: number | null;
  lifting_cost_usd_mmbtu: number | null;
  freight_usd: number | null;
  days: { laden: number; ballast: number; port: number } | null;
  legs: CargoLegDTO[];
  terminals: CargoTerminalDTO[];
  best_terminal_id: string | null;
  no_winner: boolean;
  grade: string;
  assumptions: number;
  voyage?: CargoVoyageDTO | null;
  /** Margin change per MWh for one input moved on its own (HH, hire, hub, FX). */
  sensitivity?: { key: "hh" | "hire" | "hub" | "fx"; bump: number; unit: string; margin_change_per_mwh: number }[];
}

/** A cargo to price; omitted figures come from the firm's approved assumption set. */
export interface CargoInput {
  cargo_id: string;
  label?: string;
  term: "FOB" | "DES";
  pricing_month?: string;
  q_load_mmbtu?: number;
  hh?: number;
  slope?: number;
  fee?: number;
  fob_price?: number;
  des_price?: number;
  des_currency?: "EUR" | "GBP" | "USD";
  route_id?: string;
  /** Fill what neither the request nor the assumption set holds with the desk standard (labelled). */
  standard?: boolean;
  /** The voyage as the desk states it when no saved route is named. */
  distance_nm?: number;
  laden_days?: number;
  ballast?: "round" | "one_way";
  speed_kn?: number;
  hire_per_day?: number;
  boil_off_pct_per_day?: number;
  ballast_fuel_mmbtu_per_day?: number;
  port_cost?: number;
  canal_cost?: number;
  insurance_pct?: number;
}

export interface CargoEconomicsDTO {
  arrival_month: string;
  fx_method: string;
  cargoes: CargoResultDTO[];
  table: {
    cargo_id: string;
    label: string;
    term: "FOB" | "DES";
    arrives: string;
    blocked: string | null;
    cost_per_mwh: number | null;
    best_terminal: string | null;
    netback_per_mwh: number | null;
    margin_per_mwh: number | null;
    lifting_margin_per_mwh: number | null;
    currency: string | null;
    no_winner: boolean;
    grade: string;
    assumptions: number;
  }[];
  terminals_considered: string[];
  reporting_currency?: string;
  /** The assumption-set version the evaluation read, or null when none is approved. */
  assumption_version?: string | null;
  /** Henry Hub against the hub, daily: the same chain on each day both prices are held. */
  delivered_spread_history?: {
    terminal_id: string;
    hub: string;
    currency: string;
    fx: string;
    hh_source: "EIA" | "demo" | null;
    hh_days: number;
    points: { day: string; hh: number; hub_per_mwh: number; delivered_per_mwh: number; arb_per_mwh: number; simulated: boolean }[];
  } | null;
  delivered_spread_series?: {
    terminal_id: string;
    cargo_id: string;
    points: {
      arrival_month: string;
      pricing_month: string;
      reason: string | null;
      hh: number | null;
      hh_class: string | null;
      hub_per_mwh: number | null;
      delivered_per_mwh: number | null;
      arb_per_mwh: number | null;
      grade: string;
    }[];
  } | null;
}

export interface SetupViewDTO {
  state: {
    status: "not_started" | "in_progress" | "completed" | "dismissed";
    current_step: string | null;
    steps_visited: string[];
    configured_by: "admin" | "demo_profile" | "environment" | null;
    updated_by: string | null;
    updated_at_utc: string | null;
  };
  show_on_sign_in: boolean;
  catalogue: {
    steps: { step: string; items: SetupItemDTO[] }[];
    excluded: { source_id: string; reason: string }[];
  };
  key_storage_ready: boolean;
  ai_external_enabled: boolean;
  /** LNG terminal tariffs the product holds (`lng_terminal_terms`) and where they came from. */
  terminal_tariffs: {
    held: number; from_operator: number; desk_entered: number;
    reviewed?: number; candidate?: number;
    /** Operators whose reuse permission the firm has not recorded (their documents are not read). */
    operators_needing_terms?: string[];
    terminals: string[]; latest_read_at_utc: string | null;
  };
}

/** Where an audit walk stands (#59): the anchor, whether more matches exist, the next cursor. */
export interface AuditContinuationDTO {
  anchor_utc: string;
  has_more: boolean;
  cursor: string | null;
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
  /** Simulated demo prices are valuing positions in this deployment (demo runs only). */
  demo_marks?: boolean;
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
  legacy_backtest_engine_version: string;
  strategy_schema_version: string;
  strategy_run_schema_version: string;
  solver_version: string;
  /** Installation region and its default basemap (open licence globally, none in China). */
  deployment?: { region: string; map_default_provider: string };
}

export interface RuntimeDependenciesDTO {
  generated_at_utc: string;
  database: RuntimeDependencyStateDTO;
  schedulers: Record<string, RuntimeDependencyStateDTO>;
  oidc: RuntimeDependencyStateDTO;
  llm: RuntimeDependencyStateDTO;
  streaming: RuntimeDependencyStateDTO;
}

/**
 * One persisted ECMWF forecast-grid reading at a single instant.
 *
 * Mirrors `ForecastPointReading` in the backend contract. Timestamps are the
 * backend's explicit-UTC ISO-8601 strings, not local times, and the two hashes
 * are the stored sha256 provenance. This is transport data only: no client
 * aggregation, persistence or inferred station identity belongs here.
 */
export interface ForecastPointReadingDTO {
  observation_id: string;
  point_id: string;
  series_id: string;
  entity_id: string;
  source_system: "ECMWF_OPEN_DATA";
  provider: "ECMWF";
  model: string;
  run_id: string;
  issued_at_utc: string;
  valid_at_utc: string;
  available_at_utc: string;
  temperature_c: number;
  unit: "degC";
  raw_grib_sha256: string;
  record_content_sha256: string;
  requested_latitude: number;
  requested_longitude: number;
  grid_latitude: number;
  grid_longitude: number;
}

/**
 * Envelope metadata for the research-only forecast surface.
 *
 * `research_only` is the literal `true` the backend emits; the attribution and
 * warnings are part of the answer, not decoration, so callers keep the whole
 * meta object rather than narrowing it to the data array.
 */
export interface ForecastReadMetaDTO {
  research_only: true;
  source_references: string[];
  warnings: string[];
  attribution: string;
  point_kind: "FORECAST_GRID_POINT";
}

/** Bounded forecast-grid response envelope (`GET /api/weather/forecasts`). */
export interface ForecastReadEnvelopeDTO {
  data: ForecastPointReadingDTO[];
  meta: ForecastReadMetaDTO;
}

/**
 * Explicit forecast query. Every field is required: the client never fills in
 * a default region, an implicit "now", or a zero limit on the caller's behalf.
 */
export interface FetchWeatherForecastsOptions {
  seriesIds: string[];
  entityIds: string[];
  /** Explicit UTC instant whose issued/available vintages may be selected. */
  predictionOrigin: string;
  /** Inclusive lower bound of the half-open valid-at window. */
  validFrom: string;
  /** Exclusive upper bound of the half-open valid-at window. */
  validTo: string;
  /** Maximum rows the backend may return, from 1 through 256. */
  limit: number;
  signal?: AbortSignal;
}

const WEATHER_FORECAST_MAX_IDENTIFIERS = 256;
const WEATHER_FORECAST_MAX_SERIES_ID_LENGTH = 160;
const WEATHER_FORECAST_MAX_ENTITY_ID_LENGTH = 128;
const WEATHER_FORECAST_MAX_LIMIT = 256;
const WEATHER_FORECAST_MAX_WINDOW_MS = 32 * 24 * 60 * 60 * 1000;
const UTC_ISO_TIMESTAMP =
  /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2}(?:\.\d{1,9})?)?(?:Z|z|[+-]00:00)$/;

function forecastIdentifiers(
  value: unknown,
  name: string,
  maxLength: number,
): string[] {
  if (!Array.isArray(value) || value.length === 0) {
    throw new TypeError(`${name} must be a non-empty list of identifiers.`);
  }
  if (value.length > WEATHER_FORECAST_MAX_IDENTIFIERS) {
    throw new TypeError(
      `${name} must contain at most ${WEATHER_FORECAST_MAX_IDENTIFIERS} identifiers.`,
    );
  }
  return value.map((entry, index) => {
    if (typeof entry !== "string") {
      throw new TypeError(`${name}[${index}] must be a string identifier.`);
    }
    const identifier = entry.trim();
    if (!identifier) {
      throw new TypeError(`${name}[${index}] must not be empty.`);
    }
    if (identifier.length > maxLength) {
      throw new TypeError(
        `${name}[${index}] must be at most ${maxLength} characters.`,
      );
    }
    return identifier;
  });
}

function forecastUtcInstant(value: unknown, name: string): number {
  if (typeof value !== "string" || !UTC_ISO_TIMESTAMP.test(value.trim())) {
    throw new TypeError(`${name} must be an explicit UTC ISO-8601 timestamp.`);
  }
  const parsed = Date.parse(value.trim());
  if (!Number.isFinite(parsed)) {
    throw new TypeError(`${name} must be a valid UTC ISO-8601 timestamp.`);
  }
  return parsed;
}

/**
 * Read bounded ECMWF forecast points for explicitly authorized series/entities.
 *
 * Validation happens before any transport call, so an unbounded or implicit
 * query never reaches the backend. The response is returned as the complete
 * typed envelope, including `research_only`, attribution, source references and
 * warnings; HTTP failures reject as the existing `ApiError` with its structured
 * detail intact.
 */
export async function fetchWeatherForecasts(
  options: FetchWeatherForecastsOptions,
): Promise<ForecastReadEnvelopeDTO> {
  if (!options || typeof options !== "object") {
    throw new TypeError("Weather forecast options are required.");
  }

  const seriesIds = forecastIdentifiers(
    options.seriesIds,
    "seriesIds",
    WEATHER_FORECAST_MAX_SERIES_ID_LENGTH,
  );
  const entityIds = forecastIdentifiers(
    options.entityIds,
    "entityIds",
    WEATHER_FORECAST_MAX_ENTITY_ID_LENGTH,
  );
  const predictionOrigin = options.predictionOrigin;
  const validFrom = options.validFrom;
  const validTo = options.validTo;
  forecastUtcInstant(predictionOrigin, "predictionOrigin");
  const validFromMs = forecastUtcInstant(validFrom, "validFrom");
  const validToMs = forecastUtcInstant(validTo, "validTo");

  if (validToMs <= validFromMs) {
    throw new TypeError("validTo must be after validFrom.");
  }
  if (validToMs - validFromMs > WEATHER_FORECAST_MAX_WINDOW_MS) {
    throw new TypeError("The forecast validity window must not exceed 32 days.");
  }

  const limit = options.limit;
  if (
    typeof limit !== "number" ||
    !Number.isInteger(limit) ||
    limit < 1 ||
    limit > WEATHER_FORECAST_MAX_LIMIT
  ) {
    throw new TypeError(
      `limit must be an integer between 1 and ${WEATHER_FORECAST_MAX_LIMIT}.`,
    );
  }

  const params = new URLSearchParams();
  seriesIds.forEach((seriesId) => params.append("series_ids", seriesId));
  entityIds.forEach((entityId) => params.append("entity_ids", entityId));
  params.set("prediction_origin", predictionOrigin.trim());
  params.set("valid_from", validFrom.trim());
  params.set("valid_to", validTo.trim());
  params.set("limit", String(limit));

  const response = await get<ForecastPointReadingDTO[], ForecastReadMetaDTO>(
    "/weather/forecasts",
    params,
    { signal: options.signal },
  );
  return { data: response.data, meta: response.meta };
}
