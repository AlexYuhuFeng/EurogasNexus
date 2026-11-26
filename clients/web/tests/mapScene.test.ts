/**
 * MAP-1 map scene, flat: site points sized by published capacity, flows oriented only where
 * the network gives a side, static under reduced motion, and a payload without the new fields
 * (an older server, a caller without the scopes) drawing nothing invented.
 */
import assert from "node:assert/strict";
import test from "node:test";
import type { EdgeDTO, MapAssetDTO, MapSituationDTO, NodeDTO } from "../src/api/client.ts";
import {
  FLOW_DASH_STATIC,
  FLOW_DASH_STEPS,
  assetFigures,
  assetPoints,
  distanceKm,
  flowDashAt,
  flowDayOptions,
  flowLayers,
  flowMotion,
  flowsForDay,
  greatCirclePoint,
  orientFlow,
  pathPrefix,
  pointIndex,
  pointSides,
  tweenPoints,
} from "../src/app/mapScene.ts";

const identity = (lon: number, lat: number): [number, number] => [lon, lat];

const capacity = (direction: string, gwh_d: number) => ({
  direction, capacity_type: "firm_technical" as const, gwh_d, gas_day: "2026-11-12", operator_key: "NL-TSO-0001",
  source_system: "ENTSOG", observed_at_utc: "2026-11-11T05:00:00+00:00", basis: "published" as const,
});

const gate: MapAssetDTO = {
  asset_id: "entsog-lng-00027", kind: "lng_terminal", name: "Gate Terminal (I)", country: "NL", eic: "21Z0000000002212",
  location: { lon: 4.03, lat: 51.95, ref_id: "entsog-lng-00027" },
  capacity: [capacity("entry", 400)],
  flow: [{ direction: "entry", gwh_d: 300, gas_day: "2026-11-11", operator_key: "NL-TSO-0001", source_system: "ENTSOG" }],
  stock: {
    basis: "country_aggregate", scope: "NL", dataset: "ALSI", gas_day: "2026-11-11", inventory_twh: 2.1, dtmi_twh: 3.4,
    send_out_twh_d: 0.32, source_system: "GIE", observed_at_utc: "2026-11-12T08:00:00+00:00", freshness: "live",
  },
};
const bergermeer: MapAssetDTO = {
  asset_id: "entsog-ugs-00149", kind: "storage", name: "Bergermeer", country: "NL", eic: null,
  location: { lon: 4.7, lat: 52.6, ref_id: "entsog-ugs-00149" },
  capacity: [capacity("entry", 100), capacity("exit", 50)],
  flow: [{ direction: "exit", gwh_d: 40, gas_day: "2026-11-11", operator_key: null, source_system: "ENTSOG" }],
  stock: null,
};
const loenhout: MapAssetDTO = {
  asset_id: "entsog-ugs-00002", kind: "storage", name: "Loenhout", country: "BE", eic: null,
  location: { lon: 4.6, lat: 51.4 }, capacity: [], flow: [], stock: null,
};

test("a terminal's figure is its published send-out capacity and the same direction's flow", () => {
  const figures = assetFigures(gate);
  assert.equal(figures.capacityGwhD, 400);
  assert.equal(figures.capacityDirection, "entry");
  assert.equal(figures.flowGwhD, 300);
  assert.equal(figures.utilisation, 0.75);
  // Storage: the larger direction stands for the site; the fill compares like with like, so a
  // flow in the other direction leaves no fill.
  const storage = assetFigures(bergermeer);
  assert.equal(storage.capacityDirection, "entry");
  assert.equal(storage.flowGwhD, null);
  assert.equal(storage.utilisation, null);
});

test("site points scale by square root; a site with no published capacity is the smallest", () => {
  const points = assetPoints([gate, bergermeer, loenhout], identity);
  const byId = new Map(points.features.map((feature) => [feature.properties.id, feature.properties]));
  assert.equal(byId.get("entsog-lng-00027")?.radius, 14);
  assert.equal(byId.get("entsog-ugs-00149")?.radius, 4 + 10 * Math.sqrt(100 / 400));
  assert.equal(byId.get("entsog-ugs-00002")?.radius, 4);
  assert.equal(byId.get("entsog-ugs-00002")?.published, false);
});

