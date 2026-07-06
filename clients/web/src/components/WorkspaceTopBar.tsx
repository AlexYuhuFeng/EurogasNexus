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

const groupedWorkspaceMenuCss = `
.workspace-menu {
  position: fixed;
  z-index: 60;
  top: 72px;
  left: 16px;
  display: flex;
  width: min(360px, calc(100vw - 32px));
  max-height: calc(100vh - 96px);
  flex-direction: column;
  gap: 6px;
  overflow-y: auto;
  border: 1px solid var(--eg-hairline, var(--border));
  border-radius: 18px;
  background: rgb(255 255 255 / 96%);
  box-shadow: var(--eg-shadow-3, 0 12px 28px rgb(24 32 38 / 12%));
  padding: 10px;
  backdrop-filter: blur(14px);
}

:root.dark .workspace-menu {
  background: rgb(17 17 17 / 96%);
}

.workspace-menu-item {
  display: grid;
  gap: 2px;
  width: 100%;
  min-height: 38px;
  border: 1px solid transparent;
  border-radius: 12px;
  background: transparent;
  color: var(--eg-ink, var(--text));
  cursor: pointer;
  font-size: 14px;
  font-weight: 600;
  line-height: 18px;
  padding: 9px 11px;
  text-align: left;
}

.workspace-menu-item:hover,
.workspace-menu-item.active {
  border-color: var(--eg-hairline, var(--border));
  background: var(--eg-canvas-soft, var(--surface-strong));
}

.workspace-menu-item.active {
  box-shadow: inset 3px 0 0 var(--eg-ink, var(--accent));
}

.workspace-menu-item::before {
  display: none;
  color: var(--eg-muted, var(--muted));
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.04em;
  line-height: 14px;
  text-transform: uppercase;
}

.workspace-menu-item:nth-of-type(1) { order: 110; }
.workspace-menu-item:nth-of-type(4) { order: 120; }
.workspace-menu-item:nth-of-type(7) { order: 130; }
.workspace-menu-item:nth-of-type(5) { order: 210; }
.workspace-menu-item:nth-of-type(3) { order: 220; }
.workspace-menu-item:nth-of-type(2) { order: 230; }
.workspace-menu-item:nth-of-type(8) { order: 240; }
.workspace-menu-item:nth-of-type(6) { order: 310; }
.workspace-menu-item:nth-of-type(10) { order: 320; }
.workspace-menu-item:nth-of-type(9) { order: 410; }
.workspace-menu-item:nth-of-type(11) { order: 420; }
.workspace-menu-item:nth-of-type(12) { order: 430; }
.workspace-menu-item:nth-of-type(13) { order: 440; }

.workspace-menu-item:nth-of-type(1)::before,
.workspace-menu-item:nth-of-type(5)::before,
.workspace-menu-item:nth-of-type(6)::before,
.workspace-menu-item:nth-of-type(9)::before {
  display: block;
  margin-bottom: 3px;
}

.workspace-menu-item:nth-of-type(1)::before { content: "Decision Workspace"; }
.workspace-menu-item:nth-of-type(5)::before { content: "Commercial Inputs"; }
.workspace-menu-item:nth-of-type(6)::before { content: "Analytics"; }
.workspace-menu-item:nth-of-type(9)::before { content: "Operations"; }

html[lang="zh-CN"] .workspace-menu-item:nth-of-type(1)::before { content: "决策工作区"; }
html[lang="zh-CN"] .workspace-menu-item:nth-of-type(5)::before { content: "商业输入"; }
html[lang="zh-CN"] .workspace-menu-item:nth-of-type(6)::before { content: "分析工具"; }
html[lang="zh-CN"] .workspace-menu-item:nth-of-type(9)::before { content: "运行与设置"; }

@media (max-width: 900px) {
  .workspace-menu {
    top: 68px;
    left: 12px;
    width: calc(100vw - 24px);
  }
}
`;

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
    <>
      <style>{groupedWorkspaceMenuCss}</style>
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
    </>
  );
}
