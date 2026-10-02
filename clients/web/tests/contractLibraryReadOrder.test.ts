/**
 * Stale-read ordering around the contract library and the pooled resource view (client half,
 * executable).
 *
 * The observed defect: a committed save re-read `upstreamContracts` and `resourcePoolOptions`
 * after the write and published both unconditionally, so a workspace batch (or another save)
 * dispatched *before* the write could resolve *after* the save's refresh and replace the library
 * rows - carrying pre-write edit tokens - and the resource view with its pre-write reading.
 *
 * These tests drive the real store module through the harness with only the HTTP boundary mocked
 * and its answers deferred, so the actual async ordering is exercised: a pre-write batch cannot
 * republish after the save commits, a batch dispatched after the refresh supersedes it, a newer
 * save's refresh supersedes a delayed earlier one, a failed latest read keeps the last good rows
 * (with the failure recorded) instead of publishing an empty library, an older answer cannot
 * resurrect stale rows over a failed latest read, the bounded retry of a failed library read is
 * invalidated by a committed save the same way, identity invalidation drops the pool view as well
 * as the library, and a context switch drops the refresh's older-context pool view while the
 * context re-read answers.
 *
 * Scope limits: the save's pool view is re-read through the canonical portfolio projection, so
 * these tests cover the projection lane, not a pool-options route call; the visual
 * conflict/reconciliation journey, the shared `loading` flag and the batch's own error string
 * are outside this file. Source assertions alone could not show any of the ordering above.
 */

import assert from "node:assert/strict";
import test, { after } from "node:test";

import { AUTHENTICATED_AUTH_STATE } from "../src/stores/workspaceLoading.ts";
import {
  closeApiStoreHarness,
  deferred,
  loadApiStore,
  settle,
  type ApiStoreHarness,
} from "./support/apiStoreHarness.ts";

after(closeApiStoreHarness);

const TOKEN_B = `sha256:${"b".repeat(64)}`;

const CONTRACT = {
  contract_id: "stored-contract-1",
  contract_name: "Stored contract 1",
  edit_token: TOKEN_B,
  write_outcome: "metadata_updated",
};

interface Envelope<T> {
  data: T;
  meta: Record<string, unknown>;
}

function envelope<T>(data: T, meta: Record<string, unknown> = {}): Envelope<T> {
  return { data, meta };
}

/**
 * One portfolio projection carrying the pool block the surfaces read, so the store's canonical
 * re-read has a real payload to apply (scope = which read answered, rows = its sale options).
 */
function portfolioProjection(scope: string, optionIds: string[]) {
  return {
    as_of_utc: "2026-10-02T08:00:00Z",
    time_basis: { basis: "gas_day" },
    slices: {
      summary: {
        available: true,
        freshness: { state: "FRESH" },
        payload: { open_positions: 1 },
      },
      resources: {
        available: true,
        freshness: { state: "FRESH" },
        payload: {
          scope,
          data_source: "runtime-postgresql",
          portfolio_resources: [],
          blockers: [],
          warnings: [],
        },
        rows: optionIds.map((option_id) => ({ option_id })),
      },
    },
  };
}

function authenticated(harness: ApiStoreHarness) {
  harness.store.setState({ authState: AUTHENTICATED_AUTH_STATE });
  return harness.store;
}

const callsTo = (harness: ApiStoreHarness, method: string) =>
  harness.calls.filter((call) => call.method === method).length;

