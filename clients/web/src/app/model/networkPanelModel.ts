/**
 * The Network page's information panel (Desk → Network): what the map shows, as lists.
 *
 * One Network task replaced "Network" and "Outages & capacity" (a capability does not earn a
 * page of its own). The panel beside the map has tabs - Outages (default), Capacity, Flows and,
 * in the "Our book" map view with book permission, Our book - and one selection links both
 * ways: a row focuses the map on its object, an object chosen on the map filters the lists to
 * it ("Showing: TTF zone"). With "Follow map" on, the lists hold what is in the map's current
 * view; a row the map cannot place is never hidden by it.
 *
 * Pure functions only (tests/networkPanelModel.test.ts); the component is
 * components/NetworkInfoPanel.tsx.
 */
import type { MapOutageDTO, MapSituationDTO, NodeDTO, OutageEventDTO } from "../../api/client.ts";
import type { MapSelection, Site } from "../mapSelection.ts";

export const NETWORK_PANEL_TABS = ["outages", "capacity", "flows", "book"] as const;
export type NetworkPanelTab = (typeof NETWORK_PANEL_TABS)[number];
export const DEFAULT_NETWORK_PANEL_TAB: NetworkPanelTab = "outages";

/** The URL parameter carrying the panel's tab (`?workspace=market&task=network&panel=capacity`). */
export const NETWORK_PANEL_PARAM = "panel";

export function isNetworkPanelTab(value: string | null | undefined): value is NetworkPanelTab {
  return (NETWORK_PANEL_TABS as readonly string[]).includes(value ?? "");
}

/**
 * The tab a URL opens. An explicit `panel=` wins; the retired "Outages & capacity" addresses
 * (`?workspace=capacity`, `?workspace=market&task=capacity`) open Capacity, the board that
 * page was named for; anything else opens Outages.
 */
export function networkPanelFromSearch(search: string, activeWorkspace = ""): NetworkPanelTab {
  const params = new URLSearchParams(search);
  const explicit = params.get(NETWORK_PANEL_PARAM);
  if (isNetworkPanelTab(explicit)) return explicit;
  if (activeWorkspace === "capacity" || params.get("workspace") === "capacity" || params.get("task") === "capacity") {
    return "capacity";
  }
  return DEFAULT_NETWORK_PANEL_TAB;
}

/** The canonical Network address for a tab: a legacy capacity address becomes the market task. */
export function networkPanelToSearch(search: string, tab: NetworkPanelTab): string {
  const next = new URLSearchParams(search);
  next.set("workspace", "market");
  next.set("task", "network");
  if (tab === DEFAULT_NETWORK_PANEL_TAB) next.delete(NETWORK_PANEL_PARAM);
  else next.set(NETWORK_PANEL_PARAM, tab);
  return next.toString();
}

/**
 * The outage an address selects (`outage=<event id>`): the situational strip opens an outage
 * where the job continues, on Network with the Outages panel and that outage selected.
 */
export const NETWORK_OUTAGE_PARAM = "outage";

export function networkOutageFromSearch(search: string): string | null {
  return new URLSearchParams(search).get(NETWORK_OUTAGE_PARAM) || null;
}

/* ------------------------------------------------------------------ view and placement */

export interface MapBounds {
  west: number;
  south: number;
  east: number;
  north: number;
}

export type LonLat = readonly [number, number];

export function inBounds(at: LonLat | null | undefined, bounds: MapBounds | null | undefined): boolean {
  if (!at || !bounds) return true;
  const [lon, lat] = at;
  return lon >= bounds.west && lon <= bounds.east && lat >= bounds.south && lat <= bounds.north;
}

/**
 * Where an outage stands on the map: drawn, at a facility the product knows but no source
 * positions, not located at all, or starting after the map's outage horizon (the map draws
 * the next 14 days; the list reads 90).
 */
export type OutagePlacement = "placed" | "known_no_position" | "not_located" | "later";

export type OutageState = "active" | "scheduled" | "ended";

export interface OutageListRow {
  key: string;
  eventId: string;
  asset: string;
  operators: string[];
  messages: string[];
  zone: string;
  state: OutageState;
  eventType: string;
  /** Offline in GWh/d (the desk unit), through the server's unit authority; null when none. */
  gwhD: number | null;
  /** The published figure, kept for the row's title when no daily figure exists. */
  published: string;
  dailyBasis: string;
  startUtc: string;
  endUtc: string | null;
  reason: string;
  placement: OutagePlacement;
  /**
   * Why an unplaced row is where it is, as an i18n key and its values: the GIE facility the
   * outage was identified as, or the server's reason it could not be resolved.
   */
  placementNote: { key: string; values: Record<string, string> } | null;
  at: LonLat | null;
  refId: string | null;
  country: string | null;
  simulated: boolean;
}

