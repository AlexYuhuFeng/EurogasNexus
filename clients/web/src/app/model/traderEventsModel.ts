/**
 * Desk → Board's "what just happened" list (the pure part, tested in tests/traderBoard.test.ts).
 *
 * One list, newest first, made from what the product already holds, with no store of its own:
 * - REMIT urgent market messages as the outage read serves them (`GET /api/physical/outages`,
 *   grouped by event: GIE IIP, ENTSOG TP and imported files), planned and unplanned;
 * - news items from the registered public sources (`GET /api/news`), less any item that is the
 *   same REMIT event again (`linked_event_key`).
 * Each line names the hubs of the desk's five it bears on, says whether it touches the desk's
 * own book, and keeps its source for the title. Licensed headline feeds (agencies, price
 * reporters) are never read here: the list names them as an empty slot the desk connects with
 * its own subscription (rule 18).
 */
import type { NewsItemDTO, NewsSourceDTO, OutageEventDTO } from "../../api/client.ts";
import type { BoardSelection } from "./traderDetailModel.ts";
import { BOARD_HUBS } from "./traderBoardModel.ts";

/** Balancing zones and countries as the five hubs. Norwegian supply lands at all four NWE hubs. */
const ZONE_HUBS: Readonly<Record<string, readonly string[]>> = {
  NBP: ["NBP"], GB: ["NBP"], UK: ["NBP"],
  TTF: ["TTF"], NL: ["TTF"], GTS: ["TTF"],
  THE: ["THE"], DE: ["THE"], GASPOOL: ["THE"], NCG: ["THE"], GPL: ["THE"],
  ZTP: ["ZTP"], BE: ["ZTP"], ZEE: ["ZTP"], FLUXYS: ["ZTP"],
  PVB: ["PVB"], ES: ["PVB"], ENAGAS: ["PVB"],
  NO: ["NBP", "TTF", "THE", "ZTP"], NORWAY: ["NBP", "TTF", "THE", "ZTP"],
  // Balancing-zone and trading-point EIC codes REMIT messages give.
  "21YNL----TTF---1": ["TTF"], "37Y005053MH0000R": ["THE"], "37Z005053MH0000D": ["THE"],
  "21YGB-UKGASGRIDW": ["NBP"], "21Y0000000001278": ["PEG"], "21Z000000000248J": ["ZTP"],
  "21Y---A001A003-5": ["ETF"],
};

/** The desk's hubs an outage zone or a news item's hubs and countries bear on (board order). */
export function hubsFor(codes: readonly (string | null | undefined)[]): string[] {
  const out = new Set<string>();
  for (const code of codes) {
    const key = String(code ?? "").trim().toUpperCase();
    for (const hub of ZONE_HUBS[key] ?? []) out.add(hub);
  }
  return BOARD_HUBS.filter((hub) => out.has(hub));
}

export type EventKind = "unplanned" | "planned" | "news";

export interface BoardEvent {
  key: string;
  /** When it was published (else when it starts). */
  at: string;
  kind: EventKind;
  /** The facility or the headline. */
  what: string;
  /** Capacity removed, in the hub's unit (GB mcm/d, the continent GWh/d), negative. */
  size: { value: number; unit: string } | null;
  /** When the outage ends, when known. */
  until: string | null;
  hubs: string[];
  /** The desk's book holds a position at one of its hubs, or the news item matched the book. */
  touchesBook: boolean;
  source: string;
  simulated: boolean;
  /** What the chart panel shows for it: the hub's day-ahead around the event. */
  select: BoardSelection | null;
}

function isUnplanned(outage: OutageEventDTO): boolean {
  return /unplan|forced|unscheduled/i.test(outage.event_type ?? "");
}

/** The fields of an outage the native-size rule needs. */
export interface OutageSizeFields {
  balancing_zone?: string | null;
  capacity_impact_mcm_d?: number | null;
  unavailable_mcm_d?: number | null;
  unavailable_gwh_d?: number | null;
}

