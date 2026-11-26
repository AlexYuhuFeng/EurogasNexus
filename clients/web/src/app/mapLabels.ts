import type { FacilityDTO, MapCargoDTO, MapSituationDTO, NodeDTO, NormalizedMarketObsDTO } from "@/api/client";
import { cargoDrawable, cargoEta, cargoMapLabel } from "./mapCargo.ts";
import { hubPrices } from "./mapSelection.ts";
import { compactMwhPerDay } from "./mapLineGeometry.ts";

/**
 * The map's names as one MapLibre symbol layer (owner review 2026-11-26: "labels never overlap
 * anything"). HTML markers cannot be decluttered; a symbol layer is, by MapLibre's own collision
 * detection: a label that would touch another is dropped, the less important first
 * (`symbol-sort-key`, lower is placed first), and the basemap's place names give way to ours.
 *
 * Importance answers the map's one question, "what in the gas system affects my book right now":
 *   0  our own: cargoes (name → terminal · time to go), contract places, our flows
 *   1  hubs: desk name and price ("TTF 31.20", a quiet "sim" mark where simulated)
 *   2  LNG terminals we hold slots at
 *   3  outages on the map, from regional zoom
 *   4  other network points, from regional zoom
 *   5  zone-only nodes (a balancing zone with no trading point): name only, never a price
 *   6  infrastructure, close in
 */

type Translate = (key: string, options?: Record<string, unknown>) => string;

export type LabelTone = "own" | "hub" | "zone" | "point" | "outage" | "opportunity";

export interface MapLabel {
  at: [number, number];
  text: string;
  /** The hub's price, set apart from its name ("" for none). */
  price: string;
  /** The quiet simulated mark after a simulated price ("" for none). */
  sim: string;
  rank: number;
  tone: LabelTone;
  /** What a click on the label opens (`opportunity:<id>`), or "" for nothing. */
  action: string;
}

export interface LabelInputs {
  /** The network points the active layers draw (the map's own filter). */
  nodes: readonly NodeDTO[];
  activeLayers: readonly string[];
  situation: MapSituationDTO | null;
  marketRows: readonly NormalizedMarketObsDTO[];
  facilities: readonly FacilityDTO[];
  zoom: number;
  nowMs: number;
  t: Translate;
  /** Outage event ids the map draws (by the outage layers' rule). */
  outageIds?: ReadonlySet<string>;
  /** Labels the page adds (the book view's flows, opportunities and proposals). */
  extra?: readonly MapLabel[];
}

const label = (at: [number, number], text: string, rank: number, tone: LabelTone, extra: Partial<MapLabel> = {}): MapLabel => ({
  at, text, price: "", sim: "", rank, tone, action: "", ...extra,
});

/** A node that is a balancing zone with no trading point of its own (topology `zone_only`). */
export function isZoneOnly(node: Pick<NodeDTO, "metadata_json">): boolean {
  return node.metadata_json?.zone_only === true;
}

/** The desk's name for a hub: its market code (TTF, NBP, THE), else its hub code, else its name. */
export function hubDeskName(node: Pick<NodeDTO, "name" | "metadata_json">): string {
  const meta = node.metadata_json ?? {};
  for (const key of ["market_code", "hub_code"]) {
    const value = meta[key];
    if (typeof value === "string" && value.trim()) return value.trim();
  }
  return node.name;
}

