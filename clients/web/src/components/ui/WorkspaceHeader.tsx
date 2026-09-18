import { cloneElement, isValidElement, type ReactElement, type ReactNode } from "react";
import { WorkspaceTabs, type WorkspaceTabItem } from "./WorkspaceTabs";

interface WorkspaceHeaderProps<T extends string> {
  title: ReactNode;
  taskLabel: ReactNode;
  idPrefix: string;
  tabs: readonly WorkspaceTabItem<T>[];
  activeId: T;
  panelId: string;
  tabLabel: string;
  tabsClassName?: string;
  primaryAction?: ReactNode;
  /**
   * Heading level for the workspace title.
   *
   * A page has exactly one top-level heading, and `workspacePatterns.ts` is the one place that
   * decides who owns it: a `consolidated` page's workspace renders it (level 1), while a
   * `local-tabs` page's heading belongs to the shell and the workspace's own header is a section
   * under it (level 2). Without that distinction the three surfaces Wave 9 gave a header of their
   * own - strategy, research and agents - rendered a second top-level heading beside the shell's,
   * which the whole-product browser sweep reports as a document-structure defect (and which no
   * source-text test could see). `workspaceHeaderTitleLevel(page)` computes the level from the
   * registry.
   */
  titleLevel?: 1 | 2;
  onActivate: (id: T) => void;
}

export function WorkspaceHeader<T extends string>({
  title,
  taskLabel,
  idPrefix,
  tabs,
  activeId,
  panelId,
  tabLabel,
  tabsClassName,
  primaryAction,
  titleLevel = 1,
  onActivate,
}: WorkspaceHeaderProps<T>) {
  // The one primary slot marks what it renders, so "where is this workspace's primary action"
  // has a stable answer. Wave 9 moved six surfaces' primary actions out of their panels and into
  // this slot, and the whole-product browser sweep kept looking for the button where it used to
  // live (`button.button.primary` inside the view, a class these buttons never had) - so the run
  // action could not be started at all and the sweep timed out instead of reporting why. The mark
  // belongs to the slot rather than to each call site, because the slot is what makes the action
  // the workspace's primary one.
  const markedPrimaryAction = isValidElement(primaryAction)
    ? cloneElement(primaryAction as ReactElement<Record<string, unknown>>, {
        "data-primary-action": "",
      })
    : primaryAction;

  const heading =
    titleLevel === 1 ? (
      <h1>{title}</h1>
    ) : (
      <h2>{title}</h2>
    );

  return (
    <header className="workspace-page-header">
      <div className="workspace-page-heading">
        <span className="eyebrow">{taskLabel}</span>
        {heading}
      </div>
      <div className="workspace-page-header-actions">
        {markedPrimaryAction}
        <WorkspaceTabs
          idPrefix={idPrefix}
          label={tabLabel}
          tabs={tabs}
          activeId={activeId}
          panelId={panelId}
          className={tabsClassName}
          onActivate={onActivate}
        />
      </div>
    </header>
  );
}
