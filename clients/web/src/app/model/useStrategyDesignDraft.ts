/**
 * Strategy design draft (Architecture V2 Wave 9, action geography).
 *
 * The Design task's `persist` act is saving the draft, and the geography puts it in the
 * workspace's primary slot. That was not possible while the draft - the form, its validation, the
 * request body and the busy/message/error state - lived inside the panel that renders the fields,
 * so the draft moved here and the workspace that hosts the action owns it. The panel receives it
 * and renders it.
 *
 * Only the panel's own view state stays with the panel: nothing about *what would be written*
 * belongs to the surface that happens to display the form.
 */

import { useEffect, useMemo, useRef, useState } from "react";
import type { UpstreamContractDTO } from "@/api/client";
import { strategyFormForContract } from "./strategyResourceHandoff";
import { draftVersionRecoveryKey, newStrategyDraftCreation, saveFirstStrategyDraft, type StrategyDraftCreation } from "./strategyDraftSave";
import { useApiStore } from "@/stores/api";

import { api as apiClient, configuredApiBaseUrl } from "@/api/client";
import type { StrategyLabController, StrategyLabSelection } from "@/app/model/useStrategyLab";
import {
  DEFAULT_STRATEGY_FORM,
  strategyDraftBody,
  strategyDraftName,
  strategyDraftReadiness,
  strategyDraftValidation,
  strategyFormFromVersion,
  strategyVersionFrozen,
  type StrategyDesignFormState,
  type StrategyEvidenceDeclarationState,
} from "@/app/model/strategyDraftModel";

type Translate = (key: string) => string;

type EvidenceLegKey = "dayAheadEvidence" | "intradayEvidence";

export interface StrategyDesignDraft {
  readonly dirty: boolean;
  readonly pendingContract: UpstreamContractDTO | null;
  readonly resourceOrigin: UpstreamContractDTO | null;
  readonly offerContract: (contract: UpstreamContractDTO) => void;
  readonly acceptContract: () => void;
  readonly cancelContract: () => void;
  readonly form: StrategyDesignFormState;
  readonly setField: (key: keyof StrategyDesignFormState, value: string | boolean) => void;
  /** Change one field of one leg's evidence declaration. */
  readonly setEvidenceField: (
    leg: EvidenceLegKey,
    field: keyof StrategyEvidenceDeclarationState,
    value: string | boolean,
  ) => void;
  readonly validation: ReturnType<typeof strategyDraftValidation>;
  readonly readiness: ReturnType<typeof strategyDraftReadiness>;
  readonly frozen: boolean;
  readonly busy: boolean;
  readonly message: string | null;
  readonly error: string | null;
  /** Save the draft: create the strategy and its first version, or update an editable version. */
  readonly saveDraft: () => Promise<void>;
  /** Fork a frozen version into a new draft (a `lifecycle` act, kept out of the primary slot). */
  readonly createNewVersion: () => Promise<void>;
  /** Freeze the editable version (a `lifecycle` act, kept out of the primary slot). */
  readonly freezeVersion: () => Promise<void>;
}

