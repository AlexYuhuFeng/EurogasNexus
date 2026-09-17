/**
 * The canonical experience shell contract (Architecture V2 Wave 1).
 *
 * The target shell is described in
 * `docs/engineering/Architecture-V2/04_PRODUCT_EXPERIENCE_ARCHITECTURE.md` sections 3
 * and 8: a global context row, navigation, one primary workspace, one Inspector and
 * one activity/evidence row, shared by every work mode.
 *
 * This module records, for each region, who owns it today and how far the current
 * implementation actually goes. It is deliberately honest: a region that does not
 * exist yet is marked `planned` instead of being described as if it shipped. The
 * fitness test `experienceArchitecture.test.ts` keeps the claim and the markup in
 * agreement, so a region cannot silently become "implemented" in prose.
 *
 * No region grants authority. Navigation and composition change information
 * density, never permissions.
 */

import type { ShellRegion } from "./vocabulary.ts";

export type ShellRegionImplementation = "present" | "partial" | "planned";

export interface ShellRegionContract {
  readonly region: ShellRegion;
  readonly implementation: ShellRegionImplementation;
  /** Repository paths that own the region today (or will own it). */
  readonly owners: readonly string[];
  /** What the region is for, in one line. */
  readonly purpose: string;
  /** `data-shell-region` value rendered by the owning element, when present. */
  readonly markupMarker: string | null;
}

export const shellRegions: readonly ShellRegionContract[] = [
  {
    region: "global-context",
    implementation: "present",
    owners: ["clients/web/src/components/WorkspaceTopBar.tsx"],
    purpose:
      "Gas day, delivery product, hub, portfolio/object search, data status and identity - one owner for global context.",
    markupMarker: "global-context",
  },
  {
    region: "navigation",
    implementation: "present",
    owners: [
      "clients/web/src/components/WorkspaceTopBar.tsx",
      "clients/web/src/app/workspaces/WorkspaceRenderer.tsx",
    ],
    purpose:
      "Durable work domains (primary navigation) plus the local task row owned by the active workspace header.",
    markupMarker: "navigation",
  },
  {
    region: "primary-workspace",
    implementation: "present",
    owners: [
      "clients/web/src/app/shell/AppShell.tsx",
      "clients/web/src/app/workspaces/WorkspaceRenderer.tsx",
    ],
    purpose: "The active workspace surface: exactly one primary workspace mounts at a time.",
    markupMarker: "primary-workspace",
  },
  {
    region: "inspector",
    implementation: "present",
    owners: [
      "clients/web/src/components/InspectorPanel.tsx",
      "clients/web/src/stores/inspector.ts",
    ],
    purpose:
      "Canonical object detail (route, contract, capacity, observation, strategy version, evidence) instead of a new top-level page per object kind. Docked as a right-hand drawer in Wave 9; dockable/detachable panels are Wave 10 work.",
    markupMarker: "inspector",
  },
  {
    region: "activity",
    implementation: "partial",
    owners: ["clients/web/src/app/shell/AppShell.tsx"],
    purpose:
      "Jobs, evidence and notifications. Today only the bounded endpoint-failure banner exists; the unified Job model arrives in Wave 8.",
    markupMarker: null,
  },
];

const byRegion = new Map<ShellRegion, ShellRegionContract>(
  shellRegions.map((contract) => [contract.region, contract]),
);

export function shellRegionContract(region: ShellRegion): ShellRegionContract {
  const contract = byRegion.get(region);
  if (!contract) throw new Error(`No shell contract declared for region '${region}'.`);
  return contract;
}

/** Regions the running client is expected to mark up today. */
export function renderedShellRegions(): ShellRegion[] {
  return shellRegions
    .filter((contract) => contract.markupMarker !== null)
    .map((contract) => contract.region);
}

/**
 * Shell regions that V2 requires and the client does not render yet. Wave 1
 * declares them; Wave 8/9 implement them. Reporting them here keeps the gap
 * explicit instead of implied.
 */
export function plannedShellRegions(): ShellRegion[] {
  return shellRegions
    .filter((contract) => contract.implementation === "planned")
    .map((contract) => contract.region);
}

export function shellRegionCoverage(): {
  present: ShellRegion[];
  partial: ShellRegion[];
  planned: ShellRegion[];
} {
  const pick = (status: ShellRegionImplementation) =>
    shellRegions.filter((c) => c.implementation === status).map((c) => c.region);
  return { present: pick("present"), partial: pick("partial"), planned: pick("planned") };
}
