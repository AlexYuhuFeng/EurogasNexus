/**
 * Role composition registry (role-first redesign, `docs/product/ROLE_FIRST_REDESIGN.md` §4).
 *
 * One product, role-tuned defaults. The first declared job function picks a composition:
 *
 * - the landing (the server's `ASSIGNMENT_HOME` is the persona home it mirrors);
 * - an ordered shortlist of at most four places (the task row shows them first; the rest stay
 *   under "More" and in the palette, decision D6);
 * - per page, each panel's default state (`open`, `folded` or `hidden`);
 * - the order of Today's rows (a placeholder until the Today package composes by role);
 * - the audience of the situational strip under the top bar (§5): which rule decides what may
 *   appear there for this person.
 *
 * Rules, each unit tested (`tests/roleComposition.test.ts`):
 *
 * 1. **Composition, never authority.** What is shown is the registry AND the permission. A task
 *    the role cannot open is dropped from the shortlist and the landing; a panel the role may not
 *    read is `hidden` whatever the registry says. The registry can only narrow.
 *    `ROLE_COMPOSITION_GRANTS_AUTHORITY` is false, like `WORK_MODE_GRANTS_AUTHORITY`.
 * 2. **Several job functions:** the first declared one the role supports sets the defaults.
 *    "View as" chooses among the person's own declared functions only (presentation).
 * 3. **No job function declared:** the composition follows the permissions (ANALYST → trader,
 *    REVIEWER → reviewer, VIEWER → read-only desk head, administration without a commercial
 *    role → platform).
 *
 * Pure data and pure functions; nothing here calls the backend or renders.
 */
import type { CurrentUserDTO } from "../../api/client.ts";
import type { WorkspacePageId } from "../../workspaceNavigation.ts";
import { needsCommercialWorkspaceReads } from "../../stores/workspaceReadScope.ts";
import { PRODUCT_MODES, modeTaskVisible, visibleModes, type ModeId, type ModeTask } from "../navigation/modeNavigation.ts";
import { compositionFromProfile, compositionSeesAdministration } from "./experienceProfile.ts";

/** Composition only: a job function or a "View as" choice never grants anything. */
export const ROLE_COMPOSITION_GRANTS_AUTHORITY = false as const;

/** Job functions the server declares (`security/capabilities.py`, `FunctionalAssignment`). */
export const JOB_FUNCTION_IDS = [
  "TRADER",
  "HQ_BUSINESS_ANALYST",
  "QUANT_RESEARCHER",
  "RISK_MANAGER",
  "FINANCE_SETTLEMENT",
  "LEGAL_COMPLIANCE",
  "MANAGEMENT",
  "REVIEWER_MANAGEMENT",
  "DATA_OPERATOR",
  "PLATFORM_ADMINISTRATOR",
  "ORIGINATOR",
  "OPERATIONS",
] as const;
export type JobFunctionId = (typeof JOB_FUNCTION_IDS)[number];

export function isJobFunctionId(value: string | null | undefined): value is JobFunctionId {
  return (JOB_FUNCTION_IDS as readonly string[]).includes(String(value ?? ""));
}

export const COMPOSITION_IDS = [
  "trader",
  "originator",
  "analyst",
  "risk",
  "operations",
  "finance",
  "compliance",
  "reviewer",
  "desk_head",
  "platform",
] as const;
export type CompositionId = (typeof COMPOSITION_IDS)[number];

/** Who the situational strip speaks to (§5.2). One per composition row of that table. */
export const STRIP_AUDIENCES = [
  "trader",
  "originator",
  "analyst",
  "risk",
  "operations",
  "finance",
  "compliance",
  "desk_head",
  "platform",
] as const;
export type StripAudience = (typeof STRIP_AUDIENCES)[number];

export type PanelDefault = "open" | "folded" | "hidden";

/**
 * Today's rows (design basis 2, E.2): my market, my book, what needs me, fundamentals, and
 * "My gas day" (what to clear today and tomorrow per hub; first for the trader and operations).
 */
export const TODAY_ROW_KEYS = ["market", "book", "needs_me", "fundamentals", "gas_day", "checklist"] as const;
export type TodayRowKey = (typeof TODAY_ROW_KEYS)[number];

/** A place: a mode task, or a utility page (administration, settings). */
export type PlaceRef =
  | { readonly kind: "task"; readonly mode: ModeId; readonly task: string }
  | { readonly kind: "page"; readonly page: WorkspacePageId };

