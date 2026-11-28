/**
 * Four working modes as the top-level navigation (WF-05, review M.6): Desk, Deals, Book,
 * Research. Help & Settings and Administration are utilities, reached from the account area,
 * the command palette and their shortcuts, not from the primary row.
 *
 * A mode is a row of tasks. A task names the technical page that renders it and, where that page
 * has several, the page's own task: the URL stays the page's address (`?workspace=<page>&task=`),
 * so every link, test and bookmark that worked before keeps working, and the mode is derived from
 * where the user is. Decision Center no longer exists as an area: Deals → Opportunities replaced
 * scenario and optimisation (CP-14), the review of a decision sits with the deals it approves, and
 * nomination and storage planning are Book planning views.
 *
 * Presentation only. Whether a mode or task is offered follows the caller's identity (a task the
 * role cannot use is absent, never an error); the backend authorises every request whatever the
 * shell shows. A work mode or persona never grants authority.
 */
import { needsCommercialWorkspaceReads } from "../../stores/workspaceReadScope.ts";
import type { CurrentUserDTO } from "../../api/client.ts";
import { isWorkspacePageId, type WorkspacePageId } from "../../workspaceNavigation.ts";
import { marketTaskFromLocation } from "../model/marketCockpitModel.ts";
import { decisionTaskFromLocation, portfolioTaskFromLocation } from "../model/commercialWorkflowModel.ts";

export const MODE_IDS = ["desk", "deals", "book", "research"] as const;
export type ModeId = (typeof MODE_IDS)[number];

export interface ModeTask {
  /** Stable id within the mode (`prices`, `limits`). */
  readonly id: string;
  readonly labelKey: string;
  /** A shorter name for the phone's task row (the full name stays the accessible name). */
  readonly shortLabelKey?: string;
  /** The page that renders the task. */
  readonly page: WorkspacePageId;
  /** The page's own task (`task=`), when the page has several. */
  readonly pageTask?: string;
  /** Other page tasks the same mode task shows behind a switch (Planning: `dispatch`). */
  readonly alsoPageTasks?: readonly string[];
  /** Older page ids that land on this task (kept as deep links). */
  readonly alsoPages?: readonly WorkspacePageId[];
  /** Permissions any one of which makes the task usable; none listed: any commercial identity. */
  readonly permissions?: readonly string[];
  /** Earlier names the palette still finds (translation keys of the old labels). */
  readonly aliasKeys?: readonly string[];
}

export interface ProductMode {
  readonly id: ModeId;
  readonly labelKey: string;
  readonly descriptionKey: string;
  readonly tasks: readonly ModeTask[];
  /** Earlier area names the palette still finds. */
  readonly aliasKeys: readonly string[];
}

