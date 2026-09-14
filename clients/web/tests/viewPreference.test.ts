import assert from "node:assert/strict";
import test from "node:test";
import {
  DEFAULT_MARKET_VIEW_PREFERENCE,
  MARKET_SHELL_PAGE_ID,
  MARKET_VIEW_PREFERENCE_ANONYMOUS_PRINCIPAL,
  MARKET_VIEW_PREFERENCE_IDS,
  MARKET_VIEW_PREFERENCE_STORAGE_KEY,
  isMarketViewPreferenceId,
  marketViewLandingPage,
  marketViewLandingPageCandidate,
  marketViewPreferenceForTask,
  marketViewPreferencePrincipalKey,
  normalizeMarketViewPreference,
  readMarketViewPreference,
  resolveMarketViewTask,
  writeMarketViewPreference,
} from "../src/app/context/viewPreference.ts";
import {
  DEFAULT_MARKET_TASK,
  MARKET_VIEW_TASKS,
  marketTaskFromLocation,
  marketTaskToSearch,
} from "../src/app/model/marketCockpitModel.ts";
import {
  TRADER_CONTEXT_STORAGE_KEY,
  readPersistedTraderContext,
  writePersistedTraderContext,
} from "../src/app/context/contextPersistence.ts";
import { workspaceTaskSearch } from "../src/workspaceNavigation.ts";

function memoryStorage() {
  const entries = new Map<string, string>();
  return {
    entries,
    getItem: (key: string) => entries.get(key) ?? null,
    setItem: (key: string, value: string) => {
      entries.set(key, value);
    },
  };
}

function storageWith(raw: string) {
  const storage = memoryStorage();
  storage.setItem(MARKET_VIEW_PREFERENCE_STORAGE_KEY, raw);
  return storage;
}

test("the persisted market view is one of the two separate task views", () => {
  assert.deepEqual(MARKET_VIEW_TASKS, ["curves", "network"]);
  assert.deepEqual(MARKET_VIEW_PREFERENCE_IDS, MARKET_VIEW_TASKS);
  assert.equal(DEFAULT_MARKET_VIEW_PREFERENCE, "curves");
  assert.equal(DEFAULT_MARKET_TASK, "curves");
  assert.equal(DEFAULT_MARKET_TASK === "overview", false);
});

test("only the numeric and map views are persistable", () => {
  assert.equal(marketViewPreferenceForTask("curves"), "curves");
  assert.equal(marketViewPreferenceForTask("network"), "network");
  assert.equal(marketViewPreferenceForTask("overview"), null);
  assert.equal(marketViewPreferenceForTask("capacity"), null);

  assert.equal(isMarketViewPreferenceId("curves"), true);
  assert.equal(isMarketViewPreferenceId("network"), true);
  assert.equal(isMarketViewPreferenceId("overview"), false);
  assert.equal(isMarketViewPreferenceId("capacity"), false);
  assert.equal(isMarketViewPreferenceId(""), false);
  assert.equal(isMarketViewPreferenceId(null), false);

  assert.equal(normalizeMarketViewPreference("network"), "network");
  for (const rejected of ["overview", "capacity", "grid", "", null, undefined, "NETWORK"]) {
    assert.equal(normalizeMarketViewPreference(rejected), "curves", String(rejected));
  }
  assert.equal(normalizeMarketViewPreference("overview", "network"), "network");
});

test("the preference is scoped per principal and never shared between users", () => {
  const storage = memoryStorage();
  writeMarketViewPreference("operator-a", "network", storage);

  assert.equal(readMarketViewPreference("operator-a", storage), "network");
  assert.equal(readMarketViewPreference("operator-b", storage), null);

  writeMarketViewPreference("operator-b", "curves", storage);
  assert.equal(readMarketViewPreference("operator-a", storage), "network");
  assert.equal(readMarketViewPreference("operator-b", storage), "curves");

  const record = JSON.parse(storage.entries.get(MARKET_VIEW_PREFERENCE_STORAGE_KEY) ?? "{}");
  assert.deepEqual(Object.keys(record).sort(), ["operator-a", "operator-b"]);
});

test("an unknown identity gets one explicit anonymous scope, not a shared user", () => {
  assert.equal(marketViewPreferencePrincipalKey(null), MARKET_VIEW_PREFERENCE_ANONYMOUS_PRINCIPAL);
  assert.equal(marketViewPreferencePrincipalKey(undefined), "anonymous");
  assert.equal(marketViewPreferencePrincipalKey("   "), "anonymous");
  assert.equal(marketViewPreferencePrincipalKey(" operator-a "), "operator-a");

  const storage = memoryStorage();
  writeMarketViewPreference(null, "network", storage);
  assert.equal(readMarketViewPreference(undefined, storage), "network");
  assert.equal(readMarketViewPreference("operator-a", storage), null);
});

