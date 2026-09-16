import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import {
  DEFAULT_MARKET_TASK,
  MAJOR_MARKET_HUBS,
  MARKET_TASKS,
  MARKET_VIEW_TASKS,
  marketTaskFromLocation,
  marketTaskFromSearch,
  marketTaskToSearch,
} from "../src/app/model/marketCockpitModel.ts";

function readWebSource(relativePath: string): string {
  return readFileSync(new URL(`../src/${relativePath}`, import.meta.url), "utf8");
}

test("market cockpit has four linked analysis tasks", () => {
  assert.deepEqual(MARKET_TASKS, ["overview", "curves", "network", "capacity"]);
});

test("the numeric and map views are the two separate persisted market views", () => {
  assert.deepEqual(MARKET_VIEW_TASKS, ["curves", "network"]);
  assert.equal(DEFAULT_MARKET_TASK, "curves");
  assert.equal(MARKET_VIEW_TASKS.includes(DEFAULT_MARKET_TASK), true);
  // The fused overview dashboard is an explicit opt-in, never the default.
  assert.equal(DEFAULT_MARKET_TASK === "overview", false);
});

test("legacy technical deep links map to cockpit tasks", () => {
  assert.equal(marketTaskFromLocation("?workspace=network", "network"), "network");
  assert.equal(marketTaskFromLocation("?workspace=capacity", "capacity"), "capacity");
  assert.equal(marketTaskFromLocation("?workspace=market&task=curves", "market"), "curves");
  // The numeric view is the landing task; the fused overview needs `?task=`.
  assert.equal(marketTaskFromLocation("?workspace=market", "market"), "curves");
  assert.equal(marketTaskFromLocation("", "market"), "curves");
  assert.equal(marketTaskFromLocation("?workspace=market&task=overview", "market"), "overview");
  assert.equal(marketTaskFromSearch("?task=overview"), "overview");
  assert.equal(marketTaskFromSearch("?task=network"), "network");
  assert.equal(marketTaskFromSearch("?task=unsupported"), null);
  assert.equal(marketTaskFromSearch(""), null);
});

test("task navigation preserves unrelated trader context query keys", () => {
  assert.equal(
    marketTaskToSearch("?gasDay=2026-09-07&product=day-ahead", "overview"),
    "gasDay=2026-09-07&product=day-ahead&workspace=market&task=overview",
  );
  const context = "?gasDay=2026-09-07&product=day-ahead&hub=TTF&route=route-1";
  const toMap = marketTaskToSearch(context, "network");
  const mapParams = new URLSearchParams(toMap);
  assert.equal(mapParams.get("task"), "network");
  assert.equal(mapParams.get("gasDay"), "2026-09-07");
  assert.equal(mapParams.get("product"), "day-ahead");
  assert.equal(mapParams.get("hub"), "TTF");
  assert.equal(mapParams.get("route"), "route-1");

  const backToNumeric = marketTaskToSearch(toMap, "curves");
  const numericParams = new URLSearchParams(backToNumeric);
  assert.equal(numericParams.get("task"), "curves");
  assert.equal(numericParams.get("gasDay"), "2026-09-07");
  assert.equal(numericParams.get("product"), "day-ahead");
  assert.equal(numericParams.get("hub"), "TTF");
  assert.equal(numericParams.get("route"), "route-1");
});

test("supported major hubs are explicit and finite", () => {
  assert.deepEqual(MAJOR_MARKET_HUBS, ["TTF", "NBP", "ZTP", "THE", "PEG", "PSV"]);
});

test("intraday candidate language stays inside the decision-support boundary", () => {
  const en = JSON.parse(readWebSource("i18n/en.json")) as Record<string, string>;
  const zh = JSON.parse(readWebSource("i18n/zh.json")) as Record<string, string>;

  assert.equal(en["intraday.title"], "Spread candidates for review");
  assert.equal(zh["intraday.title"], "价差候选（供复核）");
  assert.equal(en["intraday.title"].toLowerCase().includes("executable"), false);
  assert.equal(zh["intraday.title"].includes("可执行"), false);
  assert.match(en["intraday.human_review"], /decision support only/i);
  assert.match(en["intraday.human_review"], /before any external action/i);
  assert.match(zh["intraday.human_review"], /仅用于决策支持/);
  assert.match(zh["intraday.human_review"], /任何外部操作前/);
});

test("the market source matrix marks simulated provenance at the source identity", () => {
  const terminal = readWebSource("components/MarketTerminal.tsx");

  assert.match(terminal, /className="market-source-identity"/);
  assert.match(terminal, /market-source-pill simulated matrix-simulation-marker/);
  assert.match(terminal, /t\("market\.simulated_source"\)/);
  assert.equal(terminal.includes(' ? ` / ${t("market.simulated_source")}` : ""'), false);
});

test("the network map explains an evidence-empty state inside the map", () => {
  const network = readWebSource("components/NetworkWorkspace.tsx");
  const en = JSON.parse(readWebSource("i18n/en.json")) as Record<string, string>;
  const zh = JSON.parse(readWebSource("i18n/zh.json")) as Record<string, string>;

  assert.match(network, /!mapHasVisibleEvidence/);
  assert.match(network, /className="map-empty-state"/);
  assert.match(network, /map\.empty_title/);
  assert.match(network, /geometryMessageKey\(networkGeometryState\)/);
  assert.match(network, /map\.empty_help/);
  for (const key of ["map.empty_title", "map.empty_help"]) {
    assert.equal(typeof en[key], "string", `en ${key}`);
    assert.equal(typeof zh[key], "string", `zh ${key}`);
  }
});

test("the market overview renders the data status as a translated label", () => {
  const cockpit = readWebSource("components/MarketCockpit.tsx");
  const en = JSON.parse(readWebSource("i18n/en.json")) as Record<string, string>;
  const zh = JSON.parse(readWebSource("i18n/zh.json")) as Record<string, string>;

  // The overview printed the store's enum value verbatim, so both locales showed
  // the internal token ("runtime") next to a translated label, and the zh
  // surface carried an untranslated English word. It now shares the shell's
  // mapping, so the header, settings and this strip say the same words.
  assert.equal(cockpit.includes("<strong>{api.dataStatus}</strong>"), false);
  assert.match(cockpit, /dataPlaneState\(api\.dataStatus\)/);
  assert.match(cockpit, /t\(dataPlaneLabelKey\(/);

  // Every state the mapping can produce must stay translatable in both locales.
  for (const state of ["ready", "partial", "unavailable"]) {
    assert.equal(typeof en[`data.${state}`], "string", `en data.${state}`);
    assert.equal(typeof zh[`data.${state}`], "string", `zh data.${state}`);
  }
});

