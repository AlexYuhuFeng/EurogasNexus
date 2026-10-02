/**
 * The Decision workspace's two governed computes and their lifecycle (bounded repair).
 *
 * `Compare Options` (`POST /api/route-cost/recommend`) and `Optimize Resource Pool`
 * (`POST /api/route-cost/resource-pool/optimize`) are the two `compute` acts of the Decision
 * workspace. Both sit inside the architecture's commercial-data boundary, so they need a
 * declared capability *and* their actual inputs; and both produce a result that is only
 * current for the trading context it was computed under.
 *
 * Three facts live here, and only here, so the surface, the store and their tests cannot
 * disagree about any of them:
 *
 * 1. **The gate.** What may start a run: the identity's declared composition holds the
 *    capability the backend's own floor requires, the action's inputs are ready, and no run
 *    of the same action is already in flight. This is presentation - the backend re-authorises
 *    every request - but it is what stops an identity the backend will refuse (a platform
 *    administrator holds no commercial capability) from being offered, or automatically
 *    issuing, a run that can only fail closed.
 * 2. **The lifecycle.** `idle -> pending -> success | failure`, with the failure's structured
 *    cause kept for the governed error presentation, so a refusal is rendered next to the
 *    action instead of vanishing.
 * 3. **The result's provenance.** A result is stamped with the provenance key of the request
 *    **that succeeded**, never with the context in force when it was started, and never by a run of
 *    the other action. That key is the trading-context key plus the canonical identity of the
 *    caller-known effective inputs (`app/model/decisionResultProvenance.ts`), so a contract
 *    revision, a refreshed pool/market read or a financing-input change makes the held result
 *    stale exactly as a context change does. A prior result therefore stays visibly stale even
 *    when a retry fails, and one action's completion cannot relabel the other's result.
 */

import { decisionProvenanceMismatch } from "./decisionResultProvenance.ts";

/** The two `compute` acts the Decision workspace owns. */
export type DecisionComputeActionId = "optimize_pool" | "compare_routes";

/**
 * The declared capability name (ExperienceProfile) each act's backend floor requires.
 *
 * Both routes are registered GOVERNED inside the commercial-data boundary
 * (`security/permissions.py`), so a caller needs the commercial work capability - ADMIN alone is
 * refused by `require_commercial_access` - and `optimization.run` is the declared
 * capability ANALYST-class work carries. It is a *name* the backend granted, not a permission
 * check: the request is re-authorised server-side either way.
 */
export const DECISION_COMPUTE_ACTION_CAPABILITY: Readonly<Record<DecisionComputeActionId, string>> = {
  optimize_pool: "optimization.run",
  compare_routes: "optimization.run",
};

export interface DecisionComputeGate {
  readonly canRun: boolean;
  /** Translation key explaining why the action cannot start; null when it can. */
  readonly blockerKey: string | null;
}

export interface DecisionComputeGateInput {
  /** Whether a usable ExperienceProfile composition was parsed (fail closed when not). */
  readonly profileAvailable: boolean;
  /** Capability names the profile declares. */
  readonly capabilities: readonly string[];
  /** The action's own inputs, as the existing readiness rules already decide them. */
  readonly inputReady: boolean;
}

/** The one readiness rule for one act: declared capability first, then the actual inputs. */
export function decisionComputeGate(
  action: DecisionComputeActionId,
  input: DecisionComputeGateInput,
): DecisionComputeGate {
  if (!input.profileAvailable) {
    return { canRun: false, blockerKey: "decision.action.blocker_identity" };
  }
  if (!input.capabilities.includes(DECISION_COMPUTE_ACTION_CAPABILITY[action])) {
    return { canRun: false, blockerKey: "decision.action.blocker_capability" };
  }
  if (!input.inputReady) {
    return { canRun: false, blockerKey: "decision.action.blocker_inputs" };
  }
  return { canRun: true, blockerKey: null };
}

export type DecisionActionPhase = "idle" | "pending" | "success" | "failure";

/** One action's lifecycle: what it is doing, and what its last accepted result belongs to. */
export interface DecisionActionState {
  readonly phase: DecisionActionPhase;
  /** Provenance key the run in flight was requested under; null when none is in flight. */
  readonly requestContextKey: string | null;
  /**
   * Provenance key of the last result this action *succeeded* with: trading context plus the
   * caller-known input identity the request was composed from.
   *
   * Null until one did, and deliberately not re-stamped by a failed retry: a result keeps the
   * inputs it was computed under, so an input or context change cannot be erased by an
   * unsuccessful run.
   */
  readonly resultContextKey: string | null;
  /** The last failure's structured cause, presented through `errorPresentation`. */
  readonly error: unknown;
  /** The backend correlation id of the last failure, when the envelope carried one. */
  readonly correlationId: string | null;
}

export const IDLE_DECISION_ACTION_STATE: DecisionActionState = Object.freeze({
  phase: "idle",
  requestContextKey: null,
  resultContextKey: null,
  error: null,
  correlationId: null,
});

/** A run started for one provenance key. The previous result keeps its own provenance. */
export function decisionActionPending(
  state: DecisionActionState,
  provenanceKey: string,
): DecisionActionState {
  return {
    ...state,
    phase: "pending",
    requestContextKey: provenanceKey,
    error: null,
    correlationId: null,
  };
}

/**
 * A response arrived for this action: stamp the result with the inputs it was computed under.
 *
 * `requestContextKey` - what the run was started with - is the provenance, not whatever context
 * or inputs are in force after it lands. A result computed for inputs the caller has since left
 * is therefore reported stale rather than relabelled current.
 */
export function decisionActionSucceeded(
  state: DecisionActionState,
  provenanceKey: string,
): DecisionActionState {
  return {
    phase: "success",
    requestContextKey: null,
    resultContextKey: provenanceKey,
    error: null,
    correlationId: null,
  };
}

/** A refusal, validation failure or transport failure: keep the prior result and its context. */
export function decisionActionFailed(
  state: DecisionActionState,
  error: unknown,
  correlationId: string | null,
): DecisionActionState {
  return {
    phase: "failure",
    requestContextKey: null,
    resultContextKey: state.resultContextKey,
    error,
    correlationId,
  };
}

/** The control's rule: the gate is open and this action has no run already in flight. */
export function decisionActionAvailable(
  gate: DecisionComputeGate,
  state: DecisionActionState,
): boolean {
  return gate.canRun && state.phase !== "pending";
}

/**
 * Whether the result the surface holds is *not* current for the inputs the caller now knows.
 *
 * `hasResult` is the store's own fact (a payload exists); a result whose provenance the client
 * cannot vouch for counts as stale, so an unlabelled payload - or one whose caller-known input
 * identity is no longer composed (null current key) - is never presented as current.
 */
export function decisionResultContextMismatch(
  state: DecisionActionState,
  hasResult: boolean,
  currentProvenanceKey: string | null,
): boolean {
  return decisionProvenanceMismatch(hasResult, state.resultContextKey, currentProvenanceKey);
}
