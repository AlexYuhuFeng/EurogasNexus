/**
 * What the live map says about the one thing a person clicked, and how it relates to the
 * rest: the "control tower" selection model.
 *
 * - One selection at a time: a site (a place with one or more network roles), a hub (a
 *   virtual trading point) or a cargo. Clicking empty map clears it.
 * - A site gathers every network point and facility within SITE_RADIUS_KM, because one
 *   place often plays several parts. Easington is a production entry point, the landing of
 *   the Langeled pipeline and a point of the NTS in the NBP zone; a desk wants that on one
 *   card, not three overlapping dots.
 * - Roles are words, not colours. Colour on the map is kept for state (outage, the firm's
 *   own positions, gas flowing); a role chip is neutral text unless it is the firm's own
 *   or an outage.
 * - Figures are the few a trader acts on, in desk units, each with its source and age.
 */

import type {
  EdgeDTO,
  FacilityDTO,
  MapCargoDTO,
  MapSituationDTO,
  NodeDTO,
  NormalizedMarketObsDTO,
} from "@/api/client";

export const SITE_RADIUS_KM = 3;

/** The hub whose balancing zone a country's network belongs to. */
export const ZONE_HUB: Record<string, string> = {
  GB: "NBP",
  NL: "TTF",
  BE: "ZTP",
  DE: "THE",
  FR: "PEG",
  IT: "PSV",
  AT: "CEGH",
  ES: "PVB",
};

export type MapSelection =
  | { kind: "site"; id: string }
  | { kind: "hub"; id: string }
  | { kind: "cargo"; id: string };

export type RoleTone = "neutral" | "own" | "alert" | "watch";

export interface SiteRole {
  /** i18n key under `map.role.` */
  key: string;
  /** Text filled into the role (a pipeline or zone name). */
  value?: string;
  tone: RoleTone;
}

export interface SiteMember {
  kind: "node" | "facility";
  id: string;
  name: string;
  type: string;
  country: string;
  metadata: Record<string, unknown>;
  /** Where the point comes from, and whether its position is surveyed or approximate. */
  source: string;
  quality: string;
}

export interface Site {
  id: string;
  name: string;
  lon: number;
  lat: number;
  country: string;
  members: SiteMember[];
}

function km(aLon: number, aLat: number, bLon: number, bLat: number): number {
  const rad = Math.PI / 180;
  const dLat = (bLat - aLat) * rad;
  const dLon = (bLon - aLon) * rad;
  const h =
    Math.sin(dLat / 2) ** 2 + Math.cos(aLat * rad) * Math.cos(bLat * rad) * Math.sin(dLon / 2) ** 2;
  return 6371 * 2 * Math.asin(Math.sqrt(h));
}

const NAME_RANK: Record<string, number> = {
  entry_point: 0,
  interconnection: 1,
  lng: 2,
  lng_terminal: 2,
  border_point: 3,
  storage: 4,
  processing_plant: 5,
  production: 6,
  field: 7,
};

/**
 * Group network points (not hubs: a hub is a market, not a place) and facilities that sit
 * within SITE_RADIUS_KM of each other into sites. The site takes the name of its most
 * network-relevant member (an entry point before a processing plant).
 */
export function buildSites(nodes: readonly NodeDTO[], facilities: readonly FacilityDTO[]): Site[] {
  const items: Array<SiteMember & { lon: number; lat: number }> = [
    ...nodes
      .filter((node) => node.node_type !== "hub")
      .map((node) => ({
        kind: "node" as const,
        id: node.id,
        name: node.name,
        type: node.node_type,
        country: node.country,
        metadata: node.metadata_json ?? {},
        source: node.source_dataset ?? node.source_system ?? "",
        quality: node.data_quality ?? "",
        lon: node.lon,
        lat: node.lat,
      })),
    ...facilities.map((facility) => ({
      kind: "facility" as const,
      id: facility.id,
      name: facility.name,
      type: facility.facility_type,
      country: facility.country,
      metadata: facility.metadata_json ?? {},
      source: facility.source_dataset ?? facility.source_system ?? "",
      quality: facility.data_quality ?? "",
      lon: facility.lon,
      lat: facility.lat,
    })),
  ];
  const sites: Array<Site & { anchors: Array<[number, number]> }> = [];
  for (const item of items) {
    const site = sites.find((candidate) =>
      candidate.anchors.some(([lon, lat]) => km(lon, lat, item.lon, item.lat) <= SITE_RADIUS_KM),
    );
    const { lon, lat, ...member } = item;
    if (site) {
      site.members.push(member);
      site.anchors.push([lon, lat]);
    } else {
      sites.push({ id: `site:${item.id}`, name: item.name, lon, lat, country: item.country, members: [member], anchors: [[lon, lat]] });
    }
  }
  return sites.map(({ anchors: _anchors, ...site }) => {
    const lead = [...site.members].sort(
      (a, b) => (NAME_RANK[a.type] ?? 9) - (NAME_RANK[b.type] ?? 9) || a.name.length - b.name.length,
    )[0];
    return { ...site, name: sharedName(site.members.map((member) => member.name)) || lead.name, id: `site:${lead.id}` };
  });
}