test("a workspace batch dispatched before the save cannot republish its pre-write library or pool view", async () => {
  const harness = await loadApiStore();
  const store = authenticated(harness);
  const batchLibrary = deferred<Envelope<unknown[]>>();
  const batchPortfolio = deferred<Envelope<unknown>>();
  const write = deferred<Envelope<typeof CONTRACT>>();
  let libraryCalls = 0;
  harness.answer("upstreamContracts", () =>
    libraryCalls++ === 0
      ? batchLibrary.promise
      : envelope([CONTRACT], { source: "save-refresh" }),
  );
  let portfolioCalls = 0;
  harness.answer("portfolioSnapshot", () =>
    portfolioCalls++ === 0
      ? batchPortfolio.promise
      : envelope(portfolioProjection("post-save", ["option-b"]), { source: "save-refresh" }),
  );
  harness.answer("saveUpstreamContract", () => write.promise);

  const batch = store.getState().fetchWorkspace();
  await settle();
  assert.equal(libraryCalls, 1, "the pre-write batch dispatched its library read");
  assert.equal(portfolioCalls, 1, "the pre-write batch dispatched its portfolio read");

  const saving = store.getState().saveDraftContract({ contract_id: CONTRACT.contract_id });
  write.resolve(envelope(CONTRACT));
  await saving;
  assert.deepEqual(store.getState().upstreamContracts, [CONTRACT]);
  assert.equal(store.getState().resourcePoolOptions?.scope, "post-save");

  // The pre-write answers arrive only now and must neither land nor overwrite the records.
  batchLibrary.resolve(envelope([{ contract_id: "pre-write" }], { source: "batch" }));
  batchPortfolio.resolve(envelope(portfolioProjection("pre-write", ["option-a"]), { source: "batch" }));
  await batch;

  const state = store.getState();
  assert.deepEqual(state.upstreamContracts, [CONTRACT]);
  assert.equal(state.resourcePoolOptions?.scope, "post-save");
  assert.equal((state.endpointMeta.upstreamContracts as { source?: string }).source, "save-refresh");
  assert.equal((state.endpointMeta.portfolioSnapshot as { source?: string }).source, "save-refresh");
  // The pool view came from the canonical projection re-read, not a competing pool-options write.
  assert.equal(callsTo(harness, "resourcePoolOptions"), 0);
  assert.equal(callsTo(harness, "portfolioSnapshot"), 2);
});

test("a workspace batch dispatched after the save refresh supersedes its answer", async () => {
  const harness = await loadApiStore();
  const store = authenticated(harness);
  const write = deferred<Envelope<typeof CONTRACT>>();
  const refreshLibrary = deferred<Envelope<unknown[]>>();
  let libraryCalls = 0;
  harness.answer("upstreamContracts", () =>
    libraryCalls++ === 0
      ? refreshLibrary.promise
      : envelope([{ contract_id: "batch-fresh" }], { source: "batch" }),
  );
  harness.answer("saveUpstreamContract", () => write.promise);

  const saving = store.getState().saveDraftContract({ contract_id: CONTRACT.contract_id });
  write.resolve(envelope(CONTRACT));
  await settle();
  assert.equal(libraryCalls, 1, "the save's refresh is in flight");

  // A later batch is dispatched after the write committed, so its claim is the newest.
  await store.getState().fetchWorkspace();
  assert.deepEqual(store.getState().upstreamContracts, [{ contract_id: "batch-fresh" }]);

  // The earlier refresh's late answer cannot replace the newer batch's rows.
  refreshLibrary.resolve(envelope([{ contract_id: "refresh-stale" }], { source: "save-refresh" }));
  assert.deepEqual(await saving, CONTRACT);
  assert.deepEqual(store.getState().upstreamContracts, [{ contract_id: "batch-fresh" }]);
});

test("a failed latest refresh keeps the last-good library and a late older answer cannot resurrect", async () => {
  const harness = await loadApiStore();
  const store = authenticated(harness);
  const lastGood = { contract_id: "last-good" };
  harness.answer("upstreamContracts", () => envelope([lastGood]));
  await store.getState().fetchWorkspace();
  assert.deepEqual(store.getState().upstreamContracts, [lastGood]);

  const slowBatchLibrary = deferred<Envelope<unknown[]>>();
  let libraryCalls = 0;
  harness.answer("upstreamContracts", () => {
    libraryCalls += 1;
    if (libraryCalls === 1) return slowBatchLibrary.promise;
    return Promise.reject(new Error("API 500: library read failed"));
  });
  const batch = store.getState().fetchWorkspace();
  await settle();
  assert.equal(libraryCalls, 1, "the pre-write batch read is in flight");

  const write = deferred<Envelope<typeof CONTRACT>>();
  harness.answer("saveUpstreamContract", () => write.promise);
  const saving = store.getState().saveDraftContract({ contract_id: CONTRACT.contract_id });
  write.resolve(envelope(CONTRACT));
  await saving;

  // The latest read failed: the last good rows stay and the failure is recorded, not an empty library.
  assert.deepEqual(store.getState().upstreamContracts, [lastGood]);
  assert.match(String(store.getState().endpointErrors.upstreamContracts), /library read failed/);
  assert.match(
    String(store.getState().error),
    /was saved, but refreshing the contract library failed/,
  );

  slowBatchLibrary.resolve(envelope([{ contract_id: "pre-write" }], { source: "batch" }));
  await batch;
  assert.deepEqual(store.getState().upstreamContracts, [lastGood]);
});

