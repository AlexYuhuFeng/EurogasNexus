/**
 * The map's names (owner review 2026-11-26): one decluttered symbol layer, ranked by what
 * affects the book. Hubs read as the desk does ("TTF 31.20", a quiet sim mark); a zone with no
 * trading point is a name without a price; our cargo says where it is going and when.
 */
import assert from "node:assert/strict";
import test from "node:test";
import type { MapSituationDTO, NodeDTO, NormalizedMarketObsDTO } from "../src/api/client.ts";
import { hubDeskName, isZoneOnly, labelFeatures, mapLabels } from "../src/app/mapLabels.ts";

const t = (key: string, options?: Record<string, unknown>) => (options ? `${key}${JSON.stringify(options)}` : key);
const NOW = Date.parse("2026-11-26T12:00:00Z");

const node = (id: string, name: string, type: string, lon: number, lat: number, meta: Record<string, unknown> = {}): NodeDTO =>
  ({ id, name, node_type: type, country: "NL", lon, lat, capacity_boe_d: 0, metadata_json: meta }) as unknown as NodeDTO;

const nodes = [
  node("ttf", "TTF", "hub", 5, 52.3, { market_code: "TTF" }),
  node("bg", "Balancing Zone Bulgaria", "hub", 23.7, 42, { zone_only: true, hub_code: "BG" }),
  node("ip", "Oude Statenzijl (NL) / Bunde (DE)", "interconnection", 7.2, 53.2),
];
const rows = [
  { hub: "TTF", tenor: "day-ahead", is_gas_price: true, price: 31.2, unit: "EUR/MWh", observed_at_utc: "2026-11-26T09:00:00Z", source_system: "DEMO_Sim" },
] as unknown as NormalizedMarketObsDTO[];
const situation = {
  as_of_utc: "2026-11-26T12:00:00Z",
  outages: [], flows: [],
  contracts: [
    { contract_id: "a", contract_name: "A", resource_type: "X", delivery_point: "TTF", gas_year: "2026", delivery_mwh_d: 5000, entry_capacity_mwh_d: null, book_id: "b", location: { lon: 5, lat: 52.3, ref_id: "ttf" } },
    { contract_id: "b", contract_name: "B", resource_type: "X", delivery_point: "Emden", gas_year: "2026", delivery_mwh_d: 12000, entry_capacity_mwh_d: null, book_id: "b", location: { lon: 7.2, lat: 53.4 } },
  ],
  cargoes: [
    {
      cargo_id: "c", vessel_name: "Meridian", vessel_imo: null, status: "laden", load_port: "X", departed_at_utc: null,
      destination_terminal: "Zeebrugge LNG", eta_utc: "2026-11-28T16:00:00Z", position_at_utc: null, volume_m3: null, energy_gwh: 1000,
      own: true, book_id: "b", source_system: "S", origin: null, position: { lon: -10, lat: 45 }, destination: { lon: 3.2, lat: 51.3 }, track: [],
    },
    {
      cargo_id: "lost", vessel_name: "Nowhere", vessel_imo: null, status: "laden", load_port: "X", departed_at_utc: null,
      destination_terminal: "Gate", eta_utc: null, position_at_utc: null, volume_m3: null, energy_gwh: null,
      own: true, book_id: "b", source_system: "S", origin: null, position: null, destination: null, track: [],
    },
  ],
  regas_slots: [],
  unlocated: { outages: 0, contracts: 0, cargoes: 0, regas_slots: 0 },
  positions_included: true,
} as unknown as MapSituationDTO;

test("a hub is its desk name and price, a zone with no trading point its name alone", () => {
  assert.equal(hubDeskName(nodes[0]), "TTF");
  assert.ok(isZoneOnly(nodes[1]));
  const labels = mapLabels({ nodes, activeLayers: ["hubs"], situation: null, marketRows: rows, facilities: [], zoom: 4, nowMs: NOW, t });
  const ttf = labels.find((item) => item.text === "TTF")!;
  assert.equal(ttf.price, " 31.20");
  assert.equal(ttf.sim, " today.simulated_short");
  assert.equal(ttf.rank, 1);
  // Zones with no trading point and other points are context: named from regional zoom.
  assert.ok(!labels.some((item) => item.tone === "point" || item.tone === "zone"));
  const regional = mapLabels({ nodes, activeLayers: ["hubs"], situation: null, marketRows: rows, facilities: [], zoom: 6, nowMs: NOW, t });
  assert.ok(regional.some((item) => item.tone === "point"));
  // A zone is named by its desk code, as hubs are; a point by its first place, never cut.
  const zone = regional.find((item) => item.text === "BG")!;
  assert.ok(regional.some((item) => item.text === "Oude Statenzijl"));
  assert.ok(!regional.some((item) => item.text.includes("…")));
  assert.equal(zone.price, "");
  assert.equal(zone.tone, "zone");
  assert.ok(zone.rank > ttf.rank);
});

test("our positions rank first; a delivery at a hub is the hub's label, not a second one", () => {
  const labels = mapLabels({ nodes, activeLayers: ["hubs", "positions", "cargoes"], situation, marketRows: rows, facilities: [], zoom: 4, nowMs: NOW, t });
  const own = labels.filter((item) => item.tone === "own");
  assert.deepEqual(own.map((item) => item.rank), [0, 0]);
  assert.ok(own.some((item) => item.text.startsWith("Meridian → Zeebrugge LNG · map.cargo.duration_dh")));
  assert.ok(own.some((item) => item.text === "Emden · 12k MWh/d" || item.text.startsWith("Emden · ")));
  assert.ok(!own.some((item) => item.text.startsWith("TTF")));
  // A cargo with no position is not drawn, so it has no label either (the card says why).
  assert.ok(!labels.some((item) => item.text.startsWith("Nowhere")));
  // Features carry the rank the layer sorts by.
  const geo = labelFeatures(labels, (lon, lat) => [lon, lat]);
  assert.equal(geo.features.length, labels.length);
  assert.equal(typeof geo.features[0].properties.rank, "number");
});
