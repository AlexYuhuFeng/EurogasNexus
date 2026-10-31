/**
 * Semantic zoom: zoomed out the map answers "how is the portfolio doing by country",
 * zoomed in it answers "what exactly is happening at this asset".
 */
import assert from "node:assert/strict";
import test from "node:test";
import type { MapSituationDTO } from "../src/api/client.ts";
import { countrySummaries, detailLabel, zoomTier } from "../src/app/mapSituation.ts";

const situation: MapSituationDTO = {
  as_of_utc: "2026-10-31T09:30:00+00:00",
  outages: [
    {
      event_id: "U1", facility_name: "Easington", asset_type: "transmission", event_type: "Unplanned",
      status: "active", start_utc: "2026-10-31T06:00:00+00:00", end_utc: "2026-11-02T06:00:00+00:00",
      balancing_zone: "GB", unit: "GWh/d", technical_capacity: 800, unavailable_capacity: 300,
      unavailable_gwh_d: 300, unavailable_share: 0.375, description: "", market_participant: "", source_system: "REMIT",
      location: { lon: -0.1, lat: 53.65, country: "GB" },
    },
    {
      event_id: "U2", facility_name: "Emden", asset_type: "transmission", event_type: "Planned",
      status: "scheduled", start_utc: "2026-11-04T06:00:00+00:00", end_utc: null, balancing_zone: "THE",
      unit: "GWh/d", technical_capacity: 900, unavailable_capacity: 120, unavailable_gwh_d: 120,
      unavailable_share: 0.13, description: "", market_participant: "", source_system: "REMIT",
      location: { lon: 7.2, lat: 53.37, country: "DE" },
    },
  ],
  flows: [],
  contracts: [
    { contract_id: "a", contract_name: "A", resource_type: "PIPELINE_IMPORT", delivery_point: "Easington", gas_year: "2026", delivery_mwh_d: 24_000, entry_capacity_mwh_d: null, book_id: "uk", location: { lon: -0.1, lat: 53.65, country: "GB" } },
    { contract_id: "b", contract_name: "B", resource_type: "PIPELINE_IMPORT", delivery_point: "Bacton", gas_year: "2026", delivery_mwh_d: 6_000, entry_capacity_mwh_d: null, book_id: "uk", location: { lon: 1.45, lat: 52.85, country: "GB" } },
  ],
  cargoes: [
    {
      cargo_id: "C1", vessel_name: "Arctic Voyager", vessel_imo: null, status: "laden", load_port: "Hammerfest",
      departed_at_utc: null, destination_terminal: "Gate", eta_utc: "2026-11-02T08:00:00+00:00", position_at_utc: null,
      volume_m3: null, energy_gwh: 980, own: true, book_id: "uk", source_system: "ETRM", origin: null,
      position: { lon: 4.6, lat: 61.5 }, destination: { lon: 4.02, lat: 51.95, country: "NL" }, track: [],
    },
  ],
  regas_slots: [
    { slot_id: "S1", terminal_name: "Gate", window_start_utc: "2026-11-02T00:00:00+00:00", window_end_utc: "2026-11-07T00:00:00+00:00", active: false, send_out_gwh_d: 190, energy_gwh: null, cargo_id: "C1", book_id: "uk", location: { lon: 4.02, lat: 51.95, country: "NL" } },
  ],
  unlocated: { outages: 0, contracts: 0, cargoes: 0, regas_slots: 0 },
  positions_included: true,
};

test("zoom decides the question: overview, region, detail", () => {
  assert.equal(zoomTier(4), "overview");
  assert.equal(zoomTier(6), "region");
  assert.equal(zoomTier(9), "detail");
});

test("overview totals per country, placed at the centre of their activity", () => {
  const rows = Object.fromEntries(countrySummaries(situation).map((row) => [row.country, row]));
  assert.deepEqual(Object.keys(rows).sort(), ["DE", "GB", "NL"]);
  assert.equal(rows.GB.contracts, 2);
  assert.equal(rows.GB.contractedMwhD, 30_000);
  assert.equal(rows.GB.outagesNow, 1);
  assert.equal(rows.GB.unavailableGwhD, 300);
  assert.ok(Math.abs(rows.GB.lon - (-0.1 + 1.45 - 0.1) / 3) < 1e-9);
  assert.equal(rows.DE.outagesScheduled, 1);
  assert.equal(rows.NL.cargoesInbound, 1);
  assert.equal(rows.NL.inboundGwh, 980);
  assert.equal(rows.NL.slots, 1);
});

test("detail labels carry the asset's key figures", () => {
  assert.match(detailLabel("outage", "U1", situation) ?? "", /Easington · −300 GWh\/d · until 02 Nov/);
  assert.match(detailLabel("contract", "a", situation) ?? "", /Easington · 24,000 MWh\/d/);
  assert.match(detailLabel("cargo", "C1", situation) ?? "", /Arctic Voyager · 980 GWh · ETA 02 Nov/);
  assert.match(detailLabel("regas", "Gate", situation) ?? "", /Gate · slot 02 Nov 00:00–07 Nov 00:00 · 190 GWh\/d/);
  assert.equal(detailLabel("cargo", "missing", situation), null);
});