export interface RoleComposition {
  readonly id: CompositionId;
  readonly landing: PlaceRef;
  /** At most four places, landing first. */
  readonly shortlist: readonly PlaceRef[];
  /**
   * Per page, each panel's default state. Pages are filled in by the package that slims them;
   * a panel without an entry is `open`.
   */
  readonly panels: Readonly<Partial<Record<WorkspacePageId, Readonly<Record<string, PanelDefault>>>>>;
  /**
   * Today's rows in this role's order (design basis 2, E.3). A row a role does not need is
   * left out; a row with nothing to say is absent at run time (What needs me when quiet).
   */
  readonly todayRows: readonly TodayRowKey[];
  readonly stripAudience: StripAudience;
}

export const MAX_SHORTLIST = 4;

const task = (mode: ModeId, id: string): PlaceRef => ({ kind: "task", mode, task: id });
const page = (id: WorkspacePageId): PlaceRef => ({ kind: "page", page: id });

/** §4.2, one row per composition. */
export const ROLE_COMPOSITIONS: Readonly<Record<CompositionId, RoleComposition>> = {
  // D1: the trader lands on Today, whose first row carries the home-hub prices; place 3 is
  // Deals → Opportunities (design basis 2, B.8).
  trader: {
    id: "trader",
    landing: task("desk", "today"),
    shortlist: [task("desk", "today"), task("desk", "prices"), task("deals", "opportunities"), task("book", "limits")],
    panels: {},
    // The trader's day is the gas they have to clear (owner, 2026-11-19), read against the
    // market: the compact "My market" row (prices, change vs close) sits above the fold first
    // (QA-T-03), then "My gas day" and its checklist.
    todayRows: ["market", "gas_day", "checklist", "book", "needs_me", "fundamentals"],
    stripAudience: "trader",
  },
  // The originator lands on Deals → Opportunities (design basis 2, A.4 and B.8), then the book
  // the evaluation reads. Evaluate and Routes left with CP-00; their links land there too.
  originator: {
    id: "originator",
    landing: task("deals", "opportunities"),
    shortlist: [task("deals", "opportunities"), task("deals", "contracts"), task("deals", "review"), task("desk", "prices")],
    panels: {},
    todayRows: ["needs_me", "market", "fundamentals"],
    stripAudience: "originator",
  },
  analyst: {
    id: "analyst",
    // The analyst starts from the physical picture (owner, 2026-11-19): Research → Fundamentals.
    landing: task("research", "fundamentals"),
    shortlist: [task("research", "fundamentals"), task("research", "spreads"), task("research", "reports"), task("desk", "today")],
    panels: {},
    todayRows: ["fundamentals", "market", "needs_me", "book"],
    stripAudience: "analyst",
  },
  risk: {
    id: "risk",
    landing: task("book", "limits"),
    shortlist: [task("book", "limits"), task("deals", "review"), task("book", "position"), task("desk", "today")],
    panels: {},
    todayRows: ["book", "needs_me", "market"],
    stripAudience: "risk",
  },
  // Planning: nominations and storage as one task, two views behind a switch (A.4).
  operations: {
    id: "operations",
    landing: task("book", "delivery"),
    shortlist: [task("book", "delivery"), task("book", "planning"), task("desk", "network"), task("deals", "contracts")],
    panels: {},
    // Operations schedules what the desk clears: the nomination checklist first, then the gas
    // day it clears, for every book it may see.
    todayRows: ["checklist", "gas_day", "needs_me", "book", "market"],
    stripAudience: "operations",
  },
  finance: {
    id: "finance",
    landing: task("book", "position"),
    shortlist: [task("book", "position"), task("book", "delivery"), task("deals", "contracts"), task("book", "limits")],
    panels: {},
    todayRows: ["book", "needs_me", "market"],
    stripAudience: "finance",
  },
  compliance: {
    id: "compliance",
    landing: task("deals", "review"),
    shortlist: [task("deals", "review"), task("deals", "contracts"), task("research", "reports")],
    panels: {},
    todayRows: ["needs_me", "market"],
    stripAudience: "compliance",
  },
  // A decision reviewer: the review queue first, then the book it decides about.
  reviewer: {
    id: "reviewer",
    landing: task("deals", "review"),
    shortlist: [task("deals", "review"), task("book", "limits"), task("book", "position"), task("desk", "today")],
    panels: {},
    todayRows: ["book", "needs_me", "market", "fundamentals"],
    stripAudience: "desk_head",
  },
  desk_head: {
    id: "desk_head",
    landing: task("desk", "today"),
    shortlist: [task("desk", "today"), task("deals", "review"), task("book", "limits"), task("book", "position")],
    panels: {},
    todayRows: ["book", "needs_me", "market", "fundamentals"],
    stripAudience: "desk_head",
  },
  platform: {
    id: "platform",
    landing: page("sources"),
    shortlist: [page("sources"), page("runtime"), page("access"), page("settings")],
    panels: {},
    todayRows: ["needs_me", "market", "fundamentals"],
    stripAudience: "platform",
  },
};

