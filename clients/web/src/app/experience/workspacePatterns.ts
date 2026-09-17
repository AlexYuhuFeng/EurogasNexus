/**
 * Workspace-pattern registry (Architecture V2 Wave 1).
 *
 * Architecture V2 asks for a small number of canonical workspace patterns
 * (Monitor, Explore, Analyse, Compare, Configure, Review) reused by every work
 * mode, instead of a bespoke interaction model per feature page
 * (`docs/engineering/Architecture-V2/04_PRODUCT_EXPERIENCE_ARCHITECTURE.md`
 * sections 4 and 8).
 *
 * This registry is the single place that answers, for the 16 technical page ids
 * that exist today:
 *
 * 1. which primary work domain owns the page;
 * 2. which canonical pattern the surface follows;
 * 3. how the header composes (one consolidated primary header vs local tabs);
 * 4. which object kinds the surface should hand to the canonical Inspector;
 * 5. which reusable panels the surface is composed from.
 *
 * `WorkspaceRenderer` reads the header composition from here, so the contract is
 * executable rather than decorative. The registry is composition metadata only:
 * it neither grants nor describes authority, and it does not change any route,
 * deep link or API call.
 */

import {
  primaryWorkspaceForPage,
  type PrimaryWorkspaceId,
} from "../navigation/productNavigation.ts";
import type { WorkspacePageId } from "@/workspaceNavigation";
import type { InspectorSubjectKind, PanelKind, WorkspacePattern } from "./vocabulary.ts";

/**
 * How the active workspace composes its header today.
 *
 * `consolidated` - the primary workspace renders one h1 plus its own task row
 * inside its workspace component (market, portfolio, decision).
 * `local-tabs` - the shell renders the primary eyebrow, the page h1 and the
 * sibling page tabs (strategy, system).
 *
 * This is the current composition seam recorded in
 * `docs/engineering/Architecture-V2/W0-01_CLIENT_INVENTORY.md` section 2.5; the
 * target model (one shell contract for every work mode) is Wave 9 work.
 */
export type WorkspaceHeaderMode = "consolidated" | "local-tabs";

export interface WorkspaceComposition {
  readonly page: WorkspacePageId;
  readonly primary: PrimaryWorkspaceId;
  readonly pattern: WorkspacePattern;
  readonly headerMode: WorkspaceHeaderMode;
  /** Why this pattern, in one line. */
  readonly rationale: string;
  /** Object kinds this surface should open in the canonical Inspector. */
  readonly inspectorSubjects: readonly InspectorSubjectKind[];
  /** Reusable panels this surface is composed from. */
  readonly panels: readonly PanelKind[];
}

export const workspaceCompositions: readonly WorkspaceComposition[] = [
  {
    page: "network",
    primary: "market",
    pattern: "EXPLORE",
    headerMode: "consolidated",
    rationale: "Map-first physical/commercial graph exploration with route and pool overlays.",
    inspectorSubjects: ["network-node", "route", "capacity"],
    panels: ["map", "context-summary", "metric-strip", "run-result", "warnings", "evidence"],
  },
  {
    page: "market",
    primary: "market",
    pattern: "MONITOR",
    headerMode: "consolidated",
    rationale: "Continuous market watch: curves, quotes, freshness and intraday opportunities.",
    inspectorSubjects: ["market-observation"],
    panels: ["metric-strip", "time-series", "table", "warnings"],
  },
  {
    page: "capacity",
    primary: "market",
    pattern: "ANALYSE",
    headerMode: "consolidated",
    rationale: "Capacity, tariff, storage and LNG working detail behind the market cockpit.",
    inspectorSubjects: ["capacity", "market-observation"],
    panels: ["table", "context-summary", "warnings", "evidence"],
  },
  {
    page: "contracts",
    primary: "portfolio",
    pattern: "CONFIGURE",
    headerMode: "consolidated",
    rationale: "Bounded entry and validation of EFET-style resource terms before they are persisted.",
    inspectorSubjects: ["contract", "resource"],
    panels: ["assumptions", "table", "warnings", "evidence"],
  },
  {
    page: "orders",
    primary: "portfolio",
    pattern: "ANALYSE",
    headerMode: "consolidated",
    rationale:
      "Read-only market-positioning observations and PnL snapshots; legacy page id kept for deep links.",
    inspectorSubjects: ["contract", "resource", "market-observation"],
    panels: ["metric-strip", "table", "time-series", "warnings"],
  },
  {
    page: "strategy",
    primary: "strategy",
    pattern: "ANALYSE",
    headerMode: "local-tabs",
    rationale: "Research-question-led strategy lifecycle: design, backtest, compare, shadow.",
    inspectorSubjects: ["strategy-version", "strategy-run"],
    panels: ["context-summary", "time-series", "comparison", "run-result", "evidence", "warnings"],
  },
  {
    page: "scenario",
    primary: "decision",
    pattern: "CONFIGURE",
    headerMode: "consolidated",
    rationale: "Scenario inputs and bounded assumptions for the deterministic engines.",
    inspectorSubjects: ["route", "contract", "resource"],
    panels: ["assumptions", "comparison", "run-result", "warnings"],
  },
  {
    page: "review",
    primary: "decision",
    pattern: "REVIEW",
    headerMode: "consolidated",
    rationale: "Evidence, challenge and human review of a result or research artifact.",
    inspectorSubjects: ["decision-evidence", "strategy-run"],
    panels: ["evidence", "decision-history", "warnings", "ai-explanation"],
  },
  {
    page: "sources",
    primary: "administration",
    pattern: "MONITOR",
    headerMode: "local-tabs",
    rationale: "Provider/source health, freshness and credential posture - control plane (Wave 3).",
    inspectorSubjects: ["provider-connection", "data-product"],
    panels: ["metric-strip", "table", "warnings", "evidence"],
  },
  {
    page: "glossary",
    primary: "system",
    pattern: "EXPLORE",
    headerMode: "local-tabs",
    rationale: "Operational glossary exploration with the context of the selected term.",
    inspectorSubjects: [],
    panels: ["context-summary", "table"],
  },
  {
    page: "runtime",
    primary: "administration",
    pattern: "MONITOR",
    headerMode: "local-tabs",
    rationale: "Operator readiness, delivery and governance status - technical, not commercial, health.",
    inspectorSubjects: ["job", "provider-connection"],
    panels: ["metric-strip", "table", "warnings", "evidence"],
  },
  {
    page: "settings",
    primary: "system",
    pattern: "CONFIGURE",
    headerMode: "local-tabs",
    rationale: "Local display preferences and bounded backend connection settings.",
    inspectorSubjects: [],
    panels: ["assumptions", "context-summary"],
  },
  {
    page: "manual",
    primary: "system",
    pattern: "EXPLORE",
    headerMode: "local-tabs",
    rationale: "Customer-facing operating guide; candidate for consolidation into the workspace shells.",
    inspectorSubjects: [],
    panels: ["table", "context-summary"],
  },
  {
    page: "access",
    primary: "administration",
    pattern: "CONFIGURE",
    headerMode: "local-tabs",
    rationale:
      "Control plane: users, roles, API keys, audit and SSO. Platform admin is not commercial super-user.",
    inspectorSubjects: [],
    panels: ["table", "metric-strip", "evidence"],
  },
  {
    page: "research",
    primary: "system",
    pattern: "EXPLORE",
    headerMode: "local-tabs",
    rationale: "Research dataset/feature/target catalogue plus the governed build-and-validate flow.",
    inspectorSubjects: ["data-product"],
    panels: ["table", "context-summary", "evidence", "warnings", "run-result"],
  },
  {
    page: "agents",
    primary: "system",
    pattern: "REVIEW",
    headerMode: "local-tabs",
    rationale: "Governed capability catalogue, research orchestration and observable run replay.",
    inspectorSubjects: ["agent-run"],
    panels: ["evidence", "run-result", "decision-history", "ai-explanation", "warnings"],
  },
];

