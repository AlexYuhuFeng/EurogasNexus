/**
 * Stale-edit precondition on the contract editor (client half).
 *
 * The governed write now refuses a draft whose stored row changed since it was read
 * (`contract_edit_conflict`), and create-only saves never overwrite an existing identity.
 * These tests pin the client's side of that contract without a browser:

 * * a stored load carries the opaque token with its originating identity, and a new
 *   draft/reset/import (or a changed contract id) clears it, so a token can never bind a
 *   draft to the wrong row;
 * * a successful save refreshes only the lease and the preserved notes base from the
 *   server's response, never the editor fields, so edits made while the request was in
 *   flight survive; the draft is cleared dirty only when it was not touched since submit;
 * * a save result is bound to the draft session that submitted it, not merely to a contract
 *   id: a same-id reload, a reset/import or an A -> B -> A identity edit refuses an older
 *   result even though the id matches again, and a draft transition clears the previous
 *   save's store notice so it cannot show on an unrelated contract;
 * * a conflict is classified from the stable backend code, keeps the draft, and is shown
 *   through the bilingual reconciliation notice - never as a silent retry or success;
 * * a failed or stale-identity save folds nothing into the draft and never clears dirty.
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import {
  contractPayloadReadiness,
  type ContractPayloadReadiness,
} from "../src/app/contractPayload.ts";
import { contractDraftFromRecord } from "../src/app/contractImport.ts";
import { cloneDefaultContractDraft } from "../src/app/defaultContractDraft.ts";
import {
  applyContractSaveResult,
  contractSaveFailureKind,
  draftExpectedEditToken,
  type ContractDraft,
} from "../src/app/model/contractDraftModel.ts";

function readWebSource(relativePath: string): string {
  return readFileSync(new URL(`../src/${relativePath}`, import.meta.url), "utf8");
}

const TOKEN_A = `sha256:${"a".repeat(64)}`;
const TOKEN_B = `sha256:${"b".repeat(64)}`;

function storedRecord(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    contract_id: "stored-contract-1",
    contract_name: "Stored contract 1",
    resource_type: "PIPELINE_IMPORT",
    delivery_point_name: "TTF",
    gas_year: "2025+",
    delivery_quantity_mwh_per_day: 9_000,
    contract_price_gbp_mwh: 27.5,
    settlement_frequency: "monthly",
    upstream_payment_lag_days: 20,
    screen_sale_cash_lag_days: 1,
    annual_financing_rate_pct: 6,
    delivery_tolerance_pct: 2,
    nomination_tolerance_pct: 1,
    tolerance_risk_allowance_gbp_mwh: 0.1,
    owned_entry_capacity_mwh_per_day: null,
    owned_exit_capacity_mwh_per_day: null,
    // The write route carries the cost terms in the row's structured notes and the stored read
    // surfaces them top-level. The fixture records them because a row without a recorded cost
    // term is not transportable (`contractPayloadReadiness`).
    variable_cost_gbp_mwh: 1.25,
    regas_fee_gbp_mwh: 0.5,
    fuel_loss_allowance_pct: 1.1,
    allowed_exit_points: ["NBP", "TTF"],
    eligible_sale_modes: ["TARGET_MARKET_SALE"],
    notes: JSON.stringify({
      source: "upstream_capture",
      unknown_term: { keep: 1 },
      counterparty: "Recorded counterparty",
    }),
    edit_token: TOKEN_A,
    ...overrides,
  };
}

function loadedDraft(overrides: Record<string, unknown> = {}): ContractDraft {
  return contractDraftFromRecord(
    storedRecord(overrides),
    cloneDefaultContractDraft(),
    "stored",
  );
}

/** The transportable payload of a complete fixture draft, through the editor's own boundary. */
function payloadOf(
  draft: ContractDraft,
): NonNullable<ContractPayloadReadiness["payload"]> {
  const readiness = contractPayloadReadiness(draft);
  assert.equal(readiness.ready, true, "the fixture draft must be transportable");
  assert.ok(readiness.payload, "a ready readiness result carries its payload");
  return readiness.payload;
}

