import { useMemo, useRef, useState } from "react";
import type { ChangeEvent } from "react";
import type { TFunction } from "i18next";
import type { UpstreamContractDTO } from "@/api/client";
import {
  buildContractPayload,
  cloneDefaultContractDraft,
  contractDraftFromRecord,
  contractRecordFromImportedFile,
} from "@/app/index";
import type { ContractDraft } from "@/app/index";
import type { ContractNumberKey, ContractTextKey } from "@/components/ContractWorkbench";

export function useContractEditor(t: TFunction) {
  const contractImportRef = useRef<HTMLInputElement>(null);
  const [contractImportMessage, setContractImportMessage] = useState<string | null>(null);
  const [contract, setContract] = useState<ContractDraft>(() => cloneDefaultContractDraft());
  const contractPayload = useMemo(() => buildContractPayload(contract), [contract]);

  function updateContractNumber(key: ContractNumberKey, value: string) {
    setContract((current) => ({ ...current, [key]: value === "" ? 0 : Number(value) }));
  }

  function updateContractText(key: ContractTextKey, value: string) {
    setContract((current) => ({ ...current, [key]: value }));
  }

  function loadPersistedContract(saved: UpstreamContractDTO) {
    setContract((current) => contractDraftFromRecord(saved as unknown as Record<string, unknown>, current));
    setContractImportMessage(`${saved.contract_id} ${t("contracts.loaded_for_edit")}`);
  }

  function resetContractDraft() {
    setContract(cloneDefaultContractDraft());
    setContractImportMessage(t("contracts.new_draft_loaded"));
  }

  async function importContractDraftFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    try {
      const record = contractRecordFromImportedFile(file.name, await file.text());
      if (!record) throw new Error(t("contracts.import_invalid"));
      setContract((current) => contractDraftFromRecord(record, current));
      setContractImportMessage(`${file.name} ${t("contracts.import_loaded")}`);
    } catch (error) {
      setContractImportMessage(`${t("contracts.import_failed")}: ${String(error)}`);
    } finally {
      event.target.value = "";
    }
  }

  return {
    contract,
    contractPayload,
    contractImportRef,
    contractImportMessage,
    updateContractNumber,
    updateContractText,
    loadPersistedContract,
    resetContractDraft,
    importContractDraftFile,
  };
}
