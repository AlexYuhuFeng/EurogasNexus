/**
 * Research → Cargo & netback (CP-18): the form's request (a voyage the desk enters when no route
 * is saved), the waterfall and line built from the server's figures, and the page's wiring.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import type { CargoResultDTO, CargoTerminalDTO, FreightRouteDTO } from "../src/api/client.ts";
import {
  arrivalMonths,
  cargoRequest,
  exampleForm,
  fieldForBlock,
  henryHub,
  hubSimulatedFlags,
  marginWaterfall,
  monthLabel,
  seriesChart,
  shiftMonth,
} from "../src/app/model/cargoStudy.ts";

const TODAY = new Date(Date.UTC(2026, 10, 18));
const ROUTE: FreightRouteDTO = {
  route_id: "sabine-rotterdam", version: 1, load_port: "Sabine Pass", discharge_port: "Rotterdam",
  discharge_terminal_id: null, routing: "direct", distance_nm: 4900, canal: "none", source: "firm table",
  recorded_by: "a", recorded_at_utc: null,
};

test("months: shift across a year end, desk labels, the arrival list starts this month", () => {
  assert.equal(shiftMonth("2026-12", 1), "2027-01");
  assert.equal(shiftMonth("2027-01", -1), "2026-12");
  assert.equal(monthLabel("2027-01"), "Jan-27");
  assert.deepEqual(arrivalMonths(TODAY, 3), ["2026-11", "2026-12", "2027-01"]);
});

test("no saved routes: the example voyage is entered as a distance at a speed", () => {
  const form = exampleForm(TODAY);
  assert.equal(form.voyageMode, "distance");
  assert.equal(form.arrivalMonth, "2027-01");
  assert.equal(form.pricingMonth, "2026-12");
  assert.equal(form.hh, "", "Henry Hub is the server's: firm mark, licensed, else EIA spot proxy");
  const body = cargoRequest(form);
  const [cargo] = body.cargoes;
  assert.equal(cargo.distance_nm, 4900);
  assert.equal(cargo.speed_kn, 17);
  assert.equal(cargo.route_id, undefined);
  assert.equal("hh" in cargo, false, "an empty field is left out, not sent as zero");
  assert.equal(body.series_months, 12);
});

test("saved routes are offered first; days replace the distance; DES skips the voyage", () => {
  const form = exampleForm(TODAY, [ROUTE]);
  assert.equal(form.voyageMode, "route");
  assert.equal(cargoRequest(form).cargoes[0].route_id, "sabine-rotterdam");
  const days = cargoRequest({ ...form, voyageMode: "days", ladenDays: "12.5" }).cargoes[0];
  assert.equal(days.laden_days, 12.5);
  assert.equal(days.distance_nm, undefined);
  assert.equal(days.route_id, undefined);
  const des = cargoRequest({ ...form, term: "DES", desPrice: "30,00".replace(",", ".") });
  assert.equal(des.cargoes[0].des_price, 30);
  assert.equal(des.cargoes[0].hire_per_day, undefined);
  assert.equal(des.series_months, 0);
});

test("a blocked cargo points at the field that answers it", () => {
  assert.equal(fieldForBlock("no_hh_price"), "hh");
  assert.equal(fieldForBlock("no_distance"), "distanceNm");
  assert.equal(fieldForBlock("no_charter_hire"), "hire");
  assert.equal(fieldForBlock("something_else"), null);
});

const ROW: CargoTerminalDTO = {
  terminal_id: "gate", name: "Gate", hub: "TTF", currency: "EUR", arrival_month: "2027-01", reason: null,
  cost_per_mwh: 20.71, netback_per_mwh: 28.45, margin_per_mwh: 7.74, margin_usd_mmbtu: 2.63, margin_total: 8.5e6,
  lifting_margin_per_mwh: 15.2, margin_low_per_mwh: 7.1, margin_high_per_mwh: 8.0, regas_basis: "firm_terms",
  grade: "simulated", assumptions: 9, excludes: [],
  legs: [{ key: "hub", label: "TTF 2027-01", amount: 30, unit: "EUR/MWh", input_class: "simulated", source: "demo" }],
  steps: [
    { key: "hub", amount: 30, kind: "total" },
    { key: "gas_in_kind", amount: -0.15, kind: "delta" },
    { key: "entry", amount: -0.4478, kind: "delta" },
    { key: "regas", amount: -0.95, kind: "delta" },
    { key: "netback", amount: 28.4522, kind: "total" },
    { key: "fob", amount: -19.1933, kind: "delta" },
    { key: "boil_off", amount: -0.2331, kind: "delta" },
    { key: "freight", amount: -1.2843, kind: "delta" },
    { key: "margin", amount: 7.7415, kind: "total" },
  ],
};

test("the margin waterfall is the server's steps, labelled, with the simulated hub marked", () => {
  const items = marginWaterfall(ROW, { step: (key) => `step:${key}`, hub: (hub, month) => `${hub} ${monthLabel(month)}` });
  assert.deepEqual(items.map((item) => item.id), ["hub", "gas_in_kind", "entry", "regas", "netback", "fob", "boil_off", "freight", "margin"]);
  assert.equal(items[0].label, "TTF Jan-27");
  assert.equal(items[0].simulated, true);
  assert.equal(items[1].simulated, false);
  // The steps reconcile: the deltas from netback land on the margin.
  const margin = items[4].value + items[5].value + items[6].value + items[7].value;
  assert.ok(Math.abs(margin - items[8].value) < 1e-3);
});

test("Henry Hub states its basis; the simulated scope reads the hub legs", () => {
  const cargo = {
    legs: [{ key: "hh", label: "Henry Hub", amount: 3.1, unit: "USD/MMBtu", input_class: "indicative", source: "Henry Hub spot 2026-11-16 (EIA), spot proxy for 2026-12" }],
    terminals: [ROW, { ...ROW, terminal_id: "zee", legs: [{ ...ROW.legs[0], input_class: "firm_mark" }] }, { ...ROW, terminal_id: "x", reason: "no_fx" }],
  } as unknown as CargoResultDTO;
  assert.deepEqual(henryHub(cargo), { value: 3.1, inputClass: "indicative", source: cargo.legs[0].source, proxy: true, day: "2026-11-16", demo: false });
  assert.deepEqual(hubSimulatedFlags(cargo), [true, false], "left-out rows do not count");
  assert.equal(henryHub({ legs: [] } as unknown as CargoResultDTO), null);
});

test("the delivered-spread line: hub and delivered cost by arrival month", () => {
  const chart = seriesChart({
    terminal_id: "gate", cargo_id: "study",
    points: [
      { arrival_month: "2027-01", pricing_month: "2026-12", reason: null, hh: 3.5, hh_class: "assumption", hub_per_mwh: 30, delivered_per_mwh: 22.2, arb_per_mwh: 7.8, grade: "simulated" },
      { arrival_month: "2027-02", pricing_month: "2027-01", reason: "no_hub_price", hh: 3.5, hh_class: "assumption", hub_per_mwh: null, delivered_per_mwh: null, arb_per_mwh: null, grade: "missing" },
    ],
  });
  assert.deepEqual(chart.x, ["2027-01", "2027-02"]);
  assert.deepEqual(chart.hub, [30, null]);
  assert.equal(chart.priced, 1);
  assert.equal(chart.simulated, true);
});

test("Research has a Cargo & netback task rendered by the study; it uses the shared simulated scope", () => {
  const renderer = readFileSync(new URL("../src/app/workspaces/WorkspaceRenderer.tsx", import.meta.url), "utf8");
  assert.match(renderer, /researchTask === "cargo" && <CargoStudy \/>/);
  const study = readFileSync(new URL("../src/components/research/CargoStudy.tsx", import.meta.url), "utf8");
  assert.match(study, /from "@\/components\/ui\/SimulatedScope"/);
  assert.match(study, /api\.freightRoutes\(\)/);
  assert.match(study, /api\.cargoEconomics\(/);
  // Units through the one desk-unit rule shared with Prices and Today.
  assert.match(study, /unitLabel\(/);
  for (const name of ["en", "zh"] as const) {
    const locale = JSON.parse(readFileSync(new URL(`../src/i18n/${name}.json`, import.meta.url), "utf8")) as Record<string, string>;
    assert.ok(locale["nav.mode.research.cargo"]);
    assert.ok(locale["cargo.voyage.note_none"]);
    assert.ok(locale["cargo.hh.proxy"]);
  }
});

test("NBP's hub price in p/th with the per-MWh figure beside it; Henry Hub's proxy day; the daily line", async () => {
  const { hubQuote, historyChart, henryHub: hh } = await import("../src/app/model/cargoStudy.ts");
  const nbp = hubQuote("NBP", 35.7, "GBP");
  assert.equal(nbp.native, true);
  assert.equal(nbp.unit, "GBp/th");
  assert.ok(Math.abs((nbp.value ?? 0) - 104.626) < 0.01, "35.70 GBP/MWh = 104.63 p/th");
  assert.equal(nbp.perMwh, 35.7);
  assert.deepEqual(hubQuote("TTF", 40.4, "EUR"), { value: 40.4, unit: "EUR/MWh", perMwh: 40.4, native: false });
  const cargo = { legs: [{ key: "hh", label: "", amount: 4.07, unit: "USD/MMBtu", input_class: "simulated", source: "Henry Hub spot 2026-11-18 (demo, simulated), spot proxy for 2026-12" }] } as unknown as CargoResultDTO;
  const held = hh(cargo)!;
  assert.equal(held.day, "2026-11-18");
  assert.equal(held.demo, true);
  const chart = historyChart({
    terminal_id: "gate", hub: "TTF", currency: "EUR", fx: "FX", hh_source: "EIA", hh_days: 2,
    points: [
      { day: "2026-11-16", hh: 3.1, hub_per_mwh: 31, delivered_per_mwh: 21, arb_per_mwh: 10, simulated: false },
      { day: "2026-11-17", hh: 3.2, hub_per_mwh: 31.5, delivered_per_mwh: 21.4, arb_per_mwh: 10.1, simulated: false },
    ],
  });
  assert.deepEqual(chart.x, ["2026-11-16", "2026-11-17"]);
  assert.equal(chart.last?.arb_per_mwh, 10.1);
  assert.equal(chart.simulated, false);
});

test("an assumption set picked from the firm's records leaves its figures to the set; terminals chosen are sent", async () => {
  const { withSet, SET_FIELDS } = await import("../src/app/model/cargoStudy.ts");
  const form = withSet(exampleForm(TODAY), "lng-desk");
  for (const field of SET_FIELDS) assert.equal(form[field], "", field);
  assert.equal(form.distanceNm, "4900", "the voyage is not in a set: it stays");
  const body = cargoRequest({ ...form, terminalIds: ["demo-gate"] });
  assert.equal(body.assumption_set_id, "lng-desk");
  assert.deepEqual(body.terminal_ids, ["demo-gate"]);
  assert.equal(body.cargoes[0].hire_per_day, undefined, "the set's hire applies");
  assert.equal("assumption_set_id" in cargoRequest(exampleForm(TODAY)), false);
});