export const PRODUCT_MODES: readonly ProductMode[] = [
  {
    id: "desk",
    labelKey: "nav.mode.desk",
    descriptionKey: "nav.mode.desk.description",
    aliasKeys: ["nav.primary.market"],
    tasks: [
      // The small desk's one screen beside the trading screen (SMALL_DESK_PLAN step 4): a task
      // of the Desk page, reading what Today and Prices read, not a page of its own (rule 9).
      // First, so the Desk opens on it; a trader lands on it (ASSIGNMENT_HOME).
      { id: "board", labelKey: "nav.mode.desk.board", page: "market", pageTask: "board", permissions: ["market.read"], aliasKeys: ["nav.mode.desk.board.alias"] },
      { id: "today", labelKey: "nav.mode.desk.today", page: "market", pageTask: "overview", permissions: ["market.read"], aliasKeys: ["market.task.overview"] },
      { id: "prices", labelKey: "nav.mode.desk.prices", page: "market", pageTask: "curves", permissions: ["market.read"], aliasKeys: ["market.task.curves", "nav.market"] },
      // One Network task: the map with outages, capacity and flows in the panel beside it. The
      // retired "Outages & capacity" task and its `capacity` page land here (AGENTS rule 9).
      { id: "network", labelKey: "nav.mode.desk.network", page: "market", pageTask: "network", alsoPages: ["network", "capacity"], permissions: ["market.read"], aliasKeys: ["nav.network", "nav.mode.desk.events", "nav.mode.desk.events.short", "market.task.capacity", "nav.capacity"] },
      // The firm's LNG cargoes in transit, each with its plan from ETA to hedge months (QA-L-05).
      // The book's own cargoes: book read, like Position.
      // The regas auction desk is the same LNG workspace's second view (`task=auctions`), behind
      // the switch at the top of Cargoes: the one LNG workspace the architecture plan keeps.
      { id: "cargoes", labelKey: "nav.mode.desk.cargoes", page: "market", pageTask: "cargoes", alsoPageTasks: ["auctions"], permissions: ["portfolio.read"], aliasKeys: ["lng.cargo.alias_plan", "lng.cargo.alias_vessels", "regas.alias"] },
    ],
  },
  {
    id: "deals",
    labelKey: "nav.mode.deals",
    descriptionKey: "nav.mode.deals.description",
    aliasKeys: ["nav.primary.decision"],
    tasks: [
      // Opportunities first (design basis 2, B.7/B.8): ways to earn or save money with the book,
      // with the arithmetic shown. The retired Evaluate, Optimise and Routes & netback land here.
      { id: "opportunities", labelKey: "nav.mode.deals.opportunities", page: "scenario", pageTask: "opportunities", permissions: ["portfolio.read"], aliasKeys: ["decision.task.opportunities", "nav.mode.deals.evaluate"] },
      { id: "contracts", labelKey: "nav.mode.deals.contracts", page: "contracts", pageTask: "resources", permissions: ["portfolio.read"], aliasKeys: ["portfolio.task.resources", "nav.contracts"] },
      // Approvals belong with the work they approve: a decision review accepts or rejects a
      // deal's evaluation, so it sits in Deals.
      { id: "review", labelKey: "nav.mode.deals.review", page: "scenario", pageTask: "review", alsoPages: ["review"], permissions: ["review.read", "review.record"], aliasKeys: ["decision.task.review", "nav.review"] },
    ],
  },
  {
    id: "book",
    labelKey: "nav.mode.book",
    descriptionKey: "nav.mode.book.description",
    aliasKeys: ["nav.primary.portfolio"],
    tasks: [
      { id: "position", labelKey: "nav.mode.book.position", page: "contracts", pageTask: "overview", permissions: ["portfolio.read"], aliasKeys: ["portfolio.task.overview", "nav.primary.portfolio"] },
      // The day's deals from the exchange exports and by hand, the ETRM entry sheet, the
      // end-of-day check and the daily pack (SMALL_DESK_PLAN step 1): a task of the book, not
      // a page of its own (AGENTS rule 9).
      { id: "blotter", labelKey: "nav.mode.book.blotter", page: "contracts", pageTask: "deals", permissions: ["portfolio.read"], aliasKeys: ["portfolio.task.deals", "deals.alias_eod", "deals.alias_etrm"] },
      // Limits carries the hedge approvals (approval with the exposure it approves), the books
      // and the P&L snapshots; the legacy `orders` page lands here.
      { id: "limits", labelKey: "nav.mode.book.limits", shortLabelKey: "nav.mode.book.limits.short", page: "contracts", pageTask: "exposure", alsoPages: ["orders"], permissions: ["portfolio.read"], aliasKeys: ["portfolio.task.exposure", "nav.orders"] },
      { id: "delivery", labelKey: "nav.mode.book.delivery", page: "contracts", pageTask: "delivery", permissions: ["portfolio.read"] },
      // Planning: nominations and storage, two views of the same optimisation run behind one
      // switch (basis 1 WP-12). `task=nomination` and `task=dispatch` both land here.
      { id: "planning", labelKey: "nav.mode.book.planning", page: "scenario", pageTask: "nomination", alsoPageTasks: ["dispatch"], permissions: ["scenario.create"], aliasKeys: ["decision.task.nomination", "decision.task.dispatch", "nav.mode.book.nominations", "nav.mode.book.storage"] },
    ],
  },
  {
    id: "research",
    labelKey: "nav.mode.research",
    descriptionKey: "nav.mode.research.description",
    aliasKeys: ["nav.primary.strategy"],
    tasks: [
      // The analyst's path, in order (owner, 2026-11-19): the physical picture, what the price
      // structure says, what it means for a cargo or a flow, then the write-up.
      // Storage, LNG, the balance and gas for power against their own history, by country (CP-17).
      { id: "fundamentals", labelKey: "nav.mode.research.fundamentals", page: "research", pageTask: "fundamentals", permissions: ["market.read"] },
      // Spreads (design basis 2, D.2): opens on the desk's spread board; a description is
      // interpreted into the same spec the board's rows open with.
      { id: "spreads", labelKey: "nav.mode.research.spreads", page: "research", pageTask: "spreads", permissions: ["market.read"] },
      // What a cargo nets at each terminal, and Henry Hub against the hub (CP-18, design C.1-C.4).
      { id: "cargo", labelKey: "nav.mode.research.cargo", page: "research", pageTask: "cargo", permissions: ["market.read"] },
      // Market reports: assembled from the catalogue's sections on the server. Strategies, Data
      // and the Assistant were removed (COMMERCIAL_PRODUCT_DESIGN_2.md L1).
      { id: "reports", labelKey: "nav.mode.research.reports", page: "research", pageTask: "reports", permissions: ["market.read"], aliasKeys: ["nav.research"] },
    ],
  },
];

