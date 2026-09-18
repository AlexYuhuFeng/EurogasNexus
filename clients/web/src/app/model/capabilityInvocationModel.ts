/**
 * Capability invocation (Architecture V2 Wave 7 / CR-15, client half).
 *
 * The platform registers semantic capabilities with a declared posture: a determinism class, a
 * side-effect class and an `action_policy` that says whether the capability may be invoked at all
 * (`HUMAN_ONLY`) or only with an explicit human confirmation. The client read that catalogue and
 * never offered invocation, so the contract's policies were published to nobody but an API
 * caller.
 *
 * This module is the rule the surface gates on. It mirrors what the runtime enforces instead of
 * deciding authority itself: the runtime still checks the principal, its data scopes, the
 * arguments and the policy, and a confirmation only ever answers the one policy check it is for.
 * Three things it refuses to do:
 *
 * - **invent arguments.** Invalid JSON is a blocker, not an empty object: sending `{}` because the
 *   editor was mistyped would invoke the capability with inputs the user never wrote;
 * - **offer a `HUMAN_ONLY` capability.** The runtime never invokes it, so a surface that offered
 *   it would be offering a guaranteed refusal;
 * - **treat a confirmation as consent by default.** The flag starts false and the surface must
 *   state what the confirmation covers.
 */

/** The declared action policies a capability may carry. */
export const CAPABILITY_ACTION_POLICIES = [
  "AUTO_ALLOWED",
  "HUMAN_CONFIRMATION",
  "HUMAN_ONLY",
] as const;

export interface CapabilityInvocationSubject {
  readonly capabilityId: string;
  readonly actionPolicy: string;
  readonly sideEffectClass: string;
  readonly determinismClass: string;
}

export interface CapabilityInvocationReadiness {
  readonly canInvoke: boolean;
  readonly blockerKeys: readonly string[];
  readonly firstBlockerKey: string | null;
  /** True when the policy requires the caller's confirmation before the run. */
  readonly requiresConfirmation: boolean;
}

/**
 * Whether the capability may be invoked as the form stands.
 *
 * The policy is checked first because a `HUMAN_ONLY` capability has no state in which invocation
 * is right; the arguments are checked next, because a capability invoked with inputs nobody wrote
 * is worse than a refusal; an invocation already in flight is last.
 */
export function capabilityInvocationReadiness(input: {
  readonly capability: CapabilityInvocationSubject | null;
  /** The arguments as typed, i.e. the raw editor text. */
  readonly argumentsText: string;
  readonly confirmed: boolean;
  readonly running: boolean;
}): CapabilityInvocationReadiness {
  const blockerKeys: string[] = [];
  const policy = input.capability?.actionPolicy ?? "";
  const requiresConfirmation = policy === "HUMAN_CONFIRMATION";

  if (!input.capability) blockerKeys.push("capabilities.blocker.no_selection");
  else if (policy === "HUMAN_ONLY") blockerKeys.push("capabilities.blocker.human_only");

  if (input.capability && policy !== "HUMAN_ONLY" && !argumentsParsed(input.argumentsText)) {
    blockerKeys.push("capabilities.blocker.arguments_invalid");
  }
  if (requiresConfirmation && !input.confirmed) {
    blockerKeys.push("capabilities.blocker.confirmation_required");
  }
  if (input.running) blockerKeys.push("capabilities.blocker.in_flight");

  return {
    canInvoke: blockerKeys.length === 0,
    blockerKeys,
    firstBlockerKey: blockerKeys.length > 0 ? blockerKeys[0] : null,
    requiresConfirmation,
  };
}

/**
 * The parsed arguments, or null when the editor text is not a JSON object.
 *
 * Only an object is accepted: the runtime validates the arguments against the capability's input
 * schema, and a bare array or scalar could not be validated field by field.
 */
export function argumentsParsed(argumentsText: string): Record<string, unknown> | null {
  const trimmed = argumentsText.trim();
  if (!trimmed) return {};
  try {
    const parsed: unknown = JSON.parse(trimmed);
    if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed)) return null;
    return parsed as Record<string, unknown>;
  } catch {
    return null;
  }
}

export interface CapabilityInvocationRequest {
  readonly arguments: Record<string, unknown>;
  readonly humanConfirmation: boolean;
  readonly confirmationNote: string;
}

/**
 * The invocation request for the form as it stands, or null when it may not be sent.
 *
 * The confirmation note is only carried when a confirmation is actually given, so the record of
 * why a consequential capability ran cannot exist without the confirmation it explains.
 */
export function capabilityInvocationRequest(input: {
  readonly capability: CapabilityInvocationSubject | null;
  readonly argumentsText: string;
  readonly confirmed: boolean;
  readonly confirmationNote: string;
}): CapabilityInvocationRequest | null {
  const readiness = capabilityInvocationReadiness({ ...input, running: false });
  const args = argumentsParsed(input.argumentsText);
  if (!readiness.canInvoke || args === null) return null;
  return {
    arguments: args,
    humanConfirmation: readiness.requiresConfirmation ? input.confirmed : false,
    confirmationNote: readiness.requiresConfirmation && input.confirmed
      ? input.confirmationNote.trim()
      : "",
  };
}

/** How a declared action policy is labelled, falling back to the code itself. */
export function capabilityPolicyKey(policy: string): string {
  const known: Record<string, string> = {
    AUTO_ALLOWED: "capabilities.policy.auto_allowed",
    HUMAN_CONFIRMATION: "capabilities.policy.human_confirmation",
    HUMAN_ONLY: "capabilities.policy.human_only",
  };
  return known[policy] ?? policy;
}

/** What a returned `CapabilityResult` says, as the surface needs it. */
export interface CapabilityOutcome {
  readonly status: string;
  readonly capability: string;
  readonly failureCode: string | null;
  readonly failureDetail: string | null;
  readonly blockers: readonly string[];
  readonly warnings: readonly string[];
  readonly evidenceRefs: readonly string[];
  readonly entitlementState: string;
  readonly qualityState: string;
  readonly asOf: string | null;
}

/**
 * Read one invocation result without inventing anything it did not report.
 *
 * A `BLOCKED` result is a result, not an error: its stable failure code and detail are what the
 * surface shows. A missing field stays null rather than being filled with a plausible default.
 */
export function capabilityOutcome(result: Record<string, unknown> | null): CapabilityOutcome | null {
  if (!result) return null;
  const failure = (result.failure ?? null) as Record<string, unknown> | null;
  const strings = (value: unknown): string[] =>
    Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
  return {
    status: typeof result.status === "string" ? result.status : "UNKNOWN",
    capability: typeof result.capability === "string" ? result.capability : "",
    failureCode: typeof failure?.code === "string" ? failure.code : null,
    failureDetail: typeof failure?.detail === "string" ? failure.detail : null,
    blockers: strings(result.blockers),
    warnings: strings(result.warnings),
    evidenceRefs: strings(result.evidence_refs),
    entitlementState:
      typeof result.entitlement_state === "string" ? result.entitlement_state : "NOT_REPORTED",
    qualityState: typeof result.quality_state === "string" ? result.quality_state : "NOT_REPORTED",
    asOf: typeof result.as_of === "string" ? result.as_of : null,
  };
}
