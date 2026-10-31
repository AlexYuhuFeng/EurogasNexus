import type {
  FacilityDTO,
  MapCargoDTO,
  MapContractDTO,
  MapOutageDTO,
  MapPointFlowDTO,
  MapRegasSlotDTO,
  MapSituationDTO,
} from "@/api/client";

/**
 * The live map's situation layers as GeoJSON, built from `/api/portfolio/map-situation`.
 *
 * Rules (docs/ux/LIVE_MAP.md):
 * - an item is drawn only where a source located it; nothing is snapped or guessed;
 * - colour carries meaning, not decoration: red = capacity out now, amber = scheduled,
 *   accent = the firm's own positions, grey = market information;
 * - the leg from a cargo's last reported position to its destination is drawn dashed and
 *   labelled as indicative: it is not the vessel's route.
 */

export type Project = (lon: number, lat: number) => [number, number];

export const SITUATION_LAYERS = ["outages", "flows", "positions", "infrastructure"] as const;
export type SituationLayer = (typeof SITUATION_LAYERS)[number];

type Props = Record<string, string | number | boolean | null>;
interface PointFeature {
  type: "Feature";
  properties: Props;
  geometry: { type: "Point"; coordinates: [number, number] };
}
interface LineFeature {
  type: "Feature";
  properties: Props;
  geometry: { type: "LineString"; coordinates: Array<[number, number]> };
}
export interface Collection<F> {
  type: "FeatureCollection";
  features: F[];
}

const collection = <F>(features: F[]): Collection<F> => ({ type: "FeatureCollection", features });

/** Palette aligned with the design-system tokens (light, dark). */
export const SITUATION_COLOURS = {
  light: {
    outageActive: "#b91c1c",
    outageScheduled: "#b45309",
    own: "#1d4ed8",
    market: "#71717a",
    flow: "#0f766e",
    facility: "#52525b",
    halo: "#ffffff",
  },
  dark: {
    outageActive: "#f87171",
    outageScheduled: "#fbbf24",
    own: "#60a5fa",
    market: "#a1a1aa",
    flow: "#2dd4bf",
    facility: "#a1a1aa",
    halo: "#0a0a0a",
  },
} as const;

function point(project: Project, lon: number, lat: number, properties: Props): PointFeature {
  return { type: "Feature", properties, geometry: { type: "Point", coordinates: project(lon, lat) } };
}

export function outageFeatures(outages: MapOutageDTO[], project: Project): Collection<PointFeature> {
  return collection(
    outages.map((outage) =>
      point(project, outage.location.lon, outage.location.lat, {
        kind: "outage",
        id: outage.event_id,
        status: outage.status,
        // Radius grows with the share of capacity out; unknown share draws the minimum.
        share: outage.unavailable_share ?? 0,
        name: outage.facility_name,
      }),
    ),
  );
}

export function flowFeatures(flows: MapPointFlowDTO[], project: Project): Collection<PointFeature> {
  return collection(
    flows
      .filter((flow) => (flow.gwh_d ?? 0) > 0)
      .map((flow) =>
        point(project, flow.location.lon, flow.location.lat, {
          kind: "flow",
          id: `${flow.point_id}|${flow.direction}`,
          gwh_d: flow.gwh_d ?? 0,
          direction: flow.direction,
          name: flow.point_name,
        }),
      ),
  );
}

export function contractFeatures(contracts: MapContractDTO[], project: Project): Collection<PointFeature> {
  // Several contracts landing at one point share a pin; the hover lists them all.
  const byPoint = new Map<string, MapContractDTO[]>();
  for (const contract of contracts) {
    const key = `${contract.location.lon.toFixed(4)},${contract.location.lat.toFixed(4)}`;
    byPoint.set(key, [...(byPoint.get(key) ?? []), contract]);
  }
  return collection(
    [...byPoint.values()].map((group) =>
      point(project, group[0].location.lon, group[0].location.lat, {
        kind: "contract",
        id: group.map((item) => item.contract_id).join(","),
        count: group.length,
        mwh_d: group.reduce((sum, item) => sum + item.delivery_mwh_d, 0),
        name: group[0].delivery_point,
      }),
    ),
  );
}