const modeById = new Map<ModeId, ProductMode>(PRODUCT_MODES.map((mode) => [mode.id, mode]));

export function isModeId(value: string | null | undefined): value is ModeId {
  return modeById.has(value as ModeId);
}

export function productMode(id: ModeId): ProductMode {
  const mode = modeById.get(id);
  if (!mode) throw new Error(`Unknown mode '${id}'.`);
  return mode;
}

/** Pages that belong to a mode (every other page is a utility: help, settings, administration). */
export function isModePage(page: WorkspacePageId): boolean {
  return PRODUCT_MODES.some((mode) => mode.tasks.some((task) => task.page === page || task.alsoPages?.includes(page)));
}

/** The page's own task for a location, for pages that have several. */
export function pageTaskFromLocation(page: WorkspacePageId, search: string): string | undefined {
  if (page === "market" || page === "network" || page === "capacity") return marketTaskFromLocation(search, page);
  if (page === "contracts" || page === "orders") {
    return portfolioTaskFromLocation(page === "orders" ? withWorkspace(search, "orders") : search);
  }
  if (page === "research") {
    // Fundamentals is the page's first task; Spreads, Cargo & netback and Reports are named in
    // the URL.
    const task = new URLSearchParams(search).get("task");
    return task === "reports" || task === "spreads" || task === "cargo" ? task : "fundamentals";
  }
  if (page === "scenario" || page === "review") {
    return decisionTaskFromLocation(page === "review" ? withWorkspace(search, "review") : search);
  }
  return undefined;
}

function withWorkspace(search: string, page: string): string {
  const next = new URLSearchParams(search);
  next.set("workspace", page);
  return next.toString();
}

export interface ModeLocation {
  mode: ProductMode;
  task: ModeTask;
}

/** The mode and task a page (and its own task) belongs to; null for a utility page. */
export function modeLocationFor(page: WorkspacePageId, pageTask?: string): ModeLocation | null {
  for (const mode of PRODUCT_MODES) {
    for (const task of mode.tasks) {
      const onPage = task.page === page || task.alsoPages?.includes(page);
      if (!onPage) continue;
      // A legacy page id (network, capacity, review, orders) is the task itself.
      if (
        task.alsoPages?.includes(page) ||
        task.pageTask === undefined ||
        task.pageTask === pageTask ||
        (pageTask !== undefined && task.alsoPageTasks?.includes(pageTask))
      ) return { mode, task };
    }
  }
  // A page whose own task is unknown here (a stale value): its mode's first task on that page.
  for (const mode of PRODUCT_MODES) {
    const task = mode.tasks.find((item) => item.page === page);
    if (task) return { mode, task };
  }
  return null;
}