export function useStrategyDesignDraft({
  controller,
  selection,
  t,
}: {
  controller: StrategyLabController;
  selection: StrategyLabSelection;
  t: Translate;
}): StrategyDesignDraft {
  const [form, setForm] = useState<StrategyDesignFormState>(DEFAULT_STRATEGY_FORM);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [dirty, setDirty] = useState(false);
  const [pendingContract, setPendingContract] = useState<UpstreamContractDTO | null>(null);
  const [resourceOrigin, setResourceOrigin] = useState<UpstreamContractDTO | null>(null);
  const newDraft = useRef<StrategyDesignFormState | null>(null);
  const creation = useRef<StrategyDraftCreation | null>(null);
  const creationContext = useRef<string | null>(null);
  const creationSelection = useRef<string | null>(null);
  const principalId = useApiStore((state) => state.currentUser?.principal_id ?? null);
  const saveInFlight = useRef(false);
  const hydratedVersionId = useRef<string | null>(null);
  const version = controller.selectedVersion;
  const frozen = strategyVersionFrozen(version);
  const readOnly = Boolean(selection.strategyId) && !controller.canManageSelectedStrategy;

  useEffect(() => {
    // Keep the entered form while a selected version is loading or this save
    // is refreshing its lists. Refreshing the same version cannot erase edits.
    if (saveInFlight.current || (!version && selection.strategyVersionId)) return;
    if (version) {
      if (dirty && hydratedVersionId.current === version.strategy_version_id) return;
      hydratedVersionId.current = version.strategy_version_id;
      creation.current = null;
      creationContext.current = null;
      newDraft.current = null;
      setResourceOrigin(null);
      setForm(strategyFormFromVersion(version.definition_json));
      setDirty(false);
    } else {
      if (dirty) return;
      hydratedVersionId.current = null;
      setForm(newDraft.current ?? DEFAULT_STRATEGY_FORM);
      setDirty(newDraft.current !== null);
    }
  }, [version?.definition_json, version?.strategy_version_id, selection.strategyVersionId, busy]);

  const validation = useMemo(() => strategyDraftValidation(form), [form]);
  const baseReadiness = strategyDraftReadiness({ validation, busy, frozen });
  const readiness = readOnly ? { canSave: false, blockerKeys: ["strategy_lab.sharing.read_only"], firstBlockerKey: "strategy_lab.sharing.read_only" } : baseReadiness;

  function setField(key: keyof StrategyDesignFormState, value: string | boolean) {
    if (saveInFlight.current) return;
    setForm((current) => ({ ...current, [key]: value }));
    setDirty(true);
  }

  function setEvidenceField(
    leg: EvidenceLegKey,
    field: keyof StrategyEvidenceDeclarationState,
    value: string | boolean,
  ) {
    if (saveInFlight.current) return;
    setDirty(true);
    setForm((current) => ({
      ...current,
      [leg]: { ...current[leg], [field]: value },
    }));
  }

  function acceptContract() {
    // An offer never retargets a stored version. Existing unsaved edits must be
    // completed first; canceling the offer leaves their form and selection intact.
    if (!pendingContract || dirty || busy) return;
    const next = strategyFormForContract(pendingContract);
    creation.current = null;
    creationContext.current = null;
    newDraft.current = next;
    controller.selectStrategy(null);
    setForm(next);
    setResourceOrigin(pendingContract);
    setDirty(true);
    setPendingContract(null);
    setError(null);
    setMessage(null);
  }

  async function saveDraft() {
    if (readOnly || !readiness.canSave || saveInFlight.current) return;
    saveInFlight.current = true;
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      const body = strategyDraftBody(form);
      if (!version && (!selection.strategyVersionId || creation.current)) {
        // An acknowledged identity belongs to this save attempt independently
        // of the asynchronously refreshed strategy navigator.
        if (!principalId) throw new Error("strategy_lab.error.version_outcome_unknown");
        const deployment = new URL(configuredApiBaseUrl(), window.location.origin).href;
        const context = JSON.stringify([deployment, principalId]);
        if (creation.current && (creationContext.current !== context ||
            (selection.strategyId !== creationSelection.current && selection.strategyId !== creation.current.strategyId))) {
          throw new Error("strategy_lab.error.version_recovery_review");
        }
        if (!creation.current) {
          creation.current = newStrategyDraftCreation(
            selection.strategyId ?? `strategy-draft-${crypto.randomUUID()}`, selection.strategyId !== null,
          );
          creationContext.current = context;
          creationSelection.current = selection.strategyId;
          creation.current.versionAttempted = sessionStorage.getItem(
            draftVersionRecoveryKey(deployment, principalId, creation.current.strategyId),
          ) === "pending";
        }
        const recoveryKey = draftVersionRecoveryKey(deployment, principalId, creation.current.strategyId);
        const saved = await saveFirstStrategyDraft({
          creation: creation.current,
          identity: { name: strategyDraftName(form), description: form.description },
          body,
          client: {
            ...apiClient,
            createStrategyVersion: async (id, draftBody) => {
              // No form/credential values: retain only uncertainty for this
              // deployment, authenticated identity and strategy across reload.
              sessionStorage.setItem(recoveryKey, "pending");
              return apiClient.createStrategyVersion(id, draftBody);
            },
          },
        });
        sessionStorage.removeItem(recoveryKey);
        newDraft.current = form;
        controller.selectStrategy(creation.current.strategyId);
        await controller.refreshStrategies();
        await controller.refreshVersions(creation.current.strategyId);
        selection.setStrategyVersionId(saved.strategy_version_id);
        setMessage(saved.strategy_version_id);
      } else if (version && version.status === "DRAFT") {
        await apiClient.updateStrategyVersionDraft(version.strategy_version_id, body);
        await controller.refreshVersions(version.strategy_id);
        setMessage(version.strategy_version_id);
      } else {
        // A frozen version cannot be written through this act; the surface offers a fork instead.
        setError(t("strategy_lab.error.frozen_create_new_version"));
        return;
      }
      setDirty(false);
    } catch (err) {
      setError(err instanceof Error && err.message.startsWith("strategy_lab.error.version_")
        ? t(err.message) : String(err));
    } finally {
      saveInFlight.current = false;
      setBusy(false);
    }
  }

  async function createNewVersion() {
    if (readOnly || !version || version.status !== "FROZEN") return;
    setBusy(true);
    setError(null);
    try {
      // Fork the complete stored definition; the editor is only a projection.
      const result = await apiClient.forkStrategyVersion(version.strategy_version_id, {});
      controller.selectVersion(result.data.strategy_version_id);
      await controller.refreshVersions(version.strategy_id);
      setMessage(result.data.strategy_version_id);
    } catch (err) {
      setError(String(err));
    } finally {
      setBusy(false);
    }
  }

  async function freezeVersion() {
    if (readOnly || !version || version.status !== "DRAFT") return;
    setBusy(true);
    try {
      await apiClient.freezeStrategyVersion(version.strategy_version_id);
      await controller.refreshVersions(version.strategy_id);
    } catch (err) {
      setError(String(err));
    } finally {
      setBusy(false);
    }
  }

  return {
    dirty,
    pendingContract,
    resourceOrigin,
    offerContract: setPendingContract,
    acceptContract,
    cancelContract: () => setPendingContract(null),
    form,
    setField,
    setEvidenceField,
    validation,
    readiness,
    frozen,
    busy,
    message,
    error,
    saveDraft,
    createNewVersion,
    freezeVersion,
  };
}
