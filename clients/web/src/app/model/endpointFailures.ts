/**
 * Pure presentation model for the single bounded workspace endpoint-failure
 * surface.
 *
 * The store owns the failure facts: internal loader keys with the backend
 * message they produced (`endpointErrors`) plus one safe machine code per key
 * (`endpointErrorCodes`). Both are diagnostics, not display text - a raw loader
 * key such as `normalizedMarkets` and a backend prose message never reach the
 * DOM. This module turns those facts into translated labels, a bounded detail
 * list, a "showing N of M" summary and one retry-status line, so the banner
 * cannot leak internals and cannot grow without limit no matter how many
 * endpoints fail.
 */

import type { TFunction } from "i18next";
import type { WorkspaceEndpointFailureCode } from "@/stores/workspaceLoading";

/** Detail bound for the failure surface: at most five labelled endpoints. */
export const MAX_ENDPOINT_FAILURE_DETAILS = 5;

/** Safe failure vocabulary. An unreadable or unexpected code stays "unknown". */
export type EndpointFailureCode = WorkspaceEndpointFailureCode | "unknown";

/**
 * Internal loader key -> i18n label key.
 *
 * Every key the workspace, market and monitoring lanes can write is listed, so
 * a normal failure never needs the generic fallback. Values are literal keys,
 * not derived from the loader key, which keeps the mapping reviewable and
 * keeps the raw key out of the label.
 */
export const ENDPOINT_FAILURE_LABEL_KEYS: Record<string, string> = {
  referenceNodes: "workspace.endpoint.reference_nodes",
  referenceEdges: "workspace.endpoint.reference_edges",
  sources: "workspace.endpoint.sources",
  normalizedMarkets: "workspace.endpoint.normalized_markets",
  marketSpreads: "workspace.endpoint.market_spreads",
  marketQuotes: "workspace.endpoint.market_quotes",
  intradayOpportunities: "workspace.endpoint.intraday_opportunities",
  screenOrders: "workspace.endpoint.screen_orders",
  pnlSnapshots: "workspace.endpoint.pnl_snapshots",
  portfolioSummary: "workspace.endpoint.portfolio_summary",
  fxRates: "workspace.endpoint.fx_rates",
  flows: "workspace.endpoint.flows",
  capacity: "workspace.endpoint.capacity",
  storage: "workspace.endpoint.storage",
  lng: "workspace.endpoint.lng",
  tsoAccess: "workspace.endpoint.tso_access",
  routes: "workspace.endpoint.routes",
  routeCandidates: "workspace.endpoint.route_candidates",
  tsoTariffs: "workspace.endpoint.tso_tariffs",
  upstreamContracts: "workspace.endpoint.upstream_contracts",
  resourcePoolOptions: "workspace.endpoint.resource_pool_options",
  glossaryTerms: "workspace.endpoint.glossary_terms",
  runtimeDb: "workspace.endpoint.runtime_db",
  runtimeDependencies: "workspace.endpoint.runtime_dependencies",
  credentialProviders: "workspace.endpoint.credential_providers",
  monitoringAlerts: "workspace.endpoint.monitoring_alerts",
  monitoringSummary: "workspace.endpoint.monitoring_summary",
  reviewDecisions: "workspace.endpoint.review_decisions",
  pipelineHealth: "workspace.endpoint.pipeline_health",
};

/** Fallback label for a loader key this client does not know: never the raw key. */
export const UNKNOWN_ENDPOINT_FAILURE_LABEL_KEY = "workspace.endpoint.unknown";

/** Safe code -> i18n message key. */
export const ENDPOINT_FAILURE_CODE_KEYS: Record<EndpointFailureCode, string> = {
  timeout: "workspace.failure.timeout",
  aborted: "workspace.failure.aborted",
  request: "workspace.failure.request",
  unknown: "workspace.failure.unknown",
};

export const ENDPOINT_FAILURE_COUNT_KEY = "workspace.failures_count";
export const ENDPOINT_FAILURE_SHOWING_KEY = "workspace.failures_showing";

export const ENDPOINT_RETRY_ATTEMPTS_KEY = "workspace.retry_attempts";
export const ENDPOINT_RETRY_LAST_ATTEMPT_KEY = "workspace.retry_last_attempt";
export const ENDPOINT_RETRY_RUNNING_KEY = "workspace.retry_in_progress";

/** Severity order: no response, rejected, superseded, unclassified. */
const FAILURE_CODE_ORDER: Record<EndpointFailureCode, number> = {
  timeout: 0,
  request: 1,
  aborted: 2,
  unknown: 3,
};

export interface EndpointFailureDetail {
  /** Internal loader key. Used as a React key and for tests, never rendered. */
  key: string;
  labelKey: string;
  /** Translated endpoint label. Always i18n, never the loader key. */
  label: string;
  /** Safe machine code rendered as a chip. */
  code: EndpointFailureCode;
  codeKey: string;
  /** Safe translated message for the code, never the backend message. */
  message: string;
}

