import type { ReactNode } from "react";
import { PageIntro } from "./PageIntro";
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
  /** The task's purpose line under the header (design basis H.1); `useModeHeader().purpose`. */
  purpose?: string;
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
  purpose = "",
  titleLevel = 1,
  onActivate,
}: WorkspaceHeaderProps<T>) {
  // The tab row holds tabs only (UX_REFERENCE rule 26): a page's actions live in the page,
  // beside what they act on, so every page's tab bar looks the same.
  if (titleLevel === 2) {
    // Under the shell's page title (local-tabs pages) a second visible title repeats it
    // ("Research Data" twice, #30): keep the heading for assistive technology only and let
    // the task tabs and the primary action form one row.
    return (
      <header className="workspace-page-header workspace-subheader">
        <h2 className="visually-hidden">{title}</h2>
        <WorkspaceTabs
          idPrefix={idPrefix}
          label={tabLabel}
          tabs={tabs}
          activeId={activeId}
          panelId={panelId}
          className={tabsClassName}
          onActivate={onActivate}
        />
      </header>
    );
  }

  const heading =
    titleLevel === 1 ? (
      <h1>{title}</h1>
    ) : (
      <h2>{title}</h2>
    );

  return (
    <>
    <header className="workspace-page-header">
      {/* One 40 px row (UX-04): the title on the left, the task tabs and the primary action on
          the right. The active task is the selected tab, so the eyebrow that repeated it is read
          by screen readers only. */}
      <div className="workspace-page-heading">
        <span className="eyebrow visually-hidden">{taskLabel}</span>
        {heading}
      </div>
      <div className="workspace-page-header-actions">
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
    <PageIntro purpose={purpose} id={activeId} />
    </>
  );
}
