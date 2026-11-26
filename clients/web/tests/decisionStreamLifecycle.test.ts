/**
 * The tab's live connection: one per browser tab, owned by one close path.
 *
 * The server caps live streams per person (`EUROGAS_NEXUS_MAX_STREAMS_PER_PRINCIPAL`). The tab
 * used to open four (quotes, opportunities, alerts and the live stream) and to re-open them after
 * every workspace load and the live one on every page; a demo crawl as one user in one tab logged
 * a 429 on 20 of 32 pages, and a second tab or a second tester on the account hit the cap at once.
 * Now the store turns on the ONE live connection (app/data/liveStream.ts), keeps it across
 * workspace loads, and closes it through the one owner at every identity change and at a Vite hot
 * replacement (held by source contract: the Node module runner has no hot context).
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test, { after } from "node:test";

import { AUTHENTICATED_AUTH_STATE, UNRESOLVED_AUTH_STATE } from "../src/stores/workspaceLoading.ts";
import { apiRegistry } from "./support/mockApiClient.ts";
import {
  closeApiStoreHarness,
  loadApiStore,
  settle,
  type ApiStoreHarness,
} from "./support/apiStoreHarness.ts";

type LiveModule = typeof import("../src/app/data/liveStream.ts");

after(closeApiStoreHarness);

async function commercialSession(harness: ApiStoreHarness) {
  harness.store.setState({ authState: AUTHENTICATED_AUTH_STATE });
  harness.answer("me", () => ({ data: { principal_id: "p", roles: ["trader"], permissions: ["market.read"] }, meta: {} }));
  await harness.store.getState().fetchMe();
  return harness.store;
}

function openPaths(): string[] {
  return Object.keys(apiRegistry().streams).sort();
}

test("one live connection per tab, for every topic, kept across workspace loads", async () => {
  const harness = await loadApiStore();
  const live = await harness.load<LiveModule>("/src/app/data/liveStream.ts");
  live.resetLiveStreamForTests();
  const store = await commercialSession(harness);
  const registry = apiRegistry();
  registry.streamCloses.length = 0;
  const stop = live.subscribeLive("prices", () => undefined);

  store.getState().subscribeDecisionStreams();
  const paths = openPaths();
  assert.equal(paths.length, 1, "one stream, not one per feed");
  assert.match(paths[0], /^\/stream\/live\?topics=/);
  const topics = new URLSearchParams(paths[0].split("?")[1]).get("topics")?.split(",") ?? [];
  for (const topic of ["alerts", "prices", "opportunities", "cargoes", "outages", "jobs"]) {
    assert.ok(topics.includes(topic), `${topic} rides on the tab's connection`);
  }

  // The store calls this after every workspace load: the connection stays as it is.
  store.getState().subscribeDecisionStreams();
  store.getState().subscribeDecisionStreams();
  assert.deepEqual(registry.streamCloses, [], "nothing is closed and re-opened");
  assert.equal(openPaths().length, 1);

  // A page that changes what it listens to attaches to the same connection.
  const stopAlerts = live.subscribeLive("alerts", () => undefined);
  const stopOpportunities = live.subscribeLiveEvent("opportunity", () => undefined);
  stopAlerts();
  stopOpportunities();
  assert.deepEqual(registry.streamCloses, []);
  stop();
  live.resetLiveStreamForTests();
});

test("identity invalidation closes the tab's connection through the one owner", async () => {
  const harness = await loadApiStore();
  const live = await harness.load<LiveModule>("/src/app/data/liveStream.ts");
  live.resetLiveStreamForTests();
  const store = await commercialSession(harness);
  const registry = apiRegistry();
  const stop = live.subscribeLive("prices", () => undefined);
  store.getState().subscribeDecisionStreams();
  assert.equal(openPaths().length, 1);

  // A 401 on the identity read is the real owner boundary that ends the session: the store
  // must not leave a protected stream open for an identity that no longer exists.
  harness.answer("me", () => Promise.reject(new Error("API 401: session expired")));
  await store.getState().fetchMe();
  await settle();
  assert.deepEqual(openPaths(), [], "no stream survives the identity that opened it");
  assert.equal(store.getState().authState, "unauthenticated");
  assert.equal(store.getState().streamingActive, false);

  // An unauthenticated subscription opens nothing: the gate check precedes the open.
  registry.streamCloses.length = 0;
  store.setState({ authState: UNRESOLVED_AUTH_STATE });
  store.getState().subscribeDecisionStreams();
  assert.deepEqual(registry.streamCloses, []);
  assert.deepEqual(openPaths(), []);
  stop();
  live.resetLiveStreamForTests();
});

test("the client opens no per-feed stream any more", () => {
  for (const file of ["stores/api.ts", "app/hooks/useOpportunityStream.ts", "app/hooks/useCargoBoard.ts", "app/hooks/useMapSituation.ts"]) {
    const source = readFileSync(new URL(`../src/${file}`, import.meta.url), "utf8");
    assert.doesNotMatch(source, /openEventStream\(|\/stream\/(quotes|opportunities|alerts)"/, file);
  }
});

test("the dev-server disposal hook closes through the same owner, before replacement runs", () => {
  const source = readFileSync(new URL("../src/stores/api.ts", import.meta.url), "utf8");
  assert.match(
    source,
    /if \(import\.meta\.hot\) \{\s*import\.meta\.hot\.dispose\(\(\) => \{\s*closeDecisionStreams\(\);\s*\}\);\s*\}/,
  );
  const closeOwner = source.match(/function closeDecisionStreams\(\) \{\s*setLiveEnabled\(false\);\s*\}/);
  assert.ok(closeOwner, "one close owner: it turns the tab's connection off");
});