export interface EndpointFailureSurface {
  /** Every affected endpoint, including the ones beyond the detail bound. */
  total: number;
  /** At most `MAX_ENDPOINT_FAILURE_DETAILS` entries, worst first. */
  entries: EndpointFailureDetail[];
  hiddenCount: number;
  truncated: boolean;
  summaryKey: string;
  summary: string;
  /** Present only when more than five endpoints are affected. */
  truncatedSummaryKey: string | null;
  truncatedSummary: string | null;
}

function safeFailureCode(code: string | undefined): EndpointFailureCode {
  return code === "timeout" || code === "aborted" || code === "request" ? code : "unknown";
}

function compareDetails(left: EndpointFailureDetail, right: EndpointFailureDetail): number {
  const severity = FAILURE_CODE_ORDER[left.code] - FAILURE_CODE_ORDER[right.code];
  if (severity !== 0) return severity;
  if (left.label !== right.label) return left.label < right.label ? -1 : 1;
  return left.key < right.key ? -1 : left.key > right.key ? 1 : 0;
}

/**
 * Bounded, translated view of the current endpoint failures.
 *
 * An empty or missing failure map yields a zero-count surface, so the caller
 * can decide whether to mount the banner at all. Failures are ordered worst
 * first and then deterministically, so the five listed entries do not reshuffle
 * between renders while the surface is truncated.
 */
export function describeEndpointFailures(
  endpointErrors: Record<string, string> | null | undefined,
  endpointErrorCodes: Record<string, string> | null | undefined,
  t: TFunction,
): EndpointFailureSurface {
  const entries = Object.keys(endpointErrors ?? {})
    .map((key): EndpointFailureDetail => {
      const labelKey = ENDPOINT_FAILURE_LABEL_KEYS[key] ?? UNKNOWN_ENDPOINT_FAILURE_LABEL_KEY;
      const code = safeFailureCode(endpointErrorCodes?.[key]);
      const codeKey = ENDPOINT_FAILURE_CODE_KEYS[code];
      return { key, labelKey, label: t(labelKey), code, codeKey, message: t(codeKey) };
    })
    .sort(compareDetails);

  const total = entries.length;
  const shown = entries.slice(0, MAX_ENDPOINT_FAILURE_DETAILS);
  const truncated = total > MAX_ENDPOINT_FAILURE_DETAILS;

  return {
    total,
    entries: shown,
    hiddenCount: total - shown.length,
    truncated,
    summaryKey: ENDPOINT_FAILURE_COUNT_KEY,
    summary: t(ENDPOINT_FAILURE_COUNT_KEY, { total }),
    truncatedSummaryKey: truncated ? ENDPOINT_FAILURE_SHOWING_KEY : null,
    truncatedSummary: truncated
      ? t(ENDPOINT_FAILURE_SHOWING_KEY, { shown: shown.length, total })
      : null,
  };
}

export interface EndpointRetryState {
  busy: boolean;
  attempts: number;
  lastAttemptAtUtc: string | null;
}

export interface EndpointRetrySurface {
  busy: boolean;
  /** The retry control is disabled exactly while an attempt is in flight. */
  disabled: boolean;
  attempts: number;
  attemptsKey: string;
  attemptsLabel: string;
  lastAttemptAtUtc: string | null;
  lastAttemptLabel: string | null;
  /** Present only while an attempt is running. */
  runningKey: string | null;
  runningLabel: string | null;
}

/**
 * Clock time of an attempt timestamp in UTC, or null when it is missing or
 * unparsable - the surface never prints "Invalid Date".
 */
export function attemptClockUtc(iso: string | null | undefined): string | null {
  if (!iso) return null;
  const parsed = new Date(iso);
  if (Number.isNaN(parsed.getTime())) return null;
  return parsed.toISOString().slice(11, 19);
}

/**
 * Presentation of the bounded retry: one attempt at a time, a visible attempt
 * counter and the clock time of the last attempt. Refusing a second concurrent
 * attempt is the store's job; this only reports the state the control renders.
 */
export function describeEndpointRetry(
  state: EndpointRetryState,
  t: TFunction,
): EndpointRetrySurface {
  const attempts = Number.isFinite(state.attempts) && state.attempts > 0
    ? Math.floor(state.attempts)
    : 0;
  const lastAttemptAtUtc = state.lastAttemptAtUtc || null;
  const clock = attemptClockUtc(lastAttemptAtUtc);

  return {
    busy: state.busy,
    disabled: state.busy,
    attempts,
    attemptsKey: ENDPOINT_RETRY_ATTEMPTS_KEY,
    attemptsLabel: t(ENDPOINT_RETRY_ATTEMPTS_KEY, { attempts }),
    lastAttemptAtUtc,
    lastAttemptLabel: clock === null
      ? null
      : t(ENDPOINT_RETRY_LAST_ATTEMPT_KEY, { time: clock }),
    runningKey: state.busy ? ENDPOINT_RETRY_RUNNING_KEY : null,
    runningLabel: state.busy ? t(ENDPOINT_RETRY_RUNNING_KEY) : null,
  };
}
