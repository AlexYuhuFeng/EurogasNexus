import type { WorkspacePageId } from "@/workspaceNavigation";

export type PrimaryWorkspaceId =
  | "market"
  | "portfolio"
  | "strategy"
  | "decision"
  | "system";

export interface PrimaryWorkspace {
  id: PrimaryWorkspaceId;
  labelKey: string;
  descriptionKey: string;
  pages: WorkspacePageId[];
  defaultPage: WorkspacePageId;
}

export const primaryWorkspaces: PrimaryWorkspace[] = [
  {
    id: "market",
    labelKey: "nav.primary.market",
    descriptionKey: "nav.primary.market.description",
    pages: ["network", "market", "capacity"],
    defaultPage: "network",
  },
  {
    id: "portfolio",
    labelKey: "nav.primary.portfolio",
    descriptionKey: "nav.primary.portfolio.description",
    pages: ["contracts", "orders"],
    defaultPage: "contracts",
  },
  {
    id: "strategy",
    labelKey: "nav.primary.strategy",
    descriptionKey: "nav.primary.strategy.description",
    pages: ["strategy"],
    defaultPage: "strategy",
  },
  {
    id: "decision",
    labelKey: "nav.primary.decision",
    descriptionKey: "nav.primary.decision.description",
    pages: ["scenario", "review"],
    defaultPage: "scenario",
  },
  {
    id: "system",
    labelKey: "nav.primary.system",
    descriptionKey: "nav.primary.system.description",
    pages: ["sources", "runtime", "settings", "manual", "glossary"],
    defaultPage: "sources",
  },
];

const primaryByPage = new Map<WorkspacePageId, PrimaryWorkspace>(
  primaryWorkspaces.flatMap((primary) =>
    primary.pages.map((page) => [page, primary] as const),
  ),
);

const primaryById = new Map<PrimaryWorkspaceId, PrimaryWorkspace>(
  primaryWorkspaces.map((primary) => [primary.id, primary]),
);

export function primaryWorkspaceForPage(
  page: WorkspacePageId,
): PrimaryWorkspace {
  const primary = primaryByPage.get(page);
  if (!primary) throw new Error(`No primary workspace owns technical page '${page}'.`);
  return primary;
}

export function primaryWorkspaceForId(
  value: string | null | undefined,
): PrimaryWorkspace | undefined {
  if (!value) return undefined;
  return primaryById.get(value as PrimaryWorkspaceId);
}

export function isPrimaryWorkspaceId(
  value: string | null | undefined,
): value is PrimaryWorkspaceId {
  return primaryWorkspaceForId(value) !== undefined;
}

export function defaultWorkspacePageForPrimary(
  primary: PrimaryWorkspaceId | PrimaryWorkspace,
): WorkspacePageId {
  const workspace =
    typeof primary === "string" ? primaryById.get(primary) : primary;
  if (!workspace) throw new Error(`Unknown primary workspace '${String(primary)}'.`);
  return workspace.defaultPage;
}
