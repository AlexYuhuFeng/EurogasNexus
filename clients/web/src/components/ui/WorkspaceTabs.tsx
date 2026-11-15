import type { ReactNode } from "react";

import { Tabs } from "./Tabs";

export interface WorkspaceTabItem<T extends string> {
  id: T;
  label: ReactNode;
  /** A shorter label shown at compact width (an abbreviation or one word); the full label
      stays the tab's accessible name (docs/product/ADAPTIVE_CLIENT.md). */
  shortLabel?: string;
  controls?: string;
}


/**
 * Canonical shell region marker (Architecture V2 Wave 1).
 *
 * The union is declared here so a leaf UI primitive keeps importing nothing from
 * `app/`; `clients/web/tests/experienceArchitecture.test.ts` asserts it stays equal
 * to the shell vocabulary in `app/experience/vocabulary.ts`. Passing the marker only
 * adds a `data-shell-region` attribute - it changes no rendering, keyboard or
 * accessibility behaviour.
 */
export type ShellRegionMarker =
  | "global-context"
  | "navigation"
  | "primary-workspace"
  | "inspector"
  | "activity";

interface WorkspaceTabsProps<T extends string> {
  idPrefix: string;
  label: string;
  tabs: readonly WorkspaceTabItem<T>[];
  activeId: T;
  panelId: string;
  /** Always a tablist; kept so existing call sites that state it still type-check. */
  role?: "tablist";
  className?: string;
  shellRegion?: ShellRegionMarker;
  onActivate: (id: T) => void;
}

/**
 * A workspace's task tabs, or the top bar's destinations: the Tabs primitive as a `<nav>`
 * landmark holding the tablist (UX-02). Tabs owns the behaviour (roving tabindex,
 * Left/Right/Home/End, the selected tab's `aria-selected`), so every tab row in the product
 * moves the same way.
 */
export function WorkspaceTabs<T extends string>({
  idPrefix,
  label,
  tabs,
  activeId,
  panelId,
  className,
  shellRegion,
  onActivate,
}: WorkspaceTabsProps<T>) {
  return (
    <Tabs
      landmark
      idPrefix={idPrefix}
      label={label}
      tabs={tabs}
      activeId={activeId}
      panelId={panelId}
      variant={shellRegion === "navigation" ? "nav" : "line"}
      className={className}
      dataAttributes={{ "data-shell-region": shellRegion }}
      onChange={onActivate}
    />
  );
}
