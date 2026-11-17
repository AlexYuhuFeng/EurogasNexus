/**
 * The situation model behind the strip under the top bar (role-first redesign §5).
 *
 * The old "Breaking" bar showed every open alert to every user. The strip shows, per role, the
 * few things that need this person now, and otherwise one calm standing fact or nothing:
 *
 * - **Qualification per audience** (§5.2): the audience comes from the role composition
 *   (`app/experience/roleComposition.ts`). Data-source and ingestion state appear only for the
 *   platform audience (administrators and data operations).
 * - **Urgent window**: an item is urgent for `BREAKING_WINDOW_MS` (6 h) after it became true or
 *   materially changed; after that it is standing (the bell lists it, the strip does not).
 * - **Ranking** (§5.3): severity, then whether it touches the person's own book or mandate, then
 *   size against the threshold, then newest. At most `STRIP_LIST_LIMIT` are listed; the rest are
 *   counted.
 * - **Hide**: a per-user list of `id@signature`. An item comes back when its signature (size or
 *   status) changes. Hiding changes nothing about the alert itself.
 * - **Every item names its source** and is built from fields into a translated sentence; an item
 *   without a source is rejected. A simulated figure carries `simulated`.
 * - **Book-scoped items** (limits, credit) are dropped for a person who cannot read the book or
 *   who cannot see every book behind the item (the rule of `application/alert_scope.py`).
 * - **Nothing here places, amends or cancels an order, nominates or settles.** Booked trades are
 *   a read-only report of the ETRM import; nomination windows are information.
 *
 * Rows of §5.2 that need a backend read or alert not built yet (price moves, delivery shortfalls,
 * fundamentals surprises) are handled from typed signals (`SituationSignals`) so the strip shows
 * them the day the server sends them; until then the signals are empty.
 *
 * Pure functions only (`tests/breakingTicker.test.ts`).
 */
import type {
  CurrentUserDTO,
  DecisionCaseSummaryDTO,
  DeskTodayDTO,
  ExplainSubject,
  JobDTO,
  MonitoringAlertDTO,
  NominationWindowOccurrenceDTO,
  ScreenOrderObservationDTO,
  SupportReportDTO,
} from "../../api/client.ts";
import type { StripAudience } from "../experience/roleComposition.ts";
import type { WorkspacePageId } from "../../workspaceNavigation.ts";
import type { ReportSubject } from "./reportsModel.ts";

/* ------------------------------------------------------------------ inputs */

/** The fields of an outage event the strip reads (`/api/physical/outages?grouped=true`). */
export interface TickerOutage {
  event_id: string;
  facility_name: string;
  balancing_zone: string;
  event_type: string;
  status: string;
  start_utc: string;
  end_utc?: string | null;
  published_at_utc?: string | null;
  version?: number | null;
  unit: string;
  unavailable_capacity: number | null;
  technical_capacity?: number | null;
  unavailable_gwh_d?: number | null;
  source_system?: string;
  source_reference?: string;
}

/** A source as the strip needs it (`/api/sources`), for the platform audience only. */
export interface StripSource {
  source_id: string;
  source_system: string;
  /** The connectors page's group and status word (`connectorCard`). */
  attention: boolean;
  statusKey: string;
  last_failure_at_utc: string | null;
  /** When the scheduler runs it next (the analyst's "next data arrival"). */
  next_run_at_utc?: string | null;
}

/** Figures from the Today read (`/api/desk/today`) the strip uses. */
export interface StripTodayFacts {
  /** Hubs where the book has a position (the zone match for outages). */
  bookHubs: string[];
  limitCounts: { breach: number; watch: number } | null;
  /** Day P&L change summed over hubs, when every hub has one in the same unit. */
  dayPnl: { value: number; unit: string } | null;
  simulated: boolean;
}

/** G3: a DA or front-month move against the prior close at a hub (a `market/price_move` alert). */
export interface PriceMoveSignal {
  hub: string;
  product: "DA" | "FM";
  move_pct: number;
  price: number;
  unit: string;
  at_utc: string;
  source: string;
  simulated: boolean;
  /** The monitoring alert it came from (Acknowledge, Why, Report). */
  alert_id?: string | null;
}

/** G5: a contract delivering short of its nomination beyond tolerance. */
export interface DeliveryShortfallSignal {
  contract_id: string;
  contract_name: string;
  gas_day: string;
  shortfall_mwh: number;
  tolerance_pct: number;
  shortfall_pct: number;
  at_utc: string;
  source: string;
  book_ids: string[];
  simulated?: boolean;
  alert_id?: string | null;
}

/** Fundamentals rule: a daily series outside its band vs the 7-day average (a `fundamentals` alert). */
export interface FundamentalsSignal {
  series: "storage_change" | "supply_call" | "lng_sendout";
  value: number;
  unit: string;
  deviation_pct: number;
  /** The 7-day average it is compared with, when the server sends it. */
  average_7d?: number | null;
  hub: string | null;
  at_utc: string;
  source: string;
  simulated?: boolean;
  alert_id?: string | null;
}

export interface SituationSignals {
  priceMoves?: readonly PriceMoveSignal[];
  shortfalls?: readonly DeliveryShortfallSignal[];
  fundamentals?: readonly FundamentalsSignal[];
}

export interface SituationInputs extends SituationSignals {
  alerts: readonly MonitoringAlertDTO[];
  outages: readonly TickerOutage[] | null;
  cases: readonly DecisionCaseSummaryDTO[] | null;
  windows: readonly NominationWindowOccurrenceDTO[] | null;
  bookedTrades: readonly ScreenOrderObservationDTO[] | null;
  sources: readonly StripSource[] | null;
  today: StripTodayFacts | null;
  /** Platform audience: recent jobs and problem reports (`/api/jobs`, `/api/support/reports`). */
  jobs?: readonly JobDTO[] | null;
  reports?: readonly SupportReportDTO[] | null;
}

/** The person's own thresholds (personal preference, else organisation default). */
export interface StripThresholds {
  outageGwhD: number;
  outageSharePct: number;
  priceMovePct: number;
  /** Explicit focus hubs; empty: the book's hubs plus the context hub. */
  focusHubs: readonly string[];
  showQuietLine: boolean;
}

export const DEFAULT_STRIP_THRESHOLDS: StripThresholds = {
  outageGwhD: 50,
  outageSharePct: 50,
  priceMovePct: 5,
  focusHubs: [],
  showQuietLine: true,
};

export interface SituationPerson {
  name: string;
  principalId: string;
  permissions: readonly string[];
  dataScopes: readonly string[];
}

export interface SituationContext {
  audience: StripAudience;
  person: SituationPerson;
  thresholds: StripThresholds;
  contextHub: string | null;
  nowMs: number;
  /** `id@signature` entries the person hid. */
  hidden: ReadonlySet<string>;
}