test("writing the view preference never disturbs trader context", () => {
  assert.notEqual(MARKET_VIEW_PREFERENCE_STORAGE_KEY, TRADER_CONTEXT_STORAGE_KEY);
  const storage = memoryStorage();
  writePersistedTraderContext(
    { gasDay: "2026-09-07", deliveryProduct: "day-ahead", hubId: "NBP" },
    storage,
  );
  writeMarketViewPreference("operator-a", "network", storage);
  assert.deepEqual(readPersistedTraderContext(storage), {
    gasDay: "2026-09-07",
    deliveryProduct: "day-ahead",
    hubId: "NBP",
  });
});

test("unknown and legacy stored values fall back safely", () => {
  assert.equal(readMarketViewPreference("anonymous", memoryStorage()), null);
  assert.equal(readMarketViewPreference("anonymous", null), null);
  assert.equal(readMarketViewPreference("anonymous", storageWith("not json at all")), null);
  assert.equal(readMarketViewPreference("anonymous", storageWith("null")), null);
  assert.equal(readMarketViewPreference("anonymous", storageWith("[]")), null);
  assert.equal(readMarketViewPreference("anonymous", storageWith('{"anonymous":"overview"}')), null);
  assert.equal(readMarketViewPreference("anonymous", storageWith('{"anonymous":"grid"}')), null);
  assert.equal(readMarketViewPreference("anonymous", storageWith('{"other-user":"network"}')), null);
  assert.equal(
    readMarketViewPreference("anonymous", storageWith('{"anonymous":{"view":"overview"}}')),
    null,
  );

  // Legacy single-value and object shapes are accepted only when supported.
  assert.equal(readMarketViewPreference("anonymous", storageWith('"network"')), "network");
  assert.equal(readMarketViewPreference("anonymous", storageWith('"overview"')), null);
  assert.equal(
    readMarketViewPreference("anonymous", storageWith('{"anonymous":{"view":"network"}}')),
    "network",
  );

  const throwing = {
    getItem: () => {
      throw new Error("storage unavailable");
    },
    setItem: () => {
      throw new Error("storage unavailable");
    },
  };
  assert.equal(readMarketViewPreference("anonymous", throwing), null);
  assert.doesNotThrow(() => writeMarketViewPreference("anonymous", "network", throwing));
});

test("an unknown or legacy stored view cannot override the numeric default", () => {
  const persisted = readMarketViewPreference("anonymous", storageWith('{"anonymous":"overview"}'));
  assert.deepEqual(
    resolveMarketViewTask({ search: "", activeWorkspace: "market", persisted }),
    { task: "curves", source: "default" },
  );
  assert.deepEqual(
    resolveMarketViewTask({ search: "?workspace=market", activeWorkspace: "market", persisted }),
    { task: "curves", source: "default" },
  );
});

test("resolution precedence is URL task, then persisted view, then numeric default", () => {
  assert.deepEqual(
    resolveMarketViewTask({
      search: "?workspace=market&task=network",
      activeWorkspace: "market",
      persisted: "curves",
    }),
    { task: "network", source: "url" },
  );
  assert.deepEqual(
    resolveMarketViewTask({
      search: "?workspace=market&task=curves",
      activeWorkspace: "market",
      persisted: "network",
    }),
    { task: "curves", source: "url" },
  );
  assert.deepEqual(
    resolveMarketViewTask({ search: "?task=curves", activeWorkspace: "market", persisted: "network" }),
    { task: "curves", source: "url" },
  );
  assert.deepEqual(
    resolveMarketViewTask({ search: "", activeWorkspace: "market", persisted: "network" }),
    { task: "network", source: "persisted" },
  );
  assert.deepEqual(
    resolveMarketViewTask({ search: "", activeWorkspace: "market", persisted: "curves" }),
    { task: "curves", source: "persisted" },
  );
  assert.deepEqual(
    resolveMarketViewTask({ search: "", activeWorkspace: "market", persisted: null }),
    { task: "curves", source: "default" },
  );
  assert.deepEqual(
    resolveMarketViewTask({ search: "", activeWorkspace: "market", persisted: undefined }),
    { task: "curves", source: "default" },
  );
});

test("the network and capacity deep links keep their own task", () => {
  assert.deepEqual(
    resolveMarketViewTask({ search: "?workspace=network", activeWorkspace: "network", persisted: "curves" }),
    { task: "network", source: "url" },
  );
  assert.deepEqual(
    resolveMarketViewTask({ search: "?workspace=capacity", activeWorkspace: "capacity", persisted: "network" }),
    { task: "capacity", source: "url" },
  );
  assert.deepEqual(
    resolveMarketViewTask({ search: "?workspace=capacity&task=capacity", activeWorkspace: "capacity", persisted: null }),
    { task: "capacity", source: "url" },
  );
  assert.equal(marketTaskFromLocation("?workspace=network", "network"), "network");
  assert.equal(marketTaskFromLocation("?workspace=capacity", "capacity"), "capacity");
});

