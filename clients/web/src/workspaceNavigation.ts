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

export const DEFAULT_WORKSPACE_PAGE_ID: WorkspacePageId = "network";

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
