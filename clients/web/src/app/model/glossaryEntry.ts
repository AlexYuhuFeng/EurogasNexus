/**
 * One glossary entry for a trader: what a term means and, when the term names something on the
 * market (a hub, a trading venue, a price assessment, a system point), what it stands at.
 *
 * A concept (bid, gas day, firm capacity) is a definition and nothing more: no figures and no
 * date choice, because neither would change what it means. An entity gets its figures, each with
 * its source and the time it was read, and one gas-day choice; with no gas day chosen the figures
 * are the latest held. A hub's prices are the board's own rows (`hubPrices`, the read the map's
 * hub card shows), so the entry and the map never disagree.
 *
 * Links: `?workspace=glossary&term=<term>` opens an entry (term, alias or id, any case), and
 * `?workspace=market&task=network&place=<node id>` opens the map on the object (a hub's node, a
 * terminal's or storage site's node, a point).
 */

import type { GlossaryContextDTO, NodeDTO, NormalizedMarketObsDTO } from "../../api/client.ts";
import { findTerm, type GlossaryEntry } from "../answer/glossary.ts";
import { hubPrices, ZONE_HUB } from "../mapSelection.ts";
import { gasDayStartUtc } from "../tradingContext.ts";
import { workspaceTaskSearch } from "../../workspaceNavigation.ts";

/** Categories whose terms name an object on the market rather than a concept. */
const ENTITY_CATEGORIES = new Set([
  "hub",
  "venue",
  "interconnection",
  "point",
  "entry_point",
  "exit_point",
  "terminal",
  "lng_terminal",
  "storage_site",
  "pipeline",
]);

/** Context types the platform resolves to an object with figures of its own. */
const ENTITY_CONTEXT_TYPES = new Set(["hub", "venue", "price_assessment", "entry_point", "exit_point"]);

const HUB_CODES = new Set(Object.values(ZONE_HUB));

export interface GlossaryTermLike extends GlossaryEntry {
  term_id?: string;
  category?: string;
}

/** The entry a link or a search names: exact term, alias or id, any case. */
export function resolveGlossaryTerm<T extends GlossaryTermLike>(name: string | null | undefined, terms: readonly T[]): T | null {
  if (!name) return null;
  const found = findTerm(name, terms) as T | null;
  if (found) return found;
  const wanted = name.trim().toLowerCase();
  return terms.find((term) => term.term_id?.toLowerCase() === wanted) ?? null;
}

function names(term: GlossaryTermLike): string[] {
  return [term.term, ...(term.aliases ?? [])].map((name) => name.trim().toLowerCase()).filter(Boolean);
}

/** The map's parameter for one place: the network node's id. */
export const MAP_PLACE_PARAM = "place";

export function mapPlaceFromSearch(search: string): string | null {
  return new URLSearchParams(search).get(MAP_PLACE_PARAM) || null;
}

/** The network node the term names, when the map draws it (a hub, a terminal, a point). */
export function glossaryMapPlace(term: GlossaryTermLike | null, nodes: readonly NodeDTO[]): string | null {
  if (!term) return null;
  const wanted = new Set(names(term));
  const hub = nodes.find((node) => node.node_type === "hub" && wanted.has(node.name.trim().toLowerCase()));
  if (hub) return hub.id;
  if (term.category === "hub") return null;
  return nodes.find((node) => wanted.has(node.name.trim().toLowerCase()))?.id ?? null;
}

/** The hub code whose board prices a hub entry shows (the map hub card's figures), or null. */
export function glossaryHubCode(term: GlossaryTermLike | null, nodes: readonly NodeDTO[]): string | null {
  if (!term || term.category !== "hub") return null;
  const wanted = new Set(names(term));
  const hub = nodes.find((node) => node.node_type === "hub" && wanted.has(node.name.trim().toLowerCase()));
  if (hub) return hub.name.toUpperCase();
  return [...wanted].map((name) => name.toUpperCase()).find((name) => HUB_CODES.has(name)) ?? null;
}

/**
 * Whether the term names an object with figures (and so a gas-day choice). Decided from the term
 * before any read, then widened by what the platform resolved it to.
 */
export function isEntityTerm(
  term: GlossaryTermLike | null,
  mapPlace: string | null,
  context?: Pick<GlossaryContextDTO, "context_type"> | null,
): boolean {
  if (!term) return false;
  if (mapPlace) return true;
  if (ENTITY_CATEGORIES.has(String(term.category ?? "").toLowerCase())) return true;
  const name = term.term.toLowerCase();
  if (/\b(entry|exit) point\b|\bterminal\b|\bicis\b|\bheren\b/.test(name)) return true;
  return Boolean(context && ENTITY_CONTEXT_TYPES.has(context.context_type));
}