/** "31.20": a hub price as the board shows it (two decimals). */
function priceText(value: number): string {
  return value.toLocaleString("en-GB", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

/**
 * The short name a desk uses for a network point: its market code where it has one, else the
 * first place of its name ("Oude Statenzijl (NL) / Bunde (DE)" is "Oude Statenzijl"). Never a
 * name cut with an ellipsis ("GTF (Bilateral Tra…", owner review 2026-11-26).
 */
export function pointDeskName(node: Pick<NodeDTO, "name" | "metadata_json">): string {
  const code = node.metadata_json?.market_code;
  if (typeof code === "string" && code.trim()) return code.trim();
  return node.name.split(/\s+\(|\s+[-–/]\s+|\s*\/\s*/)[0].trim() || node.name;
}

function ownCargoLabels(cargoes: readonly MapCargoDTO[], nowMs: number, t: Translate): MapLabel[] {
  const out: MapLabel[] = [];
  for (const cargo of cargoes) {
    if (!cargo.own || cargo.status === "delivered" || cargo.status === "ballast") continue;
    if (!cargoDrawable(cargo).position) continue;
    const at = cargo.position ?? (cargo.status === "loading" ? cargo.origin : cargo.destination);
    if (!at) continue;
    out.push(label([at.lon, at.lat], cargoMapLabel(cargo, cargoEta(cargo, nowMs), t), 0, "own"));
  }
  return out;
}

export function mapLabels(input: LabelInputs): MapLabel[] {
  const { nodes, activeLayers, situation, marketRows, zoom, nowMs, t } = input;
  const on = (layer: string) => activeLayers.includes(layer);
  const out: MapLabel[] = [...(input.extra ?? [])];
  const hubIds = new Set(nodes.filter((node) => node.node_type === "hub").map((node) => node.id));

  if (situation && on("cargoes")) out.push(...ownCargoLabels(situation.cargoes, nowMs, t));
  if (situation && on("positions")) {
    // A delivery at a hub is a market position: the hub's own label says where. Elsewhere the
    // place carries its name and our volume there.
    const byPlace = new Map<string, { at: [number, number]; name: string; mwhD: number }>();
    for (const contract of situation.contracts) {
      const { lon, lat, ref_id: refId } = contract.location;
      if (!Number.isFinite(lon) || !Number.isFinite(lat) || (refId && hubIds.has(refId))) continue;
      const key = refId || `${lon.toFixed(3)},${lat.toFixed(3)}`;
      const place = byPlace.get(key) ?? { at: [lon, lat] as [number, number], name: contract.delivery_point, mwhD: 0 };
      place.mwhD += contract.delivery_mwh_d;
      byPlace.set(key, place);
    }
    for (const place of byPlace.values()) {
      out.push(label(place.at, place.mwhD > 0 ? `${place.name} · ${compactMwhPerDay(place.mwhD)}` : place.name, 0, "own"));
    }
    const terminals = new Map<string, [number, number]>();
    for (const slot of situation.regas_slots) terminals.set(slot.terminal_name, [slot.location.lon, slot.location.lat]);
    for (const [name, at] of terminals) out.push(label(at, name, 2, "own"));
  }
  for (const node of nodes) {
    if (!Number.isFinite(node.lon) || !Number.isFinite(node.lat)) continue;
    const at: [number, number] = [node.lon, node.lat];
    if (node.node_type === "hub") {
      if (isZoneOnly(node)) {
        // A zone with no trading point is context: its code from regional zoom, never priced.
        if (zoom >= 5) out.push(label(at, hubDeskName(node), 5, "zone"));
        continue;
      }
      const name = hubDeskName(node);
      const price = hubPrices(name.toUpperCase(), marketRows)[0];
      out.push(label(at, name, 1, "hub", price ? {
        price: ` ${priceText(price.price)}`,
        sim: price.simulated ? ` ${t("today.simulated_short")}` : "",
      } : {}));
    } else if (zoom >= 5) {
      out.push(label(at, pointDeskName(node), 4, "point"));
    }
  }
  if (situation && zoom >= 6 && input.outageIds) {
    for (const outage of situation.outages) {
      if (!input.outageIds.has(outage.event_id)) continue;
      out.push(label([outage.location.lon, outage.location.lat], outage.facility_name, 3, "outage"));
    }
  }
  if (zoom >= 7 && on("infrastructure")) {
    for (const facility of input.facilities) out.push(label([facility.lon, facility.lat], facility.name, 6, "point"));
  }
  return out;
}

/** The labels as GeoJSON for the symbol layer. */
export function labelFeatures(labels: readonly MapLabel[], project: (lon: number, lat: number) => [number, number]) {
  return {
    type: "FeatureCollection" as const,
    features: labels.map((item) => ({
      type: "Feature" as const,
      properties: { text: item.text, price: item.price, sim: item.sim, rank: item.rank, tone: item.tone, action: item.action },
      geometry: { type: "Point" as const, coordinates: project(item.at[0], item.at[1]) },
    })),
  };
}
