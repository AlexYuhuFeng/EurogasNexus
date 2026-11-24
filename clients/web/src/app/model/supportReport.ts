/**
 * What a problem report carries from the client, and the event any panel raises to open the
 * report dialog with a prefilled summary. Allowlisted facts only: versions, the page, screen
 * size and scaling, and which reads failed with their correlation codes. No prices,
 * positions, contract terms, credentials or personal data.
 */

export const REPORT_PROBLEM_EVENT = "eurogas:report-problem";

export const REPORT_CATEGORIES = ["data", "wrong_figure", "access", "performance", "how_to", "other", "suggestion"] as const;
export type ReportCategory = (typeof REPORT_CATEGORIES)[number];

/**
 * "Send feedback" is a report with this category: an improvement request, the first step of the
 * improvement loop (docs/engineering/Commercial-Intelligence-V3/14). The server stores it as P4.
 */
export const SUGGESTION_CATEGORY = "suggestion" satisfies ReportCategory;

export interface ReportPrefill {
  summary?: string;
  category?: ReportCategory;
  severity?: "P1" | "P2" | "P3" | "P4";
  /** The reporter's role composition (presentation only), so feedback can be read by role. */
  composition?: string | null;
}

export interface ClientContextFacts {
  clientVersion: string | null;
  serverVersion: string | null;
  schemaRevision: string | null;
  hostKind: string;
  language: string;
  location: { pathname: string; search: string };
  viewport: { width: number; height: number; devicePixelRatio: number };
  userAgent: string;
  dataStatus: string | null;
  endpointErrorCodes: Record<string, string>;
  /** The role composition the client shows (`trader`, `lng`, ...); never an authority. */
  composition?: string | null;
}

/** Keep only the page's navigation parameters (workspace, task, view), not record ids. */
export function safePage(location: { pathname: string; search: string }): string {
  const params = new URLSearchParams(location.search);
  const kept = ["workspace", "task", "view"]
    .filter((key) => params.get(key))
    .map((key) => `${key}=${params.get(key)}`);
  return `${location.pathname}${kept.length ? `?${kept.join("&")}` : ""}`;
}

export function supportClientContext(facts: ClientContextFacts): Record<string, unknown> {
  return {
    client_version: facts.clientVersion,
    server_version: facts.serverVersion,
    schema_revision: facts.schemaRevision,
    host: facts.hostKind,
    language: facts.language,
    page: safePage(facts.location),
    viewport: `${facts.viewport.width}x${facts.viewport.height}@${facts.viewport.devicePixelRatio}x`,
    user_agent: facts.userAgent.slice(0, 200),
    data_status: facts.dataStatus,
    composition: facts.composition ?? null,
    failed_reads: Object.entries(facts.endpointErrorCodes)
      .slice(0, 30)
      .map(([endpoint, code]) => ({ endpoint, code })),
  };
}

/** Open the report dialog in suggestion mode ("Send feedback"). */
export function requestFeedback(composition?: string | null): void {
  requestProblemReport({ category: SUGGESTION_CATEGORY, severity: "P4", composition: composition ?? null });
}

/** Open the report dialog from anywhere, e.g. a stale-price banner's "Report to IT". */
export function requestProblemReport(prefill: ReportPrefill = {}): void {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new CustomEvent(REPORT_PROBLEM_EVENT, { detail: prefill }));
}