test("a new draft is create-only and clears any stored edit lease", () => {
  const draft = cloneDefaultContractDraft();
  assert.equal(draft.stored_edit, null);
  assert.equal(draftExpectedEditToken(draft), null);
  // The payload path is asserted on a new draft the boundary can transport; the template's
  // quantity is the operator-entered placeholder, so it is supplied here as an editor would.
  const savable = { ...draft, delivery_quantity_mwh_per_day: 100 };
  assert.equal(payloadOf(savable).expected_edit_token, null);
});

test("a stored load carries the token with its originating identity", () => {
  const draft = loadedDraft();
  assert.deepEqual(draft.stored_edit, { contract_id: "stored-contract-1", edit_token: TOKEN_A });
  assert.equal(draftExpectedEditToken(draft), TOKEN_A);
  assert.equal(payloadOf(draft).expected_edit_token, TOKEN_A);
});

test("reset, import and a stored row without a token are create-only", () => {
  const loaded = loadedDraft();

  const reset = cloneDefaultContractDraft();
  assert.equal(draftExpectedEditToken(reset), null);

  const imported = contractDraftFromRecord(
    storedRecord({ edit_token: TOKEN_A }),
    loaded,
    "draft",
  );
  assert.equal(imported.stored_edit, null);
  assert.equal(draftExpectedEditToken(imported), null);

  const tokenless = loadedDraft({ edit_token: undefined });
  assert.equal(tokenless.stored_edit, null);
  assert.equal(payloadOf(tokenless).expected_edit_token, null);
});

test("switching stored contracts replaces the lease instead of accumulating it", () => {
  const first = loadedDraft();
  const second = loadedDraft({ contract_id: "stored-contract-2", edit_token: TOKEN_B });

  assert.deepEqual(second.stored_edit, { contract_id: "stored-contract-2", edit_token: TOKEN_B });
  assert.equal(draftExpectedEditToken(second), TOKEN_B);
  // The first draft it replaced is untouched; no lease rode along with the new one.
  assert.equal(draftExpectedEditToken(first), TOKEN_A);
  assert.equal(payloadOf(second).expected_edit_token, TOKEN_B);
});

