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

export type OpportunityBucket = "must_act" | "could_act" | "watching" | "blocked";

export const LANES: readonly OpportunityBucket[] = ["must_act", "could_act"];
export const GROUPS: readonly OpportunityBucket[] = ["watching", "blocked"];

/** The rows of one bucket, as the server ordered them. */
export function bucketRows(list: OpportunityListDTO | null, bucket: OpportunityBucket): OpportunityRowDTO[] {
  if (!list) return [];
  const holder = bucket === "must_act" || bucket === "could_act" ? list.lanes[bucket] : list.groups[bucket];
  return holder?.items ?? [];
}

/** The count of a bucket (more than are shown when a lane is capped). */
export function bucketTotal(list: OpportunityListDTO | null, bucket: OpportunityBucket): number {
  if (!list) return 0;
  const holder = bucket === "must_act" || bucket === "could_act" ? list.lanes[bucket] : list.groups[bucket];
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
  if (bucket === "could_act") return row.rank ? String(row.rank.position) : "";
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
      stateKey: readiness.prices.ready ? "opportunities.ready.prices.state" : "opportunities.ready.prices.none",
      values: { sources, marks: readiness.prices.firm_marks },
      fix: readiness.prices.ready ? null : "enter_marks",
    },
    {
      key: "published_costs",
      ready: readiness.published_costs.ready,
      stateKey: "opportunities.ready.costs.state",
      values: {
        tariffs: readiness.published_costs.transport_tariffs,
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

/** A period as the desk writes it: "2026-11" → "Nov-26"; anything else unchanged. */
export function periodLabel(period: string | null | undefined): string {
  const month = /^(\d{4})-(\d{2})$/.exec(period ?? "");
  if (month) return `${MONTHS[Number(month[2]) - 1]}-${month[1].slice(2)}`;
  // A gas day, or a run of days from one ("2026-11-19+3d"): "19 Nov", "19 Nov, 3 d".
  const day = /^(\d{4})-(\d{2})-(\d{2})(?:\+(\d+)d)?$/.exec(period ?? "");
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
export function rowTitle(row: OpportunityRowDTO): { key: string; values: Record<string, string | number> } {
  const count = memberCount(row);
  const total = row.group?.total_volume
    ? formatEnergy(row.group.total_volume)
    : row.volume
      ? formatEnergy(row.volume)
      : "";
  return {
    key: `opportunities.title.${row.type}${count > 1 ? ".many" : ""}`,
    values: { subject: row.subject || row.claim, count, total, period: periodLabel(row.period) },
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
export function dueOf(row: OpportunityRowDTO, now: Date): { key: string; values: Record<string, string | number> } | null {
  const members = groupMembers(row);
  const times = members
    .map((member) => ({ member, at: Date.parse(member.deadline_utc ?? member.expires_at_utc) }))
    .filter((item) => Number.isFinite(item.at))
    .sort((a, b) => a.at - b.at);
  const upcoming = times.find((item) => item.at > now.getTime());
  const passed = times.find((item) => item.at <= now.getTime());
  if (passed && passed.member.period_start && Date.parse(passed.member.period_start) <= now.getTime()) {
    return { key: "opportunities.under_way", values: { period: periodLabel(passed.member.period) } };
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
