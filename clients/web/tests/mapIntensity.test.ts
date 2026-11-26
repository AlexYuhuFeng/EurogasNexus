/**
 * Intensity on the flat map: each mark encodes a stored figure (circle area or line width) and
 * what it is (colour); no figure, no mark; at Europe zoom flow is one net figure per border.
 */
import assert from "node:assert/strict";
import test from "node:test";
import type { EdgeDTO, MapSituationDTO, NodeDTO } from "../src/api/client.ts";
import { borderFlows, intensityColour, intensityPoints, intensityRadius, rankIntensity } from "../src/app/mapIntensity.ts";

const node = (id: string, lon: number, lat: number) => ({ id, name: id.toUpperCase(), node_type: "interconnection", country: "DE", lon, lat, capacity_boe_d: 0 }) as unknown as NodeDTO;
const nodes = [node("a", 7, 53), node("b", 8, 52), node("c", 9, 51)];
const flow = (ref: string, direction: string, gwh: number) => ({
  point_id: ref, point_name: ref, direction, gas_day: "2026-11-25", gas_day_start_utc: null, value: null, unit: "kWh/d",
  gwh_d: gwh, source_system: "ENTSOG", location: { lon: 0, lat: 0, ref_id: ref },
});
const situation = {
  as_of_utc: "", contracts: [], cargoes: [], regas_slots: [], unlocated: {}, positions_included: true,
  flows: [flow("a", "entry", 100), flow("a", "exit", 98), flow("b", "exit", 40)],
  outages: [
    { event_id: "o1", facility_name: "Field", status: "active", unavailable_gwh_d: 60, start_utc: "2026-11-23T00:00:00Z", source_system: "REMIT", location: { lon: 2, lat: 60 } },
    { event_id: "o2", facility_name: "Later", status: "scheduled", unavailable_gwh_d: 90, start_utc: "2026-12-03T00:00:00Z", source_system: "REMIT", location: { lon: 2, lat: 60 } },
  ],
  assets: [
    { asset_id: "s", kind: "storage", name: "Store", country: "DE", eic: null, location: { lon: 10, lat: 50 }, capacity: [], stock: null, flow: [{ direction: "exit", gwh_d: 30, gas_day: "2026-11-25", operator_key: null, source_system: "ENTSOG" }] },
  ],
} as unknown as MapSituationDTO;
const edges = [{ id: "e", from_node_id: "a", to_node_id: "x", edge_type: "market_area_link", length_km: null, metadata_json: { firm_technical_kwh_d: 200e6 } }] as EdgeDTO[];
const palette = { into: "IN", out: "OUT", outage: "RED", ramp: ["R0", "R1", "R2", "R3"] };

test("flow: one column per point, the larger side its figure and direction", () => {
  const points = intensityPoints("flow", { situation, nodes, edges, flowDay: null });
  assert.deepEqual(points.map((item) => [item.id, item.value, item.direction]), [["a", 100, "in"], ["b", 40, "out"]]);
  assert.equal(points[0].gasDay, "2026-11-25");
  assert.equal(points[0].source, "ENTSOG");
});

test("utilisation: only points with a published, plausible capacity; colour by band", () => {
  const points = intensityPoints("utilisation", { situation, nodes, edges, flowDay: null });
  assert.deepEqual(points.map((item) => [item.id, item.ratio]), [["a", 0.5]]);
  assert.equal(intensityColour("utilisation", points[0], palette), "R1");
  const placeholder = [{ ...edges[0], metadata_json: { firm_technical_kwh_d: 24_000e6 } }] as EdgeDTO[];
  assert.equal(intensityPoints("utilisation", { situation, nodes, edges: placeholder, flowDay: null }).length, 0);
});

test("outage impact and storage come from what is stored; no figure, no column", () => {
  const outages = intensityPoints("outage", { situation, nodes, edges, flowDay: null });
  assert.deepEqual(outages.map((item) => [item.id, item.value]), [["o1", 60]]);
  const storage = intensityPoints("storage", { situation, nodes, edges, flowDay: null });
  assert.deepEqual(storage.map((item) => [item.id, item.value, item.direction]), [["s", 30, "out"]]);
  assert.deepEqual(intensityPoints("flow", { situation: { ...situation, flows: [] }, nodes, edges, flowDay: null }), []);
});

test("a border nets its points' flows between two market areas, oriented by operator side", () => {
  const sided = [
    { id: "1", from_node_id: "a", to_node_id: "THE", edge_type: "market_area_link", length_km: null, metadata_json: { operators: ["DE-OP"] } },
    { id: "2", from_node_id: "a", to_node_id: "TTF", edge_type: "market_area_link", length_km: null, metadata_json: { operators: ["NL-OP"] } },
    { id: "3", from_node_id: "b", to_node_id: "THE", edge_type: "market_area_link", length_km: null, metadata_json: { operators: ["DE-OP"] } },
    { id: "4", from_node_id: "b", to_node_id: "TTF", edge_type: "market_area_link", length_km: null, metadata_json: { operators: ["NL-OP"] } },
  ] as EdgeDTO[];
  const withOperators = {
    ...situation,
    flows: [
      { ...flow("a", "entry", 100), operator_key: "DE-OP" },
      { ...flow("b", "entry", 30), operator_key: "NL-OP" },
    ],
  } as unknown as MapSituationDTO;
  const [border] = borderFlows({ situation: withOperators, edges: sided, flowDay: null });
  // 100 into THE at a, 30 into TTF at b: net 70 from TTF to THE.
  assert.deepEqual([border.fromId, border.toId, border.value, border.points], ["TTF", "THE", 70, 2]);
});

test("circles are sized by area against the largest; the panel ranks the top ten", () => {
  assert.equal(intensityRadius(25, 100), 13);
  assert.equal(intensityRadius(0, 100), 0);
  const points = intensityPoints("flow", { situation, nodes, edges, flowDay: null });
  assert.deepEqual(rankIntensity(points, 1).map((item) => item.id), ["a"]);
  assert.equal(intensityColour("flow", points[1], palette), "OUT");
});
