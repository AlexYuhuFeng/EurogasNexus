import type { WorkspacePageId } from "@/workspaceNavigation";

export type PrimaryWorkspaceId =
  | "market"
  | "portfolio"
  | "strategy"
  | "decision"
  | "system"
  | "administration";

export interface PrimaryWorkspace {
  id: PrimaryWorkspaceId;
  labelKey: string;
  descriptionKey: string;
  pages: WorkspacePageId[];
  defaultPage: WorkspacePageId;
  /**
   * Architecture V2 control-plane boundary (06_IDENTITY_ACCESS_CONTROL_PLANE.md
   * section 8): administration is a distinct product surface, not a business
   * workspace. The shell hides it for an identity without an administration
   * capability and refuses a deep link into it; the backend authorises every
   * request independently.
   */
  controlPlane?: boolean;
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
    pages: ["research", "agents", "settings", "manual", "glossary"],
    defaultPage: "research",
  },
  {
    id: "administration",
    labelKey: "nav.primary.administration",
    descriptionKey: "nav.primary.administration.description",
    pages: ["sources", "runtime", "access"],
    defaultPage: "sources",
    controlPlane: true,
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

/** Whether a page belongs to the control plane rather than the business workspace. */
export function isControlPlanePage(page: WorkspacePageId): boolean {
  return primaryWorkspaceForPage(page).controlPlane === true;
}

/** The control-plane primaries. There is one today; the helper keeps it declarative. */
export function controlPlanePrimaries(): PrimaryWorkspace[] {
  return primaryWorkspaces.filter((primary) => primary.controlPlane === true);
}
