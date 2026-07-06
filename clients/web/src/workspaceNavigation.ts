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
  | "manual";

export type WorkspaceGroupId = "decision" | "commercial" | "analytics" | "operations";

export interface WorkspaceGroup {
  id: WorkspaceGroupId;
  labelKey: string;
  pages: WorkspacePageId[];
}

export const workspaceGroups: WorkspaceGroup[] = [
  {
    id: "decision",
    labelKey: "nav.group.decision",
    pages: ["network", "scenario", "review"],
  },
  {
    id: "commercial",
    labelKey: "nav.group.commercial",
    pages: ["contracts", "market", "capacity", "orders"],
  },
  {
    id: "analytics",
    labelKey: "nav.group.analytics",
    pages: ["strategy", "glossary"],
  },
  {
    id: "operations",
    labelKey: "nav.group.operations",
    pages: ["sources", "runtime", "settings", "manual"],
  },
];

export const workspacePageIds: WorkspacePageId[] = workspaceGroups.flatMap((group) => group.pages);

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