test("no assets in the payload (older server or no scope) draws nothing", () => {
  assert.equal(assetPoints(undefined, identity).features.length, 0);
  assert.deepEqual(flowDayOptions({} as MapSituationDTO), []);
  assert.deepEqual(flowsForDay(null, null), []);
});

const NOW = new Date("2026-11-12T12:00:00Z");

test("great circle points and prefixes are exact", () => {
  const a: [number, number] = [0, 0];
  const b: [number, number] = [90, 0];
  assert.deepEqual(greatCirclePoint(a, b, 0.5).map((v) => Math.round(v * 1e6) / 1e6), [45, 0]);
  const prefix = pathPrefix([[0, 0], [1, 0], [2, 0]], distanceKm([0, 0], [1.5, 0]));
  assert.equal(prefix.length, 3);
  assert.ok(Math.abs(prefix[2][0] - 1.5) < 1e-6);
});

// Oude Statenzijl-like point between a Dutch and a German hub; Bacton-like pipeline end.
const nodes: NodeDTO[] = [
  { id: "ip", name: "Oude Statenzijl", node_type: "interconnection", country: "NL", lat: 53.2, lon: 7.2, capacity_boe_d: null },
  { id: "ttf", name: "TTF", node_type: "hub", country: "NL", lat: 52.4, lon: 5.3, capacity_boe_d: null },
  { id: "the", name: "THE", node_type: "hub", country: "DE", lat: 51.5, lon: 9.9, capacity_boe_d: null },
  { id: "bacton", name: "Bacton (IUK)", node_type: "interconnection", country: "GB", lat: 52.85, lon: 1.46, capacity_boe_d: null },
  { id: "nbp", name: "NBP", node_type: "hub", country: "GB", lat: 53, lon: -1, capacity_boe_d: null },
  { id: "zee", name: "Zeebrugge (IUK)", node_type: "interconnection", country: "BE", lat: 51.33, lon: 3.2, capacity_boe_d: null },
];
const edges: EdgeDTO[] = [
  { id: "a1", from_node_id: "ip", to_node_id: "ttf", edge_type: "market_area_link", length_km: null, metadata_json: { operators: ["NL-TSO-0001"] } },
  { id: "a2", from_node_id: "ip", to_node_id: "the", edge_type: "market_area_link", length_km: null, metadata_json: { operators: ["DE-TSO-0002"] } },
  { id: "a3", from_node_id: "bacton", to_node_id: "nbp", edge_type: "market_area_link", length_km: null, metadata_json: { operators: ["UK-TSO-0001"] } },
  { id: "p1", from_node_id: "bacton", to_node_id: "zee", edge_type: "interconnector", length_km: null, metadata_json: { pipeline: "pipeline:UK-TSO-0003" } },
];

const flow = (refId: string, direction: string, operatorKey: string | null, gwhD = 100) => ({
  refId, pointName: refId, direction, gwhD, operatorKey, gasDay: "2026-11-11", sourceSystem: "ENTSOG",
});

