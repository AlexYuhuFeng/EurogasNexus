export type WorkspacePageId =
  | "network"
  | "capacity"
  | "market"
  | "scenario"
  | "contracts"
  | "strategy"
  | "review"
  | "orders"
  | "sources"
  | "glossary"
  | "runtime"
  | "settings"
  | "manual"
  | "access"
  | "research"
  | "agents";

export const workspacePageIds: WorkspacePageId[] = [
  "network",
  "capacity",
  "market",
  "scenario",
  "contracts",
  "strategy",
  "review",
  "orders",
  "sources",
  "glossary",
  "runtime",
  "settings",
  "manual",
  "access",
  "research",
  "agents",
];

export const DEFAULT_WORKSPACE_PAGE_ID: WorkspacePageId = "market";

/**
 * Pages whose reads take the trading context (gas day, delivery product, hub focus). Only
 * these show the context controls in the top bar; on the others (administration, settings,
 * research, the manual) a gas day or a hub would change nothing, and showing them reads as a
 * filter that is not there (#35). The context itself is kept and returns with these pages.
 */
const TRADING_CONTEXT_PAGES: ReadonlySet<WorkspacePageId> = new Set([
  "market",
  "network",
  "capacity",
  "contracts",
  "orders",
  "scenario",
  "review",
]);

export function pageUsesTradingContext(page: WorkspacePageId): boolean {
  return TRADING_CONTEXT_PAGES.has(page);
}

export function isWorkspacePageId(value: string | null | undefined): value is WorkspacePageId {
  return workspacePageIds.includes(value as WorkspacePageId);
}

export function coerceWorkspacePageId(
  value: string | null | undefined,
  fallback: WorkspacePageId = DEFAULT_WORKSPACE_PAGE_ID,
): WorkspacePageId {
  return isWorkspacePageId(value) ? value : fallback;
}

export function workspaceTaskSearch(
  search: string,
  page: WorkspacePageId,
  task?: string,
): string {
  const next = new URLSearchParams(search);
  next.set("workspace", page);
  if (page === "scenario" || page === "review" || task) {
    next.set("task", task ?? page);
  } else {
    next.delete("task");
  }
  return next.toString();
}
