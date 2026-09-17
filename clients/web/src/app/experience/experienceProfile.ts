/**
 * Client view of the backend ExperienceProfile (Architecture V2 Wave 2).
 *
 * `GET /api/me` returns an `experience` object (built by the backend capability
 * module under `src/…/security/capabilities.py`) describing what the
 * authenticated identity may compose: functional assignments, available work
 * modes and the capability names it already holds.
 *
 * Two rules govern this module:
 *
 * 1. **Composition, never authority.** The profile is a *view* of access the
 *    backend already granted. Nothing here may be used to allow an action; the
 *    backend re-authorises every request. `grantsAuthority` is `false` and is
 *    asserted by the focused tests.
 * 2. **Fail closed, and fall back honestly.** An absent or malformed profile is
 *    reported as "no server composition available" rather than silently
 *    defaulting to every mode, so a client cannot widen its own surface.
 */

import type { ExperienceProfileDTO } from "@/api/client";
import { WORK_MODE_IDS, type WorkModeId, workModeComposition } from "./workModes.ts";

/** Server work-mode ids (SCREAMING_SNAKE) mapped to the client's composition ids. */
export const SERVER_WORK_MODE_IDS: Readonly<Record<WorkModeId, string>> = {
  "trading-analysis": "TRADING_ANALYSIS",
  "portfolio-oversight": "PORTFOLIO_OVERSIGHT",
  research: "RESEARCH",
  review: "REVIEW",
  administration: "ADMINISTRATION",
};

export interface ClientExperienceComposition {
  /** Whether a usable server composition was parsed. */
  readonly available: boolean;
  /** Client work-mode ids the identity may compose, in the client's order. */
  readonly workModes: readonly WorkModeId[];
  readonly defaultWorkMode: WorkModeId | null;
  readonly functionalAssignments: readonly string[];
  readonly effectiveCapabilities: readonly string[];
  readonly commercialCapabilities: readonly string[];
  readonly scopeRefs: readonly string[];
  /** Scope kinds Architecture V2 defines that the backend cannot express yet. */
  readonly unsupportedScopeKinds: readonly string[];
  /** Always false: composition never grants authority. */
  readonly grantsAuthority: false;
}

const EMPTY_COMPOSITION: ClientExperienceComposition = {
  available: false,
  workModes: [],
  defaultWorkMode: null,
  functionalAssignments: [],
  effectiveCapabilities: [],
  commercialCapabilities: [],
  scopeRefs: [],
  unsupportedScopeKinds: [],
  grantsAuthority: false,
};

function clientWorkMode(serverValue: string): WorkModeId | null {
  const normalized = (serverValue ?? "").trim().toUpperCase();
  for (const id of WORK_MODE_IDS) {
    if (SERVER_WORK_MODE_IDS[id] === normalized) return id;
  }
  return null;
}

function stringList(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.filter((item): item is string => typeof item === "string" && item.length > 0);
}

/**
 * Parse the server composition. Unknown work modes are dropped (the client must
 * not invent a composition for a mode it does not implement), and a profile that
 * claims composition authority is refused outright.
 */
export function compositionFromProfile(
  profile: ExperienceProfileDTO | null | undefined,
): ClientExperienceComposition {
  if (!profile || typeof profile !== "object") return EMPTY_COMPOSITION;
  if (profile.work_mode_grants_authority === true) return EMPTY_COMPOSITION;

  const workModes = stringList(profile.available_work_modes)
    .map(clientWorkMode)
    .filter((id): id is WorkModeId => id !== null);

  const declaredDefault = profile.default_work_mode ? clientWorkMode(profile.default_work_mode) : null;
  const defaultWorkMode =
    declaredDefault && workModes.includes(declaredDefault) ? declaredDefault : (workModes[0] ?? null);

  return {
    available: true,
    workModes,
    defaultWorkMode,
    functionalAssignments: stringList(profile.functional_assignments),
    effectiveCapabilities: stringList(profile.effective_capabilities),
    commercialCapabilities: stringList(profile.commercial_capabilities),
    scopeRefs: stringList(profile.scope_refs),
    unsupportedScopeKinds: stringList(profile.unsupported_scope_kinds),
    grantsAuthority: false,
  };
}

/** Composition contracts for the modes the identity may actually compose. */
export function availableModeCompositions(
  composition: ClientExperienceComposition,
): ReturnType<typeof workModeComposition>[] {
  return composition.workModes.map((id) => workModeComposition(id));
}

/** Whether a work mode may be composed, per the server composition. */
export function compositionAllowsMode(
  composition: ClientExperienceComposition,
  id: WorkModeId,
): boolean {
  return composition.workModes.includes(id);
}

/**
 * Whether the identity holds a capability name. Documentation-only helper: the
 * name is a *label* for access the backend granted, not a gate the client may
 * enforce, so callers must not use it to skip a request or hide required data.
 */
export function compositionHoldsCapability(
  composition: ClientExperienceComposition,
  capability: string,
): boolean {
  return composition.effectiveCapabilities.includes(capability);
}

/** Commercial scope is reported explicitly, so a surface can explain refusals. */
export function compositionHasCommercialAccess(
  composition: ClientExperienceComposition,
): boolean {
  return composition.commercialCapabilities.length > 0;
}
