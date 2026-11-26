/**
 * Import corridors read as supply corridors with their entry-point flow; one out of service says
 * so and carries no flow. Drawn from whatever edge declares itself a corridor.
 */
import assert from "node:assert/strict";
import test from "node:test";
import type { EdgeDTO, MapPointFlowDTO, NodeDTO } from "../src/api/client.ts";
import { corridorLabel, isSupplyCorridor, supplyCorridors } from "../src/app/mapCorridors.ts";

const t = (key: string) => key;
const node = (id: string, lon: number, lat: number) => ({ id, name: id, node_type: "entry_point", country: "", lon, lat, capacity_boe_d: 0 }) as unknown as NodeDTO;
const nodes = [node("troll", 3.7, 60.6), node("easington", -0.1, 53.65), node("russia", 28, 60), node("lubmin", 13.6, 54.1)];
const edge = (id: string, from: string, to: string, edgeType: string, meta: Record<string, unknown>): EdgeDTO =>
  ({ id, from_node_id: from, to_node_id: to, edge_type: edgeType, length_km: null, metadata_json: meta }) as EdgeDTO;
const edges = [
  edge("langeled", "troll", "easington", "import_corridor", { corridor_name: "Langeled" }),
  edge("ns1", "russia", "lubmin", "pipeline", { corridor: true, corridor_name: "Nord Stream", in_service: false }),
  edge("other", "troll", "lubmin", "market_area_link", {}),
];
const flows = [
  { point_id: "x", point_name: "Easington", direction: "entry", gas_day_start_utc: null, value: null, unit: "kWh/d", gwh_d: 40, source_system: "ENTSOG", operator_key: "A", location: { lon: -0.1, lat: 53.65, ref_id: "easington" } },
  { point_id: "x", point_name: "Easington", direction: "entry", gas_day_start_utc: null, value: null, unit: "kWh/d", gwh_d: 21.4, source_system: "ENTSOG", operator_key: "B", location: { lon: -0.1, lat: 53.65, ref_id: "easington" } },
  { point_id: "y", point_name: "Lubmin", direction: "entry", gas_day_start_utc: null, value: null, unit: "kWh/d", gwh_d: 99, source_system: "ENTSOG", location: { lon: 13.6, lat: 54.1, ref_id: "lubmin" } },
] as unknown as MapPointFlowDTO[];

test("corridors are recognised by type or metadata, and nothing else is", () => {
  assert.deepEqual(edges.map(isSupplyCorridor), [true, true, false]);
});

test("a corridor carries its entry-point flow; one out of service says so, with no flow", () => {
  const [langeled, nordStream] = supplyCorridors(edges, nodes, flows);
  assert.equal(langeled.entryGwhD, 61.4);
  assert.equal(corridorLabel(langeled, t), "Langeled · 61 GWh/d");
  assert.deepEqual(langeled.labelAt, [-0.1, 53.65]);
  assert.equal(nordStream.inService, false);
  assert.equal(nordStream.entryGwhD, null);
  assert.equal(corridorLabel(nordStream, t), "Nord Stream · map.corridor.out_of_service");
});