/** "Bacton IUK" and "Bacton BBL" are both "Bacton": the leading words every member shares. */
function sharedName(names: string[]): string {
  if (names.length < 2) return "";
  const split = names.map((name) => name.split(/\s+/));
  const shared: string[] = [];
  for (let index = 0; index < split[0].length; index += 1) {
    const word = split[0][index];
    if (split.every((words) => words[index]?.toLowerCase() === word.toLowerCase())) shared.push(word);
    else break;
  }
  return shared.join(" ");
}

/** The site holding a network point or facility id. */
export function siteOf(sites: readonly Site[], refId: string | undefined | null): Site | null {
  if (!refId) return null;
  return sites.find((site) => site.members.some((member) => member.id === refId)) ?? null;
}

const memberIds = (site: Site) => new Set(site.members.map((member) => member.id));
const normal = (text: string | null | undefined) => (text ?? "").toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();

/** Pipelines that start or end at the site, by name. */
export function sitePipelines(site: Site, edges: readonly EdgeDTO[]): string[] {
  const ids = memberIds(site);
  const names = edges
    .filter((edge) => edge.edge_type === "pipeline" && (ids.has(edge.from_node_id) || ids.has(edge.to_node_id)))
    .map((edge) => String(edge.metadata_json?.name ?? "").trim())
    .filter(Boolean);
  return [...new Set(names)];
}

const TYPE_ROLE: Record<string, string> = {
  entry_point: "entry_point",
  interconnection: "interconnection",
  border_point: "border_point",
  lng: "lng_terminal",
  lng_terminal: "lng_terminal",
  storage: "storage",
  processing_plant: "gas_terminal",
  production: "production",
  production_platform: "production",
  field: "production",
  liquefaction: "liquefaction",
  compressor: "compressor",
  power_plant: "power_plant",
  city_gate: "city_gate",
};

/** What the place is, in words: its network roles, its zone, and the firm's stake. */
export function siteRoles(site: Site, edges: readonly EdgeDTO[], situation: MapSituationDTO | null): SiteRole[] {
  const roles: SiteRole[] = [];
  const seen = new Set<string>();
  for (const member of site.members) {
    const key = TYPE_ROLE[member.type];
    if (key && !seen.has(key)) {
      seen.add(key);
      roles.push({ key, tone: "neutral" });
    }
  }
  for (const pipeline of sitePipelines(site, edges)) roles.push({ key: "pipeline", value: pipeline, tone: "neutral" });
  const zone = ZONE_HUB[site.country];
  if (zone) roles.push({ key: "zone", value: zone, tone: "neutral" });
  const facts = situation ? siteSituation(site, situation) : null;
  if (facts?.contracts.length) roles.push({ key: "own_supply", tone: "own" });
  if (facts?.slots.length) roles.push({ key: "own_slot", tone: "own" });
  if (facts?.outages.some((outage) => outage.status === "active")) roles.push({ key: "outage_now", tone: "alert" });
  else if (facts?.outages.length) roles.push({ key: "outage_planned", tone: "watch" });
  return roles;
}

/** Everything in the live situation located at the site. */
export function siteSituation(site: Site, situation: MapSituationDTO) {
  const ids = memberIds(site);
  const names = new Set(site.members.map((member) => normal(member.name)));
  const at = (location: { ref_id?: string } | null | undefined) => Boolean(location?.ref_id && ids.has(location.ref_id));
  return {
    flows: situation.flows.filter((flow) => at(flow.location)),
    outages: situation.outages.filter((outage) => at(outage.location)),
    contracts: situation.contracts.filter((contract) => at(contract.location)),
    slots: situation.regas_slots.filter((slot) => at(slot.location) || names.has(normal(slot.terminal_name))),
    inbound: situation.cargoes.filter(
      (cargo) =>
        (cargo.status === "laden" || cargo.status === "discharging") &&
        (names.has(normal(cargo.destination_terminal)) || at(cargo.destination)),
    ),
  };
}

function numberAt(metadata: Record<string, unknown>, key: string): number | null {
  const value = Number(metadata[key]);
  return Number.isFinite(value) && metadata[key] !== null && metadata[key] !== "" ? value : null;
}

