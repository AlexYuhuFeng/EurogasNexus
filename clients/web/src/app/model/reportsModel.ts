/**
 * Research → Reports: the form's state, the request it sends and the situation subject a
 * "Report" action carries in the URL (`?workspace=research&task=reports&subject=outage:<id>`).
 * Pure functions, so the request a form makes is tested without a browser.
 */
import type { ReportAudience, ReportCatalogueDTO, ReportKind, ReportRequestDTO, ReportSummaryDTO } from "../../api/client.ts";

export interface ReportSubject {
  kind: "alert" | "outage";
  id: string;
}

export interface ReportForm {
  kind: ReportKind;
  variant: "morning" | "eod";
  audience: ReportAudience;
  /** null: the kind's default sections. */
  sections: string[] | null;
  hubs: string;
  periodStart: string;
  periodEnd: string;
  subject: ReportSubject | null;
  question: string;
  /** Print the data annex; null: the kind's default. */
  annex: boolean | null;
  /** The report's language; defaults to the interface language. */
  language?: "en" | "zh-CN";
  /** Reporting currency and energy unit; empty: native only. */
  currency?: "" | "EUR" | "GBP" | "USD";
  energyUnit?: "" | "MWh" | "th" | "MMBtu";
}

/** Whether a report of this kind prints its data annex unless asked otherwise. */
export function annexByDefault(kind: ReportKind): boolean {
  return kind === "weekly" || kind === "monthly";
}

export function reportSubjectFromSearch(search: string): ReportSubject | null {
  const params = new URLSearchParams(search);
  if (params.get("workspace") !== "research" || params.get("task") !== "reports") return null;
  const raw = params.get("subject") ?? "";
  const [kind, ...rest] = raw.split(":");
  const id = rest.join(":");
  return (kind === "alert" || kind === "outage") && id ? { kind, id } : null;
}

/**
 * A question handed over from the answer bar's "Open as report" (`?ask=`), on Reports only.
 * Reports then proposes its plan through its own Ask flow.
 */
export function reportQuestionFromSearch(search: string): string | null {
  const params = new URLSearchParams(search);
  if (params.get("workspace") !== "research" || params.get("task") !== "reports") return null;
  const question = (params.get("ask") ?? "").trim();
  return question.length >= 3 ? question.slice(0, 500) : null;
}

/** The URL search that opens Reports on a situation report about one alert or outage. */
export function reportSubjectSearch(search: string, subject: ReportSubject): string {
  const next = new URLSearchParams(search);
  next.delete("view");
  next.set("workspace", "research");
  next.set("task", "reports");
  next.set("subject", `${subject.kind}:${subject.id}`);
  return next.toString();
}

/** Hub codes typed by the user: upper case, separated by commas or spaces; nothing resolved here. */
export function parseHubs(text: string): string[] {
  return [...new Set(text.split(/[\s,;]+/).map((item) => item.trim().toUpperCase()).filter(Boolean))];
}

export function reportRequestFromForm(
  form: ReportForm,
  mode: "standard" | "ask",
  sections: readonly string[],
  language: "en" | "zh-CN",
): ReportRequestDTO {
  const kind: ReportKind = mode === "ask" ? "ask" : form.kind;
  const body: ReportRequestDTO = { kind, audience: form.audience, sections: [...sections], language };
  if (kind === "daily") body.variant = form.variant;
  const hubs = parseHubs(form.hubs);
  if (hubs.length) body.hubs = hubs;
  if (form.periodStart) body.period_start = form.periodStart;
  if (form.periodEnd) body.period_end = form.periodEnd;
  if (kind === "situation" && form.subject) {
    if (form.subject.kind === "alert") body.alert_id = form.subject.id;
    else body.outage_id = form.subject.id;
  }
  if (kind === "ask" && form.question.trim()) body.question = form.question.trim();
  if (form.annex !== null && form.annex !== annexByDefault(kind)) body.annex = form.annex;
  if (form.currency) body.currency = form.currency;
  if (form.energyUnit) body.energy_unit = form.energyUnit;
  return body;
}

