/**
 * Research's path (owner, 2026-11-19): the spread board's rows open the workbench with their
 * spec; the study travels in the address to Spreads, Cargo & netback and Reports.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import {
  boardReasonText,
  cargoHubOf,
  cargoSearch,
  focusHubs,
  fullSpec,
  hubFromSearch,
  rangePosition,
  reportSearch,
  routeGap,
  specFromSearch,
  specName,
  spreadsSearch,
  storageStep,
} from "../src/app/model/spreadsBoard.ts";

test("a board row's spec is completed and travels in the address to Spreads", () => {
  const spec = fullSpec({ kind: "curve", legs: [{ hub: "THE", tenor: null, weight: 1 }, { hub: "TTF", tenor: null, weight: -1 }], cost: { kind: "route_tariff", from_hub: "TTF", to_hub: "THE" } });
  assert.equal(spec.version, 1);
  assert.equal(spec.fx, "forward");
  assert.equal(spec.lookback_days, 365);
  const search = spreadsSearch("?workspace=research&task=fundamentals&view=storage&gasDay=2026-11-19", spec);
  const params = new URLSearchParams(search);
  assert.equal(params.get("task"), "spreads");
  assert.equal(params.get("view"), null, "the previous page's tab does not travel");
  assert.equal(params.get("gasDay"), "2026-11-19", "the context does");
  assert.deepEqual(specFromSearch(search), spec);
  assert.equal(specFromSearch("?spec=not-json"), null);
  assert.equal(specName(spec), "THE − TTF");
});

test("from a spread to a cargo against its hub, and to an asked report", () => {
  const spec = fullSpec({ legs: [{ hub: "NBP", tenor: null, weight: 1 }, { hub: "TTF", tenor: null, weight: -1 }] });
  assert.equal(cargoHubOf(spec), "NBP");
  const cargo = cargoSearch("?workspace=research&task=spreads&spec=x", "NBP");
  assert.equal(hubFromSearch(cargo), "NBP");
  assert.equal(new URLSearchParams(cargo).get("spec"), null);
  const report = new URLSearchParams(reportSearch("", "NBP − TTF: what moves it"));
  assert.equal(report.get("task"), "reports");
  assert.equal(report.get("ask"), "NBP − TTF: what moves it");
});

test("focus hubs, the range position, a route's gap and the storage step", () => {
  assert.deepEqual(focusHubs("nbp, THE;the  x1 PEG"), ["NBP", "THE", "PEG"]);
  assert.deepEqual(focusHubs(null), []);
  assert.equal(rangePosition({ tenor: "MA", available: true, percentile: null }), null);
  assert.deepEqual(rangePosition({ tenor: "MA", available: true, percentile: 73, range: { low: 0.2, high: 1.2, days: 365 } }), { position: 73, low: 0.2, high: 1.2, days: 365 });
  const route = { hubs: ["NBP", "ZTP", "PEG"], through: ["ZTP"], complete: false, missing: ["Bacton (IUK) exit (National Gas TSO)"], product: "ANNUAL", gas_years: [], issues: [] };
  assert.equal(routeGap({ tenor: "MA", available: true, route }), "Bacton (IUK) exit (National Gas TSO)");
  assert.equal(routeGap({ tenor: "MA", available: true, route: { ...route, complete: true } }), null);
  assert.deepEqual(storageStep(-12.04), { tone: "below", pts: 12 });
  assert.deepEqual(storageStep(0.4), { tone: "near", pts: 0.4 });
  assert.equal(storageStep(null), null);
});

test("Research opens on Fundamentals; Spreads opens on the board; each page carries its next step", () => {
  const renderer = readFileSync(new URL("../src/app/workspaces/WorkspaceRenderer.tsx", import.meta.url), "utf8");
  assert.match(renderer, /researchTask === "spreads" && <SpreadsWorkbench \/>/);
  const spreads = readFileSync(new URL("../src/components/research/SpreadsWorkbench.tsx", import.meta.url), "utf8");
  assert.match(spreads, /api\.spreadsBoard\(/);
  assert.doesNotMatch(spreads, /evaluate\(defaultSpec/, "no default study replaces the board");
  assert.match(spreads, /<SpreadNextSteps/);
  const cargo = readFileSync(new URL("../src/components/research/CargoStudy.tsx", import.meta.url), "utf8");
  assert.match(cargo, /standardForm\(/);
  assert.match(cargo, /<CargoNextSteps/);
  const fundamentals = readFileSync(new URL("../src/components/research/FundamentalsWorkbench.tsx", import.meta.url), "utf8");
  assert.match(fundamentals, /<FundamentalsNextSteps/);
});

test("a board reason is said in the reader's language from its code, months as the desk writes them", () => {
  const en = JSON.parse(readFileSync(new URL("../src/i18n/en.json", import.meta.url), "utf8")) as Record<string, string>;
  const zh = JSON.parse(readFileSync(new URL("../src/i18n/zh.json", import.meta.url), "utf8")) as Record<string, string>;
  const translate = (table: Record<string, string>) => (key: string, options: Record<string, unknown> = {}) => {
    const count = options.count;
    const text = table[count === undefined ? key : `${key}_${count === 1 ? "one" : "other"}`] ?? table[key] ?? String(options.defaultValue ?? key);
    return text.replace(/\{\{(\w+)\}\}/g, (_whole, name: string) => String(options[name] ?? ""));
  };
  const spark = { reason: "no power price held; no carbon (EUA) price held", reasons: [{ code: "no_power_price" }, { code: "no_carbon_price" }] };
  assert.equal(boardReasonText(spark, translate(en)), "no power price held; no carbon (EUA) price held");
  assert.equal(boardReasonText(spark, translate(zh)), "未持有电力价格；未持有碳（EUA）价格");
  assert.equal(boardReasonText({ reasons: [{ code: "months_not_held", params: { months: ["2027-04", "2027-05"] } }] }, translate(zh)), "未持有的月份：Apr-27, May-27");
  assert.equal(boardReasonText({ reasons: [{ code: "cargo.no_hh_price" }] }, translate(en)), "no HH price");
  assert.equal(boardReasonText({ reason: "an older server's sentence" }, translate(zh)), "an older server's sentence");
  for (const key of Object.keys(en).filter((name) => name.startsWith("spreads.reason."))) assert.ok(key in zh, key);
});
