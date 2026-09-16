/**
 * Action geography (Architecture V2 Wave 1).
 *
 * `docs/engineering/Architecture-V2/04_PRODUCT_EXPERIENCE_ARCHITECTURE.md` section 7
 * asks for one interaction grammar: configure -> validate -> run -> progress ->
 * result, one predictable place for the primary action, and one bounded place for
 * lifecycle or destructive actions. The accepted implementation companion is
 * `docs/ux/ACTION_GEOGRAPHY.md`; this module is its machine-readable form.
 *
 * The rule is deliberately derived from what an action *does*, not from which page
 * happens to host it: the same consequence always lands in the same geography, so a
 * user does not have to relearn where "run" or "retire" lives.
 *
 * Placement is presentation only. It never grants authority - every mutating call
 * is re-authorised by the backend, and a hidden control is not a permission.
 */

import type { ActionPlacement } from "./vocabulary.ts";

/** What an action does to the system, which decides where it belongs. */
export const ACTION_CONSEQUENCES = [
  "read",
  "compute",
  "persist",
  "export",
  "lifecycle",
  "destructive",
  "utility",
] as const;

export type ActionConsequence = (typeof ACTION_CONSEQUENCES)[number];

export interface ActionGeographyRule {
  readonly consequence: ActionConsequence;
  readonly placement: ActionPlacement;
  readonly rationale: string;
}

export const actionGeography: readonly ActionGeographyRule[] = [
  {
    consequence: "read",
    placement: "surface-local",
    rationale:
      "Filters, view modes and local search sit immediately above the surface they modify and never become a second global context owner.",
  },
  {
    consequence: "compute",
    placement: "workspace-primary",
    rationale:
      "Running a scenario, optimizer, backtest or report is the primary act of the workspace and belongs in the upper-right workspace header.",
  },
  {
    consequence: "persist",
    placement: "workspace-primary",
    rationale:
      "Writing a reviewed draft (contract terms, assumptions, a recorded decision) is primary for the surface that owns the object.",
  },
  {
    consequence: "export",
    placement: "workspace-secondary",
    rationale:
      "Export is available beside the primary action but subordinate to it, and stays subject to server-side entitlement checks.",
  },
  {
    consequence: "lifecycle",
    placement: "object-overflow",
    rationale:
      "Freeze, promote, re-mount or retire actions change an object's standing; they stay in a bounded overflow next to the object, never in global chrome.",
  },
  {
    consequence: "destructive",
    placement: "object-overflow",
    rationale:
      "Destructive actions require a deliberate second step adjacent to the affected object; they are never the workspace's primary affordance.",
  },
  {
    consequence: "utility",
    placement: "shell-utility",
    rationale:
      "Global utilities (search, language, theme, diagnostics, sign-out) belong to the shell, not to a workspace.",
  },
];

const byConsequence = new Map<ActionConsequence, ActionGeographyRule>(
  actionGeography.map((rule) => [rule.consequence, rule]),
);

export function actionPlacement(consequence: ActionConsequence): ActionPlacement {
  const rule = byConsequence.get(consequence);
  if (!rule) throw new Error(`No action-geography rule declared for '${consequence}'.`);
  return rule.placement;
}

export function actionGeographyRule(consequence: ActionConsequence): ActionGeographyRule {
  const rule = byConsequence.get(consequence);
  if (!rule) throw new Error(`No action-geography rule declared for '${consequence}'.`);
  return rule;
}

/**
 * Consequences that may occupy the workspace's single primary action slot. A
 * surface declares exactly one of these; everything else is secondary, local or in
 * the object overflow.
 */
export const PRIMARY_SLOT_CONSEQUENCES: readonly ActionConsequence[] = ["compute", "persist"];

export function mayOccupyPrimarySlot(consequence: ActionConsequence): boolean {
  return PRIMARY_SLOT_CONSEQUENCES.includes(consequence);
}

/**
 * Consequences that must not be reachable from a single click in the workspace
 * header, because their effect is not reversible from the same surface.
 */
export const GUARDED_CONSEQUENCES: readonly ActionConsequence[] = ["lifecycle", "destructive"];

export function requiresDeliberateStep(consequence: ActionConsequence): boolean {
  return GUARDED_CONSEQUENCES.includes(consequence);
}

/** Object detail opens the canonical Inspector instead of a new top-level page. */
export function detailPlacement(): ActionPlacement {
  return "inspector";
}
