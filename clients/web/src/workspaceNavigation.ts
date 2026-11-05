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

/**
 * URL parameters that name an object on one page (#31): a selected source, an open contract,
 * a glossary term. They belong to that page and are cleared when another page opens, so a
 * stale id never selects something on the wrong page.
 */
export const PAGE_OBJECT_PARAMS: Partial<Record<WorkspacePageId, readonly string[]>> = {
  sources: ["source"],
  contracts: ["contract"],
  glossary: ["term"],
};

export function workspaceTaskSearch(
  search: string,
  page: WorkspacePageId,
  task?: string,
): string {
  const next = new URLSearchParams(search);
  const previous = next.get("workspace");
  if (previous !== page) {
    // A sub-view and object ids belong to the page they were chosen on.
    next.delete("view");
    for (const [owner, names] of Object.entries(PAGE_OBJECT_PARAMS)) {
      if (owner === page) continue;
      for (const name of names ?? []) next.delete(name);
    }
  }
  next.set("workspace", page);
  if (page === "scenario" || page === "review" || task) {
    next.set("task", task ?? page);
  } else {
    next.delete("task");
  }
  return next.toString();
}