/** The mode location of a URL. */
export function modeLocationFromSearch(page: WorkspacePageId, search: string): ModeLocation | null {
  return modeLocationFor(page, pageTaskFromLocation(page, search));
}

/* ------------------------------------------------------------------ visibility */

/**
 * Whether the caller's identity can use a task. An identity without a commercial role (a platform
 * administrator) sees no mode; otherwise a task listing permissions needs one of them. An identity
 * that reports no permission list (an older server) is offered everything it could before.
 */
export function modeTaskVisible(task: ModeTask, user: CurrentUserDTO | null | undefined): boolean {
  if (!user) return true;
  if (!needsCommercialWorkspaceReads(user)) return false;
  if (!Array.isArray(user.permissions) || !task.permissions?.length) return true;
  return task.permissions.some((permission) => user.permissions.includes(permission));
}

/** The modes the caller is offered, each with only the tasks it can use; empty modes are absent. */
export function visibleModes(user: CurrentUserDTO | null | undefined): ProductMode[] {
  return PRODUCT_MODES.map((mode) => ({ ...mode, tasks: mode.tasks.filter((task) => modeTaskVisible(task, user)) })).filter(
    (mode) => mode.tasks.length > 0,
  );
}

/** Where a mode opens: its first task the caller can use. */
export function modeLanding(mode: ModeId, user: CurrentUserDTO | null | undefined): ModeTask | null {
  return visibleModes(user).find((item) => item.id === mode)?.tasks[0] ?? null;
}

/* ------------------------------------------------------------------ redirects */

/**
 * Addresses that no longer name a page, and where they now land. The old area ids (Market,
 * Portfolio, Decision Center, Help & Settings, Administration), the new mode ids, and task names
 * that were once used as page ids. A page id itself never redirects: `?workspace=<page>` stays
 * that page's address.
 */
const AREA_REDIRECTS: Readonly<Record<string, { page: WorkspacePageId; task?: string }>> = {
  // Old top-level areas.
  portfolio: { page: "contracts", task: "overview" },
  // Decision Center: its Evaluate task is gone (CP-00); Review is what remains of it in Deals.
  decision: { page: "scenario", task: "review" },
  system: { page: "manual" },
  administration: { page: "sources" },
  // Task names once used as page ids.
  // Optimise left with CP-00: its old page id lands on Opportunities (type R, CP-14).
  optimize: { page: "scenario", task: "opportunities" },
  nomination: { page: "scenario", task: "nomination" },
  dispatch: { page: "scenario", task: "dispatch" },
  exposure: { page: "contracts", task: "exposure" },
  // Pages removed by COMMERCIAL_PRODUCT_DESIGN_2.md (L1): the nearest surviving task.
  strategy: { page: "research", task: "spreads" },
  agents: { page: "research", task: "reports" },
};

/**
 * Tasks of a surviving page that were removed (section I.1, B.8), and where their links now
 * land: Deals → Evaluate and Optimise and Routes & netback land on Deals → Opportunities;
 * Research → Data lands on Reports.
 */
const TASK_REDIRECTS: Readonly<Record<string, { page: WorkspacePageId; task?: string }>> = {
  "scenario:scenario": { page: "scenario", task: "opportunities" },
  "scenario:optimize": { page: "scenario", task: "opportunities" },
  "contracts:routes": { page: "scenario", task: "opportunities" },
  "research:datasets": { page: "research", task: "reports" },
  "research:products": { page: "research", task: "reports" },
  "research:features": { page: "research", task: "reports" },
  "research:targets": { page: "research", task: "reports" },
};