/**
 * Capacity removed in the hub's native unit (SMALL_DESK_PLAN section 9): Great Britain in
 * mcm/d, the continent in GWh/d. One rule for the events list, the fundamentals panel and the
 * situation strip, so one outage reads the same on every surface. Null when the message has
 * no figure in that unit; another unit's figure is never substituted.
 */
export function outageNativeSize(
  outage: OutageSizeFields,
  hubs: readonly string[] = hubsFor([outage.balancing_zone]),
): { value: number; unit: "mcm/d" | "GWh/d" } | null {
  const gb = hubs.length === 1 && hubs[0] === "NBP";
  const value = gb
    ? outage.capacity_impact_mcm_d ?? outage.unavailable_mcm_d ?? null
    : outage.unavailable_gwh_d ?? null;
  return value === null ? null : { value, unit: gb ? "mcm/d" : "GWh/d" };
}

/**
 * The list, newest first. `bookHubs` are the hubs where the desk holds a position (from the
 * position ladder): an outage there touches the book.
 */
export function boardEvents(
  outages: readonly OutageEventDTO[],
  news: readonly NewsItemDTO[],
  bookHubs: ReadonlySet<string>,
): BoardEvent[] {
  const events: BoardEvent[] = [];
  const outageKeys = new Set<string>();
  for (const outage of outages) {
    if (/ended|cancel|inactive/i.test(outage.status ?? "")) continue;
    outageKeys.add(outage.event_id);
    const hubs = hubsFor([outage.balancing_zone]);
    const size = outageNativeSize(outage, hubs);
    events.push({
      key: `outage:${outage.event_id}`,
      at: outage.published_at_utc ?? outage.start_utc,
      kind: isUnplanned(outage) ? "unplanned" : "planned",
      what: outage.facility_name,
      size: size === null ? null : { value: -Math.abs(size.value), unit: size.unit },
      until: outage.end_utc,
      hubs,
      touchesBook: hubs.some((hub) => bookHubs.has(hub)),
      source: outage.source_system ?? "REMIT",
      simulated: Boolean(outage.simulated),
      select: hubs[0] ? { kind: "price", contract: "DA", hub: hubs[0] } : null,
    });
  }
  for (const item of news) {
    if (item.linked_event_key && outageKeys.has(item.linked_event_key)) continue;
    const hubs = hubsFor([...item.hubs, ...item.countries]);
    events.push({
      key: `news:${item.item_id}`,
      at: item.published_at_utc ?? item.first_seen_at_utc ?? item.retrieved_at_utc ?? "",
      kind: "news",
      what: item.title,
      size: null,
      until: null,
      hubs,
      touchesBook: item.relevance.matches > 0 || hubs.some((hub) => bookHubs.has(hub)),
      source: item.publisher,
      simulated: false,
      select: hubs[0] ? { kind: "price", contract: "DA", hub: hubs[0] } : null,
    });
  }
  return events.sort((a, b) => b.at.localeCompare(a.at) || a.key.localeCompare(b.key));
}

/** How long a new unplanned event at one of the five hubs is treated as new (the alert cue). */
export const NEW_EVENT_MINUTES = 60;

/**
 * The alert rule: an unplanned event bearing on one of the desk's five hubs, published in the
 * last hour, gets the alert cue on the board (and the shell's strip carries it as for any
 * outage at a focus hub). Planned work and news never alarm.
 */
export function isAlertEvent(event: BoardEvent, nowMs: number): boolean {
  if (event.kind !== "unplanned" || event.hubs.length === 0) return false;
  const at = Date.parse(event.at);
  return Number.isFinite(at) && nowMs - at <= NEW_EVENT_MINUTES * 60_000 && at <= nowMs + 60_000;
}

/** The licensed headline services the registry names: an empty slot, never read. */
export function licensedSlot(sources: readonly NewsSourceDTO[] | null | undefined): { publishers: string } | null {
  const licensed = (sources ?? []).filter((source) => source.reuse === "licensed");
  if (licensed.length === 0) return null;
  return { publishers: licensed.map((source) => source.publisher).join(", ") };
}
