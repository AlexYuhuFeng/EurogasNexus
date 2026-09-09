import type { Dispatch, SetStateAction } from "react";
import {
  SUPPORTED_HUB_IDS,
  type SupportedHubId,
} from "@/app/context";
import {
  primaryWorkspaces,
  type PrimaryWorkspace,
  type PrimaryWorkspaceId,
} from "@/app/navigation/productNavigation";
import { WorkspaceTabs } from "@/components/ui";
import type { WorkspacePageId } from "@/workspaceNavigation";
import type { ApiState } from "@/stores/api";
import type { CurrentUserDTO } from "@/api/client";
import { buildSourceSummary, type SourceStats } from "@/app/workspaceDerivedData";
import { AlertCenter } from "./AlertCenter";
import "./WorkspaceTopBar.css";

type ThemeMode = "light" | "dark" | "system";

interface WorkspaceTopBarProps {
  activeWorkspace: WorkspacePageId;
  activePrimaryWorkspace: PrimaryWorkspace;
  searchTerm: string;
  dataStatus: string;
  loading: boolean;
  streamingActive: boolean;
  language: string;
  mode: ThemeMode;
  gasDay: string;
  deliveryProduct: string;
  hubId: SupportedHubId | null;
  marketLastUpdatedAtUtc: string | null;
  sourceStats: SourceStats;
  sourceEndpointError?: string;
  currentUser: CurrentUserDTO | null;
  monitoring: Pick<
    ApiState,
    | "monitoringAlerts"
    | "monitoringSummary"
    | "monitoringAnalysisByAlert"
    | "monitoringBusyAlertId"
    | "acknowledgeMonitoringAlert"
    | "analyzeMonitoringAlert"
  >;
  t: (key: string) => string;
  onSearchTermChange: Dispatch<SetStateAction<string>>;
  onLanguageChange: (language: string) => void;
  onModeChange: (mode: ThemeMode) => void;
  onGasDayChange: (gasDay: string) => void;
  onDeliveryProductChange: (product: string) => void;
  onHubChange: (hubId: string | null) => void;
  onOpenPrimaryWorkspace: (primary: PrimaryWorkspaceId) => void;
  onSignIn: () => void;
  onSignOut: () => void;
  onOpenAccess: () => void;
}

export function WorkspaceTopBar({
  activeWorkspace,
  activePrimaryWorkspace,
  searchTerm,
  dataStatus,
  loading,
  streamingActive,
  language,
  mode,
  gasDay,
  deliveryProduct,
  hubId,
  marketLastUpdatedAtUtc,
  sourceStats,
  sourceEndpointError,
  currentUser,
  monitoring,
  t,
  onSearchTermChange,
  onLanguageChange,
  onModeChange,
  onGasDayChange,
  onDeliveryProductChange,
  onHubChange,
  onOpenPrimaryWorkspace,
  onSignIn,
  onSignOut,
  onOpenAccess,
}: WorkspaceTopBarProps) {
  const hasMapSearch = activeWorkspace === "network";
  const sourceSummary = buildSourceSummary(sourceStats, {
    loading,
    sourceError: sourceEndpointError,
    dataStatus,
  });
  const primaryTabs = primaryWorkspaces.map((primary) => ({
    id: primary.id,
    label: t(primary.labelKey),
  }));

  return (
    <header
      className={`app-header cockpit-topbar workspace-topbar-only ${hasMapSearch ? "has-map-search" : "workspace-topbar-page"}`}
    >
      <WorkspaceTabs
        idPrefix="workspace-primary"
        label={t("topbar.primary_navigation")}
        tabs={primaryTabs}
        activeId={activePrimaryWorkspace.id}
        panelId="workspace-primary-content"
        className="workspace-primary-tabs"
        onActivate={(primary) => onOpenPrimaryWorkspace(primary as PrimaryWorkspaceId)}
      />
      {hasMapSearch && (
        <span className="workspace-local-task" aria-label={t("topbar.current_task")}>
          <span>{t("topbar.task_label")}</span>
          <strong>{t(`nav.${activeWorkspace}`)}</strong>
        </span>
      )}
      {hasMapSearch && (
        <input
          className="topbar-search"
          value={searchTerm}
          onChange={(event) => onSearchTermChange(event.target.value)}
          placeholder={t("map.search")}
        />
      )}
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
        <label>
          <span>{t("context.hub")}</span>
          <select
            aria-label={t("context.hub")}
            value={hubId ?? ""}
            onChange={(event) => onHubChange(event.target.value || null)}
          >
            <option value="">{t("context.no_hub_focus")}</option>
            {SUPPORTED_HUB_IDS.map((hub) => (
              <option key={`context-hub-${hub}`} value={hub}>{hub}</option>
            ))}
          </select>
        </label>
        <span className={sourceSummary.viewState === "ready" ? "context-freshness" : "context-freshness issue"}>
          <strong>{t(`context.sources_${sourceSummary.viewState}`)}</strong>
          {sourceSummary.showCounts && (
            <small>
              {sourceSummary.active}/{sourceSummary.total} {t("context.active")} · {sourceSummary.issues} {t("context.issues")}
            </small>
          )}
          <small>
            {marketLastUpdatedAtUtc
              ? `${t("context.updated")} ${new Date(marketLastUpdatedAtUtc).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}`
              : t("context.no_market_update")}
          </small>
        </span>
      </div>
      <div className="header-controls">
        <AlertCenter
          alerts={monitoring.monitoringAlerts}
          summary={monitoring.monitoringSummary}
          analysisByAlert={monitoring.monitoringAnalysisByAlert}
          busyAlertId={monitoring.monitoringBusyAlertId}
          language={language}
          onAcknowledge={monitoring.acknowledgeMonitoringAlert}
          onAnalyze={monitoring.analyzeMonitoringAlert}
        />
        <span
          className={`stream-status-badge ${streamingActive ? "stream-live" : "stream-fallback"}`}
          aria-label={streamingActive ? t("stream.live") : t("stream.polling_fallback")}
        >
          {streamingActive ? t("stream.live") : t("stream.polling_fallback")}
        </span>
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
        <div className="topbar-user-menu">
          {currentUser ? (
            <>
              <span title={currentUser.name}>{currentUser.display_name ?? currentUser.name}</span>
              <small>{currentUser.role}</small>
              {currentUser.permissions.includes("identity.manage") && (
                <button type="button" onClick={onOpenAccess}>{t("topbar.access_identity")}</button>
              )}
              <button type="button" onClick={onSignOut}>{t("topbar.sign_out")}</button>
            </>
          ) : (
            <button type="button" onClick={onSignIn}>{t("topbar.sign_in")}</button>
          )}
        </div>
      </div>
    </header>
  );
}