/* ------------------------------------------------------------------ the item */

export type SituationKind =
  | "outage"
  | "limit"
  | "credit"
  | "price_move"
  | "delivery"
  | "deadline"
  | "decision"
  | "fundamentals"
  | "booked_trade"
  | "source"
  | "strategy"
  | "job"
  | "problem_report";

export type SituationSeverity = "critical" | "warning" | "info";

/** A translated sentence built from fields: the key and the values it is filled with. */
export interface Phrase {
  key: string;
  values: Record<string, string | number>;
}

/** Where the item continues: a page, its task and the object parameter. */
export interface SituationTarget {
  page: WorkspacePageId;
  task?: string;
  params?: Record<string, string>;
}

/** Which rule of §5.2 let the item through (tests and "why am I seeing this"). */
export type AudienceRule =
  | "outage_position"
  | "outage_focus_hub"
  | "outage_nw_europe"
  | "outage_book"
  | "outage_delivery_zone"
  | "own_mandate"
  | "credit_line"
  | "limit_breach"
  | "credit_watch"
  | "case_overdue"
  | "case_half_time"
  | "own_case_decided"
  | "price_move"
  | "fundamentals"
  | "strategy_alert"
  | "shortfall"
  | "window_closing"
  | "source_failing"
  | "source_alert"
  | "job_failed"
  | "problem_report";

export interface SituationItem {
  id: string;
  kind: SituationKind;
  severity: SituationSeverity;
  /** When the item stops being urgent (ISO); after that it is standing. */
  urgentUntil: string;
  headline: Phrase;
  magnitude: number | null;
  unit: string | null;
  /** The comparison that gives the number meaning ("563 GWh/d of 758"). */
  comparison: Phrase | null;
  affects: { hubs: string[]; zones: string[]; books: string[]; contracts: string[] };
  occurredAt: string;
  /** A named source; the evidence reference is kept for the Inspector. */
  source: { name: string; ref: string | null };
  target: SituationTarget;
  audience: AudienceRule;
  simulated: boolean;
  /** The monitoring alert behind it, for Acknowledge (offered only with the permission). */
  alertId: string | null;
  explain: { subject: ExplainSubject; id: string } | null;
  report: ReportSubject | null;
  /** Size and status: a change makes a hidden item come back. */
  signature: string;
  /** Touches the person's own book or mandate (ranking 2). */
  ownBook: boolean;
  /** Size against the threshold, ≥ 1 when it qualifies on size (ranking 3). */
  ratio: number;
}

export interface QuietLine {
  phrase: Phrase;
  target: SituationTarget | null;
  source: string;
}

export type StripState = "hidden" | "quiet" | "urgent";

export interface Situation {
  state: StripState;
  /** Ranked; at most `STRIP_LIST_LIMIT`. */
  items: SituationItem[];
  /** Qualifying items beyond the list. */
  more: number;
  quiet: QuietLine | null;
  /** Items dropped because they had no named source (should stay 0). */
  rejected: number;
}

/** How long an item stays urgent after it became true or materially changed. */
export const BREAKING_WINDOW_MS = 6 * 60 * 60 * 1000;
/** The expanded list holds at most this many; the rest are counted. */
export const STRIP_LIST_LIMIT = 7;
/** A nomination window counts as closing within this. */
export const WINDOW_CLOSING_MS = 60 * 60 * 1000;

/* ------------------------------------------------------------------ zones and hubs */

const HUB_CODES = ["TTF", "NBP", "THE", "PEG", "ZTP", "PSV", "CEGH", "PVB", "ETF", "GTF"];
const NW_EUROPE_HUBS = new Set(["TTF", "NBP", "THE", "PEG", "ZTP", "ETF", "GTF"]);
const ZONE_TOKEN_HUBS: Record<string, readonly string[]> = {
  NO: ["NBP", "TTF", "THE", "ZTP"],
  NORWAY: ["NBP", "TTF", "THE", "ZTP"],
  UK: ["NBP"],
  GB: ["NBP"],
  NL: ["TTF"],
  DE: ["THE"],
  GASPOOL: ["THE"],
  NCG: ["THE"],
  BE: ["ZTP"],
  FR: ["PEG"],
  TRF: ["PEG"],
  IT: ["PSV"],
  AT: ["CEGH"],
  VTP: ["CEGH"],
  ES: ["PVB"],
  DK: ["ETF"],
  // Balancing-zone and trading-point EIC codes REMIT messages give.
  "21YNL----TTF---1": ["TTF"],
  "37Y005053MH0000R": ["THE"],
  "37Z005053MH0000D": ["THE"],
  "21YGB-UKGASGRIDW": ["NBP"],
  "21Y0000000001278": ["PEG"],
  "21Z000000000248J": ["ZTP"],
  "21Y---A001A003-5": ["ETF"],
};

/** Hubs a REMIT balancing zone touches: by hub name, country code or EIC code. */
export function zoneHubs(zone: string | null | undefined): string[] {
  const tokens = String(zone ?? "").toUpperCase().split(/[\s,;/]+/).filter(Boolean);
  const hubs: string[] = [];
  for (const token of tokens) {
    const found = HUB_CODES.includes(token)
      ? [token]
      : (ZONE_TOKEN_HUBS[token] ?? ZONE_TOKEN_HUBS[token.split("-")[0]] ?? []);
    for (const hub of found) if (!hubs.includes(hub)) hubs.push(hub);
  }
  return hubs;
}

/* ------------------------------------------------------------------ helpers */

function at(value: string | null | undefined): number {
  const parsed = Date.parse(String(value ?? ""));
  return Number.isFinite(parsed) ? parsed : Number.NaN;
}

function iso(ms: number): string {
  return Number.isFinite(ms) ? new Date(ms).toISOString() : "";
}

function urgentUntil(becameTrueMs: number): string {
  return iso(becameTrueMs + BREAKING_WINDOW_MS);
}

function round(value: number): number {
  return Math.round(value);
}

/** The person's books: null when they see every book (or isolation leaves it to the server). */
export function personBooks(person: SituationPerson): Set<string> | null {
  const books = person.dataScopes
    .filter((scope) => scope.toUpperCase().startsWith("BOOKS:"))
    .map((scope) => scope.slice("BOOKS:".length).trim().toUpperCase());
  if (!books.length || books.includes("*")) return null;
  return new Set(books);
}

/** §5.5 / alert_scope.py: a book-scoped item is shown only to someone who sees every book behind it. */
export function bookScopeAllows(person: SituationPerson, books: readonly string[]): boolean {
  if (!person.permissions.includes("portfolio.read")) return false;
  const mine = personBooks(person);
  if (mine === null) return true;
  return books.length > 0 && books.every((book) => mine.has(book.toUpperCase()));
}