/** Job function → composition. Every server job function has exactly one. */
export const JOB_FUNCTION_COMPOSITION: Readonly<Record<JobFunctionId, CompositionId>> = {
  TRADER: "trader",
  HQ_BUSINESS_ANALYST: "analyst",
  QUANT_RESEARCHER: "analyst",
  RISK_MANAGER: "risk",
  FINANCE_SETTLEMENT: "finance",
  LEGAL_COMPLIANCE: "compliance",
  MANAGEMENT: "desk_head",
  REVIEWER_MANAGEMENT: "reviewer",
  DATA_OPERATOR: "platform",
  PLATFORM_ADMINISTRATOR: "platform",
  ORIGINATOR: "originator",
  OPERATIONS: "operations",
};

/* ------------------------------------------------------------------ resolution */

/**
 * The person's own declared job functions the role supports, in declared order. The server
 * reports declared functions it could not honour as unsatisfied; they never compose.
 */
export function declaredJobFunctions(user: CurrentUserDTO | null | undefined): JobFunctionId[] {
  const experience = user?.experience;
  if (!experience) return [];
  const declared = (experience.declared_job_functions ?? []).filter(isJobFunctionId);
  if (!declared.length) return [];
  const unsatisfied = new Set(experience.unsatisfied_job_functions ?? []);
  const honoured = new Set(experience.functional_assignments ?? []);
  return declared.filter((item) => !unsatisfied.has(item) && honoured.has(item));
}

function hasPermission(user: CurrentUserDTO | null | undefined, permission: string): boolean {
  return Array.isArray(user?.permissions) && user.permissions.includes(permission);
}

/** The composition a person without a declared job function gets, from their permissions. */
export function fallbackComposition(user: CurrentUserDTO | null | undefined): CompositionId {
  if (user && !needsCommercialWorkspaceReads(user)) return "platform";
  if (hasPermission(user, "scenario.create")) return "trader";
  // An operator runs sources; without scenario work their day is the platform's.
  if (compositionSeesAdministration(compositionFromProfile(user?.experience))) return "platform";
  if (hasPermission(user, "review.record")) return "reviewer";
  // A scheduler records nomination status: their day is deliveries and deadlines.
  if (hasPermission(user, "gas_day.record")) return "operations";
  return "desk_head";
}

export interface ResolvedComposition {
  readonly composition: RoleComposition;
  /** The job function that chose it; null when it came from the permissions. */
  readonly jobFunction: JobFunctionId | null;
  /** The person's own declared functions ("View as" offers these and nothing else). */
  readonly declared: readonly JobFunctionId[];
  /** Always false. */
  readonly grantsAuthority: false;
}

/**
 * Resolve the composition for a person. `viewAs` is honoured only when it is one of the
 * person's own declared functions; anything else falls back to the first declared one.
 */
export function resolveComposition(
  user: CurrentUserDTO | null | undefined,
  viewAs?: string | null,
): ResolvedComposition {
  const declared = declaredJobFunctions(user);
  const chosen = viewAs && isJobFunctionId(viewAs) && declared.includes(viewAs) ? viewAs : (declared[0] ?? null);
  const id = chosen ? JOB_FUNCTION_COMPOSITION[chosen] : fallbackComposition(user);
  return { composition: ROLE_COMPOSITIONS[id], jobFunction: chosen, declared, grantsAuthority: false };
}

/* ------------------------------------------------------------------ what a person is called */

/**
 * The function a person is called by, from the role registry: what the account menu, Settings,
 * Access review and bylines show. The backend authority roles (ANALYST, REVIEWER, ...) are
 * permissions, shown only in Admin → Access; nobody calls themselves an "Analyst" because their
 * authority is ANALYST.
 */
export const PERSON_FUNCTIONS = [
  "trader", "risk", "originator", "operations", "desk_head", "analyst", "finance", "compliance", "administrator",
] as const;
export type PersonFunction = (typeof PERSON_FUNCTIONS)[number];

const JOB_FUNCTION_PERSON: Readonly<Record<JobFunctionId, PersonFunction>> = {
  TRADER: "trader",
  HQ_BUSINESS_ANALYST: "analyst",
  QUANT_RESEARCHER: "analyst",
  RISK_MANAGER: "risk",
  FINANCE_SETTLEMENT: "finance",
  LEGAL_COMPLIANCE: "compliance",
  MANAGEMENT: "desk_head",
  REVIEWER_MANAGEMENT: "desk_head",
  DATA_OPERATOR: "administrator",
  PLATFORM_ADMINISTRATOR: "administrator",
  ORIGINATOR: "originator",
  OPERATIONS: "operations",
};