/** The report's own data block (the series behind its exhibits) as CSV, one block per table. */
export function reportCsv(html: string): string {
  const match = /<script type="application\/json" id="report-data">([\s\S]*?)<\/script>/.exec(html);
  if (!match) return "";
  let data: { tables?: { section: string; caption: string; columns: string[]; rows: Record<string, unknown>[] }[] };
  try {
    data = JSON.parse(match[1].replace(/<\\\//g, "</"));
  } catch {
    return "";
  }
  const cell = (value: unknown) => {
    const text = value === null || value === undefined ? "" : String(value);
    return /[",\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
  };
  const blocks = (data.tables ?? []).map((table) =>
    [cell(`${table.section}: ${table.caption}`), table.columns.map(cell).join(","),
      ...table.rows.map((row) => table.columns.map((column) => cell(row[column])).join(","))].join("\n"));
  return blocks.join("\n\n");
}

/** The report with only page one shown: what "Summary only" prints. */
export function summaryOnlyHtml(html: string): string {
  return html.replace("</head>", "<style>.r-body,.r-back-sheet{display:none!important}</style></head>");
}

/**
 * Generation progress. A report is one request (the server does not stream its steps yet),
 * so the stages after planning advance on the typical durations measured on the demo desk
 * and the public store (rule-written about 5 s; AI-edited 20 to 80 s, most of it writing);
 * "laying out" holds until the reply arrives. Kept separate from the component so a shared
 * progress hook can replace it without touching the page.
 */
export type ReportStage = "planning" | "collecting" | "writing" | "checking" | "laying_out";

export const REPORT_STAGES: readonly ReportStage[] = ["planning", "collecting", "writing", "checking", "laying_out"];

/** The stage to show `elapsedMs` after the report request was sent (planning is its own step). */
export function reportStageAt(elapsedMs: number): Exclude<ReportStage, "planning"> {
  if (elapsedMs < 3_000) return "collecting";
  if (elapsedMs < 45_000) return "writing";
  if (elapsedMs < 60_000) return "checking";
  return "laying_out";
}

/** The stored-report list's "who edited it" word. */
export function editedByLabel(summary: Pick<ReportSummaryDTO, "edited_by">): "model" | "rule" {
  return summary.edited_by === "model" ? "model" : "rule";
}

/** A report's period as the list shows it ("9 Nov – 15 Nov", one day, or empty). */
export function reportPeriodLabel(start: string | null, end: string | null): string {
  const short = (value: string) => {
    const day = new Date(`${value.slice(0, 10)}T00:00:00Z`);
    return `${day.getUTCDate()} ${day.toLocaleString("en-GB", { month: "short", timeZone: "UTC" })}`;
  };
  if (!start && !end) return "";
  if (start && end && start !== end) return `${short(start)} – ${short(end)}`;
  return short((end ?? start) as string);
}

/**
 * What stops this form from being generated, decided before Generate is pressed (the server
 * would refuse the same plan): each entry is a translation key and its values, shown beside
 * the control it concerns. An empty list means the server will accept the plan.
 */
export interface FormIssue {
  field: "role" | "sections" | "period" | "hubs" | "question" | "store";
  key: string;
  values?: Record<string, string | number>;
}

export function formIssues(
  form: ReportForm,
  mode: "standard" | "ask",
  sections: readonly string[],
  catalogue: Pick<ReportCatalogueDTO, "hubs" | "availability"> | null,
  today: string,
): FormIssue[] {
  const issues: FormIssue[] = [];
  const offer = catalogue?.availability;
  if (offer && !offer.can_generate) issues.push({ field: "role", key: "reports.issue.role" });
  if (catalogue && offer === null) issues.push({ field: "store", key: "reports.issue.store" });
  if (mode === "ask") {
    if (form.question.trim().length < 3) issues.push({ field: "question", key: "reports.issue.question" });
  } else if (!sections.length) {
    issues.push({ field: "sections", key: "reports.issue.no_sections" });
  }
  const latest = offer?.period.latest_end ?? today;
  const maxDays = offer?.period.max_days ?? 400;
  const { periodStart: start, periodEnd: end } = form;
  if (start && end && end < start) issues.push({ field: "period", key: "reports.issue.period_order" });
  else if (start && end && daysBetween(start, end) + 1 > maxDays) {
    issues.push({ field: "period", key: "reports.issue.period_long", values: { days: maxDays } });
  }
  if ((end && end > latest) || (start && start > latest)) {
    issues.push({ field: "period", key: "reports.issue.period_future", values: { day: latest } });
  }
  const known = new Set((catalogue?.hubs ?? []).map((hub) => hub.toUpperCase()));
  const unknown = known.size ? parseHubs(form.hubs).filter((hub) => !known.has(hub)) : [];
  if (unknown.length) issues.push({ field: "hubs", key: "reports.issue.hub", values: { hubs: unknown.join(", ") } });
  return issues;
}

function daysBetween(start: string, end: string): number {
  return Math.round((Date.parse(`${end}T00:00:00Z`) - Date.parse(`${start}T00:00:00Z`)) / 86_400_000);
}

/** The sections a form actually sends: those offered for its audience (a report for
 * distribution leaves the book out, so it is never refused for it). */
export function sendableSections(chosen: readonly string[], offered: readonly { key: string }[]): string[] {
  const keys = new Set(offered.map((section) => section.key));
  return chosen.filter((key) => keys.has(key));
}

/** What went wrong when a report could not be made, and what the user can do: a translation
 * key for the message and which recovery actions to offer. */
export function explainFailure(status: number | null, code: string | null, aborted: boolean): {
  key: string;
  retry: boolean;
  withoutAi: boolean;
} {
  if (aborted) return { key: "reports.fail.cancelled", retry: true, withoutAi: false };
  if (code === "licensed_data_not_redistributable") return { key: "reports.licensed_refused", retry: false, withoutAi: false };
  if (status === 403) return { key: "reports.fail.forbidden", retry: false, withoutAi: false };
  if (status === 422) return { key: "reports.fail.plan", retry: false, withoutAi: false };
  if (status === 503) return { key: "reports.fail.store", retry: true, withoutAi: false };
  if (status === 504 || status === 502 || status === null) return { key: "reports.fail.timeout", retry: true, withoutAi: true };
  return { key: "reports.fail.server", retry: true, withoutAi: true };
}

/** A failure that may still finish on the server: the connection gave out (a proxy's 504 or
 * 502, or no answer at all) while the report was being written. The server keeps going and
 * stores the report, so the page waits for it in the archive rather than saying it failed. */
export function mayStillLand(status: number | null, aborted: boolean): boolean {
  return !aborted && (status === 504 || status === 502 || status === null);
}

/** How long the page keeps looking for a report whose connection gave out (the server allows
 * the AI editor four minutes), and how often it looks. */
export const LANDING_WAIT_MS = 6 * 60_000;
export const LANDING_POLL_MS = 8_000;

/** The report a timed-out request produced: one that was not in the archive when the request
 * started, written by the same reader, of the same kind, audience and period and, for an asked
 * report, the same question. The archive is shared with every entitled reader and with
 * schedules, so a report someone else wrote meanwhile must not end the wait. */
export function landedReport(
  before: ReadonlySet<string>,
  reports: readonly Pick<ReportSummaryDTO, "report_id" | "kind" | "question" | "generated_by" | "audience" | "period_start" | "period_end">[],
  request: Pick<ReportRequestDTO, "kind" | "question" | "audience" | "period_start" | "period_end">,
  generatedBy: string | null,
): string | null {
  const question = (request.question ?? "").trim();
  const match = reports.find((report) =>
    !before.has(report.report_id)
    && report.kind === request.kind
    && (!generatedBy || report.generated_by === generatedBy)
    && (!request.audience || !report.audience || report.audience === request.audience)
    && (!request.period_start || !report.period_start || report.period_start.slice(0, 10) === request.period_start.slice(0, 10))
    && (!request.period_end || !report.period_end || report.period_end.slice(0, 10) === request.period_end.slice(0, 10))
    && (!question || (report.question ?? "").trim() === question));
  return match ? match.report_id : null;
}

/** A signal that aborts when `parent` does or after `ms`, so one archive read can neither
 * outlive "Stop waiting" nor the landing deadline. */
export function boundedSignal(parent: AbortSignal, ms: number): { signal: AbortSignal; done: () => void } {
  const controller = new AbortController();
  const stop = () => controller.abort();
  if (parent.aborted) controller.abort();
  else parent.addEventListener("abort", stop, { once: true });
  const timer = setTimeout(stop, Math.max(0, ms));
  return {
    signal: controller.signal,
    done: () => {
      clearTimeout(timer);
      parent.removeEventListener("abort", stop);
    },
  };
}

/** "0:42": the time a generation has run. */
export function elapsedLabel(ms: number): string {
  const seconds = Math.max(0, Math.floor(ms / 1000));
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}