function evidence(alert: MonitoringAlertDTO): Record<string, unknown> {
  return (alert.evidence_snapshot ?? {}) as Record<string, unknown>;
}

function stringList(value: unknown): string[] {
  return Array.isArray(value) ? value.map(String).filter(Boolean) : [];
}

function sourceName(alert: MonitoringAlertDTO): string {
  return alert.source_refs?.[0] ?? "";
}

const NO_AFFECTS = () => ({ hubs: [] as string[], zones: [] as string[], books: [] as string[], contracts: [] as string[] });

/* ------------------------------------------------------------------ outages */

interface OutageFacts {
  item: TickerOutage;
  gwh: number | null;
  share: number | null;
  hubs: string[];
}

function outageFacts(outage: TickerOutage): OutageFacts {
  const gwh = outage.unavailable_gwh_d ?? null;
  const share =
    outage.technical_capacity && outage.unavailable_capacity != null
      ? outage.unavailable_capacity / outage.technical_capacity
      : null;
  return { item: outage, gwh, share, hubs: zoneHubs(outage.balancing_zone) };
}

/** The size test of §5.2: ≥ the GWh/d threshold or ≥ the share threshold. Returns the ratio, 0 when not. */
export function outageSizeRatio(outage: TickerOutage, thresholds: StripThresholds): number {
  const { gwh, share } = outageFacts(outage);
  const byVolume = gwh !== null && thresholds.outageGwhD > 0 ? gwh / thresholds.outageGwhD : 0;
  const byShare = share !== null && thresholds.outageSharePct > 0 ? (100 * share) / thresholds.outageSharePct : 0;
  const ratio = Math.max(byVolume, byShare);
  return ratio >= 1 ? ratio : 0;
}

function outageItem(
  facts: OutageFacts,
  rule: AudienceRule,
  ratio: number,
  ownBook: boolean,
  alert: MonitoringAlertDTO | null,
): SituationItem {
  const { item, gwh, share, hubs } = facts;
  const technicalGwh = gwh !== null && share ? gwh / share : null;
  const published = at(item.published_at_utc);
  const became = Math.max(at(item.start_utc), Number.isFinite(published) ? published : 0);
  return {
    id: `outage:${item.event_id}`,
    kind: "outage",
    severity: share !== null && share >= 0.5 ? "critical" : "warning",
    urgentUntil: urgentUntil(became),
    headline: {
      key: "strip.headline.outage",
      values: {
        asset: item.facility_name,
        zone: item.balancing_zone,
        size: gwh !== null ? `${round(gwh)} GWh/d` : item.unavailable_capacity != null ? `${item.unavailable_capacity} ${item.unit}` : "",
      },
    },
    magnitude: gwh,
    unit: gwh !== null ? "GWh/d" : item.unit,
    comparison:
      gwh !== null && technicalGwh !== null
        ? { key: "strip.comparison.of_capacity", values: { value: round(gwh), total: round(technicalGwh), unit: "GWh/d" } }
        : share !== null
          ? { key: "strip.comparison.share", values: { pct: round(100 * share) } }
          : null,
    affects: { hubs, zones: [item.balancing_zone], books: [], contracts: [] },
    occurredAt: iso(became),
    source: { name: "REMIT", ref: item.source_reference ?? alert?.source_refs?.[0] ?? `remit:${item.event_id}` },
    // Desk → Network, the Outages panel (its default tab) with this outage selected.
    target: { page: "market", task: "network", params: { outage: item.event_id } },
    audience: rule,
    // A fictional demo message is marked like the Network list marks it (`demo:` reference).
    simulated: item.source_system === "DEMO" || /^demo/i.test(item.source_reference ?? "") || Boolean(alert?.simulated),
    alertId: alert?.status === "open" ? alert.alert_id : null,
    explain: { subject: "outage", id: item.event_id },
    report: { kind: "outage", id: item.event_id },
    signature: `${item.status}|${gwh !== null ? round(gwh) : item.unavailable_capacity}|${item.version ?? ""}`,
    ownBook,
    ratio,
  };
}

/** An outage alert's evidence as an outage row, when the events read is not available. */
function outageFromAlert(alert: MonitoringAlertDTO): TickerOutage | null {
  const facts = evidence(alert);
  const eventId = String(facts.event_id ?? alert.entity_id ?? "");
  if (!eventId) return null;
  const number = (value: unknown) => (typeof value === "number" && Number.isFinite(value) ? value : null);
  return {
    event_id: eventId,
    facility_name: String(facts.facility_name ?? ""),
    balancing_zone: String(facts.balancing_zone ?? ""),
    event_type: String(facts.event_type ?? ""),
    status: String(facts.status ?? ""),
    start_utc: String(facts.start_utc ?? alert.event_time_utc ?? ""),
    end_utc: facts.end_utc ? String(facts.end_utc) : null,
    published_at_utc: facts.published_at_utc ? String(facts.published_at_utc) : null,
    version: number(facts.version),
    unit: String(facts.unit ?? ""),
    unavailable_capacity: number(facts.unavailable_capacity),
    technical_capacity: number(facts.technical_capacity),
    unavailable_gwh_d: number(facts.unavailable_gwh_d),
    source_reference: alert.source_refs?.[0],
  };
}

function qualifyOutages(inputs: SituationInputs, context: SituationContext, focus: Set<string>, bookHubs: Set<string>): SituationItem[] {
  const { audience, thresholds } = context;
  const alertsByEvent = new Map<string, MonitoringAlertDTO>();
  for (const alert of inputs.alerts) {
    if (alert.category === "physical" && alert.alert_type === "outage") alertsByEvent.set(alert.entity_id, alert);
  }
  const rows: TickerOutage[] = inputs.outages
    ? [...inputs.outages]
    : [...alertsByEvent.values()].map(outageFromAlert).filter((row): row is TickerOutage => row !== null);
  const items: SituationItem[] = [];
  for (const row of rows) {
    // News is an unplanned outage in force now; a planned one, however large, is a schedule.
    if (row.status !== "active" || !/unplanned/i.test(row.event_type)) continue;
    const ratio = outageSizeRatio(row, thresholds);
    if (!ratio) continue;
    const facts = outageFacts(row);
    const inBook = facts.hubs.some((hub) => bookHubs.has(hub));
    const atFocus = facts.hubs.some((hub) => focus.has(hub));
    let rule: AudienceRule | null = null;
    if (audience === "trader") rule = inBook ? "outage_position" : atFocus ? "outage_focus_hub" : null;
    else if (audience === "desk_head") rule = inBook ? "outage_book" : null;
    else if (audience === "operations") rule = inBook ? "outage_delivery_zone" : null;
    else if (audience === "analyst") rule = facts.hubs.some((hub) => NW_EUROPE_HUBS.has(hub)) ? "outage_nw_europe" : null;
    if (!rule) continue;
    items.push(outageItem(facts, rule, ratio, inBook, alertsByEvent.get(row.event_id) ?? null));
  }
  return items;
}

