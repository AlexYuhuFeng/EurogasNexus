/**
 * The workspace loader's own lifecycle, driven through the real store.
 *
 * The runtime-loader repair added three facts a surface states itself with: `workspaceLoading` (the
 * batch alone, not any on-demand action), `workspaceLoadsCommitted` (how many batches have
 * committed for this session) and an unread `dataStatus` before any status read answers. These
 * tests exercise them against the actual store through the harness the projection tests use, with
 * answers the test settles by hand: source-text assertions cannot show that a superseded pass
 * settles nothing or that a failed status read leaves the status unread.
 */

import assert from "node:assert/strict";
import test, { after } from "node:test";

import type { RuntimeDbStatusDTO } from "../src/api/client.ts";
import {
  AUTHENTICATED_AUTH_STATE,
  UNAUTHENTICATED_AUTH_STATE,
} from "../src/stores/workspaceLoading.ts";
import {
  closeApiStoreHarness,
  deferred,
  loadApiStore,
  settle,
  type ApiStoreHarness,
} from "./support/apiStoreHarness.ts";

after(closeApiStoreHarness);

function runtimeDb(overrides: Partial<RuntimeDbStatusDTO> = {}): RuntimeDbStatusDTO {
  return {
    database_url_present: true,
    redacted_database_url: null,
    connectivity: { ok: true, error: null },
    alembic_revision: "0036_job_records",
    required_tables: [],
    missing_tables: [],
    warnings: [],
    ...overrides,
  };
}

function nodeIds(nodes: unknown[]): string[] {
  return nodes.map((item) => String((item as { node_id?: unknown }).node_id));
}

/** Put the session past the identity gate, as a resolved sign-in does, and hand the store back. */
function authenticated(harness: ApiStoreHarness) {
  harness.store.setState({ authState: AUTHENTICATED_AUTH_STATE });
  return harness.store;
}

test("a batch that has not committed is pending, and the commit is its own fact", async () => {
  const harness = await loadApiStore();
  const store = authenticated(harness);

  // Nothing asked yet: no batch in flight, none committed, the runtime status unread.
  assert.equal(store.getState().workspaceLoading, false);
  assert.equal(store.getState().workspaceLoadsCommitted, 0);
  assert.equal(store.getState().dataStatus, "unknown");

  const nodes = deferred<unknown>();
  harness.answer("nodes", () => nodes.promise);
  const batch = store.getState().fetchWorkspace();
  await settle();

  // In flight: the workspace is loading because of the batch, and no read has committed.
  assert.equal(
    harness.calls.some((call) => call.method === "runtimeDb"),
    true,
    "the batch is issuing its reads",
  );
  assert.equal(store.getState().workspaceLoading, true);
  assert.equal(store.getState().workspaceLoadsCommitted, 0);
  assert.equal(store.getState().dataStatus, "unknown");
  assert.deepEqual(nodeIds(store.getState().nodes), []);

  nodes.resolve({ data: [{ node_id: "n1" }], meta: {} });
  await batch;
  await settle();

  // Committed: the flag that says a batch is in flight is cleared, and the batch is counted.
  assert.equal(store.getState().workspaceLoading, false);
  assert.equal(store.getState().workspaceLoadsCommitted, 1);
  assert.deepEqual(nodeIds(store.getState().nodes), ["n1"]);
});

test("a status read that failed leaves the status unread, and an unavailable answer is an answer", async () => {
  const harness = await loadApiStore();
  const store = authenticated(harness);
  harness.answer("runtimeDb", () => Promise.reject(new Error("API 503: runtime status unavailable")));

  await store.getState().fetchWorkspace();
  await settle();

  // The batch committed, so its reads are answered - but this one answered nothing, so no
  // disconnection may be claimed from it.
  assert.match(store.getState().endpointErrors.runtimeDb, /API 503/);
  assert.equal(store.getState().workspaceLoadsCommitted, 1);
  assert.equal(store.getState().dataStatus, "unknown");

  // The same read answering "not available" is a completed read with a verdict, and the store
  // reports that verdict rather than the fact that nothing failed.
  harness.answer("runtimeDb", () => ({
    data: runtimeDb({ database_url_present: false, connectivity: { ok: false, error: "no url" } }),
    meta: {},
  }));
  await store.getState().fetchWorkspace();
  await settle();
  assert.equal(store.getState().endpointErrors.runtimeDb, undefined);
  assert.equal(store.getState().workspaceLoadsCommitted, 2);
  assert.equal(store.getState().dataStatus, "unavailable");

  // And the store answering with runtime-backed slices is the third reading.
  harness.answer("runtimeDb", () => ({
    data: runtimeDb(),
    meta: { source_references: ["runtime-postgresql"] },
  }));
  await store.getState().fetchWorkspace();
  await settle();
  assert.equal(store.getState().workspaceLoadsCommitted, 3);
  assert.equal(store.getState().dataStatus, "runtime");
});