/** The figures a site's card leads with. */
export function siteFacts(site: Site, situation: MapSituationDTO | null) {
  const facts = situation ? siteSituation(site, situation) : null;
  const operator = site.members.map((member) => String(member.metadata.operator ?? "")).find(Boolean) ?? null;
  const sendOut = site.members.map((member) => numberAt(member.metadata, "send_out_gwh_d")).find((value) => value != null) ?? null;
  const storage = site.members.map((member) => numberAt(member.metadata, "storage_m3")).find((value) => value != null) ?? null;
  const flowIn = facts?.flows.filter((flow) => flow.direction === "entry").reduce((sum, flow) => sum + (flow.gwh_d ?? 0), 0) ?? 0;
  const flowOut = facts?.flows.filter((flow) => flow.direction === "exit").reduce((sum, flow) => sum + (flow.gwh_d ?? 0), 0) ?? 0;
  const hasFlow = Boolean(facts?.flows.length);
  // Capacity: the terminal's declared send-out, else the technical capacity a REMIT message
  // states for a point (in GWh/d only: other units are not compared with flows). A site with
  // several points (Bacton: IUK and BBL) names the point the capacity belongs to, and only
  // compares it with a flow measured at that same point.
  const remit = facts?.outages.find((outage) => outage.unit.toLowerCase() === "gwh/d" && outage.technical_capacity != null) ?? null;
  const capacity = sendOut ?? remit?.technical_capacity ?? null;
  const points = site.members.filter((member) => member.kind === "node");
  const capacityPoint = sendOut == null && remit && points.length > 1
    ? site.members.find((member) => member.id === remit.location.ref_id)?.name ?? null
    : null;
  const flowAtCapacityPoint = sendOut != null
    ? Math.max(flowIn, flowOut)
    : remit
      ? (facts?.flows.filter((flow) => flow.location.ref_id === remit.location.ref_id).reduce((sum, flow) => sum + (flow.gwh_d ?? 0), 0) ?? 0)
      : 0;
  const comparable = hasFlow && capacity && (sendOut != null || facts?.flows.some((flow) => flow.location.ref_id === remit?.location.ref_id));
  const gasDay = facts?.flows.map((flow) => flow.gas_day ?? flow.gas_day_start_utc?.slice(0, 10)).find(Boolean) ?? null;
  return {
    operator,
    capacityGwhD: capacity,
    capacityPoint,
    storageM3: storage,
    flowEntryGwhD: hasFlow ? flowIn : null,
    flowExitGwhD: hasFlow ? flowOut : null,
    utilisation: comparable && capacity ? flowAtCapacityPoint / capacity : null,
    gasDay,
    flowSource: facts?.flows[0]?.source_system ?? null,
    ...(facts ?? { flows: [], outages: [], contracts: [], slots: [], inbound: [] }),
  };
}

export interface HubPrice {
  tenor: string;
  price: number;
  unit: string;
  change: number | null;
  observedAt: string | null;
  source: string | null;
}

/** Latest day-ahead and month-ahead prices for a hub from the rows the hub board shows. */
export function hubPrices(hub: string, rows: readonly NormalizedMarketObsDTO[]): HubPrice[] {
  const out: HubPrice[] = [];
  for (const tenor of ["day-ahead", "month-ahead"]) {
    const series = rows
      .filter((row) => row.hub === hub && row.tenor === tenor && row.is_gas_price && Number.isFinite(row.price))
      .sort((a, b) => String(b.observed_at_utc ?? "").localeCompare(String(a.observed_at_utc ?? "")));
    if (!series.length) continue;
    const [latest, previous] = series;
    out.push({
      tenor,
      price: latest.price,
      unit: latest.unit,
      change: previous && previous.unit === latest.unit ? latest.price - previous.price : null,
      observedAt: latest.observed_at_utc ?? null,
      source: latest.source_system ?? latest.market_venue ?? null,
    });
  }
  return out;
}

