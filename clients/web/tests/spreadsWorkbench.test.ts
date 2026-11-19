/**
 * Research → Spreads (CP-16/CP-23): the spec edits the "Understood as" chips make, answers to
 * the server's questions, the chart and waterfall from a result, and the answer bar opening
 * Spreads for a spread study (EN and ZH).
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import type { UnitsReferenceDTO } from "../src/api/client.ts";
import type { CurveResultDTO, StrategySpecDTO } from "../src/api/spreads.ts";
import { instantAnswer } from "../src/app/answer/instant.ts";
import { routeQuery } from "../src/app/answer/route.ts";
import { hubsNamed, spreadStudy } from "../src/app/answer/strategy.ts";
import {
  applyChoice,
  curveChart,
  curveClasses,
  defaultSpec,
  describeFromSearch,
  frontWaterfall,
  setKind,
  setLegHub,
  spreadName,
  swapDirection,
  toggleCost,
  weakestClass,
} from "../src/app/model/spreadsWorkbench.ts";

const UNITS = JSON.parse(readFileSync(new URL("./fixtures/unitsReference.json", import.meta.url), "utf8")) as UnitsReferenceDTO;

test("the default view: NBP over TTF by delivery month, net of the TTF → NBP route", () => {
  const spec = defaultSpec(["TTF", "NBP", "THE"]);
  assert.equal(spreadName(spec), "NBP − TTF");
  assert.deepEqual(spec.cost, { kind: "route_tariff", from_hub: "TTF", to_hub: "NBP" });
  assert.equal(defaultSpec(["TTF", "THE"]).legs[0].hub, "THE");
});

test("chips: swapping turns the spread and the route round together; a route follows its hub", () => {
  const spec = defaultSpec(["TTF", "NBP"]);
  const swapped = swapDirection(spec);
  assert.equal(spreadName(swapped), "TTF − NBP");
  assert.deepEqual(swapped.cost, { kind: "route_tariff", from_hub: "NBP", to_hub: "TTF" });
  const moved = setLegHub(spec, 1, "ZTP");
  assert.deepEqual(moved.cost, { kind: "route_tariff", from_hub: "ZTP", to_hub: "NBP" });
  const off = toggleCost(spec);
  assert.equal(off.cost, null);
  assert.deepEqual(toggleCost(off).cost, spec.cost);
  const history = setKind(spec, "history");
  assert.deepEqual(history.legs.map((leg) => leg.tenor), ["M+1", "M+1"]);
  assert.equal(setKind(history, "curve").legs[0].tenor, null);
});

test("answers to the server's questions edit the spec", () => {
  const spec: StrategySpecDTO = { ...defaultSpec(["TTF", "NBP"]), legs: [{ hub: "XYZ", tenor: null, weight: 1 }, { hub: "TTF", tenor: null, weight: -1 }] };
  const fixed = applyChoice(spec, { code: "hub_not_held", field: "legs[0].hub", message: "", choices: ["NBP"] }, "NBP");
  assert.equal(fixed.legs[0].hub, "NBP");
  assert.equal(applyChoice(spec, { code: "route_unproven", field: "cost", message: "", choices: ["no_cost"] }, "no_cost").cost, null);
  assert.equal(applyChoice(spec, { code: "no_curve", field: "legs[0].hub", message: "", choices: ["history"] }, "history").kind, "history");
  const tenor = applyChoice(setKind(spec, "history"), { code: "tenor_not_held", field: "legs[1].tenor", message: "", choices: ["Jan-27"] }, "Jan-27");
  assert.equal(tenor.legs[1].tenor, "Jan-27");
});

const RESULT = {
  kind: "curve",
  unit: "EUR/MWh",
  fx_mode: "forward",
  fx_labels: [],
  months: 2,
  input_class: "indicative",
  simulated: false,
  empty: null,
  spread: "NBP − TTF",
  route: {
    from_hub: "TTF", to_hub: "NBP", direction: "TTF → NBP", proven: true, via: ["BBL"], total: 1.88, currency: "EUR", complete: true,
    gas_years: ["2026/27"], input_class: "sourced", missing: [], load_factor: "100 %",
    legs: [
      { point_name: "Julianadorp", tso: "GTS", direction: "EXIT", role: "market_area_exit", value: 0.56, currency: "EUR", gas_year: "2026/27", status: "FINAL", input_class: "sourced" },
      { point_name: "Bacton (BBL)", tso: "BBL company", direction: "EXIT", role: "pipeline", value: 1.2, currency: "EUR", gas_year: "2026/27", status: "FINAL", input_class: "sourced" },
      { point_name: "Bacton (BBL)", tso: "National Gas TSO", direction: "ENTRY", role: "market_area_entry", value: 0.12, currency: "EUR", gas_year: "2026/27", status: "FINAL", input_class: "sourced" },
    ],
  },
  rows: [
    {
      month: "2027-01-01", label: "Jan-27", gross: 0.5, cost: 1.88, net: -1.38, refused: null, cost_class: "sourced", input_class: "indicative", simulated: false,
      legs: [
        { hub: "NBP", weight: 1, native_value: 78, native_unit: "p/th", value: 30.5, source_system: "S", observed: "2026-11-16", input_class: "derived", price_class: "indicative", fx: { input_class: "derived" } },
        { hub: "TTF", weight: -1, native_value: 30, native_unit: "EUR/MWh", value: 30, source_system: "S", observed: "2026-11-16", input_class: "indicative", price_class: "indicative", fx: null },
      ],
    },
    { month: "2027-02-01", label: "Feb-27", gross: null, cost: null, net: null, refused: "not convertible: no EURGBP rate held", input_class: "missing", simulated: false, legs: [] },
  ],
} as unknown as CurveResultDTO;

test("the result: net as the line, gross as context, the front month as a reconciling waterfall", () => {
  const chart = curveChart(RESULT);
  assert.deepEqual(chart.x, ["2027-01"]);
  assert.deepEqual(chart.net, [-1.38]);
  assert.deepEqual(chart.gross, [0.5]);
  assert.equal(chart.hasCost, true);
  const fall = frontWaterfall(RESULT, { gross: "Gross", net: "Net", leg: (hub) => hub });
  assert.ok(fall);
  assert.deepEqual(fall.items.map((item) => item.id), ["gross", "tariff-0", "tariff-1", "tariff-2", "net"]);
  const sum = fall.items.filter((item) => item.kind !== "total").reduce((total, item) => total + item.value, 0.5);
  assert.ok(Math.abs(sum - -1.38) < 1e-9, `steps reconcile to the net (${sum})`);
  assert.deepEqual(curveClasses(RESULT), ["missing", "indicative", "derived", "sourced"]);
  assert.equal(weakestClass(["sourced", "simulated", "derived"]), "simulated");
});

test("a link carries the description; a too-short one is ignored", () => {
  assert.equal(describeFromSearch("?workspace=research&task=spreads&describe=NBP%20vs%20TTF"), "NBP vs TTF");
  assert.equal(describeFromSearch("?describe=ab"), null);
});

test("answer bar: a spread study opens Research → Spreads with the text, EN and ZH", () => {
  const context = { units: UNITS, fx: null, glossary: [], bookAllowed: true, zh: false, now: new Date("2026-11-16T12:00:00Z") };
  for (const text of ["forward spread net of transport tariff between TTF and NBP", "NBP vs TTF front month", "英国和荷兰之间的价差"]) {
    const route = routeQuery(text, context);
    assert.equal(route.kind, "spreads", text);
    const answer = instantAnswer(route);
    assert.deepEqual(answer?.target, { kind: "task", mode: "research", task: "spreads", params: { describe: text } });
  }
  // A price look-up or a single hub is not a spread study.
  assert.equal(spreadStudy("TTF Jan-27"), null);
  assert.equal(spreadStudy("the spread"), null);
  assert.equal(routeQuery("TTF Dec-26", context).kind, "lookup");
  assert.deepEqual(hubsNamed("the THE vs TTF"), ["THE", "TTF"]);
});

test("examples follow the interface language; the route the desk picks goes into the spec", async () => {
  const { pickRoute, routeVia } = await import("../src/app/model/spreadsWorkbench.ts");
  const source = readFileSync(new URL("../src/components/research/SpreadsWorkbench.tsx", import.meta.url), "utf8");
  const keys = [...(/const EXAMPLES = \[([^\]]*)\]/.exec(source)?.[1] ?? "").matchAll(/"([^"]+)"/g)].map((m) => m[1]);
  assert.equal(keys.length, 3);
  for (const name of ["en", "zh"] as const) {
    const locale = JSON.parse(readFileSync(new URL(`../src/i18n/${name}.json`, import.meta.url), "utf8")) as Record<string, string>;
    for (const key of keys) {
      const cjk = /[一-鿿]/.test(locale[key]);
      assert.equal(cjk, name === "zh", `${name} ${key}: ${locale[key]}`);
    }
  }
  const spec = { ...defaultSpec(["NBP", "PEG"]), cost: { kind: "route_tariff" as const, from_hub: "NBP", to_hub: "PEG" } };
  assert.deepEqual(pickRoute(spec, ["TTF", "THE"]).cost?.through, ["TTF", "THE"]);
  assert.equal("through" in (pickRoute(pickRoute(spec, ["ZTP"]), null).cost ?? {}), false);
  assert.deepEqual(routeVia(["NBP", "ZTP", "PEG"]), ["ZTP"]);
  assert.deepEqual(routeVia(["TTF", "NBP"]), []);
});
