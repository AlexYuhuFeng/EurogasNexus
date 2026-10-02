import { useMemo, useRef, useState } from "react";
import type { ChangeEvent } from "react";
import type { TFunction } from "i18next";
import type { UpstreamContractDTO, UpstreamContractInputDTO } from "@/api/client";
import {
  contractPayloadReadiness,
  cloneDefaultContractDraft,
  contractDraftFromRecord,
  contractRecordFromImportedFile,
} from "@/app/index";
import type { ContractDraft } from "@/app/index";
import { preservedNotesFromRecord } from "@/app/contractImport";
import { applyContractSaveResult, draftNumberFromInput } from "@/app/model/contractDraftModel";
import type { ContractListKey, ContractNumberKey, ContractTextKey } from "@/components/ContractWorkbench";

export function useContractEditor(
  t: TFunction,
  saveContractDraft: (
    body: UpstreamContractInputDTO,
  ) => Promise<UpstreamContractDTO | null>,
  /** Drop a previous save's store feedback when the editor moves to another draft. */
  clearContractSaveFeedback?: () => void,
) {
  const contractImportRef = useRef<HTMLInputElement>(null);
  const [contractImportMessage, setContractImportMessage] = useState<string | null>(null);
  const [draftDirty, setDraftDirty] = useState(false);
  const [contract, setContract] = useState<ContractDraft>(() => cloneDefaultContractDraft());
  // The readiness result is the one payload path: the save uses it and the surface could report
  // it, so there is no second composition that could disagree with the transport.
  const payloadReadiness = useMemo(() => contractPayloadReadiness(contract), [contract]);
  // Two counters decide whether a save result still belongs to the shown draft:
  //   * the session counts draft replacements and identity edits (a stored load, a reset, a
  //     file import, a typed contract id). A result from an earlier session is refused even
  //     when the id reads the same again (a same-id reload, or A -> B -> A while in flight);
  //   * the generation counts every editor act within a session, and decides whether a result
  //     may clear the dirty flag.
  const draftSessionRef = useRef(0);
  const draftGenerationRef = useRef(0);
  const saveInFlightRef = useRef(false);
  // Latest committed draft, kept synchronous by `commitDraft`: a save response folded in
  // before React renders a queued edit must not clobber that edit.
  const contractRef = useRef(contract);

  function commitDraft(update: (current: ContractDraft) => ContractDraft) {
    const next = update(contractRef.current);
    contractRef.current = next;
    setContract(next);
  }

  /** A replacement or identity edit: new draft session, and the old save's notice is stale. */
  function beginDraftSession() {
    draftSessionRef.current += 1;
    draftGenerationRef.current += 1;
    clearContractSaveFeedback?.();
  }

  function updateContractNumber(key: ContractNumberKey, value: string) {
    draftGenerationRef.current += 1;
    setDraftDirty(true);
    // A cleared control is unknown (`null`), never `0`; an explicit zero the operator typed is
    // recorded as `0` and stays one.
    commitDraft((current) => ({ ...current, [key]: draftNumberFromInput(value) }));
  }

  function updateContractText(key: ContractTextKey, value: string) {
    // Typing another contract id rebinds the draft to a new identity: that is a new session,
    // so a save still in flight for the previous identity can never land on this draft.
    if (key === "contract_id") beginDraftSession();
    else draftGenerationRef.current += 1;
    setDraftDirty(true);
    commitDraft((current) => ({
      ...current,
      // The stored edit token belongs to the identity it was read from: typing another
      // contract id makes this draft create-only, never an update of the old row.
      ...(key === "contract_id" ? { stored_edit: null } : {}),
      [key]: value,
    }));
  }

  function updateContractList(key: ContractListKey, value: string) {
    draftGenerationRef.current += 1;
    setDraftDirty(true);
    const items = value.split(",").map((item) => item.trim()).filter(Boolean);
    commitDraft((current) => ({ ...current, [key]: items }));
  }

  function loadPersistedContract(saved: UpstreamContractDTO) {
    beginDraftSession();
    // A persisted row hydrates with the `"stored"` base: terms the row does not carry stay
    // blank instead of inheriting this template's draft facts.
    commitDraft(() => contractDraftFromRecord(saved as unknown as Record<string, unknown>, cloneDefaultContractDraft(), "stored"));
    setDraftDirty(false);
    setContractImportMessage(`${saved.contract_id} ${t("contracts.loaded_for_edit")}`);
  }

  function resetContractDraft() {
    beginDraftSession();
    commitDraft(() => cloneDefaultContractDraft());
    setDraftDirty(false);
    setContractImportMessage(t("contracts.new_draft_loaded"));
  }

  async function importContractDraftFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    try {
      const record = contractRecordFromImportedFile(file.name, await file.text());
      if (!record) throw new Error(t("contracts.import_invalid"));
      beginDraftSession();
      commitDraft((current) => contractDraftFromRecord(record, current));
      setDraftDirty(true);
      setContractImportMessage(`${file.name} ${t("contracts.import_loaded")}`);
    } catch (error) {
      setContractImportMessage(`${t("contracts.import_failed")}: ${String(error)}`);
    } finally {
      event.target.value = "";
    }
  }

  /**
   * Save the reviewed draft through the governed write, then fold the result back in.
   *
   * A failure (including the 409 stale-edit conflict) returns null: the store reports it and
   * this hook leaves the draft and its dirty flag untouched, so a failed save never reads as
   * success. A success refreshes only the stored edit lease and the preserved notes base
   * from the server's own response - never the editor fields - so an edit made while the
   * request was in flight survives, and the draft is cleared dirty only when it was not
   * touched since submission. A committed write whose follow-up library refresh failed is
   * still a success: the store returns the saved contract so this fold adopts its token.
   */
  async function saveContract(): Promise<void> {
    if (saveInFlightRef.current) return;
    // The disabled action is a presentation of this rule, not the guard: an invocation that
    // bypasses the button (keyboard commit, a future caller) must not transport a draft whose
    // required numeric terms are unknown or outside the write route's bounds.
    const readiness = contractPayloadReadiness(contractRef.current);
    if (!readiness.ready || readiness.payload === null) return;
    const payload = readiness.payload;
    const submitted = {
      contractId: contractRef.current.contract_id.trim(),
      session: draftSessionRef.current,
      generation: draftGenerationRef.current,
    };
    saveInFlightRef.current = true;
    try {
      const saved = await saveContractDraft(payload);
      if (!saved) return;
      const applied = applyContractSaveResult({
        current: contractRef.current,
        savedContractId: saved.contract_id,
        savedEditToken: typeof saved.edit_token === "string" ? saved.edit_token : null,
        savedPreservedNotes: preservedNotesFromRecord(saved as unknown as Record<string, unknown>),
        submittedContractId: submitted.contractId,
        submittedSession: submitted.session,
        currentSession: draftSessionRef.current,
        submittedGeneration: submitted.generation,
        currentGeneration: draftGenerationRef.current,
      });
      contractRef.current = applied.contract;
      setContract(applied.contract);
      if (applied.clearDirty) setDraftDirty(false);
    } finally {
      saveInFlightRef.current = false;
    }
  }

  return {
    contract,
    payloadReadiness,
    draftDirty,
    contractImportRef,
    contractImportMessage,
    updateContractNumber,
    updateContractText,
    updateContractList,
    loadPersistedContract,
    resetContractDraft,
    importContractDraftFile,
    saveContract,
  };
}
