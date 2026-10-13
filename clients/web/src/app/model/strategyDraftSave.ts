import type { StrategyCreateInputDTO, StrategyVersionCreateInputDTO, StrategyVersionDTO } from "../../api/client.ts";

export interface StrategyDraftCreation {
  strategyId: string;
  identityKnown: boolean;
  identityAttempted: boolean;
  versionAttempted: boolean;
}

export interface StrategyDraftSaveClient {
  strategy: (id: string) => Promise<unknown>;
  createStrategy: (body: StrategyCreateInputDTO) => Promise<unknown>;
  strategyVersions: (id: string) => Promise<{ data: StrategyVersionDTO[] }>;
  createStrategyVersion: (id: string, body: StrategyVersionCreateInputDTO) => Promise<{ data: StrategyVersionDTO }>;
}

export function newStrategyDraftCreation(strategyId: string, existing = false): StrategyDraftCreation {
  return { strategyId, identityKnown: existing, identityAttempted: false, versionAttempted: false };
}

export function draftVersionRecoveryKey(deployment: string, principalId: string, strategyId: string): string {
  return `eurogas.strategy-draft.pending-version:${encodeURIComponent(deployment)}:${encodeURIComponent(principalId)}:${encodeURIComponent(strategyId)}`;
}

/** The server adds schema defaults. Every supplied field must still match exactly. */
function containsSupplied(stored: unknown, supplied: unknown): boolean {
  if (Array.isArray(supplied)) return Array.isArray(stored) && stored.length === supplied.length &&
    supplied.every((value, index) => containsSupplied(stored[index], value));
  if (supplied !== null && typeof supplied === "object") return stored !== null && typeof stored === "object" &&
    Object.entries(supplied).every(([key, value]) => containsSupplied((stored as Record<string, unknown>)[key], value));
  return stored === supplied;
}

export function strategyVersionMatchesDraft(version: StrategyVersionDTO, body: StrategyVersionCreateInputDTO): boolean {
  return version.status === "DRAFT" && version.hypothesis === (body.hypothesis ?? "") &&
    containsSupplied(version.definition_json, {
      ...body.definition,
      strategy_name: body.strategy_name,
      run_mode: body.run_mode,
      resource_contexts: body.resource_contexts,
      price_observations: body.price_observations,
      existing_shadow_pnl_gbp: body.existing_shadow_pnl_gbp,
    });
}

/** A two-step first save, with authoritative reads before retrying uncertain writes.
 * This is client recovery within one draft, not a server exactly-once guarantee.
 */
export async function saveFirstStrategyDraft(input: {
  creation: StrategyDraftCreation;
  identity: { name: string; description: string };
  body: StrategyVersionCreateInputDTO;
  client: StrategyDraftSaveClient;
}): Promise<StrategyVersionDTO> {
  const { creation, identity, body, client } = input;
  if (!creation.identityKnown) {
    if (creation.identityAttempted) {
      try {
        await client.strategy(creation.strategyId);
        creation.identityKnown = true;
      } catch (error) {
        if ((error as { status?: number }).status !== 404) throw error;
      }
    }
    if (!creation.identityKnown) {
      creation.identityAttempted = true;
      await client.createStrategy({ strategy_id: creation.strategyId, ...identity });
      creation.identityKnown = true;
    }
  }

  // A failed GET is uncertainty, never permission to blindly repeat a POST.
  const versions = (await client.strategyVersions(creation.strategyId)).data;
  if (versions.length > 0) {
    // Recover only this draft's prior attempt, with one exact editable match.
    // Existing/frozen or changed definitions require deliberate version selection.
    if (creation.versionAttempted && versions.length === 1 && strategyVersionMatchesDraft(versions[0], body)) {
      return versions[0];
    }
    throw new Error("strategy_lab.error.version_recovery_review");
  }
  if (creation.versionAttempted) {
    // Even an empty read cannot prove a timed-out original request will not
    // commit later. Without server idempotency, never blindly re-POST here.
    throw new Error("strategy_lab.error.version_outcome_unknown");
  }
  creation.versionAttempted = true;
  return (await client.createStrategyVersion(creation.strategyId, body)).data;
}
