/**
 * Supply corridors: solid on a SciGRID path, dashed when schematic; in service carries its flow
 * width and an arrow, out of service is grey with none; an unknown flow is "not published".
 */
import assert from "node:assert/strict";
import test from "node:test";
import type { SupplyCorridorDTO } from "../src/api/client.ts";
import {
  corridorFlowDay,
  corridorFlowText,
  corridorLabel,
  corridorLines,
  corridorWidth,
} from "../src/app/mapCorridors.ts";

const t = (key: string, options?: Record<string, unknown>) => (options ? `${key}${JSON.stringify(options)}` : key);
const corridor = (overrides: Partial<SupplyCorridorDTO>): SupplyCorridorDTO => ({
  id: "x", name: "Langeled", group: "norway", source_country: "NO",
  source: { place: "Nyhamna", lon: 6.9, lat: 62.8, position_quality: "scigrid_node" },
  operator: { operator_key: "NO-TSO-0001", name: "Gassco AS" },
  landing_points: [{ point_key: "ITP-00091", name: "Easington", node_id: "n", lon: 0.19, lat: 53.66 }],
  into_market_areas: ["NBP"], capacity: { firm_technical_kwh_d: 1.06e9, gas_day: "2026-11-25", citation: "ENTSOG" },
  status: "in_service", since: null, status_source: { citation: "ENTSOG" },
  geometry: { basis: "reference_pipeline_direction", coordinates: [[6.9, 62.8], [0.19, 53.66]] },
  flow_series: [{ point_key: "ITP-00091", operator_key: "UK", latest_flow: { energy_gwh_d: 61.4, gas_day_start_utc: "2026-11-24T05:00:00+00:00", source_system: "ENTSOG" } }],
  latest_flow_gwh_d: 61.4,
  ...overrides,
});

test("labels say the flow, out of service since a year, or not published", () => {
  assert.equal(corridorLabel(corridor({}), t), "Langeled · 61 GWh/d");
  assert.equal(corridorLabel(corridor({ name: "Nord Stream 1", status: "out_of_service", since: "2022-09-01", latest_flow_gwh_d: null }), t), 'Nord Stream 1 · map.corridor.out_since{"year":"2022"}');
  assert.equal(corridorLabel(corridor({ name: "Norpipe", status: "not_published", latest_flow_gwh_d: null }), t), "Norpipe · map.corridor.not_published");
  assert.equal(corridorFlowDay(corridor({})), "2026-11-24");
});

test("a shared entry point names its point and keeps the figure off the map", () => {
  const shared = corridor({ shared_entry_point: true, latest_flow_gwh_d: 794 });
  assert.equal(corridorLabel(shared, t), "Langeled · map.corridor.shared");
  assert.doesNotMatch(corridorLabel(shared, t), /794/);
  assert.equal(
    corridorFlowText(shared, t),
    'map.corridor.card.shared_flow{"point":"Easington","flow":"794 GWh/d"}',
  );
  // An ordinary corridor still shows its own flow in the panel.
  assert.equal(corridorFlowText(corridor({}), t), "61 GWh/d");
  assert.equal(corridorFlowText(corridor({ latest_flow_gwh_d: null }), t), "map.corridor.not_published");
});

test("lines: dashed when schematic, flow width in service, thin grey out of service", () => {
  const [inService, out, schematic] = corridorLines([
    corridor({}),
    corridor({ id: "ns", status: "out_of_service", latest_flow_gwh_d: null }),
    corridor({ id: "s", latest_flow_gwh_d: 15.35, geometry: { basis: "schematic", coordinates: [[10, 30], [12, 37]] } }),
  ]);
  assert.equal(inService.width, 5);
  assert.equal(inService.schematic, false);
  assert.deepEqual(inService.landing, [0.19, 53.66]);
  assert.equal(out.inService, false);
  assert.equal(out.width, 1.2);
  assert.equal(schematic.schematic, true);
  assert.equal(schematic.width, 3.3);
  assert.equal(corridorWidth(null, 100, true), 1.5);
});
