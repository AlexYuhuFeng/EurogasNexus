/**
 * Research → Reports: the form's state, the request it sends and the situation subject a
 * "Report" action carries in the URL (`?workspace=research&task=reports&subject=outage:<id>`).
 * Pure functions, so the request a form makes is tested without a browser.
 */
import type { ReportAudience, ReportKind, ReportRequestDTO } from "../../api/client.ts";

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
}

export function reportSubjectFromSearch(search: string): ReportSubject | null {
  const params = new URLSearchParams(search);
  if (params.get("workspace") !== "research" || params.get("task") !== "reports") return null;
  const raw = params.get("subject") ?? "";
  const [kind, ...rest] = raw.split(":");
  const id = rest.join(":");
  return (kind === "alert" || kind === "outage") && id ? { kind, id } : null;
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
  return body;
}