/**
 * The read window for one gas day (CAM: 05:00 UTC in winter, 04:00 in summer), a second inside
 * each end so the adjoining days' rows, which touch the boundary, are not read as this day's.
 * No gas day reads the latest held.
 */
export function gasDayReadWindow(gasDay: string): { duration_start_utc?: string; duration_end_utc?: string } {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(gasDay)) return {};
  const start = gasDayStartUtc(gasDay);
  const next = new Date(start + 36 * 3_600_000).toISOString().slice(0, 10);
  const end = gasDayStartUtc(next);
  return {
    duration_start_utc: new Date(start + 1000).toISOString(),
    duration_end_utc: new Date(end - 1000).toISOString(),
  };
}

/** Whether the context read answers this term for this gas day (and not an earlier choice). */
export function contextAnswers(context: GlossaryContextDTO | null, term: GlossaryTermLike | null, gasDay: string): boolean {
  if (!context || !term) return false;
  if (context.term.trim().toLowerCase() !== term.term.trim().toLowerCase()) return false;
  const window = gasDayReadWindow(gasDay);
  const requested = (context.requested_duration ?? null) as { duration_start_utc?: string | null } | null;
  if (!window.duration_start_utc) return !requested || !requested.duration_start_utc;
  const asked = requested?.duration_start_utc ? Date.parse(requested.duration_start_utc) : NaN;
  return asked === Date.parse(window.duration_start_utc);
}

/** One figure of an entry: the value as read, its unit, where it came from and when. */
export interface EntryFigure {
  id: string;
  label: string;
  value: number;
  unit: string;
  source: string | null;
  asOf: string | null;
  /** A second line: bid / ask, or the share of capacity in use. */
  detail?: string;
  /** The change on the previous reading of the same series, in the figure's unit. */
  change?: number | null;
  /** A day-ahead / month-ahead row whose label the page translates. */
  tenor?: "day-ahead" | "month-ahead";
}

const num = (value: unknown): number | null => {
  const parsed = typeof value === "number" ? value : typeof value === "string" && value.trim() !== "" ? Number(value) : NaN;
  return Number.isFinite(parsed) ? parsed : null;
};
const text = (value: unknown): string | null => (typeof value === "string" && value.trim() ? value.trim() : null);
const fixed = (value: number, digits = 3) => value.toLocaleString("en-GB", { maximumFractionDigits: digits });

/**
 * Prices for the entry. A map hub with no gas day chosen shows the board's latest day-ahead and
 * month-ahead (the map card's figures); otherwise the latest reading of each venue and product the
 * platform matched for the term in the chosen window: one figure per series, never a list of ticks.
 */
export function entryPrices(
  context: GlossaryContextDTO | null,
  options: { hub?: string | null; gasDay: string; boardRows: readonly NormalizedMarketObsDTO[] },
): EntryFigure[] {
  if (options.hub && !options.gasDay) {
    const board = hubPrices(options.hub, options.boardRows);
    if (board.length > 0) {
      return board.map((price) => ({
        id: `board:${price.tenor}`,
        label: price.tenor,
        tenor: price.tenor === "day-ahead" ? "day-ahead" : "month-ahead",
        value: price.price,
        unit: price.unit,
        source: price.source,
        asOf: price.observedAt,
        change: price.change,
      }));
    }
  }
  if (!context) return [];
  const latest = new Map<string, EntryFigure>();
  const keep = (figure: EntryFigure) => {
    const held = latest.get(figure.id);
    if (!held || String(figure.asOf ?? "") > String(held.asOf ?? "")) latest.set(figure.id, figure);
  };
  for (const row of context.related_prices ?? []) {
    const value = num(row.price);
    if (value == null) continue;
    const venue = text(row.market_venue) ?? text(row.source_system) ?? "";
    const product = text(row.product) ?? text(row.price_name) ?? "";
    keep({
      id: `price:${venue}|${product}`.toLowerCase(),
      label: [venue, product].filter(Boolean).join(" · "),
      value,
      unit: text(row.unit) ?? text(row.currency) ?? "",
      source: text(row.source_reference) ?? text(row.source_system),
      asOf: text(row.observed_at_utc) ?? text(row.period_end_utc),
    });
  }
  for (const row of context.live_market_marks ?? []) {
    const bid = num(row.bid_gbp_mwh);
    const ask = num(row.ask_gbp_mwh);
    const value = num(row.last_gbp_mwh) ?? (bid != null && ask != null ? (bid + ask) / 2 : bid ?? ask);
    if (value == null) continue;
    const venue = text(row.venue) ?? "";
    const product = [text(row.hub), text(row.product)].filter(Boolean).join(" ");
    keep({
      id: `mark:${venue}|${product}`.toLowerCase(),
      label: [venue, product].filter(Boolean).join(" · "),
      value,
      unit: "GBP/MWh",
      source: text(row.source_reference) ?? text(row.source_system),
      asOf: text(row.mark_time_utc),
      detail: bid != null && ask != null ? `${fixed(bid)} / ${fixed(ask)}` : undefined,
    });
  }
  return [...latest.values()].sort((a, b) => String(b.asOf ?? "").localeCompare(String(a.asOf ?? ""))).slice(0, 6);
}

