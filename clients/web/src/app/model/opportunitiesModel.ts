/**
 * Deals → Opportunities (CP-14): pure helpers over `GET /api/opportunities` and
 * `GET /api/opportunities/{id}`. The server evaluates, ranks, classes and phrases every
 * opportunity; the client only formats the figures it was given (decimal text, in the unit the
 * server named), orders nothing of its own and grants nothing. A simulated figure is always
 * marked; the page never offers an order, a nomination or an instruction.
 */
import type {
  OpportunityDetailDTO,
  OpportunityGroupMemberDTO,
  OpportunityLegDTO,
  OpportunityListDTO,
  OpportunityMeasureDTO,
  OpportunityReadinessDTO,
  OpportunityRowDTO,
} from "@/api/client";

/* ------------------------------------------------------------------ figures */

function num(text: string | null | undefined): number | null {
  if (text === null || text === undefined || text === "") return null;
  const value = Number(text);
  return Number.isFinite(value) ? value : null;
}

/** Decimals for a figure in its unit: energy quantities whole, money whole, prices to three. */
function decimalsFor(unit: string, magnitude: number): number {
  const upper = unit.toUpperCase();
  if (/^(MWH|GWH|KWH|TH|THERM|MWH\/D|GWH\/D|KWH\/H\/D|MWH\/H|M3|MCM)$/.test(upper)) return 0;
  if (upper === "%" || upper === "PERCENT") return 1;
  if (/\//.test(upper)) return magnitude !== 0 && magnitude < 0.01 ? 4 : 3;
  return 0;
}

/** "1,234,567" with the given decimals, en-GB grouping (desk convention). */
function grouped(value: number, decimals: number): string {
  const text = Math.abs(value).toLocaleString("en-GB", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
  // Rounding can turn a tiny negative into zero: never show "-0".
  const negative = value < 0 && Number(text.replace(/,/g, "")) !== 0;
  return `${negative ? "−" : ""}${text}`;
}

/** A price or quantity in its native unit: "+0.230 EUR/MWh", "−24,000 MWh". */
export function formatMeasure(
  measure: { value: string | null; unit: string } | null | undefined,
  { signed = false }: { signed?: boolean } = {},
): string {
  const value = num(measure?.value);
  if (measure === null || measure === undefined || value === null) return "–";
  const text = grouped(value, decimalsFor(measure.unit, Math.abs(value)));
  // Only a price or margin per unit carries a sign; a quantity is a size, never "+".
  const sign = signed && value > 0 && measure.unit.includes("/") ? "+" : "";
  return `${sign}${text} ${measure.unit}`.trim();
}

/** Money in a compact desk form: "EUR 71k", "EUR 1.25m", "EUR 783". */
export function formatValue(value: { amount: string | null; currency: string } | null | undefined): string {
  const amount = num(value?.amount);
  if (!value || amount === null) return "–";
  const magnitude = Math.abs(amount);
  const sign = amount < 0 ? "−" : "";
  if (magnitude >= 1_000_000) return `${value.currency} ${sign}${(magnitude / 1_000_000).toFixed(2)}m`;
  if (magnitude >= 10_000) return `${value.currency} ${sign}${Math.round(magnitude / 1_000)}k`;
  return `${value.currency} ${sign}${grouped(magnitude, 0)}`;
}

/** A leg's figure: its contribution, else its subtotal, else its quantity. */
export function legFigure(leg: OpportunityLegDTO): string {
  const measure: OpportunityMeasureDTO | null = leg.contribution ?? leg.subtotal ?? leg.quantity ?? null;
  if (!measure) return "–";
  if (leg.kind === "value" && measure.currency) {
    return formatValue({ amount: measure.value, currency: measure.unit || measure.currency });
  }
  return formatMeasure(measure, { signed: leg.kind === "term" });
}

/** Rows that close a block of the arithmetic (a subtotal or the result) are drawn as totals. */
export function legIsTotal(leg: OpportunityLegDTO): boolean {
  return leg.kind === "subtotal" || leg.kind === "result" || leg.kind === "value";
}

/* ------------------------------------------------------------------ time */

const DAY_MS = 86_400_000;

/** "expires in 9 d", "expires in 5 h", "expired". */
export function timeLeft(iso: string | null | undefined, now: Date): { key: string; count: number } | null {
  if (!iso) return null;
  const at = Date.parse(iso);
  if (!Number.isFinite(at)) return null;
  const left = at - now.getTime();
  if (left <= 0) return { key: "opportunities.time.passed", count: 0 };
  if (left >= DAY_MS) return { key: "opportunities.time.days", count: Math.floor(left / DAY_MS) };
  return { key: "opportunities.time.hours", count: Math.max(1, Math.floor(left / 3_600_000)) };
}

/* ------------------------------------------------------------------ list */

export type OpportunityBucket = "must_act" | "could_act" | "market" | "watching" | "blocked";

/** Must act, could act, then the market lane ("in the market, not on your book"). */
export const LANES: readonly OpportunityBucket[] = ["must_act", "could_act", "market"];
export const GROUPS: readonly OpportunityBucket[] = ["watching", "blocked"];

/** The rows of one bucket, as the server ordered them. */
export function bucketRows(list: OpportunityListDTO | null, bucket: OpportunityBucket): OpportunityRowDTO[] {
  if (!list) return [];
  const holder = bucket === "must_act" || bucket === "could_act" || bucket === "market" ? list.lanes[bucket] : list.groups[bucket];
  return holder?.items ?? [];
}

/** The count of a bucket (more than are shown when a lane is capped). */
export function bucketTotal(list: OpportunityListDTO | null, bucket: OpportunityBucket): number {
  if (!list) return 0;
  const holder = bucket === "must_act" || bucket === "could_act" || bucket === "market" ? list.lanes[bucket] : list.groups[bucket];
  return holder?.total ?? 0;
}

/** Whether anything at all is listed (any lane or group). */
export function hasAnyOpportunity(list: OpportunityListDTO | null): boolean {
  return [...LANES, ...GROUPS].some((bucket) => bucketTotal(list, bucket) > 0);
}

/**
 * The quality marker beside a row: "simulated" on the demo desk, otherwise the weakest input
 * class when it is weaker than sourced (a firm's mark, indicative, an assumption). Sourced and
 * derived rows carry no marker.
 */
export function qualityMarker(row: Pick<OpportunityRowDTO, "simulated" | "quality">): string | null {
  if (row.simulated) return "simulated";
  const klass = row.quality?.class ?? "";
  return klass && klass !== "sourced" && klass !== "derived" ? klass : null;
}

/** The status tone of a marker (design-system badge). */
export function markerTone(marker: string | null): "simulated" | "watch" | "info" | null {
  if (!marker) return null;
  if (marker === "simulated") return "simulated";
  if (marker === "assumption" || marker === "missing") return "watch";
  return "info";
}

/** The leading cell of a row: "!" in the must-act lane, the rank in could-act, nothing elsewhere. */
export function rowLead(row: OpportunityRowDTO, bucket: OpportunityBucket): string {
  if (bucket === "must_act") return "!";
  if (bucket === "could_act" || bucket === "market") return row.rank ? String(row.rank.position) : "";
  return "";
}

/* ------------------------------------------------------------------ readiness */

export interface ReadinessLine {
  key: "book" | "prices" | "published_costs";
  ready: boolean;
  /** Translation key and values for the state shown beside the line. */
  stateKey: string;
  values: Record<string, number | string>;
  /** The one control that fixes it, when it is missing. */
  fix: "add_contract" | "enter_marks" | "connect_feed" | null;
}

/** The three things the engine needs (B.7), each with its state and its fix. */
export function readinessLines(readiness: OpportunityReadinessDTO | null | undefined): ReadinessLine[] {
  if (!readiness) return [];
  const simulated = readiness.prices.simulated_sources?.length ?? 0;
  const sources = readiness.prices.licensed_quote_sources.length + readiness.prices.settlement_sources.length;
  return [
    {
      key: "book",
      ready: readiness.book.ready,
      stateKey: "opportunities.ready.book.state",
      values: { contracts: readiness.book.contracts, bands: readiness.book.approved_hedge_bands },
      fix: readiness.book.ready ? null : "add_contract",
    },
    {
      key: "prices",
      ready: readiness.prices.ready,
      stateKey: !readiness.prices.ready
        ? "opportunities.ready.prices.none"
        : sources === 0 && readiness.prices.firm_marks === 0 && simulated > 0
          ? "opportunities.ready.prices.simulated"
          : "opportunities.ready.prices.state",
      values: { sources, marks: readiness.prices.firm_marks, simulated },
      fix: readiness.prices.ready ? null : "enter_marks",
    },
    {
      key: "published_costs",
      ready: readiness.published_costs.ready,
      stateKey:
        readiness.published_costs.transport_tariffs === 0 &&
        (readiness.published_costs.simulated_transport_tariffs ?? 0) > 0
          ? "opportunities.ready.costs.simulated"
          : "opportunities.ready.costs.state",
      values: {
        tariffs: readiness.published_costs.transport_tariffs,
        simulated: readiness.published_costs.simulated_transport_tariffs ?? 0,
        terminals: readiness.published_costs.terminal_terms,
      },
      fix: null,
    },
  ];
}

/** "What it needs" shows only when something is missing (H.1). */
export function showReadiness(list: OpportunityListDTO | null): boolean {
  return readinessLines(list?.readiness).some((line) => !line.ready);
}

/** The page's empty state: why it is empty, in one key. */
export function emptyReason(list: OpportunityListDTO | null): string {
  if (!list) return "opportunities.empty.loading";
  if (!list.evaluation) {
    return showReadiness(list) ? "opportunities.empty.day_one" : "opportunities.empty.not_evaluated";
  }
  if (list.confirming > 0) return "opportunities.empty.confirming";
  if (list.hidden_by_you > 0) return "opportunities.empty.hidden";
  return "opportunities.empty.nothing";
}

/* ------------------------------------------------------------------ detail */

export type CheckTone = "ok" | "breach" | "watch";

export function checkTone(result: string): CheckTone {
  if (result === "pass") return "ok";
  if (result === "fail") return "breach";
  return "watch";
}

/** Dismissal reasons the server accepts (counted per type to tune the thresholds). */
export const DISMISS_REASONS = [
  "not_executable",
  "already_covered",
  "margin_too_thin",
  "data_wrong",
  "outside_mandate",
  "not_relevant",
  "other",
] as const;

/** Whether the single primary action (Open as a case) is offered. */
export function canOpenCase(detail: OpportunityDetailDTO | null): boolean {
  return Boolean(detail?.next_steps?.includes("open_as_case"));
}

/** Whether the caller has dismissed this opportunity (and it has not changed since). */
export function isDismissed(row: Pick<OpportunityRowDTO, "user_state">): boolean {
  const state = row.user_state as { state?: string; changed_since?: boolean } | null;
  return state?.state === "dismissed" && !state.changed_since;
}

/** Whether the caller follows this opportunity. */
export function isWatched(row: Pick<OpportunityRowDTO, "user_state">): boolean {
  const state = row.user_state as { state?: string } | null;
  return state?.state === "watching";
}

/* ------------------------------------------------------------------ address */

/** The opportunity named in a URL (`opportunity=`), or null. */
export function opportunityFromLocation(search: string): string | null {
  const value = new URLSearchParams(search).get("opportunity");
  return value && /^[A-Za-z0-9_.:-]{1,80}$/.test(value) ? value : null;
}

/** The URL search with the open opportunity set (or cleared), other context kept. */
export function withOpportunity(search: string, opportunityId: string | null): string {
  const next = new URLSearchParams(search);
  if (opportunityId) next.set("opportunity", opportunityId);
  else next.delete("opportunity");
  return next.toString();
}

/* ------------------------------------------------------------------ one item per subject */

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/**
 * A period as the desk writes it: "2026-11" → "Nov-26" (the screen's product name in either
 * language); a gas day or a run of days from one ("2026-11-19+3d") → "19 Nov", "19 Nov, 3 d",
 * in Chinese "11月19日", "11月19日，3 天".
 */
export function periodLabel(period: string | null | undefined, language = "en"): string {
  const month = /^(\d{4})-(\d{2})$/.exec(period ?? "");
  if (month) return `${MONTHS[Number(month[2]) - 1]}-${month[1].slice(2)}`;
  const day = /^(\d{4})-(\d{2})-(\d{2})(?:\+(\d+)d)?$/.exec(period ?? "");
  if (day && language.toLowerCase().startsWith("zh")) {
    return `${Number(day[2])}月${Number(day[3])}日${day[4] ? `，${day[4]} 天` : ""}`;
  }
  if (day) return `${Number(day[3])} ${MONTHS[Number(day[2]) - 1]}${day[4] ? `, ${day[4]} d` : ""}`;
  return period ?? "";
}

/** An energy quantity at a readable scale: "1.12 TWh", "187,200 MWh". */
export function formatEnergy(measure: { value: string | null; unit: string } | null | undefined): string {
  const value = num(measure?.value);
  if (!measure || value === null) return "–";
  if (measure.unit === "MWh" && Math.abs(value) >= 1_000_000) {
    return `${grouped(value / 1_000_000, 2)} TWh`;
  }
  return formatMeasure(measure);
}

/** How many months (members) the item stands for. */
export function memberCount(row: Pick<OpportunityRowDTO, "group">): number {
  return row.group?.count ?? 1;
}

/** The title of a row: type, subject, and for several months their count and total. */
export function rowTitle(row: OpportunityRowDTO, language = "en"): { key: string; values: Record<string, string | number> } {
  const count = memberCount(row);
  const total = row.group?.total_volume
    ? formatEnergy(row.group.total_volume)
    : row.volume
      ? formatEnergy(row.volume)
      : "";
  return {
    key: `opportunities.title.${row.type}${count > 1 ? ".many" : ""}`,
    values: { subject: row.subject || row.claim, count, total, period: periodLabel(row.period, language) },
  };
}

/** The row's figure: the subject's total value when the months share a currency, else the
 * lead's headline (a hedge gap: its total volume). */
export function rowFigure(row: OpportunityRowDTO): string {
  if (row.type === "hedge_gap") return formatEnergy(row.group?.total_volume ?? row.volume);
  if (row.group?.total_value) return formatValue(row.group.total_value);
  return formatValue(row.value) !== "–" ? formatValue(row.value) : formatMeasure(row.headline, { signed: true });
}

/** The months of an item, largest first (the server's order). */
export function groupMembers(row: OpportunityRowDTO): OpportunityGroupMemberDTO[] {
  if (row.group?.members?.length) return row.group.members;
  return [
    {
      opportunity_id: row.opportunity_id,
      period: row.period,
      period_start: row.period_start,
      headline: row.headline,
      value: row.value,
      volume: row.volume,
      state: row.state,
      deadline_utc: row.deadline_utc,
      expires_at_utc: row.expires_at_utc,
    },
  ];
}

/**
 * When the item is due, said truthfully: the earliest deadline (or expiry) of its months; a
 * deadline that has passed while the delivery month is under way says so, never "past due".
 */
export function dueOf(row: OpportunityRowDTO, now: Date, language = "en"): { key: string; values: Record<string, string | number> } | null {
  const members = groupMembers(row);
  const times = members
    .map((member) => ({ member, at: Date.parse(member.deadline_utc ?? member.expires_at_utc) }))
    .filter((item) => Number.isFinite(item.at))
    .sort((a, b) => a.at - b.at);
  const upcoming = times.find((item) => item.at > now.getTime());
  const passed = times.find((item) => item.at <= now.getTime());
  if (passed && passed.member.period_start && Date.parse(passed.member.period_start) <= now.getTime()) {
    return { key: "opportunities.under_way", values: { period: periodLabel(passed.member.period, language) } };
  }
  if (!upcoming) return passed ? { key: row.deadline_utc ? "opportunities.overdue" : "opportunities.lapsed", values: {} } : null;
  const left = timeLeft(new Date(upcoming.at).toISOString(), now);
  if (!left) return null;
  return {
    key: upcoming.member.deadline_utc ? "opportunities.due" : "opportunities.expires",
    values: { whenKey: left.key, count: left.count },
  };
}

/** The evaluation line: when it last ran and what started it; what is pending next. */
export function evaluationLine(list: OpportunityListDTO | null): { trigger: string | null; pending: string[] } {
  const evaluation = list?.evaluation;
  const next = evaluation && typeof evaluation.next === "object" ? evaluation.next : null;
  return { trigger: evaluation?.trigger ?? null, pending: next?.pending_inputs ?? [] };
}

/* ------------------------------------------------------------------ live (M7) */

/**
 * One notice on the opportunity stream (`/api/stream/opportunities`): an opportunity that opened
 * or was withdrawn (expired, converted, blocked, fell to watch), or an evaluation that finished.
 * It carries no figure; the page re-reads its list.
 */
export interface OpportunityStreamNotice {
  event: "opportunity" | "evaluated";
  opportunityId: string | null;
  status: "open" | "withdrawn" | null;
  reason: string | null;
  at: string | null;
}

/** With the stream open, a safety re-read; with it down, the poll. */
export const OPPORTUNITY_REFRESH_MS = 5 * 60_000;
export const OPPORTUNITY_FALLBACK_MS = 60_000;
/** Notices that arrive together (an evaluation and the changes it made) cause one read. */
export const OPPORTUNITY_NOTICE_COALESCE_MS = 800;

/** A stream payload as a notice, or null for anything else. */
export function readOpportunityNotice(payload: unknown): OpportunityStreamNotice | null {
  if (!payload || typeof payload !== "object") return null;
  const item = payload as Record<string, unknown>;
  const text = (key: string) => (typeof item[key] === "string" ? (item[key] as string) : null);
  if (item.event === "evaluated") {
    return { event: "evaluated", opportunityId: null, status: null, reason: null, at: text("as_of_utc") ?? text("changed_at") };
  }
  if (item.event !== "opportunity") return null;
  const status = item.status === "open" || item.status === "withdrawn" ? item.status : null;
  if (!text("opportunity_id") || !status) return null;
  return {
    event: "opportunity",
    opportunityId: text("opportunity_id"),
    status,
    reason: text("reason"),
    at: text("changed_at_utc") ?? text("changed_at"),
  };
}

/** "12 s", "4 min", "3 h", "2 d": how long ago, for the freshness line. */
export function ageText(asOf: string | null | undefined, now: Date): string | null {
  if (!asOf) return null;
  const ms = now.getTime() - new Date(asOf).getTime();
  if (!Number.isFinite(ms)) return null;
  const seconds = Math.max(0, Math.round(ms / 1000));
  if (seconds < 60) return `${seconds} s`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)} min`;
  if (seconds < 86_400) return `${Math.floor(seconds / 3600)} h`;
  return `${Math.floor(seconds / 86_400)} d`;
}

/**
 * The page's freshness line: whether changes arrive as they happen (`live`), or by the one-minute
 * poll while the stream is down (`polling`), and how old the evaluation behind the list is.
 */
export function freshness(
  asOf: string | null | undefined,
  live: boolean,
  now: Date,
): { mode: "live" | "polling"; age: string | null } {
  return { mode: live ? "live" : "polling", age: ageText(asOf, now) };
}

/** The opportunities withdrawn since the list was last read, newest first, one per id. */
export function recentWithdrawals(notices: OpportunityStreamNotice[]): OpportunityStreamNotice[] {
  const seen = new Set<string>();
  const out: OpportunityStreamNotice[] = [];
  for (const notice of [...notices].reverse()) {
    if (notice.status !== "withdrawn" || !notice.opportunityId || seen.has(notice.opportunityId)) continue;
    seen.add(notice.opportunityId);
    out.push(notice);
  }
  return out;
}

/* ------------------------------------------------------------------ server words (CP-14 i18n) */

type Words = (key: string, options?: Record<string, unknown>) => string;

/** The engine's blocker sentences (server `claims.CLAIM_TEMPLATES["blocked.*"]`), English. */
const BLOCKED_TEMPLATES: Readonly<Record<string, string>> = {
  tariff_not_held: "Cannot evaluate: tariff not held at {subject}.",
  price_missing: "Cannot evaluate: no price or firm's mark held for {subject}.",
  input_missing: "Cannot evaluate: {subject} not held.",
  input_stale: "Cannot evaluate: {subject} is stale ({detail}).",
  check_failed: "Cannot evaluate: {subject} check failed ({detail}).",
  path_unproven: "Cannot evaluate: no proven path for {subject}.",
  evaluator: "Cannot evaluate: {subject}.",
};

/** The fixes the engine names (server `controls.py`), English → key. */
const BLOCKED_FIXES: Readonly<Record<string, string>> = {
  "load the operator's tariff for the gas year (entsog-tariffs source)": "tariff",
  "connect a licensed price feed or enter the firm's mark": "price",
  "supply the input": "input",
  "refresh it": "refresh",
  "load the ECB reference rates and the overnight benchmark fixings": "fx",
};

function fillTemplate(template: string, values: Record<string, string>): string {
  return template.replace(/\{(\w+)\}/g, (_match, name: string) => values[name] ?? "");
}

/** An assumption catalogue key ("balancing.long_discount") as the desk names it. */
export function assumptionLabel(key: string, t: Words): string {
  return t(`assumption.label.${key}`, { defaultValue: key.replace(/[._]/g, " ") });
}

/** A dotted catalogue key, never shown bare. */
const CATALOGUE_KEY = /^[a-z]+(?:\.[a-z_]+)+$/;

/**
 * What a blocker or an item is about, in words: a catalogue key reads as its label, a benchmark
 * fixing and a position side are translated; a name (a contract, a point, a hub) stays as given.
 */
export function subjectWords(subject: string, t: Words): string {
  const text = subject.trim();
  if (CATALOGUE_KEY.test(text)) return assumptionLabel(text, t);
  const forPeriod = /^(.+) for ([A-Z][a-z]{2}-\d{2}|\d{1,2} [A-Z][a-z]{2}(?:, \d+ d)?)$/.exec(text);
  if (forPeriod) return t("opportunities.subject.for_period", { subject: subjectWords(forPeriod[1], t), period: forPeriod[2] });
  const fixing = /^([A-Z€][A-Za-z€]*) fixing of (\d{4}-\d{2}-\d{2})$/.exec(text);
  if (fixing) return t("opportunities.subject.fixing", { name: fixing[1], date: fixing[2] });
  return text
    .split(" · ")
    .map((part) => (part === "long" || part === "short" ? t(`opportunities.side.${part}`) : part))
    .join(" · ");
}

/** A blocker's detail ("ESTR fixing of 2026-11-24: as of 2026-11-24") in words. */
export function blockerDetailWords(detail: string, t: Words): string {
  const at = /^(.*): (as of|priced on gas day|published) (\d{4}-\d{2}-\d{2})$/.exec(detail.trim());
  if (!at) return detail;
  const how = at[2] === "as of" ? "as_of" : at[2] === "published" ? "published" : "priced_on";
  return t(`opportunities.blocked.detail.${how}`, { subject: subjectWords(at[1], t), date: at[3] });
}

/**
 * Why an opportunity cannot be evaluated, in the reader's language: from the blocker's code,
 * subject and detail (the server's English sentence is the fallback, and the `title`). A
 * sentence the engine did not build from its template reads as a generic line in Chinese.
 */
export function blockerText(
  blocked: { code: string; subject: string; text: string; fix?: string; detail?: string } | null | undefined,
  t: Words,
  language: string,
): { text: string; fix: string } {
  if (!blocked) return { text: "", fix: "" };
  const template = BLOCKED_TEMPLATES[blocked.code];
  // An older server sends no detail: it is the bracket of the stale or failed sentence.
  const detail = blocked.detail ?? /\(([^()]*(?:\([^()]*\))?[^()]*)\)\.$/.exec(blocked.text)?.[1] ?? "";
  const fixKey = blocked.fix ? BLOCKED_FIXES[blocked.fix] : undefined;
  const fix = blocked.fix ? (fixKey ? t(`opportunities.blocked.fix.${fixKey}`) : language.startsWith("zh") ? "" : blocked.fix) : "";
  if (template && fillTemplate(template, { subject: blocked.subject, detail }) === blocked.text) {
    return {
      text: t(`opportunities.blocked.${blocked.code}`, {
        subject: subjectWords(blocked.subject, t),
        detail: blockerDetailWords(detail, t),
      }),
      fix,
    };
  }
  return { text: language.startsWith("zh") ? t("opportunities.blocked.other") : blocked.text, fix };
}