test("an entry flows into the operator's side, an exit out of it", () => {
  const sides = pointSides(nodes, edges);
  const at: [number, number] = [7.2, 53.2];
  // GTS (NL) reports entry: gas comes from the German side into the Dutch side.
  const entry = orientFlow(flow("ip", "entry", "NL-TSO-0001"), at, sides.get("ip"));
  assert.ok(entry);
  const start = entry.coordinates[0];
  const end = entry.coordinates[entry.coordinates.length - 1];
  assert.ok(distanceKm(start, [9.9, 51.5]) < distanceKm(end, [9.9, 51.5]), "starts towards THE");
  assert.ok(distanceKm(end, [5.3, 52.4]) < distanceKm(start, [5.3, 52.4]), "ends towards TTF");
  assert.ok(entry.coordinates.some(([lon, lat]) => lon === 7.2 && lat === 53.2), "passes through the point");
  // The same physical flow reported by the German operator as its exit points the same way.
  const exit = orientFlow(flow("ip", "exit", "DE-TSO-0002"), at, sides.get("ip"));
  assert.deepEqual(exit?.coordinates, entry.coordinates);
  // A pipeline operator: exit from National Gas at Bacton goes towards Zeebrugge.
  const bacton = orientFlow(flow("bacton", "exit", "UK-TSO-0001"), [1.46, 52.85], sides.get("bacton"));
  const tail = bacton?.coordinates[bacton.coordinates.length - 1];
  assert.ok(tail && distanceKm(tail, [3.2, 51.33]) < distanceKm([1.46, 52.85], [3.2, 51.33]));
});

test("no direction is claimed when the operator is on no listed side", () => {
  const sides = pointSides(nodes, edges);
  assert.equal(orientFlow(flow("ip", "entry", "FR-TSO-0003"), [7.2, 53.2], sides.get("ip")), null);
  assert.equal(orientFlow(flow("ip", "entry", null), [7.2, 53.2], sides.get("ip")), null);
  assert.equal(orientFlow(flow("ttf", "entry", "NL-TSO-0001"), [5.3, 52.4], sides.get("ttf")), null);
  const layers = flowLayers([flow("ip", "entry", "NL-TSO-0001", 200), flow("ip", "exit", "NL-TSO-0001", 20), flow("ip", "entry", "XX")], nodes, edges, identity);
  // One line per point (its larger direction); the chevron sits at the downstream end.
  assert.equal(layers.lines.features.length, 1);
  assert.equal(layers.lines.features[0].properties.direction, "entry");
  assert.equal(layers.lines.features[0].properties.width, 3.5);
  assert.equal(layers.chevrons.features.length, 1);
  assert.equal(layers.oriented, 1);
});

test("the scrubber shows a stored day; latest is each point's newest", () => {
  const situation = {
    flows: [{ point_id: "ITP-1", point_name: "Oude Statenzijl", direction: "entry", gas_day: "2026-11-11", gas_day_start_utc: null, value: 1, unit: "kWh/d", gwh_d: 120, source_system: "ENTSOG", operator_key: "NL-TSO-0001", location: { lon: 7.2, lat: 53.2, ref_id: "ip" } }],
    flow_days: [
      { gas_day: "2026-11-10", flows: [{ point_id: "ITP-1", ref_id: "ip", direction: "entry", gwh_d: 90, operator_key: "NL-TSO-0001", source_system: "ENTSOG" }] },
      { gas_day: "2026-11-11", flows: [{ point_id: "ITP-1", ref_id: "ip", direction: "entry", gwh_d: 120, operator_key: "NL-TSO-0001", source_system: "ENTSOG" }] },
    ],
  } as unknown as MapSituationDTO;
  assert.deepEqual(flowDayOptions(situation), ["2026-11-10", "2026-11-11"]);
  assert.equal(flowsForDay(situation, null)[0].gwhD, 120);
  const day = flowsForDay(situation, "2026-11-10");
  assert.equal(day[0].gwhD, 90);
  assert.equal(day[0].pointName, "Oude Statenzijl");
  assert.deepEqual(flowsForDay(situation, "2026-01-01"), []);
});

test("flows move only when motion is allowed; reduced motion and a hidden page are static", () => {
  assert.equal(flowMotion(true), "static");
  assert.equal(flowMotion(false, false), "static");
  assert.equal(flowMotion(false, true), "animated");
  assert.deepEqual(flowDashAt(5_000, "static"), FLOW_DASH_STATIC);
  assert.deepEqual(flowDashAt(0, "animated"), FLOW_DASH_STEPS[0]);
  assert.notDeepEqual(flowDashAt(70, "animated"), FLOW_DASH_STEPS[0]);
});

