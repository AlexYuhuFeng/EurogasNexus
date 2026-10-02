/**
 * Decision stream ownership: replacement, identity, and dev-server disposal.
 *
 * `decisionStreamClosers` is module-scoped store state. `subscribeDecisionStreams` closes the
 * streams it can see before opening its three, and every identity change closes them again; the
 * remaining leak path was module replacement: a Vite hot replacement creates a new module
 * instance whose closer list is empty, and the old instance's EventSources would stay open
 * (three more per replacement, each holding a connection to the same origin). These tests hold
 * the streams to the single close owner through the real store boundary for replacement and
 * identity, and hold the disposal hook to that same owner by source contract: the Node module
 * runner used here has no Vite hot context, so the hook itself cannot be executed in-process and
 * is not claimed to be.
 *
 * No new stream protocol, broadcast infrastructure or auth material is introduced: the close
 * owner, the three paths and the identity gate are unchanged.
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

after(closeApiStoreHarness);

const STREAM_PATHS = ["/stream/quotes", "/stream/opportunities", "/stream/alerts"];

function authenticated(harness: ApiStoreHarness) {
  harness.store.setState({ authState: AUTHENTICATED_AUTH_STATE });
  return harness.store;
}

function openPaths(): string[] {
  return Object.keys(apiRegistry().streams).sort();
}

test("re-subscribing closes the previous streams through the one close owner", async () => {
  const harness = await loadApiStore();
  const store = authenticated(harness);
  const registry = apiRegistry();

  store.getState().subscribeDecisionStreams();
  assert.deepEqual(openPaths(), [...STREAM_PATHS].sort());
  const firstQuotes = registry.streams["/stream/quotes"];
  const firstAlerts = registry.streams["/stream/alerts"];

  // A second subscription replaces the set instead of stacking a second one: the previous
  // handles are closed first, through the same owner identity invalidation uses.
  store.getState().subscribeDecisionStreams();
  assert.deepEqual(registry.streamCloses, [
    "/stream/quotes",
    "/stream/opportunities",
    "/stream/alerts",
  ]);
  assert.deepEqual(openPaths(), [...STREAM_PATHS].sort(), "exactly one live set remains");
  assert.notEqual(registry.streams["/stream/quotes"], firstQuotes);
  assert.notEqual(registry.streams["/stream/alerts"], firstAlerts);
});

test("identity invalidation closes every decision stream", async () => {
  const harness = await loadApiStore();
  const store = authenticated(harness);
  const registry = apiRegistry();

  store.getState().subscribeDecisionStreams();
  assert.equal(openPaths().length, 3);

  // A 401 on the identity read is the real owner boundary that ends the session: the store
  // must not leave protected streams open for an identity that no longer exists.
  harness.answer("me", () => Promise.reject(new Error("API 401: session expired")));
  await store.getState().fetchMe();
  await settle();

  assert.deepEqual(openPaths(), [], "no stream survives the identity that opened it");
  assert.deepEqual(registry.streamCloses, [
    "/stream/quotes",
    "/stream/opportunities",
    "/stream/alerts",
  ]);
  assert.equal(store.getState().authState, "unauthenticated");

  // An unauthenticated subscription opens nothing - the gate check precedes the open - and
  // closes nothing, so it cannot disturb a healthy session's streams.
  registry.streamCloses.length = 0;
  store.setState({ authState: UNRESOLVED_AUTH_STATE });
  store.getState().subscribeDecisionStreams();
  assert.deepEqual(registry.streamCloses, []);
  assert.deepEqual(openPaths(), []);
});

test("the dev-server disposal hook closes through the same owner, before replacement runs", () => {
  const source = readFileSync(new URL("../src/stores/api.ts", import.meta.url), "utf8");
  // The hook is dev-only and cannot be executed through the Node module runner; this contract
  // holds it to the module's single close owner instead of a second cleanup implementation.
  assert.match(
    source,
    /if \(import\.meta\.hot\) \{\s*import\.meta\.hot\.dispose\(\(\) => \{\s*closeDecisionStreams\(\);\s*\}\);\s*\}/,
  );
  // No second stream-close implementation: the three subscription paths and the disposal hook
  // all go through the one function.
  const closeOwnerCalls = source.match(/closeDecisionStreams\(\);/g) ?? [];
  assert.ok(closeOwnerCalls.length >= 4, "subscription, identity and disposal share one owner");
});
