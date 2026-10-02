/**
 * The governed contract save's outcomes and the scope of its editor feedback (client half,
 * executable).
 *
 * A committed write and the contract-library refresh that follows it are separate outcomes.
 * The observed defect: when the write committed but the follow-up read failed, the store
 * answered null, showed the raw read error as the save message and discarded the refreshed
 * edit token - the user was told the save failed when it had not. The later reviewed defect is
 * the other side of that feedback: a save's success, conflict and error notices name the draft
 * they were saved from, so a draft transition or a newer save must take the notice away from a
 * response still in flight. These tests drive the real store module through the harness with
 * only the HTTP boundary mocked, so the actual async flow is exercised: success survives a
 * failed refresh (with the saved contract returned and the refresh failure reported beside
 * it), a draft transition keeps a late answer from publishing its notice on the next draft, a
 * committed write whose notice moved still refreshes the same-identity library and still
 * returns its result for the editor's own draft-session guard, overlapping saves let the newer
 * one own the notice and the busy flag, and a stale identity generation still drops the
 * response before any readback or commit. Source assertions alone could not show any of that.
 *
 * The notice claim is deliberately not the identity generation: the identity guard decides
 * whether a response may be written at all, while the notice claim only decides whether the
 * surface showing a draft may show its notice. Stale workspace and projection reads are
 * guarded by their own lanes and are outside these tests.
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

/** The backend's stable 409 refusal for a draft whose stored row changed after the read. */
function staleEditRefusal(): Error {
  return Object.assign(new Error("API 409: conflict"), {
    status: 409,
    detail: { error: "conflict", code: "contract_edit_conflict", message: "..." },
    body: { error: "conflict", family: "VALIDATION" },
  });
}

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
  // The committed record's feedback is gone with the identity that earned it: no success
  // message survives, and the dropped refresh raises no notice on the new session's behalf.
  assert.equal(store.getState().contractSaveMessage, null);
  assert.equal(store.getState().contractSaveConflict, false);
  assert.equal(store.getState().error, null);
});

