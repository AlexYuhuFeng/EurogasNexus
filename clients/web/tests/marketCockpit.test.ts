import assert from "node:assert/strict";
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
