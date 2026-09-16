import { type KeyboardEvent, type ReactNode } from "react";
import { getNextWorkspaceTabIndex, workspaceTabButtonId } from "./tabKeyboard";

export interface WorkspaceTabItem<T extends string> {
  id: T;
  label: ReactNode;
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
  role?: "tablist";
  className?: string;
  shellRegion?: ShellRegionMarker;
  onActivate: (id: T) => void;
}

export function WorkspaceTabs<T extends string>({
  idPrefix,
  label,
  tabs,
  activeId,
  panelId,
  role = "tablist",
  className,
  shellRegion,
  onActivate,
}: WorkspaceTabsProps<T>) {
  const focusTab = (id: T) => {
    window.requestAnimationFrame(() => {
      document.getElementById(workspaceTabButtonId(idPrefix, id))?.focus();
    });
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLButtonElement>, currentId: T) => {
    const currentIndex = tabs.findIndex((tab) => tab.id === currentId);
    const nextIndex = getNextWorkspaceTabIndex(currentIndex, tabs.length, event.key);
    if (nextIndex === null) return;
    event.preventDefault();
    const nextTab = tabs[nextIndex];
    if (!nextTab) return;
    onActivate(nextTab.id);
    focusTab(nextTab.id);
  };

  return (
    <nav className={className} role={role} aria-label={label} data-shell-region={shellRegion}>
      {tabs.map((tab) => {
        const isActive = tab.id === activeId;
        return (
          <button
            key={tab.id}
            id={workspaceTabButtonId(idPrefix, tab.id)}
            type="button"
            role="tab"
            aria-selected={isActive}
            aria-controls={tab.controls ?? panelId}
            className={isActive ? "active" : undefined}
            onClick={() => onActivate(tab.id)}
            onKeyDown={(event) => handleKeyDown(event, tab.id)}
          >
            {tab.label}
          </button>
        );
      })}
    </nav>
  );
}
