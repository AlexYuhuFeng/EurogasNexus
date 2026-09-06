import assert from "node:assert/strict";
import test from "node:test";
import {
  MAJOR_MARKET_HUBS,
  MARKET_TASKS,
  marketTaskFromLocation,
  marketTaskToSearch,
} from "../src/app/model/marketCockpitModel.ts";

test("market cockpit has four linked analysis tasks", () => {
  assert.deepEqual(MARKET_TASKS, ["overview", "curves", "network", "capacity"]);
});

test("legacy technical deep links map to cockpit tasks", () => {
  assert.equal(marketTaskFromLocation("?workspace=network", "network"), "network");
  assert.equal(marketTaskFromLocation("?workspace=capacity", "capacity"), "capacity");
  assert.equal(marketTaskFromLocation("?workspace=market&task=curves", "market"), "curves");
  assert.equal(marketTaskFromLocation("?workspace=market", "market"), "overview");
});

test("task navigation preserves unrelated trader context query keys", () => {
  assert.equal(
    marketTaskToSearch("?gasDay=2026-09-07&product=day-ahead", "overview"),
    "gasDay=2026-09-07&product=day-ahead&workspace=market&task=overview",
  );
});

test("supported major hubs are explicit and finite", () => {
  assert.deepEqual(MAJOR_MARKET_HUBS, ["TTF", "NBP", "ZTP", "THE", "PEG", "PSV"]);
});
