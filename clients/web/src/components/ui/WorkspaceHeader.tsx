import type { ReactNode } from "react";
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
  onActivate,
}: WorkspaceHeaderProps<T>) {
  return (
    <header className="workspace-page-header">
      <div className="workspace-page-heading">
        <span className="eyebrow">{taskLabel}</span>
        <h1>{title}</h1>
      </div>
      <div className="workspace-page-header-actions">
        {primaryAction}
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