function normalizeName(value: string | null | undefined): string {
  return String(value ?? "").toLowerCase().replace(/[^0-9a-z]/g, "");
}

/** The server's unresolved-outage reason (`map_situation._Locator.explain`) as an i18n key. */
export function unlocatedReasonKey(reason: string): string {
  const code = reason.split(":")[0];
  if (code === "ambiguous_name" || code === "ambiguous_facility_name") return "outages.unresolved.ambiguous";
  if (code === "no_eic_match_and_no_name") return "outages.unresolved.no_identity";
  return "outages.unresolved.no_match";
}

function knownFacilityNote(
  facility: NonNullable<MapSituationDTO["known_facility_outages"]>[number],
): { key: string; values: Record<string, string> } {
  // A group's site is named only when the group's own name does not already list it.
  const fold = (text: string) => text.normalize("NFKD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
  const name = facility.facility_name ?? facility.facility_eic;
  const unnamed = (facility.sites ?? []).filter((site) => !fold(name).includes(fold(site)));
  const sites = unnamed.length ? ` (${unnamed.join(", ")})` : "";
  const values = {
    facility: `${name}${sites}`,
    country: facility.country ?? "",
  };
  return facility.reason === "outside_reference_network"
    ? { key: "outages.known.outside_network", values }
    : { key: "outages.known.no_position", values };
}

function stateOf(status: string): OutageState {
  if (status === "active") return "active";
  if (status === "ended") return "ended";
  return "scheduled";
}

/**
 * One list row per outage event (the server collapses messages: `grouped=true`), placed with
 * the map situation's own answer for that event, else at the position the map gives the same
 * asset, else in the state the situation names.
 */
export function outageListRows(events: readonly OutageEventDTO[], situation: MapSituationDTO | null): OutageListRow[] {
  const placed = new Map<string, MapOutageDTO>();
  const placedByAsset = new Map<string, MapOutageDTO>();
  for (const outage of situation?.outages ?? []) {
    placed.set(outage.event_id, outage);
    placedByAsset.set(normalizeName(outage.facility_name), outage);
  }
  const knownByEvent = new Map<string, NonNullable<MapSituationDTO["known_facility_outages"]>[number]>();
  for (const item of situation?.known_facility_outages ?? []) {
    for (const id of item.event_ids) knownByEvent.set(String(id), item);
  }
  const unlocatedByEvent = new Map((situation?.unlocated_outages ?? []).map((item) => [String(item.event_id), item.reason] as const));
  return events.map((event) => {
    const members = event.messages?.length ? event.messages : [event.event_id];
    const direct = members.map((id) => placed.get(id)).find(Boolean) ?? null;
    const sameAsset = direct ?? placedByAsset.get(normalizeName(event.facility_name)) ?? null;
    let placement: OutagePlacement;
    if (sameAsset) placement = "placed";
    else if (members.some((id) => knownByEvent.has(id))) placement = "known_no_position";
    else if (members.some((id) => unlocatedByEvent.has(id)) || !situation) placement = "not_located";
    else placement = "later";
    let placementNote: OutageListRow["placementNote"] = null;
    if (placement === "known_no_position") {
      const facility = members.map((id) => knownByEvent.get(id)).find(Boolean);
      if (facility) placementNote = knownFacilityNote(facility);
    } else if (placement === "not_located") {
      const reason = members.map((id) => unlocatedByEvent.get(id)).find(Boolean);
      if (reason) placementNote = { key: unlocatedReasonKey(reason), values: {} };
    }
    const location = sameAsset?.location ?? null;
    const unit = event.unit ?? "";
    return {
      key: event.event_id,
      eventId: event.event_id,
      asset: event.facility_name || event.facility_id,
      operators: event.operators?.length ? event.operators : [event.market_participant].filter(Boolean),
      messages: members,
      zone: event.balancing_zone,
      state: stateOf(event.status),
      eventType: event.event_type,
      gwhD: event.unavailable_gwh_d ?? null,
      published: event.unavailable_capacity == null ? "" : `${event.unavailable_capacity.toLocaleString("en-GB", { maximumFractionDigits: 1 })} ${unit}`.trim(),
      dailyBasis: event.daily_basis ?? "",
      startUtc: event.start_utc,
      endUtc: event.end_utc,
      reason: event.description,
      placement,
      placementNote,
      at: location ? [location.lon, location.lat] : null,
      refId: location?.ref_id ?? null,
      country: location?.country ?? null,
      simulated: String(event.source_reference ?? "").toLowerCase().startsWith("demo"),
    };
  });
}

/* ------------------------------------------------------------------ selection scope */

/** What a map selection filters the panel to, and the words of its "Showing:" line. */
export interface SelectionScope {
  label: string;
  kind: "zone" | "site";
  /** The hub's countries (zone) or the site's member ids and names (site). */
  countries: ReadonlySet<string>;
  hubCode: string | null;
  memberIds: ReadonlySet<string>;
  memberNames: ReadonlySet<string>;
}

const ZONE_COUNTRIES: Record<string, string[]> = {
  NBP: ["GB"],
  TTF: ["NL"],
  ZTP: ["BE"],
  THE: ["DE"],
  PEG: ["FR"],
  PSV: ["IT"],
  CEGH: ["AT"],
  PVB: ["ES"],
};

/** The hub code a map hub selection names ("THE VTP (DE)" is THE). */
export function hubCode(hubId: string): string | null {
  const upper = hubId.toUpperCase();
  return Object.keys(ZONE_COUNTRIES).find((code) => upper === code || upper.startsWith(`${code} `) || upper.startsWith(`${code}(`)) ?? null;
}

/**
 * The scope of a map selection: a hub is its zone (its countries' points and the outages in
 * its balancing zone), a site is its members. A cargo filters nothing (null).
 */
export function selectionScope(
  selection: MapSelection | null,
  context: { sites: readonly Site[]; nodes: readonly NodeDTO[]; zoneMemberIds?: (hubNodeId: string) => ReadonlySet<string> },
): SelectionScope | null {
  if (!selection) return null;
  if (selection.kind === "hub") {
    const code = hubCode(selection.id);
    const hubNode = context.nodes.find((node) => node.node_type === "hub" && node.name.toUpperCase() === selection.id);
    const members = hubNode && context.zoneMemberIds ? context.zoneMemberIds(hubNode.id) : new Set<string>();
    const memberNodes = context.nodes.filter((node) => members.has(node.id));
    return {
      label: `${code ?? selection.id}`,
      kind: "zone",
      countries: new Set(code ? ZONE_COUNTRIES[code] : []),
      hubCode: code,
      memberIds: new Set(members),
      memberNames: new Set(memberNodes.map((node) => normalizeName(node.name))),
    };
  }
  if (selection.kind === "site") {
    const site = context.sites.find((item) => item.id === selection.id);
    if (!site) return null;
    return {
      label: site.name,
      kind: "site",
      countries: new Set(),
      hubCode: null,
      memberIds: new Set(site.members.map((member) => member.id)),
      memberNames: new Set([site.name, ...site.members.map((member) => member.name)].map(normalizeName)),
    };
  }
  return null;
}

/** Whether a row (an outage, a capacity or flow point) belongs to the scope. */
export function inScope(
  scope: SelectionScope | null,
  row: { refId?: string | null; name?: string | null; country?: string | null; zone?: string | null },
): boolean {
  if (!scope) return true;
  if (row.refId && scope.memberIds.has(row.refId)) return true;
  const name = normalizeName(row.name);
  if (name && scope.memberNames.has(name)) return true;
  if (scope.kind === "zone") {
    if (row.country && scope.countries.has(row.country.toUpperCase())) return true;
    const zone = String(row.zone ?? "").toUpperCase();
    if (scope.hubCode && zone && (zone === scope.hubCode || zone.split(/[^A-Z]+/).includes(scope.hubCode))) return true;
  }
  return false;
}

/**
 * The panel's one filter: the map selection when there is one, else - with "Follow map" on -
 * the map's current view. A row with no position passes the view filter: it cannot be in or
 * out of a view, and an outage the map cannot draw is never hidden.
 */
export function panelFilter<R>(
  rows: readonly R[],
  options: {
    scope: SelectionScope | null;
    followMap: boolean;
    bounds: MapBounds | null;
    describe: (row: R) => { at: LonLat | null; refId?: string | null; name?: string | null; country?: string | null; zone?: string | null };
  },
): R[] {
  return rows.filter((row) => {
    const facts = options.describe(row);
    if (options.scope) return inScope(options.scope, facts);
    if (!options.followMap) return true;
    return facts.at === null || inBounds(facts.at, options.bounds);
  });
}

/* ------------------------------------------------------------------ ordering */

const STATE_ORDER: Record<OutageState, number> = { active: 0, scheduled: 1, ended: 2 };

/** Default order: out now first, then planned, then ended; within each, capacity offline, largest first. */
export function compareOutages(left: OutageListRow, right: OutageListRow): number {
  return (
    STATE_ORDER[left.state] - STATE_ORDER[right.state] ||
    (right.gwhD ?? -1) - (left.gwhD ?? -1) ||
    left.startUtc.localeCompare(right.startUtc) ||
    left.eventId.localeCompare(right.eventId)
  );
}
