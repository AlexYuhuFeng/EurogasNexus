import { useState } from "react";
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

type WorkspaceGroupId = "decision" | "commercial" | "analytics" | "operations";

export interface WorkspaceGroup {
  id: WorkspaceGroupId;
  labelKey: string;
  pages: WorkspacePageId[];
}

export const workspaceGroups: WorkspaceGroup[] = [
  {
    id: "decision",
    labelKey: "nav.group.decision",
    pages: ["network", "scenario", "review"],
  },
  {
    id: "commercial",
    labelKey: "nav.group.commercial",
    pages: ["contracts", "market", "capacity", "orders"],
  },
  {
    id: "analytics",
    labelKey: "nav.group.analytics",
    pages: ["strategy", "glossary"],
  },
  {
    id: "operations",
    labelKey: "nav.group.operations",
    pages: ["sources", "runtime", "settings", "manual"],
  },
];

interface WorkspaceTopBarProps {
  activeWorkspace: WorkspacePageId;
  searchTerm: string;
  dataStatus: string;
  language: string;
  mode: ThemeMode;
  t: (key: string) => string;
  onSearchTermChange: Dispatch<SetStateAction<string>>;
  onLanguageChange: (language: string) => void;
  onModeChange: (mode: ThemeMode) => void;
  [legacyProp: string]: unknown;
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
  gap: 10px;
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

.workspace-menu-group {
  display: grid;
  gap: 5px;
}

.workspace-menu-group-title {
  color: var(--eg-muted, var(--muted));
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.06em;
  line-height: 14px;
  padding: 2px 11px 0;
  text-transform: uppercase;
}

.workspace-menu-group-items {
  display: grid;
  gap: 4px;
}

.workspace-menu-group.active .workspace-menu-group-title {
  color: var(--eg-ink, var(--accent));
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
  searchTerm,
  dataStatus,
  language,
  mode,
  t,
  onSearchTermChange,
  onLanguageChange,
  onModeChange,
}: WorkspaceTopBarProps) {
  const [groupedMenuOpen, setGroupedMenuOpen] = useState(false);

  function openWorkspace(page: WorkspacePageId) {
    if (typeof window !== "undefined") {
      const nextUrl = new URL(window.location.href);
      nextUrl.searchParams.set("workspace", page);
      window.history.pushState({ workspace: page }, "", nextUrl);
      window.dispatchEvent(new Event("popstate"));
    }
    setGroupedMenuOpen(false);
  }

  return (
    <>
      <style>{groupedWorkspaceMenuCss}</style>
      <header className="app-header cockpit-topbar workspace-topbar-only">
        <button
          className="workspace-pill workspace-trigger"
          type="button"
          aria-label={t("topbar.workspace_menu")}
          aria-expanded={groupedMenuOpen}
          onClick={() => setGroupedMenuOpen((current) => !current)}
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

      {groupedMenuOpen && (
        <nav className="workspace-menu grouped-workspace-menu" aria-label={t("topbar.workspace_menu")}>
          {workspaceGroups.map((group) => (
            <section
              key={`workspace-group-${group.id}`}
              className={group.pages.includes(activeWorkspace) ? "workspace-menu-group active" : "workspace-menu-group"}
            >
              <span className="workspace-menu-group-title">{t(group.labelKey)}</span>
              <div className="workspace-menu-group-items">
                {group.pages.map((page) => (
                  <button
                    key={`grouped-menu-${page}`}
                    type="button"
                    className={activeWorkspace === page ? "workspace-menu-item active" : "workspace-menu-item"}
                    onClick={() => openWorkspace(page)}
                  >
                    {t(`nav.${page}`)}
                  </button>
                ))}
              </div>
            </section>
          ))}
        </nav>
      )}
    </>
  );
}
