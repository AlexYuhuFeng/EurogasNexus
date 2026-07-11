import { useState } from "react";
import type { Dispatch, SetStateAction } from "react";
import { workspaceGroups } from "../workspaceNavigation";
import type { WorkspaceGroup, WorkspacePageId } from "../workspaceNavigation";
import "./WorkspaceTopBar.css";

export type { WorkspaceGroup, WorkspacePageId } from "../workspaceNavigation";

type ThemeMode = "light" | "dark" | "system";

interface WorkspaceTopBarProps {
  activeWorkspace: WorkspacePageId;
  searchTerm: string;
  dataStatus: string;
  loading: boolean;
  language: string;
  mode: ThemeMode;
  gasDay: string;
  deliveryProduct: string;
  marketLastUpdatedAtUtc: string | null;
  sourceIssueCount: number;
  t: (key: string) => string;
  onSearchTermChange: Dispatch<SetStateAction<string>>;
  onLanguageChange: (language: string) => void;
  onModeChange: (mode: ThemeMode) => void;
  onGasDayChange: (gasDay: string) => void;
  onDeliveryProductChange: (product: string) => void;
}

export function WorkspaceTopBar({
  activeWorkspace,
  searchTerm,
  dataStatus,
  loading,
  language,
  mode,
  gasDay,
  deliveryProduct,
  marketLastUpdatedAtUtc,
  sourceIssueCount,
  t,
  onSearchTermChange,
  onLanguageChange,
  onModeChange,
  onGasDayChange,
  onDeliveryProductChange,
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
        <div className="topbar-trading-context" aria-label={t("context.title")}>
          <label>
            <span>{t("context.gas_day")}</span>
            <input
              type="date"
              value={gasDay}
              onChange={(event) => onGasDayChange(event.target.value)}
            />
          </label>
          <label>
            <span>{t("context.product")}</span>
            <select
              value={deliveryProduct}
              onChange={(event) => onDeliveryProductChange(event.target.value)}
            >
              <option value="all">{t("context.all_products")}</option>
              <option value="day-ahead">{t("context.day_ahead")}</option>
              <option value="within-day">{t("context.within_day")}</option>
              <option value="month-ahead">{t("context.month_ahead")}</option>
            </select>
          </label>
          <span className={sourceIssueCount > 0 ? "context-freshness issue" : "context-freshness"}>
            <strong>{sourceIssueCount > 0 ? `${sourceIssueCount} ${t("context.issues")}` : t("context.sources_ready")}</strong>
            <small>
              {marketLastUpdatedAtUtc
                ? `${t("context.updated")} ${new Date(marketLastUpdatedAtUtc).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}`
                : t("context.no_market_update")}
            </small>
          </span>
        </div>
        <div className="header-controls">
          <span className={`status-badge status-${loading ? "loading" : dataStatus}`} aria-live="polite">
            {loading ? t("status.loading") : t(`data.${dataStatus}`)}
          </span>
          <select
            aria-label={t("settings.language")}
            value={language}
            onChange={(event) => onLanguageChange(event.target.value)}
          >
            <option value="en">EN</option>
            <option value="zh-CN">{t("settings.chinese")}</option>
          </select>
          <select
            aria-label={t("settings.appearance")}
            value={mode}
            onChange={(event) => onModeChange(event.target.value as ThemeMode)}
          >
            <option value="light">{t("theme.light")}</option>
            <option value="dark">{t("theme.dark")}</option>
            <option value="system">{t("theme.system")}</option>
          </select>
        </div>
      </header>

      {groupedMenuOpen && (
        <nav className="workspace-menu grouped-workspace-menu" aria-label={t("topbar.workspace_menu")}>
          {workspaceGroups.map((group: WorkspaceGroup) => (
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