test("a newer save's refresh supersedes a delayed earlier save's refresh", async () => {
  const harness = await loadApiStore();
  const store = authenticated(harness);
  const writes = [deferred<Envelope<typeof CONTRACT>>(), deferred<Envelope<typeof CONTRACT>>()];
  let writeIndex = 0;
  harness.answer("saveUpstreamContract", () => writes[writeIndex++].promise);
  const refreshes = [deferred<Envelope<unknown[]>>(), deferred<Envelope<unknown[]>>()];
  let refreshIndex = 0;
  harness.answer("upstreamContracts", () => refreshes[refreshIndex++].promise);
  const olderContract = { ...CONTRACT, contract_id: "older-contract" };
  const newerContract = { ...CONTRACT, contract_id: "newer-contract" };

  const olderSave = store.getState().saveDraftContract({ contract_id: olderContract.contract_id });
  const newerSave = store.getState().saveDraftContract({ contract_id: newerContract.contract_id });
  await settle();

  writes[0].resolve(envelope(olderContract));
  await settle();
  assert.equal(refreshIndex, 1, "the older save's refresh is in flight");

  writes[1].resolve(envelope(newerContract));
  await settle();
  assert.equal(refreshIndex, 2, "the newer save's refresh replaced it in the lane");

  refreshes[1].resolve(envelope([newerContract], { source: "newer-save" }));
  assert.deepEqual(await newerSave, newerContract);
  assert.deepEqual(store.getState().upstreamContracts, [newerContract]);

  // The older save's delayed refresh resolves last; its committed result is still returned to
  // the editor, but its pre-newer-save rows may not replace the library.
  refreshes[0].resolve(envelope([olderContract], { source: "older-save" }));
  assert.deepEqual(await olderSave, olderContract);
  assert.deepEqual(store.getState().upstreamContracts, [newerContract]);
});

test("identity invalidation during the refresh drops the pool view as well as the library", async () => {
  const harness = await loadApiStore();
  const store = authenticated(harness);
  const write = deferred<Envelope<typeof CONTRACT>>();
  const portfolio = deferred<Envelope<unknown>>();
  harness.answer("saveUpstreamContract", () => write.promise);
  harness.answer("upstreamContracts", () => envelope([CONTRACT]));
  harness.answer("portfolioSnapshot", () => portfolio.promise);
  harness.answer("me", () => {
    throw new Error("API 401: session expired");
  });

  const saving = store.getState().saveDraftContract({ contract_id: CONTRACT.contract_id });
  write.resolve(envelope(CONTRACT));
  await settle();
  assert.equal(callsTo(harness, "portfolioSnapshot"), 1, "the refresh read the pool view");

  // The session ends while the refresh is still in flight.
  await store.getState().fetchMe();
  portfolio.resolve(envelope(portfolioProjection("expired-identity", ["option-a"])));

  assert.equal(await saving, null);
  const state = store.getState();
  assert.equal(state.resourcePoolOptions, null);
  assert.deepEqual(state.upstreamContracts, []);
  assert.equal(state.authState, "unauthenticated");
});