test("an on-demand action's loading does not make a committed workspace read as loading", async () => {
  const harness = await loadApiStore();
  const store = authenticated(harness);
  await store.getState().fetchWorkspace();
  await settle();
  assert.equal(store.getState().workspaceLoadsCommitted, 1);

  const optimizer = deferred<unknown>();
  harness.answer("optimizeResourcePool", () => optimizer.promise);
  const run = store.getState().optimizeResourcePool({ objective: "min_cost" });
  await settle();

  // The action raises its own flag; the workspace's reading and its committed count stand.
  assert.equal(store.getState().loading, true);
  assert.equal(store.getState().workspaceLoading, false);
  assert.equal(store.getState().workspaceLoadsCommitted, 1);

  optimizer.resolve({ data: { plan: [] }, meta: {} });
  await run;
  await settle();
  assert.equal(store.getState().loading, false);
  assert.equal(store.getState().workspaceLoading, false);
  assert.equal(store.getState().workspaceLoadsCommitted, 1);
});

test("a superseded batch cannot settle or count the batch that superseded it", async () => {
  const harness = await loadApiStore();
  const store = authenticated(harness);
  const first = deferred<unknown>();
  const second = deferred<unknown>();
  const answers = [first, second];
  let read = 0;
  harness.answer("nodes", () => answers[read++]?.promise ?? { data: [], meta: {} });

  const superseded = store.getState().fetchWorkspace();
  await settle();
  assert.equal(store.getState().workspaceLoading, true);
  const current = store.getState().fetchWorkspace();
  await settle();
  assert.equal(read, 2, "both passes asked");
  assert.equal(store.getState().workspaceLoading, true);

  // The superseded pass answers: it writes nothing and settles nothing, least of all the pass
  // still in flight.
  first.resolve({ data: [{ node_id: "superseded" }], meta: {} });
  await superseded;
  await settle();
  assert.equal(store.getState().workspaceLoading, true);
  assert.equal(store.getState().workspaceLoadsCommitted, 0);
  assert.deepEqual(nodeIds(store.getState().nodes), []);

  second.resolve({ data: [{ node_id: "current" }], meta: {} });
  await current;
  await settle();
  assert.equal(store.getState().workspaceLoading, false);
  assert.equal(store.getState().workspaceLoadsCommitted, 1);
  assert.deepEqual(nodeIds(store.getState().nodes), ["current"]);
});

test("an identity reset returns the session to unread and drops a batch that was in flight", async () => {
  const harness = await loadApiStore();
  const store = authenticated(harness);
  harness.answer("runtimeDb", () => ({
    data: runtimeDb(),
    meta: { source_references: ["runtime-postgresql"] },
  }));
  await store.getState().fetchWorkspace();
  await settle();
  assert.equal(store.getState().workspaceLoadsCommitted, 1);
  assert.equal(store.getState().dataStatus, "runtime");

  const pending = deferred<unknown>();
  harness.answer("nodes", () => pending.promise);
  const batch = store.getState().fetchWorkspace();
  await settle();
  assert.equal(store.getState().workspaceLoading, true);

  // The backend revokes the session while the batch is in flight.
  harness.answer("me", () => Promise.reject(new Error("API 401: session revoked")));
  await store.getState().fetchMe();
  assert.equal(store.getState().authState, UNAUTHENTICATED_AUTH_STATE);
  assert.equal(store.getState().workspaceLoading, false);
  assert.equal(store.getState().workspaceLoadsCommitted, 0);
  assert.equal(store.getState().dataStatus, "unknown");

  // The batch answers into a session that no longer exists: no rows, no commit, no reading.
  pending.resolve({ data: [{ node_id: "revoked" }], meta: {} });
  await batch;
  await settle();
  assert.equal(store.getState().workspaceLoading, false);
  assert.equal(store.getState().workspaceLoadsCommitted, 0);
  assert.equal(store.getState().dataStatus, "unknown");
  assert.deepEqual(nodeIds(store.getState().nodes), []);
});
