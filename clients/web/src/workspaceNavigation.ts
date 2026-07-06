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