/* ------------------------------------------------------------------ limits and credit */

function limitItem(alert: MonitoringAlertDTO, rule: AudienceRule, ownBook: boolean, becameMs: number): SituationItem {
  const facts = evidence(alert);
  const credit = alert.alert_type === "credit";
  const name = String((credit ? facts.counterparty : facts.name || facts.trader) ?? "");
  const status = String(facts.status ?? alert.severity);
  const used = typeof facts.utilisation_pct === "number" ? (facts.utilisation_pct as number) : null;
  const books = stringList(facts.book_ids);
  const id = credit ? String(facts.counterparty_id ?? alert.entity_id) : String(facts.mandate_id ?? alert.entity_id);
  return {
    id: `${credit ? "credit" : "mandate"}:${id}`,
    kind: credit ? "credit" : "limit",
    severity: alert.severity,
    urgentUntil: urgentUntil(becameMs),
    headline: {
      key: `strip.headline.${credit ? "credit" : "mandate"}.${["breach", "watch", "expired", "incomplete"].includes(status) ? status : "other"}`,
      values: { name: name || alert.entity_id, used: used !== null ? `${round(used)}%` : "" },
    },
    magnitude: used,
    unit: used !== null ? "%" : null,
    comparison: used !== null ? { key: "strip.comparison.used", values: { pct: round(used) } } : null,
    affects: { hubs: stringList(facts.hubs), zones: [], books, contracts: [] },
    occurredAt: iso(becameMs),
    // The register the figure comes from; the alert's own reference stays for the Inspector.
    source: { name: sourceName(alert) ? (credit ? "credit-line" : "mandate") : "", ref: sourceName(alert) },
    target: { page: "contracts", task: "exposure" },
    audience: rule,
    simulated: Boolean(alert.simulated),
    alertId: alert.status === "open" ? alert.alert_id : null,
    explain: { subject: credit ? "credit" : "mandate", id },
    report: { kind: "alert", id: alert.alert_id },
    signature: `${status}|${used !== null ? Math.floor(used / 5) * 5 : ""}`,
    ownBook,
    ratio: used !== null ? used / 100 : 1,
  };
}

function qualifyLimits(inputs: SituationInputs, context: SituationContext): SituationItem[] {
  const { audience, person } = context;
  const items: SituationItem[] = [];
  const books = personBooks(person);
  for (const alert of inputs.alerts) {
    if (alert.status !== "open" || alert.category !== "limits") continue;
    const facts = evidence(alert);
    const itemBooks = stringList(facts.book_ids);
    if (!bookScopeAllows(person, itemBooks)) continue;
    const detected = at(alert.detected_at_utc);
    const became = Number.isFinite(detected) ? detected : at(alert.updated_at_utc);
    const status = String(facts.status ?? "");
    const breach = alert.severity === "critical";
    const ownMandate =
      alert.alert_type === "mandate" &&
      [person.name, person.principalId].some((who) => who && String(facts.trader ?? "").toLowerCase() === who.toLowerCase());
    const touchesBook = books === null ? true : itemBooks.some((book) => books.has(book.toUpperCase()));
    let rule: AudienceRule | null = null;
    if (audience === "trader") {
      if (breach && ownMandate) rule = "own_mandate";
      else if (breach && alert.alert_type === "credit" && touchesBook) rule = "credit_line";
    } else if (audience === "risk") {
      if (breach) rule = "limit_breach";
      else if (alert.alert_type === "credit" && status === "watch") rule = "credit_watch";
    } else if (audience === "desk_head") {
      if (breach) rule = "limit_breach";
    }
    if (!rule) continue;
    items.push(limitItem(alert, rule, ownMandate || (books !== null && touchesBook), became));
  }
  return items;
}

/* ------------------------------------------------------------------ decision cases */

const OPEN_CASE = new Set(["DRAFT", "OPEN", "UNDER_REVIEW", "REOPENED"]);

function caseItem(row: DecisionCaseSummaryDTO, rule: AudienceRule, becameMs: number, headline: Phrase, severity: SituationSeverity): SituationItem {
  return {
    id: `case:${row.case_id}`,
    kind: "decision",
    severity,
    urgentUntil: urgentUntil(becameMs),
    headline,
    magnitude: null,
    unit: null,
    comparison: null,
    affects: { ...NO_AFFECTS(), hubs: row.hub_id ? [row.hub_id] : [] },
    occurredAt: iso(becameMs),
    source: { name: "decision-case", ref: row.case_id },
    target: { page: "scenario", task: "review", params: { case: row.case_id } },
    audience: rule,
    simulated: false,
    alertId: null,
    explain: null,
    report: null,
    signature: `${row.status}|${row.last_record?.outcome ?? ""}|${row.record_count}`,
    ownBook: false,
    ratio: 1,
  };
}

function isMine(row: DecisionCaseSummaryDTO, person: SituationPerson): boolean {
  const opener = String(row.created_by ?? "").toLowerCase();
  return Boolean(opener) && [person.name, person.principalId].some((who) => who && who.toLowerCase() === opener);
}

function isWaiting(row: DecisionCaseSummaryDTO): boolean {
  return OPEN_CASE.has(row.status) && (!row.last_record || row.status === "REOPENED");
}

function qualifyCases(inputs: SituationInputs, context: SituationContext): SituationItem[] {
  const { audience, person, nowMs } = context;
  const items: SituationItem[] = [];
  for (const row of inputs.cases ?? []) {
    const objective = row.objective.length > 60 ? `${row.objective.slice(0, 59)}…` : row.objective;
    const due = at(row.decision_due_at_utc);
    const waiting = isWaiting(row);
    if (audience === "originator" && isMine(row, person) && row.last_record) {
      const outcome = row.last_record.outcome.toLowerCase();
      items.push(caseItem(row, "own_case_decided", at(row.last_record.recorded_at_utc),
        { key: `strip.headline.case_decided.${["accept", "reject", "reopen", "attention"].find((word) => outcome.includes(word)) ?? "other"}`, values: { objective } },
        outcome.includes("reject") || outcome.includes("attention") ? "warning" : "info"));
    }
    if (audience === "risk" && waiting && Number.isFinite(due) && due < nowMs) {
      items.push(caseItem(row, "case_overdue", due, { key: "strip.headline.case_overdue", values: { objective } }, "warning"));
    }
    if (audience === "desk_head" && waiting && Number.isFinite(due)) {
      const created = at(row.created_at_utc);
      if (!Number.isFinite(created) || due <= created) continue;
      const half = created + (due - created) / 2;
      if (nowMs >= half) {
        items.push(caseItem(row, "case_half_time", half, { key: "strip.headline.case_waiting", values: { objective } }, due < nowMs ? "warning" : "info"));
      }
    }
  }
  return items;
}