/** The zone behind a hub today: outages, measured flows at its points, the firm's supply. */
export function hubZone(
  hub: string,
  situation: MapSituationDTO | null,
  network?: { nodes: readonly NodeDTO[]; edges: readonly EdgeDTO[] },
) {
  const countries = new Set(Object.entries(ZONE_HUB).filter(([, code]) => code === hub).map(([country]) => country));
  const inZone = (location: { country?: string | null } | null | undefined) => Boolean(location?.country && countries.has(location.country));
  if (!situation) return { outagesNow: 0, outagesPlanned: 0, unavailableGwhD: 0, entryGwhD: null, exitGwhD: null, supplyMwhD: 0, contracts: 0, upstream: [] };
  // Outages one pipeline upstream of the zone (Nyhamna feeding NBP through Langeled): a
  // trader reads these as the zone's supply risk even though they sit in another country.
  const countryOf = new Map((network?.nodes ?? []).map((node) => [node.id, node.country]));
  const feeding = new Set<string>();
  for (const edge of network?.edges ?? []) {
    const from = countryOf.get(edge.from_node_id);
    const to = countryOf.get(edge.to_node_id);
    if (to && countries.has(to) && from && !countries.has(from)) feeding.add(edge.from_node_id);
    if (from && countries.has(from) && to && !countries.has(to)) feeding.add(edge.to_node_id);
  }
  const upstream = situation.outages.filter((outage) => outage.location.ref_id && feeding.has(outage.location.ref_id) && !inZone(outage.location));
  const outages = situation.outages.filter((outage) => inZone(outage.location));
  const flows = situation.flows.filter((flow) => inZone(flow.location));
  const contracts = situation.contracts.filter((contract) => inZone(contract.location));
  return {
    outagesNow: outages.filter((outage) => outage.status === "active").length,
    outagesPlanned: outages.filter((outage) => outage.status !== "active").length,
    unavailableGwhD: outages.filter((outage) => outage.status === "active").reduce((sum, outage) => sum + (outage.unavailable_gwh_d ?? 0), 0),
    entryGwhD: flows.length ? flows.filter((flow) => flow.direction === "entry").reduce((sum, flow) => sum + (flow.gwh_d ?? 0), 0) : null,
    exitGwhD: flows.length ? flows.filter((flow) => flow.direction === "exit").reduce((sum, flow) => sum + (flow.gwh_d ?? 0), 0) : null,
    supplyMwhD: contracts.reduce((sum, contract) => sum + contract.delivery_mwh_d, 0),
    contracts: contracts.length,
    upstream,
  };
}

/** A cargo's voyage: where from, where to, how far along, and the slot waiting for it. */
export function cargoVoyage(cargo: MapCargoDTO, situation: MapSituationDTO | null, now = new Date()) {
  const etaDays = cargo.eta_utc ? (Date.parse(cargo.eta_utc) - now.getTime()) / 86_400_000 : null;
  const departed = cargo.departed_at_utc ? Date.parse(cargo.departed_at_utc) : null;
  const eta = cargo.eta_utc ? Date.parse(cargo.eta_utc) : null;
  const progress =
    departed != null && eta != null && eta > departed
      ? Math.min(1, Math.max(0, (now.getTime() - departed) / (eta - departed)))
      : null;
  const slot = situation?.regas_slots.find((item) => item.cargo_id === cargo.cargo_id) ?? null;
  return { etaDays, progress, slot };
}

export interface TopologyIssue {
  /** i18n key under `map.topology.` */
  kind: "missing_endpoint" | "cross_border_landing" | "isolated_point" | "duplicate_connection";
  edgeId?: string;
  nodeId?: string;
  detail: string;
}

const BORDER_LANDINGS = new Set(["entry_point", "interconnection", "lng", "production", "storage"]);

/**
 * Checks that the network's topology is right, which is what netbacks and flow reasoning
 * depend on (a pipe's surveyed path is not): every connection ends at known points, a
 * connection that crosses a border lands at an entry or interconnection point (so gas
 * entering Easington cannot be routed onwards as if it were already in Ireland), entry and
 * interconnection points are connected to something, and no connection is recorded twice.
 */
export function topologyIssues(nodes: readonly NodeDTO[], edges: readonly EdgeDTO[]): TopologyIssue[] {
  const byId = new Map(nodes.map((node) => [node.id, node]));
  const issues: TopologyIssue[] = [];
  const seen = new Set<string>();
  const connected = new Set<string>();
  for (const edge of edges) {
    // Route candidates are scenario corridors, not the network.
    if (edge.source_system === "route_candidate" || edge.metadata_json?.materialization === "route_candidate_edge") continue;
    const from = byId.get(edge.from_node_id);
    const to = byId.get(edge.to_node_id);
    const name = String(edge.metadata_json?.name ?? edge.id);
    if (!from || !to) {
      issues.push({ kind: "missing_endpoint", edgeId: edge.id, detail: `${name}: ${!from ? edge.from_node_id : edge.to_node_id}` });
      continue;
    }
    connected.add(from.id);
    connected.add(to.id);
    const key = [from.id, to.id].sort().join("|");
    if (seen.has(key)) issues.push({ kind: "duplicate_connection", edgeId: edge.id, detail: `${name}: ${from.name} – ${to.name}` });
    seen.add(key);
    if (from.country !== to.country) {
      for (const end of [from, to]) {
        if (!BORDER_LANDINGS.has(end.node_type)) {
          issues.push({ kind: "cross_border_landing", edgeId: edge.id, nodeId: end.id, detail: `${name}: ${from.name} (${from.country}) – ${to.name} (${to.country}) lands at ${end.name}, a ${end.node_type}` });
        }
      }
    }
  }
  for (const node of nodes) {
    if ((node.node_type === "entry_point" || node.node_type === "interconnection") && !connected.has(node.id)) {
      issues.push({ kind: "isolated_point", nodeId: node.id, detail: node.name });
    }
  }
  return issues;
}