test("changing the contract id makes the draft create-only", () => {
  const loaded = loadedDraft();
  const renamedIdentity: ContractDraft = { ...loaded, contract_id: "another-contract" };

  // Even if a lease were still attached, a different identity never receives the token.
  assert.equal(draftExpectedEditToken(renamedIdentity), null);
  assert.equal(payloadOf(renamedIdentity).expected_edit_token, null);

  // The editor clears it as the id is typed, rather than relying on the payload check alone.
  const hook = readWebSource("app/hooks/useContractEditor.ts");
  assert.match(hook, /\(key === "contract_id" \? \{ stored_edit: null \}/);
});

test("a successful save refreshes the lease and preserved notes but keeps in-flight edits", () => {
  const loaded = loadedDraft();
  const edited: ContractDraft = { ...loaded, counterparty: "Edited while saving", contract_price_gbp_mwh: 31.5 };
  const savedPreservedNotes = { source: "upstream_capture", unknown_term: { keep: 2 } };

  const applied = applyContractSaveResult({
    current: edited,
    savedContractId: "stored-contract-1",
    savedEditToken: TOKEN_B,
    savedPreservedNotes,
    submittedContractId: "stored-contract-1",
    submittedSession: 1,
    currentSession: 1,
    submittedGeneration: 3,
    currentGeneration: 3,
  });

  assert.equal(applied.clearDirty, true);
  assert.equal(applied.contract.stored_edit?.edit_token, TOKEN_B);
  assert.deepEqual(applied.contract.preserved_notes, savedPreservedNotes);
  // The editor-owned fields are the user's: the response's older values never overwrite them.
  assert.equal(applied.contract.counterparty, "Edited while saving");
  assert.equal(applied.contract.contract_price_gbp_mwh, 31.5);
});

test("a response that arrives after further edits keeps the draft dirty", () => {
  const loaded = loadedDraft();
  const editedAfterSubmit: ContractDraft = { ...loaded, contract_price_gbp_mwh: 33.25 };
  const applied = applyContractSaveResult({
    current: editedAfterSubmit,
    savedContractId: "stored-contract-1",
    savedEditToken: TOKEN_B,
    savedPreservedNotes: null,
    submittedContractId: "stored-contract-1",
    submittedSession: 1,
    currentSession: 1,
    submittedGeneration: 3,
    currentGeneration: 4,
  });

  // The lease still refreshes (it names the stored row the save wrote) ...
  assert.equal(applied.contract.stored_edit?.edit_token, TOKEN_B);
  assert.equal(applied.contract.contract_price_gbp_mwh, 33.25);
  // ... but the unsaved edit keeps the draft dirty.
  assert.equal(applied.clearDirty, false);
});

test("a response for another identity is never attached to the current draft", () => {
  const switched = { ...loadedDraft(), contract_id: "other-contract" };
  const applied = applyContractSaveResult({
    current: switched,
    savedContractId: "stored-contract-1",
    savedEditToken: TOKEN_B,
    savedPreservedNotes: { source: "other" },
    submittedContractId: "stored-contract-1",
    submittedSession: 1,
    currentSession: 1,
    submittedGeneration: 3,
    currentGeneration: 3,
  });

  assert.equal(applied.contract, switched);
  assert.equal(applied.clearDirty, false);
  assert.equal(draftExpectedEditToken(applied.contract), null);
});

test("a same-id reload rejects the older session's result even though the id matches", () => {
  // The user asked for the stored row again while the first save was in flight: the current
  // draft names the same identity, but it is a different draft session, so the older result
  // must not adopt its token, notes or success.
  const reloaded = loadedDraft();
  const applied = applyContractSaveResult({
    current: reloaded,
    savedContractId: "stored-contract-1",
    savedEditToken: TOKEN_B,
    savedPreservedNotes: { source: "stale_session" },
    submittedContractId: "stored-contract-1",
    submittedSession: 1,
    currentSession: 2,
    submittedGeneration: 4,
    currentGeneration: 5,
  });

  assert.equal(applied.contract, reloaded);
  assert.equal(applied.clearDirty, false);
  // The reloaded draft keeps the token it was actually read with; the older save's is not adopted.
  assert.equal(applied.contract.stored_edit?.edit_token, TOKEN_A);
});

test("an A -> B -> A identity round trip is a new session and wins over the older result", () => {
  // The id reads the submitted one again, so an identity-only check would accept the result;
  // the session stamp refuses it instead.
  const backToA: ContractDraft = { ...loadedDraft(), counterparty: "Typed while saving" };
  assert.equal(backToA.contract_id, "stored-contract-1");
  const applied = applyContractSaveResult({
    current: backToA,
    savedContractId: "stored-contract-1",
    savedEditToken: TOKEN_B,
    savedPreservedNotes: { source: "stale_session" },
    submittedContractId: "stored-contract-1",
    submittedSession: 3,
    currentSession: 5,
    submittedGeneration: 2,
    currentGeneration: 4,
  });

  assert.equal(applied.contract, backToA);
  assert.equal(applied.clearDirty, false);
});

test("field edits inside the submitting session adopt the saved token and stay dirty", () => {
  const editedDuringSave: ContractDraft = { ...loadedDraft(), contract_name: "Renamed while saving" };
  const applied = applyContractSaveResult({
    current: editedDuringSave,
    savedContractId: "stored-contract-1",
    savedEditToken: TOKEN_B,
    savedPreservedNotes: { source: "upstream_capture" },
    submittedContractId: "stored-contract-1",
    submittedSession: 7,
    currentSession: 7,
    submittedGeneration: 2,
    currentGeneration: 3,
  });

  // Same session: the refreshed lease is adopted and the in-flight edit survives, but that
  // edit is not what was saved, so dirty must not be cleared.
  assert.equal(applied.contract.stored_edit?.edit_token, TOKEN_B);
  assert.equal(applied.contract.contract_name, "Renamed while saving");
  assert.equal(applied.clearDirty, false);
});

test("an import or reset is a new session even when the id reads the same", () => {
  const imported = contractDraftFromRecord(storedRecord(), loadedDraft(), "draft");
  assert.equal(imported.contract_id, "stored-contract-1");
  assert.equal(imported.stored_edit, null);

  const applied = applyContractSaveResult({
    current: imported,
    savedContractId: "stored-contract-1",
    savedEditToken: TOKEN_B,
    savedPreservedNotes: { source: "stale_session" },
    submittedContractId: "stored-contract-1",
    submittedSession: 1,
    currentSession: 2,
    submittedGeneration: 1,
    currentGeneration: 2,
  });

  assert.equal(applied.contract, imported);
  assert.equal(applied.clearDirty, false);
  // The import stays create-only; the older session's token is never attached to it.
  assert.equal(draftExpectedEditToken(applied.contract), null);

  // A reset (shown here with the id it replaced, the only way it could fool an identity
  // check) is refused the same way.
  const reset: ContractDraft = { ...cloneDefaultContractDraft(), contract_id: "stored-contract-1" };
  const resetApplied = applyContractSaveResult({
    current: reset,
    savedContractId: "stored-contract-1",
    savedEditToken: TOKEN_B,
    savedPreservedNotes: { source: "stale_session" },
    submittedContractId: "stored-contract-1",
    submittedSession: 1,
    currentSession: 2,
    submittedGeneration: 1,
    currentGeneration: 2,
  });

  assert.equal(resetApplied.contract, reset);
  assert.equal(resetApplied.clearDirty, false);
});

test("the stale-edit refusal is classified from the stable backend detail codes", () => {
  const conflict = {
    status: 409,
    detail: { error: "conflict", code: "contract_edit_conflict", message: "..." },
    body: { error: "conflict", family: "VALIDATION" },
  };
  const malformed = {
    status: 409,
    detail: { error: "conflict", code: "contract_edit_token_malformed", message: "..." },
  };
  assert.equal(contractSaveFailureKind(conflict), "contract_edit_conflict");
  assert.equal(contractSaveFailureKind(malformed), "contract_edit_conflict");

  // A capture refusal is a conflict too, but not a stale-edit conflict: it gets its own
  // message rather than the reload/reconcile notice.
  const captureRefusal = {
    status: 409,
    detail: { error: "conflict", code: "contract_revision_mapping_ambiguous" },
  };
  assert.equal(contractSaveFailureKind(captureRefusal), "other");
  assert.equal(contractSaveFailureKind(new Error("network")), "other");
});

test("failed and stale saves fold nothing into the draft and never clear dirty", () => {
  const hook = readWebSource("app/hooks/useContractEditor.ts");
  // The success fold happens only for a returned contract; a null result leaves the draft.
  assert.match(hook, /const saved = await saveContractDraft\(payload\);\s*if \(!saved\) return;/);
  assert.match(hook, /if \(applied\.clearDirty\) setDraftDirty\(false\);/);
  const foldAt = hook.indexOf("applyContractSaveResult({");
  const guardAt = hook.indexOf("if (!saved) return;");
  const clearAt = hook.indexOf("if (applied.clearDirty) setDraftDirty(false);");
  assert.ok(guardAt > 0 && guardAt < foldAt, "the null guard must precede the fold");
  assert.ok(clearAt > foldAt, "dirty is cleared only after the fold decided it");

  const store = readWebSource("stores/api.ts");
  // A stale identity generation answers null before any readback or state commit ...
  assert.ok(
    (store.match(/if \(!followUpReadIsCurrent\(requestGeneration\)\) return null;/g)?.length ?? 0) >= 2,
    "the store must guard the mutation response and the readback against staleness",
  );
  // ... and a failed save reports the failure state, never the success message.
  assert.match(store, /contractSaveFailureKind\(write\.error\) === "contract_edit_conflict"/);
  assert.match(store, /contractSaveMessage: conflict \? null : String\(write\.error\)/);
  // A committed write and its follow-up refresh are separate outcomes: the refresh failure
  // is reported beside the success, and the saved contract is still returned to the editor.
  assert.match(store, /was saved, but refreshing the contract library failed/);
  assert.match(store, /return saved\.data;/);
});

test("the editor separates its draft-session epoch from field edit generations", () => {
  const hook = readWebSource("app/hooks/useContractEditor.ts");
  // The session bumps once per replacement/identity transition, through the one helper the
  // stored load, the reset, the import and a typed contract id all call.
  assert.match(hook, /draftSessionRef\.current \+= 1/);
  assert.ok(
    (hook.match(/beginDraftSession\(\);/g)?.length ?? 0) >= 4,
    "stored load, reset, import and identity edit each start a new draft session",
  );
  assert.match(hook, /if \(key === "contract_id"\) beginDraftSession\(\);/);
  // The submit stamps the session, and the fold compares the current one with it.
  assert.match(hook, /session: draftSessionRef\.current/);
  assert.match(hook, /submittedSession: submitted\.session/);
  assert.match(hook, /currentSession: draftSessionRef\.current/);
  // The draft is held synchronously, so a fold cannot clobber an edit queued before render.
  assert.match(hook, /function commitDraft\(update: \(current: ContractDraft\) => ContractDraft\)/);
  assert.equal(hook.includes("contractRef.current = contract;"), false);
});

test("editor transitions clear the previous save's store notice", () => {
  const hook = readWebSource("app/hooks/useContractEditor.ts");
  // The shared session transition is the single place that drops the old notice ...
  assert.match(hook, /clearContractSaveFeedback\?\.\(\)/);
  const beginAt = hook.indexOf("function beginDraftSession()");
  const clearAt = hook.indexOf("clearContractSaveFeedback?.()");
  assert.ok(beginAt > 0 && clearAt > beginAt, "the transition helper clears the store notice");
  // ... and that action clears both the message and the conflict flag, while releasing any
  // save still in flight from publishing its own notice on the new draft.
  const store = readWebSource("stores/api.ts");
  const clearAction = store.slice(
    store.indexOf("clearContractSaveFeedback: () => {"),
    store.indexOf("saveDraftContract: async"),
  );
  const feedbackClaimAt = clearAction.indexOf("contractSaveFeedbackSequence += 1;");
  const clearSetAt = clearAction.indexOf(
    "set({ contractSaveMessage: null, contractSaveConflict: false });",
  );
  assert.ok(feedbackClaimAt > 0, "the transition releases an in-flight save's feedback claim");
  assert.ok(clearSetAt > feedbackClaimAt, "the claim is released before the notice is cleared");
});

test("the conflict is surfaced through the bilingual reconciliation notice", () => {
  const workbench = readWebSource("components/ContractWorkbench.tsx");
  assert.match(workbench, /contractSaveConflict/);
  assert.match(workbench, /t\("contracts\.edit_conflict_title"\)/);
  assert.match(workbench, /t\("contracts\.edit_conflict_detail"\)/);

  const en = JSON.parse(readWebSource("i18n/en.json")) as Record<string, string>;
  const zh = JSON.parse(readWebSource("i18n/zh.json")) as Record<string, string>;
  for (const key of ["contracts.edit_conflict_title", "contracts.edit_conflict_detail"]) {
    assert.ok(en[key]?.trim(), `en.json is missing ${key}`);
    assert.ok(zh[key]?.trim(), `zh.json is missing ${key}`);
    assert.notEqual(en[key], zh[key], `${key} must be translated, not copied`);
  }
  assert.match(en["contracts.edit_conflict_detail"], /Reload the stored resource/);
  assert.match(zh["contracts.edit_conflict_detail"], /重新加载已保存资源/);
});