test("the fused overview task stays reachable and is never implicit", () => {
  assert.deepEqual(
    resolveMarketViewTask({
      search: "?workspace=market&task=overview",
      activeWorkspace: "market",
      persisted: "network",
    }),
    { task: "overview", source: "url" },
  );
  assert.equal(marketTaskFromLocation("?workspace=market&task=overview", "market"), "overview");
  assert.equal(marketTaskFromLocation("", "market"), "curves");
  assert.equal(marketTaskFromLocation("?workspace=market", "market"), "curves");
  assert.equal(marketTaskFromLocation("?workspace=market&task=legacy-unknown", "market"), "curves");
  assert.notEqual(marketTaskFromLocation("", "market"), "overview");
});

test("the persisted view also chooses which market child page opens", () => {
  assert.equal(MARKET_SHELL_PAGE_ID, "market");
  // Both persisted views land on the market shell: the standalone `network`
  // page renders the map without any task tabs, so landing a map-preferring
  // user there would leave no in-UI way back to the numeric view.
  assert.equal(marketViewLandingPage("curves"), "market");
  assert.equal(marketViewLandingPage("network"), "market");

  assert.equal(marketViewLandingPageCandidate({ task: null, persisted: "curves" }), "market");
  assert.equal(marketViewLandingPageCandidate({ task: null, persisted: "network" }), "market");
  // With nothing persisted the declared default stands, unchanged.
  assert.equal(marketViewLandingPageCandidate({ task: null, persisted: null }), null);
  assert.equal(marketViewLandingPageCandidate({ task: null, persisted: undefined }), null);
  // An explicit URL task needs the shell that owns the task switcher.
  assert.equal(marketViewLandingPageCandidate({ task: "curves", persisted: "network" }), "market");
  assert.equal(marketViewLandingPageCandidate({ task: "overview", persisted: "network" }), "market");
});

test("a stored view survives a write/read/resolve round trip for its principal", () => {
  const storage = memoryStorage();
  writeMarketViewPreference("operator-a", "network", storage);
  assert.deepEqual(
    resolveMarketViewTask({
      search: "?gasDay=2026-09-07&product=day-ahead&hub=TTF&workspace=market",
      activeWorkspace: "market",
      persisted: readMarketViewPreference("operator-a", storage),
    }),
    { task: "network", source: "persisted" },
  );

  writeMarketViewPreference("operator-a", "curves", storage);
  assert.deepEqual(
    resolveMarketViewTask({
      search: "",
      activeWorkspace: "market",
      persisted: readMarketViewPreference("operator-a", storage),
    }),
    { task: "curves", source: "persisted" },
  );

  // The other principal on this workstation keeps their own landing view.
  assert.deepEqual(
    resolveMarketViewTask({
      search: "",
      activeWorkspace: "market",
      persisted: readMarketViewPreference("operator-b", storage),
    }),
    { task: "curves", source: "default" },
  );
});

test("switching between the numeric and map views preserves trader context keys", () => {
  const context =
    "?gasDay=2026-09-07&product=day-ahead&hub=TTF&route=route-1&resource=res-2&run=run-3&strategy=strat-4";
  const carried: Array<[string, string]> = [
    ["gasDay", "2026-09-07"],
    ["product", "day-ahead"],
    ["hub", "TTF"],
    ["route", "route-1"],
    ["resource", "res-2"],
    ["run", "run-3"],
    ["strategy", "strat-4"],
  ];

  const toMap = workspaceTaskSearch(context, "market", "network");
  const mapParams = new URLSearchParams(toMap);
  assert.equal(mapParams.get("workspace"), "market");
  assert.equal(mapParams.get("task"), "network");
  for (const [key, value] of carried) {
    assert.equal(mapParams.get(key), value, `${key} survived numeric -> map`);
  }

  const toNumeric = workspaceTaskSearch(toMap, "market", "curves");
  const numericParams = new URLSearchParams(toNumeric);
  assert.equal(numericParams.get("task"), "curves");
  for (const [key, value] of carried) {
    assert.equal(numericParams.get(key), value, `${key} survived map -> numeric`);
  }

  assert.equal(
    marketTaskToSearch(context, "network"),
    "gasDay=2026-09-07&product=day-ahead&hub=TTF&route=route-1&resource=res-2&run=run-3&strategy=strat-4&workspace=market&task=network",
  );
  assert.equal(
    marketTaskToSearch(marketTaskToSearch(context, "network"), "curves"),
    "gasDay=2026-09-07&product=day-ahead&hub=TTF&route=route-1&resource=res-2&run=run-3&strategy=strat-4&workspace=market&task=curves",
  );

  // A bare switch keeps the hub/product/gas-day context even with no selection.
  assert.equal(
    workspaceTaskSearch("?gasDay=2026-09-07&product=within-day&hub=NBP", "market", "curves"),
    "gasDay=2026-09-07&product=within-day&hub=NBP&workspace=market&task=curves",
  );
});
