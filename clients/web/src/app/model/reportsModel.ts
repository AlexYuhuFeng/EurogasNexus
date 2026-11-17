/**
 * Research → Reports: the form's state, the request it sends and the situation subject a
 * "Report" action carries in the URL (`?workspace=research&task=reports&subject=outage:<id>`).
 * Pure functions, so the request a form makes is tested without a browser.
 */
import type { ReportAudience, ReportKind, ReportRequestDTO, ReportSummaryDTO } from "../../api/client.ts";

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