test("a contract-library authentication denial clears the session and drops the saved result", async () => {
  const harness = await loadApiStore();
  const store = authenticated(harness);
  harness.answer("saveUpstreamContract", () => envelope(CONTRACT));
  harness.answer("portfolioSnapshot", () => envelope(portfolioProjection("prior-session", ["option-a"])));
  harness.answer("upstreamContracts", () => {
    throw new Error("API 401: session expired");
  });

  const result = await store.getState().saveDraftContract({ contract_id: CONTRACT.contract_id });
  assert.equal(result, null);
  assert.equal(store.getState().authState, "unauthenticated");
  assert.deepEqual(store.getState().upstreamContracts, []);
  assert.equal(store.getState().resourcePoolOptions, null);
  assert.equal(store.getState().contractSaveMessage, null);
});

test("a context switch drops the save refresh's older-context pool view", async () => {
  const harness = await loadApiStore();
  const store = authenticated(harness);
  const write = deferred<Envelope<typeof CONTRACT>>();
  const stalePortfolio = deferred<Envelope<unknown>>();
  harness.answer("saveUpstreamContract", () => write.promise);
  let portfolioCalls = 0;
  harness.answer("portfolioSnapshot", () =>
    portfolioCalls++ === 0
      ? stalePortfolio.promise
      : envelope(portfolioProjection("new-context", ["option-b"]), { source: "context-re-read" }),
  );
  harness.answer("upstreamContracts", () => envelope([CONTRACT]));

  const saving = store.getState().saveDraftContract({ contract_id: CONTRACT.contract_id });
  write.resolve(envelope(CONTRACT));
  await settle();
  assert.equal(portfolioCalls, 1, "the refresh read the pool view for the context in force");

  // The caller moves to another context: the lane is cleared and its own re-read answers.
  store.getState().publishTradingContext({ gasDay: "2026-11-01", deliveryProduct: "day-ahead", hubId: "TTF" });
  await settle();
  assert.equal(portfolioCalls, 2, "the context change re-read the portfolio lane");
  assert.equal(store.getState().resourcePoolOptions?.scope, "new-context");

  // The refresh's older-context answer arrives last and must not be re-labelled as current.
  stalePortfolio.resolve(envelope(portfolioProjection("pre-switch", ["option-a"])));
  await saving;
  assert.equal(store.getState().resourcePoolOptions?.scope, "new-context");
});

test("the bounded retry of a failed contract-library read obeys the same lane", async () => {
  const harness = await loadApiStore();
  const store = authenticated(harness);
  harness.answer("upstreamContracts", () => Promise.reject(new Error("API 500: library read failed")));
  await store.getState().fetchWorkspace();
  assert.match(String(store.getState().endpointErrors.upstreamContracts), /library read failed/);
  assert.deepEqual(store.getState().upstreamContracts, []);

  // The bounded retry dispatches its own library read and holds it.
  const retryLibrary = deferred<Envelope<unknown[]>>();
  let libraryCalls = 0;
  harness.answer("upstreamContracts", () => {
    libraryCalls += 1;
    return libraryCalls === 1
      ? retryLibrary.promise
      : envelope([{ contract_id: "saved" }], { source: "save-refresh" });
  });
  const retry = store.getState().retryFailedWorkspaceEndpoints();
  await settle();
  assert.equal(libraryCalls, 1, "the retry read is in flight");

  // A save commits while that retry is still in flight.
  const write = deferred<Envelope<typeof CONTRACT>>();
  harness.answer("saveUpstreamContract", () => write.promise);
  const saving = store.getState().saveDraftContract({ contract_id: CONTRACT.contract_id });
  write.resolve(envelope(CONTRACT));
  await saving;
  assert.deepEqual(store.getState().upstreamContracts, [{ contract_id: "saved" }]);
  assert.equal("upstreamContracts" in store.getState().endpointErrors, false);

  // The retry's pre-write answer arrives last and must not land or restore its stale failure.
  retryLibrary.resolve(envelope([{ contract_id: "retry-stale" }], { source: "retry" }));
  await retry;
  assert.deepEqual(store.getState().upstreamContracts, [{ contract_id: "saved" }]);
  assert.equal("upstreamContracts" in store.getState().endpointErrors, false);
});