test("a moved vessel eases from where it was; a new one appears in place", () => {
  const vessel = (lon: number, lat: number) => ({
    type: "FeatureCollection" as const,
    features: [{ type: "Feature" as const, properties: { id: "C1", basis: "reported" }, geometry: { type: "Point" as const, coordinates: [lon, lat] as [number, number] } }],
  });
  const half = tweenPoints(pointIndex(vessel(10, 62)), vessel(8, 60), 0.5);
  assert.deepEqual(half.features[0].geometry.coordinates, [9, 61]);
  assert.deepEqual(tweenPoints(pointIndex(vessel(10, 62)), vessel(8, 60), 1).features[0].geometry.coordinates, [8, 60]);
  assert.deepEqual(tweenPoints(new Map(), vessel(8, 60), 0.2).features[0].geometry.coordinates, [8, 60]);
});

test("frame behaviour is summarised as median and p95 interval", async () => {
  const { frameSummary } = await import("../src/app/mapSceneFrames.ts");
  const smooth = frameSummary(Array.from({ length: 100 }, () => 16.7));
  assert.deepEqual(smooth, { frames: 100, medianMs: 16.7, p95Ms: 16.7, longShare: 0 });
  const stutter = frameSummary([...Array.from({ length: 90 }, () => 16.7), ...Array.from({ length: 10 }, () => 50)]);
  assert.equal(stutter.p95Ms, 50);
  assert.equal(stutter.longShare, 0.1);
  assert.equal(frameSummary([]).frames, 0);
});

test("the scene's map colours are the series tokens the key's swatches use", async () => {
  const { readFileSync } = await import("node:fs");
  const { SCENE_COLOURS } = await import("../src/app/mapScene.ts");
  const tokens = readFileSync(new URL("../src/styles/tokens.css", import.meta.url), "utf8");
  const values = (name: string) => [...tokens.matchAll(new RegExp(`${name}:\\s*(#[0-9a-f]{6})`, "gi"))].map((m) => m[1].toLowerCase());
  assert.deepEqual(values("--ds-series-5").slice(0, 2), [SCENE_COLOURS.light.lng, SCENE_COLOURS.dark.lng]);
  assert.deepEqual(values("--ds-series-6").slice(0, 2), [SCENE_COLOURS.light.storage, SCENE_COLOURS.dark.storage]);
});

test("cards name each figure's source and age; a country total says what it is", async () => {
  const { assetCard, flowCard } = await import("../src/app/mapSceneCards.ts");
  const en = (await import("../src/i18n/en.json", { with: { type: "json" } })).default as Record<string, string>;
  const t = (key: string, options: Record<string, unknown> = {}) => {
    const template = en[key];
    assert.ok(template, `missing ${key}`);
    return template.replace(/\{\{(\w+)\}\}/g, (_, name: string) => String(options[name] ?? ""));
  };
  const card = assetCard(gate, NOW, t);
  assert.match(card.lines[0], /Published send-out capacity: 400 GWh\/d \(ENTSOG firm technical, gas day 2026-11-12, received 31 h ago\)/);
  assert.match(card.lines[1], /send-out: 300 GWh\/d .* · 75% of capacity/);
  assert.match(card.lines[2], /Inventory \(NL total, not this site\): 2\.1 TWh of 3\.4 TWh \(GIE ALSI, gas day 2026-11-11, received 4 h ago\)/);
  assert.match(card.note ?? "", /approximate/);
  const empty = assetCard(loenhout, NOW, t);
  assert.deepEqual(empty.lines, [en["map.scene.no_capacity"], en["map.scene.no_stock"]]);
  // Storage directions are withdrawal and injection, not entry and exit.
  assert.match(assetCard(bergermeer, NOW, t).lines[0], /Published withdrawal capacity/);
  assert.match(flowCard({ name: "Oude Statenzijl", direction: "entry", gwh_d: 120.4, gas_day: "2026-11-11" }, t).lines[0], /120 GWh\/d, gas day 2026-11-11/);
});
