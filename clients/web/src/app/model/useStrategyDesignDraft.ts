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

import { useEffect, useMemo, useState } from "react";

import { api as apiClient } from "@/api/client";
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
} from "@/app/model/strategyDraftModel";

type Translate = (key: string) => string;

export interface StrategyDesignDraft {
  readonly form: StrategyDesignFormState;
  readonly setField: (key: keyof StrategyDesignFormState, value: string | boolean) => void;
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
  const version = controller.selectedVersion;
  const frozen = strategyVersionFrozen(version);

  useEffect(() => {
    setForm(strategyFormFromVersion(version?.definition_json));
  }, [version?.definition_json, version?.strategy_version_id]);

  const validation = useMemo(() => strategyDraftValidation(form), [form]);
  const readiness = strategyDraftReadiness({ validation, busy, frozen });

  function setField(key: keyof StrategyDesignFormState, value: string | boolean) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  async function saveDraft() {
    if (!readiness.canSave) return;
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      const body = strategyDraftBody(form);
      if (!controller.selectedStrategy) {
        const created = await apiClient.createStrategy({
          name: strategyDraftName(form),
          description: form.description,
        });
        controller.selectStrategy(created.data.strategy_id);
        const versionResult = await apiClient.createStrategyVersion(created.data.strategy_id, body);
        selection.setStrategyVersionId(versionResult.data.strategy_version_id);
        setMessage(versionResult.data.strategy_version_id);
        await controller.refreshStrategies();
        await controller.refreshVersions(created.data.strategy_id);
      } else if (version && version.status === "DRAFT") {
        await apiClient.updateStrategyVersionDraft(version.strategy_version_id, body);
        await controller.refreshVersions(controller.selectedStrategy.strategy_id);
        setMessage(version.strategy_version_id);
      } else {
        // A frozen version cannot be written through this act; the surface offers a fork instead.
        setError(t("strategy_lab.error.frozen_create_new_version"));
      }
    } catch (err) {
      setError(String(err));
    } finally {
      setBusy(false);
    }
  }

  async function createNewVersion() {
    if (!version || version.status !== "FROZEN") return;
    setBusy(true);
    setError(null);
    try {
      const result = await apiClient.forkStrategyVersion(version.strategy_version_id, {
        definition: strategyDraftBody(form).definition,
        hypothesis: form.hypothesis,
      });
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
    if (!version || version.status !== "DRAFT") return;
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
    form,
    setField,
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
