/**
 * Research's path (owner, 2026-11-19): the spread board's rows open the workbench with their
 * spec; the study travels in the address to Spreads, Cargo & netback and Reports.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import {
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
