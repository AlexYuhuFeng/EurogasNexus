/**
 * Architecture V2 Wave 1 vocabulary.
 *
 * Architecture V2 makes the Product Experience Architecture a first-class
 * domain (`docs/engineering/Architecture-V2/04_PRODUCT_EXPERIENCE_ARCHITECTURE.md`).
 * That document defines one interaction language for every work mode: the same
 * shell, a small set of workspace patterns, a reusable panel taxonomy, one
 * Inspector for object detail, one action geography and one set of AI actions.
 *
 * This module is the machine-readable form of that vocabulary. It contains
 * names, guards and translation keys only - no rendering, no behaviour and no
 * authority. Composition never grants a permission: the backend re-authorises
 * every call (V2 Constitution rules 16-20, 27; `06_IDENTITY_ACCESS_CONTROL_PLANE.md`).
 */

/** Persistent regions of the canonical shell. */
export const SHELL_REGIONS = [
  "global-context",
  "navigation",
  "primary-workspace",
  "inspector",
  "activity",
] as const;

export type ShellRegion = (typeof SHELL_REGIONS)[number];

/** The six canonical workspace patterns. Do not invent a seventh per domain. */
export const WORKSPACE_PATTERNS = [
  "MONITOR",
  "EXPLORE",
  "ANALYSE",
  "COMPARE",
  "CONFIGURE",
  "REVIEW",
] as const;

export type WorkspacePattern = (typeof WORKSPACE_PATTERNS)[number];

/** Reusable panel types. A new capability must first reuse one of these. */
export const PANEL_KINDS = [
  "context-summary",
  "metric-strip",
  "time-series",
  "table",
  "map",
  "assumptions",
  "warnings",
  "evidence",
  "run-result",
  "comparison",
  "decision-history",
  "ai-explanation",
] as const;

export type PanelKind = (typeof PANEL_KINDS)[number];

/** Where an action belongs. One action has exactly one placement. */
export const ACTION_PLACEMENTS = [
  "workspace-primary",
  "workspace-secondary",
  "surface-local",
  "row-local",
  "object-overflow",
  "inspector",
  "shell-utility",
] as const;

export type ActionPlacement = (typeof ACTION_PLACEMENTS)[number];

/** Canonical AI actions. No ad-hoc "magic AI buttons". */
export const AI_ACTION_KINDS = ["ask", "explain", "compare", "challenge", "draft"] as const;

export type AiActionKind = (typeof AI_ACTION_KINDS)[number];

/** Object kinds the canonical Inspector may present. */
export const INSPECTOR_SUBJECT_KINDS = [
  "network-node",
  "route",
  "capacity",
  "contract",
  "resource",
  "market-observation",
  "strategy-version",
  "strategy-run",
  "decision-evidence",
  "data-product",
  "provider-connection",
  "agent-run",
  "job",
] as const;

export type InspectorSubjectKind = (typeof INSPECTOR_SUBJECT_KINDS)[number];

function membershipGuard<T extends string>(values: readonly T[]): (value: unknown) => value is T {
  const allowed = new Set<string>(values);
  return (value: unknown): value is T => typeof value === "string" && allowed.has(value);
}

export const isShellRegion = membershipGuard(SHELL_REGIONS);
export const isWorkspacePattern = membershipGuard(WORKSPACE_PATTERNS);
export const isPanelKind = membershipGuard(PANEL_KINDS);
export const isActionPlacement = membershipGuard(ACTION_PLACEMENTS);
export const isAiActionKind = membershipGuard(AI_ACTION_KINDS);
export const isInspectorSubjectKind = membershipGuard(INSPECTOR_SUBJECT_KINDS);

/** Translation keys for the canonical vocabulary (EN and zh-CN share the keys). */
export function shellRegionLabelKey(region: ShellRegion): string {
  return `experience.region.${region}`;
}

export function workspacePatternLabelKey(pattern: WorkspacePattern): string {
  return `experience.pattern.${pattern.toLowerCase()}`;
}

export function panelKindLabelKey(kind: PanelKind): string {
  return `experience.panel.${kind}`;
}

export function aiActionLabelKey(action: AiActionKind): string {
  return `experience.ai.${action}`;
}