/**
 * Mode task ids that a `?mode=` link may still carry after CP-00 merged or removed them: the two
 * Planning views keep their own page task; removed tasks land on the nearest surviving one.
 */
const RETIRED_MODE_TASKS: Readonly<Record<string, { page: WorkspacePageId; task?: string }>> = {
  "book:nominations": { page: "scenario", task: "nomination" },
  "book:storage": { page: "scenario", task: "dispatch" },
  "deals:evaluate": { page: "scenario", task: "opportunities" },
  "deals:optimise": { page: "scenario", task: "opportunities" },
  "deals:routes": { page: "scenario", task: "opportunities" },
  "research:strategies": { page: "research", task: "spreads" },
  "research:data": { page: "research", task: "reports" },
  "research:assistant": { page: "research", task: "reports" },
};

function landingOf(mode: ProductMode, taskId: string | null): { page: WorkspacePageId; task?: string } {
  const retired = RETIRED_MODE_TASKS[`${mode.id}:${taskId}`];
  if (retired) return retired;
  const task = mode.tasks.find((item) => item.id === taskId) ?? mode.tasks[0];
  return { page: task.page, task: task.pageTask };
}

/**
 * The canonical search for a URL that names an old area or a mode (`?workspace=decision`,
 * `?workspace=book&task=limits`, `?mode=deals&task=review`), or null when the URL is already a
 * page address. Other parameters (gas day, hub, a selected object) are kept.
 */
export function redirectSearch(search: string): string | null {
  const params = new URLSearchParams(search);
  const workspace = params.get("workspace");
  const modeParam = params.get("mode");
  let target: { page: WorkspacePageId; task?: string } | null = null;
  if (modeParam !== null) {
    target = isModeId(modeParam) ? landingOf(productMode(modeParam), params.get("task")) : null;
    params.delete("mode");
    if (!target) {
      // An unknown mode is dropped; the page address (if any) stands.
      return params.toString() === new URLSearchParams(search).toString() ? null : params.toString();
    }
  } else if (workspace && !isWorkspacePageId(workspace)) {
    if (isModeId(workspace)) target = landingOf(productMode(workspace), params.get("task"));
    else if (AREA_REDIRECTS[workspace]) target = AREA_REDIRECTS[workspace];
  } else if (workspace) {
    // A removed task of a surviving page (`?workspace=scenario&task=optimize`), or a removed
    // view (`?workspace=research&view=datasets`). A bare page address never redirects: the
    // scenario page with no task opens Review (its default since CP-00).
    const task = params.get("task") ?? params.get("view");
    if (task && TASK_REDIRECTS[`${workspace}:${task}`]) {
      target = TASK_REDIRECTS[`${workspace}:${task}`];
      params.delete("view");
    }
  }
  if (!target) return null;
  // The page address first, then whatever context the link carried.
  const next = new URLSearchParams();
  next.set("workspace", target.page);
  if (target.task) next.set("task", target.task);
  for (const [name, value] of params) {
    if (name !== "workspace" && name !== "task" && name !== "mode") next.append(name, value);
  }
  return next.toString();
}

/** Every old address the redirect table knows, for tests and the user manual. */
export function legacyAddresses(): string[] {
  return Object.keys(AREA_REDIRECTS);
}

/** Removed tasks of surviving pages, as `page:task`, for tests and the user manual. */
export function retiredTaskAddresses(): string[] {
  return Object.keys(TASK_REDIRECTS);
}

/* ------------------------------------------------------------------ shortcuts */

/**
 * Ctrl+Shift+1 … 6 (⌘ on a Mac): the four modes in order, then Help & Settings and
 * Administration. The palette shows the same binding from this list.
 */
export const NAVIGATION_SHORTCUT_COMMANDS = [
  "navigate.mode.desk",
  "navigate.mode.deals",
  "navigate.mode.book",
  "navigate.mode.research",
  "navigate.primary.system",
  "navigate.primary.administration",
] as const;