export function slotTerminalFeatures(slots: MapRegasSlotDTO[], project: Project): Collection<PointFeature> {
  const byTerminal = new Map<string, MapRegasSlotDTO[]>();
  for (const slot of slots) byTerminal.set(slot.terminal_name, [...(byTerminal.get(slot.terminal_name) ?? []), slot]);
  return collection(
    [...byTerminal.entries()].map(([terminal, group]) =>
      point(project, group[0].location.lon, group[0].location.lat, {
        kind: "regas",
        id: terminal,
        count: group.length,
        active: group.some((slot) => slot.active),
        name: terminal,
      }),
    ),
  );
}

export function cargoFeatures(
  cargoes: MapCargoDTO[],
  project: Project,
): { positions: Collection<PointFeature>; sailed: Collection<LineFeature>; ahead: Collection<LineFeature> } {
  const positions: PointFeature[] = [];
  const sailed: LineFeature[] = [];
  const ahead: LineFeature[] = [];
  for (const cargo of cargoes) {
    const at = cargo.position ?? (cargo.status === "loading" ? cargo.origin : null)
      ?? (cargo.status === "discharging" || cargo.status === "delivered" ? cargo.destination : null);
    const props: Props = { kind: "cargo", id: cargo.cargo_id, own: cargo.own, status: cargo.status, name: cargo.vessel_name };
    if (at) positions.push(point(project, at.lon, at.lat, props));
    const track = cargo.track.length > 1
      ? cargo.track
      : cargo.origin && cargo.position
        ? [[cargo.origin.lon, cargo.origin.lat], [cargo.position.lon, cargo.position.lat]] as Array<[number, number]>
        : [];
    if (track.length > 1) {
      sailed.push({
        type: "Feature",
        properties: props,
        geometry: { type: "LineString", coordinates: track.map(([lon, lat]) => project(lon, lat)) },
      });
    }
    if (at && cargo.destination && cargo.status === "laden") {
      ahead.push({
        type: "Feature",
        properties: { ...props, indicative: true },
        geometry: {
          type: "LineString",
          coordinates: [project(at.lon, at.lat), project(cargo.destination.lon, cargo.destination.lat)],
        },
      });
    }
  }
  return { positions: collection(positions), sailed: collection(sailed), ahead: collection(ahead) };
}

const FACILITY_KINDS = new Set([
  "production_platform",
  "field",
  "liquefaction",
  "storage",
  "processing_plant",
  "compressor",
  "power_plant",
]);

export function facilityFeatures(facilities: FacilityDTO[], project: Project): Collection<PointFeature> {
  return collection(
    facilities
      .filter((facility) => FACILITY_KINDS.has(facility.facility_type))
      .map((facility) =>
        point(project, facility.lon, facility.lat, {
          kind: "facility",
          id: facility.id,
          facility_type: facility.facility_type,
          name: facility.name,
        }),
      ),
  );
}

/** One line a manager reads first: what needs attention now. */
export function situationSummary(situation: MapSituationDTO | null) {
  if (!situation) return null;
  const outagesNow = situation.outages.filter((item) => item.status === "active").length;
  return {
    outagesNow,
    outagesScheduled: situation.outages.length - outagesNow,
    contracts: situation.contracts.length,
    cargoesAtSea: situation.cargoes.filter((item) => item.own && item.status === "laden").length,
    slots: situation.regas_slots.length,
    unlocated: Object.values(situation.unlocated).reduce((sum, value) => sum + value, 0),
    asOf: situation.as_of_utc,
  };
}

function number(value: number | null | undefined, digits = 0): string {
  return value == null ? "—" : value.toLocaleString(undefined, { maximumFractionDigits: digits });
}

function utc(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value);
  return `${date.toISOString().slice(0, 16).replace("T", " ")} UTC`;
}

/** Compact window bound for cards: "02 Nov 03:34". */
function shortUtc(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value);
  const month = date.toLocaleString("en-GB", { month: "short", timeZone: "UTC" });
  return `${String(date.getUTCDate()).padStart(2, "0")} ${month} ${date.toISOString().slice(11, 16)}`;
}

type Translate = (key: string) => string;
type Escape = (value: unknown) => string;