/* ------------------------------------------------------------------ alerts by category */

function qualifyCategoryAlerts(inputs: SituationInputs, context: SituationContext, sourceSystems: Set<string>): SituationItem[] {
  const { audience } = context;
  const items: SituationItem[] = [];
  for (const alert of inputs.alerts) {
    if (alert.status !== "open") continue;
    const detected = at(alert.detected_at_utc);
    const became = Number.isFinite(detected) ? detected : at(alert.updated_at_utc);
    let rule: AudienceRule | null = null;
    let kind: SituationKind = "strategy";
    // Pipeline state is for the platform audience only (§5.5).
    if (alert.category === "data_source") {
      if (audience !== "platform" || sourceSystems.has(alert.entity_id.toLowerCase())) continue;
      rule = "source_alert";
      kind = "source";
    } else if (alert.category === "strategy" && audience === "analyst") {
      rule = "strategy_alert";
    }
    if (!rule) continue;
    items.push({
      id: `alert:${alert.alert_id}`,
      kind,
      severity: alert.severity,
      urgentUntil: urgentUntil(became),
      headline: kind === "source"
        ? { key: "strip.headline.source_failing", values: { source: alert.entity_id } }
        : { key: "strip.headline.strategy", values: { run: alert.entity_id } },
      magnitude: null,
      unit: null,
      comparison: null,
      affects: NO_AFFECTS(),
      occurredAt: iso(became),
      source: { name: sourceName(alert), ref: alert.alert_id },
      target: kind === "source" ? { page: "sources", params: { view: "attention" } } : { page: "strategy", task: "shadow" },
      audience: rule,
      simulated: Boolean(alert.simulated),
      alertId: alert.alert_id,
      explain: { subject: "alert", id: alert.alert_id },
      report: { kind: "alert", id: alert.alert_id },
      signature: `${alert.severity}|${alert.occurrence_count}`,
      ownBook: false,
      ratio: 1,
    });
  }
  return items;
}

/* ------------------------------------------------------------------ sources (platform) */

const HELD_BACK = new Set(["connectors.status.not_approved", "connectors.status.approved_waiting_for_key"]);

function qualifySources(inputs: SituationInputs, context: SituationContext): SituationItem[] {
  if (context.audience !== "platform") return [];
  const items: SituationItem[] = [];
  for (const source of inputs.sources ?? []) {
    // Failing, or held back by the approval gate (a run was refused): news when it last failed.
    const held = HELD_BACK.has(source.statusKey);
    if (!source.attention || (source.statusKey !== "connectors.status.failing" && !held)) continue;
    const failed = at(source.last_failure_at_utc);
    if (!Number.isFinite(failed)) continue;
    items.push({
      id: `source:${source.source_id}`,
      kind: "source",
      severity: "warning",
      urgentUntil: urgentUntil(failed),
      headline: { key: held ? "strip.headline.source_held_back" : "strip.headline.source_failing", values: { source: source.source_system } },
      magnitude: null,
      unit: null,
      comparison: null,
      affects: NO_AFFECTS(),
      occurredAt: iso(failed),
      source: { name: source.source_system, ref: source.source_id },
      target: { page: "sources", params: { view: "attention", source: source.source_id } },
      audience: "source_failing",
      simulated: false,
      alertId: null,
      explain: null,
      report: null,
      signature: `${source.statusKey}|${source.last_failure_at_utc}`,
      ownBook: false,
      ratio: 1,
    });
  }
  return items;
}

/* ------------------------------------------------------------------ nomination windows */

function windowClose(window: NominationWindowOccurrenceDTO, nowMs: number): number | null {
  for (const value of [window.closes_at_utc, window.next_closes_at_utc]) {
    const close = at(value);
    if (Number.isFinite(close) && close > nowMs) return close;
  }
  return null;
}

function nextWindow(windows: readonly NominationWindowOccurrenceDTO[] | null, nowMs: number) {
  let best: { window: NominationWindowOccurrenceDTO; close: number } | null = null;
  for (const window of windows ?? []) {
    const close = windowClose(window, nowMs);
    if (close !== null && (!best || close < best.close)) best = { window, close };
  }
  return best;
}

function windowTarget(person: SituationPerson): SituationTarget {
  // The planning task needs scenario work; a read-only role reads the deadlines on Delivery.
  return person.permissions.includes("scenario.create") ? { page: "scenario", task: "nomination" } : { page: "contracts", task: "delivery" };
}

function minutesUntil(ms: number): number {
  return Math.max(1, Math.round(ms / 60_000));
}

function qualifyWindows(inputs: SituationInputs, context: SituationContext): SituationItem[] {
  if (context.audience !== "operations") return [];
  const items: SituationItem[] = [];
  for (const window of inputs.windows ?? []) {
    const close = windowClose(window, context.nowMs);
    if (close === null || close - context.nowMs > WINDOW_CLOSING_MS) continue;
    items.push({
      id: `window:${window.window_id}`,
      kind: "deadline",
      severity: "info",
      // Information only: it stops being news when the window closes.
      urgentUntil: iso(close),
      headline: { key: "strip.headline.window_closing", values: { window: window.name, close: iso(close) } },
      magnitude: minutesUntil(close - context.nowMs),
      unit: "min",
      comparison: null,
      affects: { ...NO_AFFECTS(), zones: [window.country] },
      occurredAt: iso(close - WINDOW_CLOSING_MS),
      source: { name: window.source_system ?? "nomination-window", ref: window.window_id },
      target: windowTarget(context.person),
      audience: "window_closing",
      simulated: false,
      alertId: null,
      explain: null,
      report: null,
      signature: iso(close),
      ownBook: false,
      ratio: 1,
    });
  }
  return items;
}

/* ------------------------------------------------------------------ signals awaiting a backend */

