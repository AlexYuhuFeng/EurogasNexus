/**
 * Canonical AI interaction contract (Architecture V2 Wave 1).
 *
 * Architecture V2 section 7 of
 * `docs/engineering/Architecture-V2/04_PRODUCT_EXPERIENCE_ARCHITECTURE.md` fixes five
 * AI actions - Ask, Explain, Compare, Challenge, Draft - so the product does not grow
 * inconsistent "magic AI buttons". Section 4 of
 * `docs/engineering/Architecture-V2/08_DECISION_APPLICATION_AI.md` fixes what AI may
 * and may not do.
 *
 * This registry makes those boundaries explicit and testable:
 *
 * - deterministic engines own calculations, optimisation and numeric truth;
 * - AI may interpret, explain, compare, challenge and draft, always bound to the
 *   evidence actually returned by the backend;
 * - AI inherits the invoking user's authority, may not bypass entitlement, and its
 *   runs are recorded as observable actions rather than hidden reasoning.
 *
 * The module holds contracts and guards only. It performs no model call, holds no
 * provider credential and creates no backend capability.
 */

import { AI_ACTION_KINDS, type AiActionKind } from "./vocabulary.ts";

/** What an AI action is allowed to do with deterministic output. */
export type AiActionPosture = "interpret-only" | "evidence-backed-draft" | "evidence-backed-review";

export interface AiActionContract {
  readonly action: AiActionKind;
  readonly purpose: string;
  readonly posture: AiActionPosture;
  /** Context the action needs before it can be offered. */
  readonly requiresActiveContext: boolean;
  /** Evidence references the action must carry into its run. */
  readonly requiresEvidenceRefs: boolean;
  /** Output the action produces, in product language. */
  readonly produces: string;
}

export const aiActions: readonly AiActionContract[] = [
  {
    action: "ask",
    purpose: "Answer a market, portfolio or research question from governed data already returned by the backend.",
    posture: "interpret-only",
    requiresActiveContext: true,
    requiresEvidenceRefs: true,
    produces: "A sourced answer that names the data it used and states what it could not see.",
  },
  {
    action: "explain",
    purpose: "Explain a deterministic result: which inputs, assumptions and versions produced it.",
    posture: "interpret-only",
    requiresActiveContext: true,
    requiresEvidenceRefs: true,
    produces: "An explanation bound to the run, snapshot and assumption set it describes.",
  },
  {
    action: "compare",
    purpose: "Compare alternatives, scenarios or strategy versions on one explicit time basis.",
    posture: "interpret-only",
    requiresActiveContext: true,
    requiresEvidenceRefs: true,
    produces: "A side-by-side reading that names the basis of comparison and any missing input.",
  },
  {
    action: "challenge",
    purpose: "Challenge an assumption, hypothesis or result and name the evidence that would falsify it.",
    posture: "evidence-backed-review",
    requiresActiveContext: true,
    requiresEvidenceRefs: true,
    produces: "A challenge record that stays evidence-linked and human-owned.",
  },
  {
    action: "draft",
    purpose: "Draft a research plan, hypothesis, StrategyIR candidate or report structure for human review.",
    posture: "evidence-backed-draft",
    requiresActiveContext: true,
    requiresEvidenceRefs: true,
    produces: "A draft marked as unverified until a named human accepts or edits it.",
  },
];

const byAction = new Map<AiActionKind, AiActionContract>(
  aiActions.map((contract) => [contract.action, contract]),
);

export function aiActionContract(action: AiActionKind): AiActionContract {
  const contract = byAction.get(action);
  if (!contract) throw new Error(`No AI action contract declared for '${action}'.`);
  return contract;
}

/**
 * Product and security invariants every AI action inherits. They restate the V2
 * product boundary and are asserted by the focused tests so a future surface cannot
 * quietly relax them.
 */
export const AI_INVARIANTS = {
  deterministicEnginesOwnNumbers: true,
  inheritsUserAuthority: true,
  mayBypassEntitlement: false,
  mayInventMissingData: false,
  mayExecuteOrNominate: false,
  storesHiddenReasoning: false,
  requiresReauthorisationPerCall: true,
} as const;

export type AiInvariant = keyof typeof AI_INVARIANTS;

export function aiInvariantHolds(invariant: AiInvariant): boolean {
  return AI_INVARIANTS[invariant] === true;
}

/**
 * Whether an AI action may be offered on a surface. It needs the active context the
 * product promises to send, and - because every action must be explainable from
 * governed evidence - at least one evidence reference. Absence of evidence is a
 * reason to withhold the action, not a reason to let the model guess.
 */
export function aiActionIsAvailable(
  action: AiActionKind,
  availability: { activeContextComplete: boolean; evidenceRefCount: number },
): boolean {
  const contract = aiActionContract(action);
  if (contract.requiresActiveContext && !availability.activeContextComplete) return false;
  if (contract.requiresEvidenceRefs && availability.evidenceRefCount < 1) return false;
  return true;
}

export function declaredAiActions(): AiActionKind[] {
  return [...AI_ACTION_KINDS];
}
