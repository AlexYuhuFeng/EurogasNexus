/**
 * Strategy identity metadata (Architecture V2, Wave 9 surface completion).
 *
 * The route has accepted `PATCH /api/strategies/{id}/metadata` since the registry shipped and no
 * surface ever sent it, so renaming a strategy meant calling the API. The edit belongs to the
 * strategy *identity*, not to a version: the version draft has the workspace's primary action, and
 * this is a second `persist` on a different object, so it sits bounded beside that object exactly
 * where its `lifecycle` acts do.
 *
 * The rule and the state live here for the same reason the draft's do: a panel that held what would
 * be written could not report the verdict the workspace gates the action on, and the workspace's own
 * test holds every panel to rendering rather than deciding. What the panel keeps is the fields.
 */

import { useCallback, useEffect, useState } from "react";

import type { StrategyLabController } from "@/app/model/useStrategyLab";

/** Route bounds for the identity edit (`StrategyMetadataUpdateRequest`). */
export const STRATEGY_NAME_MAX_LENGTH = 256;
export const STRATEGY_DESCRIPTION_MAX_LENGTH = 4000;

export interface StrategyIdentityMetadata {
  readonly name: string;
  readonly description: string;
  /** The tags as the field shows them; the request splits them. */
  readonly tags: string;
  readonly setName: (value: string) => void;
  readonly setDescription: (value: string) => void;
  readonly setTags: (value: string) => void;
  /** Whether the fields differ from the identity's own values. */
  readonly dirty: boolean;
  /** Whether the edit may be sent: the identity is selected, named, and actually changed. */
  readonly canSave: boolean;
  readonly busy: boolean;
  readonly saved: boolean;
  readonly error: string | null;
  readonly save: () => Promise<void>;
}

/** Split the tag field into the list the route accepts, dropping blank entries. */
export function identityTags(value: string): string[] {
  return value
    .split(",")
    .map((tag) => tag.trim())
    .filter(Boolean);
}

/** Whether an identity edit differs from the identity it would be written to. */
export function identityEditIsDirty(
  identity: { name: string; description: string; tags: readonly string[] } | null,
  fields: { name: string; description: string; tags: string },
): boolean {
  if (!identity) return false;
  return (
    fields.name.trim() !== identity.name ||
    fields.description !== identity.description ||
    identityTags(fields.tags).join(",") !== [...identity.tags].join(",")
  );
}

export function useStrategyIdentityMetadata({
  controller,
}: {
  controller: StrategyLabController;
}): StrategyIdentityMetadata {
  const strategy = controller.selectedStrategy;
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [tags, setTags] = useState("");
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // The fields follow the selected identity until the user edits them: a form that kept the previous
  // strategy's name after a switch would offer to write it into the new one.
  useEffect(() => {
    setName(strategy?.name ?? "");
    setDescription(strategy?.description ?? "");
    setTags((strategy?.tags ?? []).join(", "));
    setSaved(false);
    setError(null);
  }, [strategy?.strategy_id, strategy?.name, strategy?.description, strategy?.tags]);

  const fields = { name, description, tags };
  const identity = strategy
    ? { name: strategy.name, description: strategy.description, tags: strategy.tags }
    : null;
  const dirty = identityEditIsDirty(identity, fields);
  // A name is required and the edit must change something. The route accepts a no-op (it returns the
  // identity unchanged), but a surface that offers to write the values already stored is offering an
  // action with no effect.
  const canSave = Boolean(strategy) && name.trim().length > 0 && dirty;

  const save = useCallback(async () => {
    if (!strategy || !canSave) return;
    setBusy(true);
    setError(null);
    setSaved(false);
    // The controller performs the write and refreshes the identity list, so the surface never holds
    // a second copy of the identity it just changed.
    const updated = await controller.updateStrategyMetadata(strategy.strategy_id, {
      name: name.trim(),
      description,
      tags: identityTags(tags),
    });
    if (updated) {
      setSaved(true);
      setError(null);
    } else {
      setError(controller.error ?? "identity_update_failed");
    }
    setBusy(false);
  }, [canSave, controller, description, name, strategy, tags]);

  return {
    name,
    description,
    tags,
    setName: (value) => {
      setSaved(false);
      setName(value);
    },
    setDescription: (value) => {
      setSaved(false);
      setDescription(value);
    },
    setTags: (value) => {
      setSaved(false);
      setTags(value);
    },
    dirty,
    canSave,
    busy,
    saved,
    error: error ?? null,
    save,
  };
}
