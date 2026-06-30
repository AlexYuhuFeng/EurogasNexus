import type { Dispatch, SetStateAction } from "react";

type ThemeMode = "light" | "dark" | "system";

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

interface WorkspaceTopBarProps {
  activeWorkspace: WorkspacePageId;
  workspaceMenuOpen: boolean;
  searchTerm: string;
  dataStatus: string;
  language: string;
  mode: ThemeMode;
  t: (key: string) => string;
  onWorkspaceMenuToggle: () => void;
  onSearchTermChange: Dispatch<SetStateAction<string>>;
  onLanguageChange: (language: string) => void;
  onModeChange: (mode: ThemeMode) => void;
}

export function WorkspaceTopBar({
  activeWorkspace,
  workspaceMenuOpen,
  searchTerm,
  dataStatus,
  language,
  mode,
  t,
  onWorkspaceMenuToggle,
  onSearchTermChange,
  onLanguageChange,
  onModeChange,
}: WorkspaceTopBarProps) {
  return (
    <header className="app-header cockpit-topbar workspace-topbar-only">
      <button
        className="workspace-pill workspace-trigger"
        type="button"
        aria-label={t("topbar.workspace_menu")}
        aria-expanded={workspaceMenuOpen}
        onClick={onWorkspaceMenuToggle}
      >
        <span className="topbar-menu-glyph" aria-hidden="true" />
        <span className="workspace-pill-copy">
          <span>{t("topbar.workspace_label")}</span>
          <strong>{t(`nav.${activeWorkspace}`)}</strong>
        </span>
      </button>
      <input
        className="topbar-search"
        value={searchTerm}
        onChange={(event) => onSearchTermChange(event.target.value)}
        placeholder={t("map.search")}
      />
      <div className="header-controls">
        <span className={`status-badge status-${dataStatus}`}>{t(`data.${dataStatus}`)}</span>
        <select value={language} onChange={(event) => onLanguageChange(event.target.value)}>
          <option value="en">EN</option>
          <option value="zh-CN">{t("settings.chinese")}</option>
        </select>
        <select value={mode} onChange={(event) => onModeChange(event.target.value as ThemeMode)}>
          <option value="light">{t("theme.light")}</option>
          <option value="dark">{t("theme.dark")}</option>
          <option value="system">{t("theme.system")}</option>
        </select>
      </div>
    </header>
  );
}