/** Capacity and its use at the point, when the platform holds them for the window. */
export function entryCapacity(context: GlossaryContextDTO | null): EntryFigure[] {
  const out: EntryFigure[] = [];
  const capacity = context?.capacity ?? null;
  if (capacity) {
    const mwh = num(capacity.capacity_mwh_per_day);
    const mcm = num(capacity.capacity_mcm_d);
    const value = mwh ?? mcm;
    if (value != null) {
      const direction = text(capacity.direction);
      const firmness = text(capacity.firmness);
      out.push({
        id: "capacity",
        label: [text(capacity.point_name), direction, firmness].filter(Boolean).join(" · "),
        value,
        unit: mwh != null ? "MWh/d" : "mcm/d",
        source: text(capacity.source_reference),
        asOf: text(capacity.valid_from_utc) ?? text(capacity.period_start_utc),
      });
    }
  }
  const usage = context?.capacity_usage ?? null;
  if (usage) {
    const used = num(usage.used);
    if (used != null) {
      const pct = num(usage.usage_pct);
      out.push({
        id: "capacity_used",
        label: "used",
        value: used,
        unit: text(usage.unit) ?? "",
        source: text(usage.source_reference),
        asOf: text(usage.period_end_utc),
        detail: pct != null ? `${fixed(pct, 1)} %` : undefined,
      });
    }
  }
  return out;
}

/** Route and contract names that run through the entity (no figures of their own here). */
export function entryLinks(context: GlossaryContextDTO | null): { routes: string[]; contracts: string[] } {
  const unique = (values: Array<string | null>) => [...new Set(values.filter((value): value is string => Boolean(value)))];
  return {
    routes: unique((context?.related_routes ?? []).map((row) => text(row.route_name) ?? text(row.route_id))).slice(0, 6),
    contracts: unique((context?.related_contracts ?? []).map((row) => text(row.contract_name) ?? text(row.contract_id))).slice(0, 6),
  };
}

/** The sources a term cites, once, in the order given. */
export function uniqueSources(...lists: ReadonlyArray<readonly string[] | null | undefined>): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const list of lists) {
    for (const item of list ?? []) {
      const clean = item.trim();
      if (!clean || seen.has(clean.toLowerCase())) continue;
      seen.add(clean.toLowerCase());
      out.push(clean);
    }
  }
  return out;
}

/** The URL search that opens an entry; another page's object ids are dropped. */
export function glossaryTermSearch(search: string, term: string): string {
  const params = new URLSearchParams(workspaceTaskSearch(search, "glossary"));
  params.set("term", term);
  return params.toString();
}

/** The URL search that opens the network map on one place (a network node's id). */
export function mapPlaceSearch(search: string, nodeId: string): string {
  const params = new URLSearchParams(workspaceTaskSearch(search, "market", "network"));
  params.set(MAP_PLACE_PARAM, nodeId);
  return params.toString();
}

function follow(search: string, workspace: string): void {
  if (typeof window === "undefined") return;
  const url = new URL(window.location.href);
  url.search = search;
  window.history.pushState({ workspace }, "", url);
  window.dispatchEvent(new PopStateEvent("popstate", { state: window.history.state }));
}

/**
 * Open the map on one place from anywhere: the address changes and the shell and the kept map
 * follow it as they follow Back.
 */
export function openMapPlace(nodeId: string): void {
  if (typeof window === "undefined") return;
  follow(mapPlaceSearch(window.location.search, nodeId), "market");
}

/**
 * Open an entry from anywhere (a map card, a palette result): the address changes and the shell
 * follows it as it follows Back, so the glossary opens on the term whether or not it is showing.
 */
export function openGlossaryTerm(term: string): void {
  if (typeof window === "undefined") return;
  follow(glossaryTermSearch(window.location.search, term), "glossary");
}