function qualifySignals(inputs: SituationInputs, context: SituationContext, focus: Set<string>): SituationItem[] {
  const { audience, thresholds, person } = context;
  const items: SituationItem[] = [];
  if (audience === "trader") {
    for (const move of inputs.priceMoves ?? []) {
      if (!focus.has(move.hub) || Math.abs(move.move_pct) < thresholds.priceMovePct) continue;
      const became = at(move.at_utc);
      items.push({
        id: `price:${move.hub}:${move.product}`,
        kind: "price_move",
        severity: "warning",
        urgentUntil: urgentUntil(became),
        headline: { key: "strip.headline.price_move", values: { hub: move.hub, product: move.product, move: `${move.move_pct > 0 ? "+" : ""}${move.move_pct.toFixed(1)}%` } },
        magnitude: move.price,
        unit: move.unit,
        comparison: { key: "strip.comparison.vs_close", values: { pct: move.move_pct.toFixed(1) } },
        affects: { ...NO_AFFECTS(), hubs: [move.hub] },
        occurredAt: iso(became),
        source: { name: move.source, ref: move.alert_id ?? null },
        target: { page: "market", task: "curves" },
        audience: "price_move",
        simulated: move.simulated,
        alertId: move.alert_id ?? null,
        explain: move.alert_id ? { subject: "alert", id: move.alert_id } : null,
        report: move.alert_id ? { kind: "alert", id: move.alert_id } : null,
        signature: `${Math.trunc(move.move_pct)}`,
        ownBook: false,
        ratio: Math.abs(move.move_pct) / thresholds.priceMovePct,
      });
    }
  }
  if (audience === "operations") {
    for (const gap of inputs.shortfalls ?? []) {
      if (gap.shortfall_pct <= gap.tolerance_pct || !bookScopeAllows(person, gap.book_ids)) continue;
      const became = at(gap.at_utc);
      items.push({
        id: `shortfall:${gap.contract_id}:${gap.gas_day}`,
        kind: "delivery",
        severity: "warning",
        urgentUntil: urgentUntil(became),
        headline: { key: "strip.headline.shortfall", values: { contract: gap.contract_name, mwh: round(gap.shortfall_mwh) } },
        magnitude: gap.shortfall_mwh,
        unit: "MWh",
        comparison: { key: "strip.comparison.tolerance", values: { pct: gap.shortfall_pct.toFixed(1), tolerance: gap.tolerance_pct.toFixed(1) } },
        affects: { ...NO_AFFECTS(), books: gap.book_ids, contracts: [gap.contract_id] },
        occurredAt: iso(became),
        source: { name: gap.source, ref: gap.contract_id },
        target: { page: "contracts", task: "delivery", params: { contract: gap.contract_id } },
        audience: "shortfall",
        simulated: Boolean(gap.simulated),
        alertId: gap.alert_id ?? null,
        explain: gap.alert_id ? { subject: "alert", id: gap.alert_id } : null,
        report: gap.alert_id ? { kind: "alert", id: gap.alert_id } : null,
        signature: `${round(gap.shortfall_mwh)}`,
        ownBook: true,
        ratio: gap.shortfall_pct / Math.max(gap.tolerance_pct, 0.1),
      });
    }
  }
  if (audience === "analyst") {
    for (const surprise of inputs.fundamentals ?? []) {
      const became = at(surprise.at_utc);
      items.push({
        id: `fundamentals:${surprise.series}`,
        kind: "fundamentals",
        severity: "warning",
        urgentUntil: urgentUntil(became),
        headline: { key: `strip.headline.fundamentals.${surprise.series}`, values: { value: surprise.value, unit: surprise.unit } },
        magnitude: surprise.value,
        unit: surprise.unit,
        comparison: surprise.average_7d != null
          ? { key: "strip.comparison.vs_7d_average", values: { average: surprise.average_7d.toFixed(2), unit: surprise.unit } }
          : { key: "strip.comparison.vs_7d", values: { pct: surprise.deviation_pct.toFixed(1) } },
        affects: { ...NO_AFFECTS(), hubs: surprise.hub ? [surprise.hub] : [] },
        occurredAt: iso(became),
        source: { name: surprise.source, ref: null },
        target: { page: "market", task: "overview" },
        audience: "fundamentals",
        simulated: Boolean(surprise.simulated),
        alertId: surprise.alert_id ?? null,
        explain: surprise.alert_id ? { subject: "alert", id: surprise.alert_id } : null,
        report: surprise.alert_id ? { kind: "alert", id: surprise.alert_id } : null,
        signature: `${Math.trunc(surprise.deviation_pct)}`,
        ownBook: false,
        ratio: 1,
      });
    }
  }
  return items;
}

/* ------------------------------------------------------------------ signals from the server's alerts */