const COMPOSITION_PERSON: Readonly<Record<CompositionId, PersonFunction>> = {
  trader: "trader",
  originator: "originator",
  analyst: "analyst",
  risk: "risk",
  operations: "operations",
  finance: "finance",
  compliance: "compliance",
  reviewer: "desk_head",
  desk_head: "desk_head",
  platform: "administrator",
};

/** A job function code (`TRADER`) as the function a person is called by, or null. */
export function personFunctionOfJob(code: string | null | undefined): PersonFunction | null {
  return isJobFunctionId(code) ? JOB_FUNCTION_PERSON[code] : null;
}

/**
 * The function to show for a person: their first declared job function, else the function their
 * permissions compose to (a person with no declared function is still not "ANALYST").
 */
export function personFunction(user: CurrentUserDTO | null | undefined): PersonFunction | null {
  if (!user) return null;
  const declared = user.experience?.declared_job_functions?.find(isJobFunctionId);
  if (declared) return JOB_FUNCTION_PERSON[declared];
  return COMPOSITION_PERSON[fallbackComposition(user)];
}

/* ------------------------------------------------------------------ registry AND permission */

function modeTaskFor(ref: PlaceRef): ModeTask | null {
  if (ref.kind !== "task") return null;
  return PRODUCT_MODES.find((mode) => mode.id === ref.mode)?.tasks.find((item) => item.id === ref.task) ?? null;
}

/** Whether the person may open a place. A utility page follows the shell's own rule for it. */
export function placeVisible(ref: PlaceRef, user: CurrentUserDTO | null | undefined): boolean {
  if (ref.kind === "task") {
    const modeTask = modeTaskFor(ref);
    return modeTask !== null && modeTaskVisible(modeTask, user);
  }
  if (ref.page === "settings" || ref.page === "manual" || ref.page === "glossary") return true;
  // Administration pages: only for an identity with an administration capability.
  return compositionSeesAdministration(compositionFromProfile(user?.experience));
}

/** The shortlist the person sees: registry order, without any place the role cannot open. */
export function composedShortlist(
  composition: RoleComposition,
  user: CurrentUserDTO | null | undefined,
): PlaceRef[] {
  return composition.shortlist.filter((ref) => placeVisible(ref, user)).slice(0, MAX_SHORTLIST);
}

/**
 * Where the person lands: the registry's landing if they may open it, else the first shortlist
 * place they may open, else the first task of their first mode, else null.
 */
export function composedLanding(
  composition: RoleComposition,
  user: CurrentUserDTO | null | undefined,
): PlaceRef | null {
  if (placeVisible(composition.landing, user)) return composition.landing;
  const fromShortlist = composedShortlist(composition, user)[0];
  if (fromShortlist) return fromShortlist;
  const mode = visibleModes(user)[0];
  const first = mode?.tasks[0];
  return mode && first ? task(mode.id, first.id) : null;
}

/**
 * Tasks the person may open that are not on their shortlist: the task row's "More" (D6). Never
 * empty of a permitted task: shortlist plus "More" is exactly what the role may open.
 */
export function moreTasks(composition: RoleComposition, user: CurrentUserDTO | null | undefined): PlaceRef[] {
  const shortlist = composedShortlist(composition, user);
  const listed = new Set(shortlist.map(placeKey));
  return visibleModes(user)
    .flatMap((mode) => mode.tasks.map((item) => task(mode.id, item.id)))
    .filter((ref) => !listed.has(placeKey(ref)));
}

export function placeKey(ref: PlaceRef): string {
  return ref.kind === "task" ? `${ref.mode}.${ref.task}` : `page.${ref.page}`;
}

/**
 * A panel's default state for the person: `hidden` when the role may not read it, whatever the
 * registry says; otherwise the registry's entry, `open` when it has none. The registry can fold
 * or hide a permitted panel; it can never show a refused one.
 */
export function panelDefault(
  composition: RoleComposition,
  pageId: WorkspacePageId,
  panel: string,
  permitted: boolean,
): PanelDefault {
  if (!permitted) return "hidden";
  return composition.panels[pageId]?.[panel] ?? "open";
}

/** Today's row order, keeping only the rows the read returned (a row without permission is absent). */
export function composedTodayRows(composition: RoleComposition, available: readonly TodayRowKey[]): TodayRowKey[] {
  const present = new Set(available);
  return composition.todayRows.filter((key) => present.has(key));
}