const byPage = new Map<WorkspacePageId, WorkspaceComposition>(
  workspaceCompositions.map((composition) => [composition.page, composition]),
);

export function compositionForPage(page: WorkspacePageId): WorkspaceComposition {
  const composition = byPage.get(page);
  if (!composition) throw new Error(`No workspace composition declared for page '${page}'.`);
  return composition;
}

export function workspacePatternForPage(page: WorkspacePageId): WorkspacePattern {
  return compositionForPage(page).pattern;
}

export function headerModeForPage(page: WorkspacePageId): WorkspaceHeaderMode {
  return compositionForPage(page).headerMode;
}

/** True when the primary workspace renders its own consolidated header and task row. */
export function usesConsolidatedHeader(page: WorkspacePageId): boolean {
  return headerModeForPage(page) === "consolidated";
}

export function inspectorSubjectsForPage(page: WorkspacePageId): readonly InspectorSubjectKind[] {
  return compositionForPage(page).inspectorSubjects;
}

/**
 * Pattern of a *task* inside a primary workspace, where the task vocabulary is
 * already URL-addressable. Task ids are the ones the live resolvers return
 * (`marketCockpitModel`, `commercialWorkflowModel`, `strategyLabModel`).
 */
export const taskPatterns: Readonly<Record<PrimaryWorkspaceId, Readonly<Record<string, WorkspacePattern>>>> = {
  market: {
    overview: "MONITOR",
    curves: "MONITOR",
    network: "EXPLORE",
    capacity: "ANALYSE",
  },
  portfolio: {
    overview: "MONITOR",
    resources: "ANALYSE",
    routes: "COMPARE",
    exposure: "ANALYSE",
  },
  strategy: {
    design: "CONFIGURE",
    backtest: "ANALYSE",
    compare: "COMPARE",
    shadow: "MONITOR",
  },
  decision: {
    scenario: "CONFIGURE",
    optimize: "ANALYSE",
    review: "REVIEW",
  },
  // The system and administration primaries keep their views local (not
  // URL-addressable) until Wave 9 converges navigation; no task pattern is
  // claimed for them here.
  system: {},
  administration: {},
};

export function taskPatternFor(primary: PrimaryWorkspaceId, task: string): WorkspacePattern {
  const pattern = taskPatterns[primary][task];
  if (!pattern) {
    throw new Error(`No workspace pattern declared for task '${task}' in primary '${primary}'.`);
  }
  return pattern;
}

/** Pages whose pattern the registry claims, in navigation-registry order. */
export function registeredPages(): WorkspacePageId[] {
  return workspaceCompositions.map((composition) => composition.page);
}

/** Composition as the renderer sees it: the primary owner is derived, never restated. */
export function compositionOwner(page: WorkspacePageId): PrimaryWorkspaceId {
  const declared = compositionForPage(page).primary;
  const actual = primaryWorkspaceForPage(page).id;
  if (declared !== actual) {
    throw new Error(
      `Composition for '${page}' claims primary '${declared}' but navigation assigns '${actual}'.`,
    );
  }
  return actual;
}
