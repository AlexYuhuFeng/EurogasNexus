/**
 * The governed contract save's two outcomes (client half, executable).
 *
 * A committed write and the contract-library refresh that follows it are separate outcomes.
 * The observed defect: when the write committed but the follow-up read failed, the store
 * answered null, showed the raw read error as the save message and discarded the refreshed
 * edit token - the user was told the save failed when it had not. These tests drive the real
 * store module through the harness with only the HTTP boundary mocked, so the actual async
 * flow is exercised: success survives a failed refresh (with the saved contract returned and
 * the refresh failure reported beside it), a stale identity generation still drops the
 * response before any readback or commit, and a refresh snapshot never overwrites a newer
 * read. Source assertions alone could not show any of that.
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

const SAVED_CONTRACT = {
  contract_id: "stored-contract-1",
  contract_name: "Stored contract 1",
  edit_token: TOKEN_B,
  write_outcome: "metadata_updated",
};

function authenticated(harness: ApiStoreHarness) {
  harness.store.setState({ authState: AUTHENTICATED_AUTH_STATE });
  return harness.store;
}

const callsTo = (harness: ApiStoreHarness, method: string) =>
  harness.calls.filter((call) => call.method === method).length;

test("a committed write stays a success when the library refresh fails", async () => {
  const harness = await loadApiStore();
  const store = authenticated(harness);
  harness.answer("saveUpstreamContract", () => ({ data: SAVED_CONTRACT, meta: { source: "test" } }));
  harness.answer("upstreamContracts", () => Promise.reject(new Error("API 500: library read failed")));

  const result = await store.getState().saveDraftContract({ contract_id: "stored-contract-1" });

  // The editor receives the saved contract (its refreshed edit token included) ...
  assert.deepEqual(result, SAVED_CONTRACT);
  const state = store.getState();
  // ... the success message stands and never claims the save failed ...
  assert.match(String(state.contractSaveMessage), /stored-contract-1 persisted for decision support/);
  assert.equal(String(state.contractSaveMessage).includes("failed"), false);
  assert.equal(state.contractSaveConflict, false);
  assert.equal(state.loading, false);
  // ... while the refresh failure is reported in its own lane, naming the write as saved.
  assert.match(String(state.error), /was saved, but refreshing the contract library failed/);
  assert.match(String(state.error), /library read failed/);
  // No automatic retry of the write.
  assert.equal(callsTo(harness, "saveUpstreamContract"), 1);
});

test("an identity session that ended while the write was in flight drops it before any commit", async () => {
  const harness = await loadApiStore();
  const store = authenticated(harness);
  const write = deferred<{ data: typeof SAVED_CONTRACT; meta: Record<string, unknown> }>();
  harness.answer("saveUpstreamContract", () => write.promise);
  harness.answer("upstreamContracts", () => ({ data: [SAVED_CONTRACT], meta: {} }));
  harness.answer("me", () => {
    throw new Error("API 401: session expired");
  });

  const pending = store.getState().saveDraftContract({ contract_id: "stored-contract-1" });
  // The identity session ends before the write answers (a 401 on the follow-up identity read).
  await store.getState().fetchMe();
  write.resolve({ data: SAVED_CONTRACT, meta: {} });

  assert.equal(await pending, null);
  const state = store.getState();
  assert.equal(state.contractSaveMessage, null);
  assert.equal(state.contractSaveConflict, false);
  // A dropped response starts neither the readback nor a state commit.
  assert.equal(callsTo(harness, "upstreamContracts"), 0);
});

test("identity invalidation during refresh drops the committed record as well as the snapshot", async () => {
  const harness = await loadApiStore();
  const store = authenticated(harness);
  const write = deferred<{ data: typeof SAVED_CONTRACT; meta: Record<string, unknown> }>();
  const refresh = deferred<{ data: unknown[]; meta: Record<string, unknown> }>();
  harness.answer("saveUpstreamContract", () => write.promise);
  harness.answer("upstreamContracts", () => refresh.promise);
  harness.answer("me", () => {
    throw new Error("API 401: session expired");
  });

  const pending = store.getState().saveDraftContract({ contract_id: "stored-contract-1" });
  write.resolve({ data: SAVED_CONTRACT, meta: {} });
  await settle();
  assert.equal(callsTo(harness, "upstreamContracts"), 1, "the refresh is in flight");

  // Authentication failure invalidates the identity that owns this commercial record.
  await store.getState().fetchMe();
  refresh.resolve({ data: [SAVED_CONTRACT], meta: {} });
  await settle();

  // Neither the editor nor the store may receive data from the expired identity.
  assert.equal(await pending, null);
  assert.deepEqual(store.getState().upstreamContracts, []);
});

test("a stale-edit refusal keeps the draft and offers no saved contract", async () => {
  const harness = await loadApiStore();
  const store = authenticated(harness);
  const refusal = Object.assign(new Error("API 409: conflict"), {
    status: 409,
    detail: { error: "conflict", code: "contract_edit_conflict", message: "..." },
    body: { error: "conflict", family: "VALIDATION" },
  });
  harness.answer("saveUpstreamContract", () => Promise.reject(refusal));

  assert.equal(await store.getState().saveDraftContract({ contract_id: "stored-contract-1" }), null);
  const state = store.getState();
  assert.equal(state.contractSaveConflict, true);
  assert.equal(state.contractSaveMessage, null);
  assert.equal(state.loading, false);
  assert.match(String(state.error), /API 409/);
  assert.equal(callsTo(harness, "upstreamContracts"), 0);

  // The editor's draft transition clears the notice instead of showing it on another draft.
  store.getState().clearContractSaveFeedback();
  const cleared = store.getState();
  assert.equal(cleared.contractSaveConflict, false);
  assert.equal(cleared.contractSaveMessage, null);
});