/** Hover card for one situation feature; plain rows in desk units, no decoration. */
export function situationCardHtml(
  kind: string,
  id: string,
  situation: MapSituationDTO,
  t: Translate,
  escape: Escape,
): string {
  const rows = (pairs: Array<[string, string]>) =>
    pairs.map(([label, value]) => `<span><small>${escape(label)}</small> ${escape(value)}</span>`).join("");
  if (kind === "outage") {
    const item = situation.outages.find((outage) => outage.event_id === id);
    if (!item) return "";
    return `<div class="node-popup situation-card">
      <strong>${escape(item.facility_name)}</strong>
      <em class="situation-tag is-${item.status}">${escape(t(`map.situation.outage_${item.status}`))}</em>
      ${rows([
        [t("map.situation.unavailable"), `${number(item.unavailable_capacity)} / ${number(item.technical_capacity)} ${item.unit}`],
        [t("map.situation.window"), `${shortUtc(item.start_utc)} → ${item.end_utc ? shortUtc(item.end_utc) : "open"} UTC`],
        [t("map.situation.zone"), item.balancing_zone],
        [t("map.situation.reason"), item.description || "—"],
      ])}
      <small>REMIT ${escape(item.event_id)} · ${escape(item.market_participant)}</small>
    </div>`;
  }
  if (kind === "contract") {
    const items = situation.contracts.filter((contract) => id.split(",").includes(contract.contract_id));
    if (!items.length) return "";
    return `<div class="node-popup situation-card">
      <strong>${escape(items[0].delivery_point)}</strong>
      <em class="situation-tag is-own">${escape(t("map.situation.upstream_contracts"))}</em>
      ${items.map((item) => rows([
        [item.contract_name, `${number(item.delivery_mwh_d)} MWh/d`],
        [t("map.situation.entry_capacity"), item.entry_capacity_mwh_d == null ? "—" : `${number(item.entry_capacity_mwh_d)} MWh/d`],
        [t("map.situation.book"), `${item.book_id ?? "—"} · ${item.gas_year}`],
      ])).join("")}
    </div>`;
  }
  if (kind === "cargo") {
    const item = situation.cargoes.find((cargo) => cargo.cargo_id === id);
    if (!item) return "";
    return `<div class="node-popup situation-card">
      <strong>${escape(item.vessel_name)}</strong>
      <em class="situation-tag is-${item.own ? "own" : "market"}">${escape(t(item.own ? "map.situation.own_cargo" : "map.situation.market_cargo"))} · ${escape(t(`map.situation.cargo_${item.status}`))}</em>
      ${rows([
        [t("map.situation.route"), `${item.load_port} → ${item.destination_terminal ?? t("map.situation.destination_unknown")}`],
        [t("map.situation.eta"), utc(item.eta_utc)],
        [t("map.situation.cargo_size"), item.energy_gwh != null ? `${number(item.energy_gwh)} GWh` : item.volume_m3 != null ? `${number(item.volume_m3)} m³ LNG` : "—"],
        [t("map.situation.position_at"), utc(item.position_at_utc)],
      ])}
      <small>${escape(t("map.situation.source"))} ${escape(item.source_system)}${item.status === "laden" && item.destination ? ` · ${escape(t("map.situation.indicative_leg"))}` : ""}</small>
    </div>`;
  }
  if (kind === "regas") {
    const items = situation.regas_slots.filter((slot) => slot.terminal_name === id);
    if (!items.length) return "";
    return `<div class="node-popup situation-card">
      <strong>${escape(id)}</strong>
      <em class="situation-tag is-own">${escape(t("map.situation.regas_slots"))}</em>
      ${items.map((slot) => rows([
        [`${shortUtc(slot.window_start_utc)} → ${shortUtc(slot.window_end_utc)} UTC`, slot.send_out_gwh_d == null ? "—" : `${number(slot.send_out_gwh_d)} GWh/d`],
        [t("map.situation.book"), `${slot.book_id ?? "—"}${slot.cargo_id ? ` · ${slot.cargo_id}` : ""}`],
      ])).join("")}
    </div>`;
  }
  if (kind === "flow") {
    const [pointId, direction] = id.split("|");
    const item = situation.flows.find((flow) => flow.point_id === pointId && flow.direction === direction);
    if (!item) return "";
    return `<div class="node-popup situation-card">
      <strong>${escape(item.point_name)}</strong>
      <em class="situation-tag is-flow">${escape(t("map.situation.physical_flow"))} · ${escape(item.direction)}</em>
      ${rows([
        [t("map.situation.flow"), item.gwh_d != null ? `${number(item.gwh_d, 1)} GWh/d` : `${number(item.value)} ${item.unit}`],
        [t("map.situation.gas_day"), (item.gas_day_start_utc ?? "").slice(0, 10) || "—"],
      ])}
      <small>${escape(t("map.situation.source"))} ${escape(item.source_system)}</small>
    </div>`;
  }
  return "";
}