function num(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

/**
 * The open alerts behind the rows that needed a backend rule: price moves (G3), delivery
 * shortfalls (G5) and fundamentals surprises. Each keeps its alert id (Acknowledge, Why, Report)
 * and the source the server named; one without a usable figure is left out.
 */
export function signalsFromAlerts(alerts: readonly MonitoringAlertDTO[]): Required<SituationSignals> {
  const out: Required<SituationSignals> = { priceMoves: [], shortfalls: [], fundamentals: [] };
  for (const alert of alerts) {
    if (alert.status !== "open") continue;
    const facts = evidence(alert);
    const at = alert.detected_at_utc || alert.updated_at_utc;
    if (alert.category === "market" && alert.alert_type === "price_move") {
      const move = num(facts.move_pct);
      const price = num(facts.price);
      const product = facts.product === "DA" ? "DA" : facts.product === "FM" ? "FM" : null;
      if (move === null || price === null || !product || !facts.hub) continue;
      out.priceMoves = [...out.priceMoves, {
        hub: String(facts.hub), product, move_pct: move, price, unit: String(facts.unit ?? ""),
        at_utc: at, source: String(facts.source_system ?? ""), simulated: Boolean(alert.simulated),
        alert_id: alert.alert_id,
      }];
    } else if (alert.category === "delivery" && alert.alert_type === "shortfall") {
      const mwh = num(facts.shortfall_mwh);
      const pct = num(facts.shortfall_pct);
      const tolerance = num(facts.tolerance_pct);
      if (mwh === null || pct === null || tolerance === null) continue;
      out.shortfalls = [...out.shortfalls, {
        contract_id: String(facts.contract_id ?? ""), contract_name: String(facts.contract_name ?? facts.contract_id ?? ""),
        gas_day: String(facts.gas_day ?? ""), shortfall_mwh: mwh, tolerance_pct: tolerance, shortfall_pct: pct,
        at_utc: at, source: String(facts.source_system ?? sourceName(alert)), book_ids: stringList(facts.book_ids),
        simulated: Boolean(alert.simulated), alert_id: alert.alert_id,
      }];
    } else if (alert.category === "fundamentals") {
      const value = num(facts.value);
      const deviation = num(facts.deviation_pct);
      const series = facts.series;
      if (value === null || deviation === null || (series !== "storage_change" && series !== "lng_sendout" && series !== "supply_call")) continue;
      out.fundamentals = [...out.fundamentals, {
        series, value, unit: String(facts.unit ?? ""), deviation_pct: deviation, average_7d: num(facts.average_7d), hub: null, at_utc: at,
        source: String(facts.source_system ?? ""), simulated: Boolean(alert.simulated), alert_id: alert.alert_id,
      }];
    }
  }
  return out;
}

/* ------------------------------------------------------------------ jobs and problem reports (platform) */

function qualifyPlatformWork(inputs: SituationInputs, context: SituationContext): SituationItem[] {
  if (context.audience !== "platform") return [];
  const items: SituationItem[] = [];
  for (const job of inputs.jobs ?? []) {
    if (job.status !== "FAILED") continue;
    const failed = at(job.finished_at_utc ?? job.started_at_utc ?? job.created_at_utc);
    if (!Number.isFinite(failed)) continue;
    items.push({
      id: `job:${job.job_id}`,
      kind: "job",
      severity: "warning",
      urgentUntil: urgentUntil(failed),
      headline: { key: `strip.headline.job_failed.${job.kind}`, values: {} },
      magnitude: null,
      unit: null,
      comparison: null,
      affects: NO_AFFECTS(),
      occurredAt: iso(failed),
      source: { name: "jobs", ref: job.job_id },
      target: { page: "runtime", params: { view: "delivery" } },
      audience: "job_failed",
      simulated: false,
      alertId: null,
      explain: null,
      report: null,
      signature: `${job.status}|${job.finished_at_utc ?? ""}`,
      ownBook: false,
      ratio: 1,
    });
  }
  for (const report of inputs.reports ?? []) {
    if (report.status !== "open") continue;
    const filed = at(report.created_at_utc);
    if (!Number.isFinite(filed)) continue;
    items.push({
      id: `report:${report.report_id}`,
      kind: "problem_report",
      severity: report.severity === "P1" ? "critical" : report.severity === "P2" ? "warning" : "info",
      urgentUntil: urgentUntil(filed),
      headline: {
        key: "strip.headline.problem_report",
        values: { severity: report.severity, summary: report.summary.length > 60 ? `${report.summary.slice(0, 59)}…` : report.summary },
      },
      magnitude: null,
      unit: null,
      comparison: null,
      affects: NO_AFFECTS(),
      occurredAt: iso(filed),
      source: { name: "support", ref: report.report_id },
      target: { page: "runtime", params: { view: "support" } },
      audience: "problem_report",
      simulated: false,
      alertId: null,
      explain: null,
      report: null,
      signature: `${report.status}|${report.severity}`,
      ownBook: false,
      ratio: 1,
    });
  }
  return items;
}

/* ------------------------------------------------------------------ quiet lines */

function startOfLocalDay(nowMs: number): number {
  const day = new Date(nowMs);
  day.setHours(0, 0, 0, 0);
  return day.getTime();
}

function quietLine(inputs: SituationInputs, context: SituationContext): QuietLine | null {
  const { audience, nowMs, person } = context;
  const window = (): QuietLine | null => {
    const next = nextWindow(inputs.windows, nowMs);
    return next
      ? {
          phrase: { key: "strip.quiet.next_window", values: { window: next.window.name, close: iso(next.close) } },
          target: windowTarget(person),
          source: next.window.source_system ?? "nomination-window",
        }
      : null;
  };
  if (audience === "trader") {
    // D2: booked today from the ETRM import, read-only. With no booking time held the import
    // cannot say which trades are today's, so it says how many trades it holds.
    const trades = (inputs.bookedTrades ?? []).filter((row) => row.source_system === "ETRM");
    if (trades.length) {
      const timed = trades.filter((row) => row.observed_at_utc !== row.delivery_start_utc);
      if (!timed.length) {
        return { phrase: { key: "strip.quiet.booked_count", values: { count: trades.length } }, target: { page: "contracts", task: "exposure" }, source: "ETRM" };
      }
      const today = timed.filter((row) => at(row.observed_at_utc) >= startOfLocalDay(nowMs));
      const booked: QuietLine = { phrase: { key: "strip.quiet.booked_today", values: { count: today.length } }, target: { page: "contracts", task: "exposure" }, source: "ETRM" };
      // Trades booked today first; with none, the next window, else "none booked today".
      return today.length ? booked : (window() ?? booked);
    }
    return window();
  }
  if (audience === "operations") return window();
  if (audience === "risk") {
    const counts = inputs.today?.limitCounts ?? null;
    if (!counts && inputs.cases === null) return null;
    const waiting = (inputs.cases ?? []).filter(isWaiting).length;
    return {
      phrase: { key: "strip.quiet.risk_counts", values: { breach: counts?.breach ?? 0, watch: counts?.watch ?? 0, waiting } },
      target: { page: "contracts", task: "exposure" },
      source: "limits",
    };
  }
  if (audience === "originator") {
    const mine = (inputs.cases ?? []).filter((row) => isMine(row, person) && isWaiting(row));
    if (!mine.length) return null;
    const dues = mine.map((row) => at(row.decision_due_at_utc)).filter((value) => Number.isFinite(value) && value > nowMs);
    return {
      phrase: dues.length
        ? { key: "strip.quiet.cases_waiting_due", values: { count: mine.length, due: iso(Math.min(...dues)) } }
        : { key: "strip.quiet.cases_waiting", values: { count: mine.length } },
      target: { page: "scenario", task: "review" },
      source: "decision-case",
    };
  }
  if (audience === "compliance") {
    if (inputs.cases === null) return null;
    const week = nowMs - 7 * 24 * 3600 * 1000;
    const decided = inputs.cases.filter((row) => row.last_record && at(row.last_record.recorded_at_utc) >= week).length;
    return { phrase: { key: "strip.quiet.decided_week", values: { count: decided } }, target: { page: "scenario", task: "review" }, source: "decision-case" };
  }
  if (audience === "desk_head") {
    const today = inputs.today;
    if (!today || (!today.dayPnl && !today.limitCounts)) return null;
    return {
      phrase: today.dayPnl
        ? { key: "strip.quiet.desk_head", values: { pnl: `${today.dayPnl.value >= 0 ? "+" : "−"}${Math.abs(round(today.dayPnl.value)).toLocaleString("en-GB")} ${today.dayPnl.unit}`, breach: today.limitCounts?.breach ?? 0 } }
        : { key: "strip.quiet.breaches", values: { breach: today.limitCounts?.breach ?? 0 } },
      target: { page: "market", task: "overview" },
      source: "desk-today",
    };
  }
  if (audience === "platform") {
    if (inputs.sources === null) return null;
    const count = inputs.sources.filter((source) => source.attention).length;
    if (!count) return null;
    return { phrase: { key: "strip.quiet.sources_attention", values: { count } }, target: { page: "sources", params: { view: "attention" } }, source: "sources" };
  }
  if (audience === "analyst") {
    // The next scheduled data arrival, from the source registry's schedule.
    let next: StripSource | null = null;
    for (const source of inputs.sources ?? []) {
      const run = at(source.next_run_at_utc);
      if (!Number.isFinite(run) || run <= nowMs) continue;
      if (!next || run < at(next.next_run_at_utc)) next = source;
    }
    return next
      ? { phrase: { key: "strip.quiet.next_data", values: { source: next.source_system, close: String(next.next_run_at_utc) } }, target: null, source: next.source_system }
      : null;
  }
  // Finance has no strip.
  return null;
}

/* ------------------------------------------------------------------ assembly */

const RANK = { critical: 0, warning: 1, info: 2 } as const;

/** §5.3 ranking: severity, own book or mandate, size against the threshold, newest. */
export function rankItems(items: readonly SituationItem[]): SituationItem[] {
  return [...items].sort(
    (a, b) =>
      RANK[a.severity] - RANK[b.severity] ||
      Number(b.ownBook) - Number(a.ownBook) ||
      b.ratio - a.ratio ||
      at(b.occurredAt) - at(a.occurredAt) ||
      a.id.localeCompare(b.id),
  );
}

/** §5.5: an item without a named source never reaches the strip. */
export function hasNamedSource(item: SituationItem): boolean {
  return Boolean(item.source?.name?.trim());
}

export function hideKey(item: Pick<SituationItem, "id" | "signature">): string {
  return `${item.id}@${item.signature}`;
}

/** The hubs the person follows: explicit focus hubs, else the book's hubs plus the context hub. */
export function focusHubs(thresholds: StripThresholds, bookHubs: readonly string[], contextHub: string | null): Set<string> {
  if (thresholds.focusHubs.length) return new Set(thresholds.focusHubs.map((hub) => hub.toUpperCase()));
  const hubs = new Set(bookHubs.map((hub) => hub.toUpperCase()));
  if (contextHub) hubs.add(contextHub.toUpperCase());
  return hubs;
}

/** The signals given directly (tests, a future read) plus those the open alerts carry. */
function withAlertSignals(inputs: SituationInputs): SituationInputs {
  const fromAlerts = signalsFromAlerts(inputs.alerts);
  return {
    ...inputs,
    priceMoves: [...(inputs.priceMoves ?? []), ...fromAlerts.priceMoves],
    shortfalls: [...(inputs.shortfalls ?? []), ...fromAlerts.shortfalls],
    fundamentals: [...(inputs.fundamentals ?? []), ...fromAlerts.fundamentals],
  };
}

/** Every item that qualifies for the audience, before the urgent window and the hide list. */
export function qualifyingItems(inputs: SituationInputs, context: SituationContext): { items: SituationItem[]; rejected: number } {
  if (context.audience === "finance") return { items: [], rejected: 0 };
  const bookHubs = new Set((inputs.today?.bookHubs ?? []).map((hub) => hub.toUpperCase()));
  const focus = focusHubs(context.thresholds, [...bookHubs], context.contextHub);
  const sourceSystems = new Set((inputs.sources ?? []).map((source) => source.source_system.toLowerCase()));
  const all = [
    ...qualifyOutages(inputs, context, focus, bookHubs),
    ...qualifyLimits(inputs, context),
    ...qualifyCases(inputs, context),
    ...qualifyCategoryAlerts(inputs, context, sourceSystems),
    ...qualifySources(inputs, context),
    ...qualifyPlatformWork(inputs, context),
    ...qualifyWindows(inputs, context),
    ...qualifySignals(withAlertSignals(inputs), context, focus),
  ];
  const accepted = all.filter(hasNamedSource);
  return { items: accepted, rejected: all.length - accepted.length };
}

/** The strip's state for one person now. */
export function buildSituation(inputs: SituationInputs, context: SituationContext): Situation {
  const { items, rejected } = qualifyingItems(inputs, context);
  const urgent = rankItems(
    items.filter((item) => at(item.urgentUntil) > context.nowMs && !context.hidden.has(hideKey(item))),
  );
  const quiet = context.thresholds.showQuietLine ? quietLine(inputs, context) : null;
  return {
    state: urgent.length ? "urgent" : quiet ? "quiet" : "hidden",
    items: urgent.slice(0, STRIP_LIST_LIMIT),
    more: Math.max(0, urgent.length - STRIP_LIST_LIMIT),
    quiet,
    rejected,
  };
}

/** Hide entries that still name a current item (an entry for a changed or gone item is dropped). */
export function pruneHidden(hidden: readonly string[], items: readonly SituationItem[]): string[] {
  const live = new Set(items.map(hideKey));
  return hidden.filter((entry) => live.has(entry));
}

/** The URL search a target opens (page, task, object parameter). */
export function targetSearch(target: SituationTarget): string {
  const params = new URLSearchParams();
  params.set("workspace", target.page);
  if (target.task) params.set("task", target.task);
  for (const [key, value] of Object.entries(target.params ?? {})) params.set(key, value);
  return params.toString();
}

/* ------------------------------------------------------------------ adapters */

/** The Today read's figures the strip uses (book hubs, limit counts, the day's P&L change). */
export function todayFacts(today: DeskTodayDTO): StripTodayFacts {
  const [keyFigures, , book] = today.rows;
  const hubs = (book?.hubs ?? []).filter(
    (row) => (row.position_today?.value ?? 0) !== 0 || (row.position_front_month?.value ?? 0) !== 0 || row.net_open_mwh !== 0,
  );
  const counts = keyFigures?.tightest_limit?.counts;
  const pnl = hubs.map((row) => row.day_pnl_change).filter((figure): figure is Extract<typeof figure, { value: number | null }> => "value" in figure);
  const units = new Set(pnl.map((figure) => figure.unit));
  const dayPnl =
    pnl.length && pnl.length === hubs.length && units.size === 1 && pnl.every((figure) => typeof figure.value === "number")
      ? { value: pnl.reduce((sum, figure) => sum + (figure.value ?? 0), 0), unit: [...units][0] }
      : null;
  return {
    bookHubs: hubs.map((row) => row.hub.toUpperCase()),
    limitCounts: counts ? { breach: counts.breach, watch: counts.watch } : null,
    dayPnl,
    simulated: Boolean(today.simulated),
  };
}

const ROLE_RANK: Record<string, number> = { VIEWER: 0, REVIEWER: 1, ANALYST: 2, OPERATOR: 3, ADMIN: 4 };

/**
 * Whether the person may acknowledge an alert: the governed write's own rule (ANALYST floor,
 * inside the commercial-data boundary; `security/permissions.py`). Offered only then (D5); the
 * server decides regardless.
 */
export function canAcknowledgeAlerts(user: CurrentUserDTO | null | undefined): boolean {
  if (!user) return false;
  const commercial = user.experience ? user.experience.commercial_capabilities.length > 0 : (user.roles ?? [user.role]).some((role) => role !== "ADMIN");
  if (!commercial) return false;
  const roles = user.roles?.length ? user.roles : [user.role];
  return roles.some((role) => (ROLE_RANK[String(role).toUpperCase()] ?? -1) >= ROLE_RANK.ANALYST);
}