test("a stale-edit refusal keeps the draft and offers no saved contract", async () => {
  const harness = await loadApiStore();
  const store = authenticated(harness);
  harness.answer("saveUpstreamContract", () => Promise.reject(staleEditRefusal()));

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

test("a draft transition keeps an in-flight refusal off the draft the editor moved to", async () => {
  const harness = await loadApiStore();
  const store = authenticated(harness);
  const write = deferred<{ data: typeof SAVED_CONTRACT; meta: Record<string, unknown> }>();
  harness.answer("saveUpstreamContract", () => write.promise);

  const pending = store.getState().saveDraftContract({ contract_id: "stored-contract-1" });
  await settle();
  // The editor moves to another draft (a stored load, reset, import or a typed contract id):
  // the previous draft's notice is dropped, and the save still in flight loses its claim on it.
  store.getState().clearContractSaveFeedback();

  write.reject(staleEditRefusal());
  assert.equal(await pending, null);

  const state = store.getState();
  // The refusal names the draft that was left, so it must not appear on this one.
  assert.equal(state.contractSaveConflict, false);
  assert.equal(state.contractSaveMessage, null);
  assert.equal(state.error, null);
  // No newer action owns the busy flag, so this attempt still completes it.
  assert.equal(state.loading, false);
  // A refusal starts no readback regardless.
  assert.equal(callsTo(harness, "upstreamContracts"), 0);
});

test("a committed write whose draft was left refreshes the same-identity library without a success notice", async () => {
  const harness = await loadApiStore();
  const store = authenticated(harness);
  const write = deferred<{ data: typeof SAVED_CONTRACT; meta: Record<string, unknown> }>();
  harness.answer("saveUpstreamContract", () => write.promise);
  harness.answer("upstreamContracts", () => ({ data: [SAVED_CONTRACT], meta: {} }));

  const pending = store.getState().saveDraftContract({ contract_id: "stored-contract-1" });
  await settle();
  store.getState().clearContractSaveFeedback();
  write.resolve({ data: SAVED_CONTRACT, meta: { source: "test" } });

  // The write committed, so the submitting hook still receives the server's result - its own
  // draft-session guard is what refuses to fold it into a different draft ...
  assert.deepEqual(await pending, SAVED_CONTRACT);
  const state = store.getState();
  // ... while no notice claims a save on the draft the editor now holds ...
  assert.equal(state.contractSaveMessage, null);
  assert.equal(state.contractSaveConflict, false);
  assert.equal(state.error, null);
  assert.equal(state.loading, false);
  // ... and the committed write's library data is not draft-scoped, so it still lands.
  assert.equal(callsTo(harness, "upstreamContracts"), 1);
  assert.deepEqual(state.upstreamContracts, [SAVED_CONTRACT]);
});

test("a same-id reload keeps a committed write's failed refresh from raising its notice", async () => {
  const harness = await loadApiStore();
  const store = authenticated(harness);
  const write = deferred<{ data: typeof SAVED_CONTRACT; meta: Record<string, unknown> }>();
  harness.answer("saveUpstreamContract", () => write.promise);
  harness.answer("upstreamContracts", () => Promise.reject(new Error("API 500: library read failed")));

  const pending = store.getState().saveDraftContract({ contract_id: "stored-contract-1" });
  await settle();
  // A stored reload of the same contract id is still a new draft session, which the hook
  // expresses by clearing the previous save's feedback.
  store.getState().clearContractSaveFeedback();
  write.resolve({ data: SAVED_CONTRACT, meta: {} });

  // The write committed, so a failed follow-up read neither turns the result into a failure
  // nor raises its refresh notice against the reloaded draft.
  assert.deepEqual(await pending, SAVED_CONTRACT);
  const state = store.getState();
  assert.equal(state.contractSaveMessage, null);
  assert.equal(state.contractSaveConflict, false);
  assert.equal(state.error, null);
  assert.equal(state.loading, false);
});

test("a save from the current draft publishes its normal feedback", async () => {
  const harness = await loadApiStore();
  const store = authenticated(harness);
  harness.answer("saveUpstreamContract", () => ({ data: SAVED_CONTRACT, meta: { source: "test" } }));
  harness.answer("upstreamContracts", () => ({ data: [SAVED_CONTRACT], meta: {} }));

  const result = await store.getState().saveDraftContract({ contract_id: "stored-contract-1" });

  assert.deepEqual(result, SAVED_CONTRACT);
  const state = store.getState();
  assert.match(String(state.contractSaveMessage), /stored-contract-1 persisted for decision support/);
  assert.equal(state.contractSaveConflict, false);
  assert.equal(state.loading, false);
  assert.deepEqual(state.upstreamContracts, [SAVED_CONTRACT]);
});

test("overlapping saves: the newer save owns the notice and the busy flag", async () => {
  const harness = await loadApiStore();
  const store = authenticated(harness);
  const older = deferred<{ data: typeof SAVED_CONTRACT; meta: Record<string, unknown> }>();
  const newer = deferred<{ data: typeof SAVED_CONTRACT; meta: Record<string, unknown> }>();
  const writes = [older, newer];
  let writeIndex = 0;
  harness.answer("saveUpstreamContract", () => writes[writeIndex++].promise);
  harness.answer("upstreamContracts", () => ({ data: [SAVED_CONTRACT], meta: {} }));
  const newerContract = { ...SAVED_CONTRACT, contract_id: "stored-contract-2" };

  const olderSave = store.getState().saveDraftContract({ contract_id: "stored-contract-1" });
  const newerSave = store.getState().saveDraftContract({ contract_id: "stored-contract-2" });
  await settle();

  // The older save answers first with a stale-edit refusal. The newer save owns the notice, so
  // the refusal must not appear, and it must not settle the busy flag the newer save owns.
  older.reject(staleEditRefusal());
  assert.equal(await olderSave, null);
  assert.equal(store.getState().contractSaveConflict, false);
  assert.equal(store.getState().contractSaveMessage, null);
  assert.equal(store.getState().loading, true);

  // The newer save's own success then publishes its notice and completes the busy flag.
  newer.resolve({ data: newerContract, meta: {} });
  assert.equal((await newerSave)?.contract_id, "stored-contract-2");
  const state = store.getState();
  assert.match(String(state.contractSaveMessage), /stored-contract-2 persisted for decision support/);
  assert.equal(state.contractSaveConflict, false);
  assert.equal(state.loading, false);
});
