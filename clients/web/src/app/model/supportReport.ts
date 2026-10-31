/**
 * What a problem report carries from the client, and the event any panel raises to open the
 * report dialog with a prefilled summary. Allowlisted facts only: versions, the page, screen
 * size and scaling, and which reads failed with their correlation codes. No prices,
 * positions, contract terms, credentials or personal data.
 */

export const REPORT_PROBLEM_EVENT = "eurogas:report-problem";

export interface ReportPrefill {
  summary?: string;
  category?: "data" | "wrong_figure" | "access" | "performance" | "how_to" | "other";
  severity?: "P1" | "P2" | "P3" | "P4";
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
    failed_reads: Object.entries(facts.endpointErrorCodes)
      .slice(0, 30)
      .map(([endpoint, code]) => ({ endpoint, code })),
  };
}

/** Open the report dialog from anywhere, e.g. a stale-price banner's "Report to IT". */
export function requestProblemReport(prefill: ReportPrefill = {}): void {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new CustomEvent(REPORT_PROBLEM_EVENT, { detail: prefill }));
}
