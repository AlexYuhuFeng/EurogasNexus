import { useState } from "react";
import type { Dispatch, SetStateAction } from "react";
import "./WorkspaceTopBar.css";

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
