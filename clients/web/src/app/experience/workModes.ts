/**
 * Work-mode compositions (Architecture V2 Wave 1).
 *
 * Architecture V2 section 9 of
 * `docs/engineering/Architecture-V2/04_PRODUCT_EXPERIENCE_ARCHITECTURE.md` describes
 * work modes: a multi-function user selects the mode they are working in, and the
 * mode changes *composition* - which domains and patterns are emphasised - never
 * authority.
 *
 * Wave 1 fixes the composition vocabulary and the canonical specification for each
 * mode. Binding a mode to a backend-delivered `ExperienceProfile` is Wave 2 work
 * (`06_IDENTITY_ACCESS_CONTROL_PLANE.md` section 9): until then this registry is a
 * design contract, not an access decision, and nothing here is consulted to allow or
 * deny anything.
 *
 * Functional assignments are not mutually exclusive personas: a person may be a
 * trader and a researcher at the same time, so modes are a view over one account,
 * not a type of account.
 */

import type { PrimaryWorkspaceId } from "@/app/navigation/productNavigation";
import type { WorkspacePattern } from "./vocabulary.ts";

export const WORK_MODE_IDS = [
  "trading-analysis",
  "portfolio-oversight",
  "research",
  "review",
  "administration",
] as const;

export type WorkModeId = (typeof WORK_MODE_IDS)[number];

export interface WorkModeComposition {
  readonly id: WorkModeId;
  /** Translation key for the mode's name. */
  readonly labelKey: string;
  /** Durable work domains the mode emphasises, in reading order. */
  readonly emphasis: readonly PrimaryWorkspaceId[];
  /** Pattern the mode opens with when the user has no more specific intent. */
  readonly defaultPattern: WorkspacePattern;
  /** Canonical specification delivered by Wave 1. */
  readonly canonicalSpec: string;
  /** One-line description of the user question the mode answers. */
  readonly question: string;
}

export const workModes: readonly WorkModeComposition[] = [
  {
    id: "trading-analysis",
    labelKey: "experience.mode.trading_analysis",
    emphasis: ["market", "portfolio", "decision"],
    defaultPattern: "MONITOR",
    canonicalSpec: "docs/engineering/Architecture-V2/W1-05_CANONICAL_EXPERIENCE_SPECS.md",
    question: "Where should this gas day's resource go, and what does the physical system allow?",
  },
  {
    id: "portfolio-oversight",
    labelKey: "experience.mode.portfolio_oversight",
    emphasis: ["portfolio", "decision", "market"],
    defaultPattern: "ANALYSE",
    canonicalSpec: "docs/engineering/Architecture-V2/W1-05_CANONICAL_EXPERIENCE_SPECS.md",
    question: "What is the portfolio exposed to, what is stale, and what needs a decision?",
  },
  {
    id: "research",
    labelKey: "experience.mode.research",
    emphasis: ["strategy", "system"],
    defaultPattern: "ANALYSE",
    canonicalSpec: "docs/engineering/Architecture-V2/W1-05_CANONICAL_EXPERIENCE_SPECS.md",
    question: "Does this hypothesis survive contact with point-in-time data and a backtest?",
  },
  {
    id: "review",
    labelKey: "experience.mode.review",
    emphasis: ["decision", "strategy"],
    defaultPattern: "REVIEW",
    canonicalSpec: "docs/engineering/Architecture-V2/W1-05_CANONICAL_EXPERIENCE_SPECS.md",
    question: "Is the evidence sufficient for a human to accept, reject or reopen this result?",
  },
  {
    id: "administration",
    labelKey: "experience.mode.administration",
    emphasis: ["system"],
    defaultPattern: "CONFIGURE",
    canonicalSpec: "docs/engineering/Architecture-V2/W1-05_CANONICAL_EXPERIENCE_SPECS.md",
    question: "Are connections, access, entitlements and runtime healthy - without exposing commercial data?",
  },
];

const byId = new Map<WorkModeId, WorkModeComposition>(workModes.map((mode) => [mode.id, mode]));

export function workModeComposition(id: WorkModeId): WorkModeComposition {
  const composition = byId.get(id);
  if (!composition) throw new Error(`No work-mode composition declared for '${id}'.`);
  return composition;
}

export function modeEmphasizes(id: WorkModeId, primary: PrimaryWorkspaceId): boolean {
  return workModeComposition(id).emphasis.includes(primary);
}

/**
 * The rule the whole Wave 2 identity work depends on, stated once:
 * selecting a work mode cannot grant a capability, a scope or an entitlement.
 * `AUTONOMOUS_EXECUTION_POLICY.md` section 3 and the V2 Constitution rules 16-20
 * keep backend enforcement authoritative; this constant exists so the property is
 * asserted in a focused test rather than only described in prose.
 */
export const WORK_MODE_GRANTS_AUTHORITY = false;

/** Composition decision for a mode and a workspace, without consulting any grant. */
export function modeEmphasisFor(id: WorkModeId, primary: PrimaryWorkspaceId): "emphasis" | "available" {
  return modeEmphasizes(id, primary) ? "emphasis" : "available";
}
