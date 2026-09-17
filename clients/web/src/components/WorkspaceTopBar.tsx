import { useEffect, useState, type Dispatch, type SetStateAction } from "react";
import {
  SUPPORTED_HUB_IDS,
  type SupportedHubId,
} from "@/app/context";
import {
  primaryWorkspaces,
  type PrimaryWorkspace,
  type PrimaryWorkspaceId,
} from "@/app/navigation/productNavigation";
import {
  compositionFromProfile,
  compositionSeesAdministration,
} from "@/app/experience/experienceProfile";
import { StatusBadge, WorkspaceTabs } from "@/components/ui";
import type { WorkspacePageId } from "@/workspaceNavigation";
import type { ApiState } from "@/stores/api";
import type { ThemeMode } from "@/stores/theme";
import type { CurrentUserDTO } from "@/api/client";
import { buildSourceSummary, type SourceStats } from "@/app/workspaceDerivedData";
import { dataPlaneLabelKey, dataPlaneState } from "@/app/model/dataPlaneStatus";
import { formatUtcTimestamp } from "@/app/model/evidencePresentation";
import { AlertCenter } from "./AlertCenter";
import { HeaderPreferencesMenu } from "./HeaderPreferencesMenu";
import "./WorkspaceTopBar.css";

interface WorkspaceTopBarProps {
  activeWorkspace: WorkspacePageId;
  activePrimaryWorkspace: PrimaryWorkspace;
  searchTerm: string;
  dataStatus: string;
  loading: boolean;
  streamingActive: boolean;
  /** Current interface language; persisted by the shared language writer. */
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
  onGasDayChange: (gasDay: string) => void;
  onDeliveryProductChange: (product: string) => void;
  onHubChange: (hubId: string | null) => void;
  onOpenPrimaryWorkspace: (primary: PrimaryWorkspaceId) => void;
  onSignIn: () => void;
  onSignOut: () => void;
  onOpenAccess: () => void;
  onOpenSettings: () => void;
  onLanguageChange: (language: string) => void;
  onModeChange: (mode: ThemeMode) => void;
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
  onGasDayChange,
  onDeliveryProductChange,
  onHubChange,
  onOpenPrimaryWorkspace,
  onSignIn,
  onSignOut,
  onOpenAccess,
  onOpenSettings,
  onLanguageChange,
  onModeChange,
}: WorkspaceTopBarProps) {
  const hasMapSearch = activeWorkspace === "network";
  const sourceSummary = buildSourceSummary(sourceStats, {
    loading,
    sourceError: sourceEndpointError,
    dataStatus,
  });
  // Architecture V2 control-plane boundary: the administration primary is only
  // offered to an identity whose composition includes an administration
  // capability. Presentation only - the backend authorises every request - and it
  // fails closed, so an absent profile hides the surface instead of showing it.
  const composition = compositionFromProfile(currentUser?.experience);
  const visiblePrimaries = compositionSeesAdministration(composition)
    ? primaryWorkspaces
    : primaryWorkspaces.filter((primary) => primary.controlPlane !== true);
  const primaryTabs = visiblePrimaries.map((primary) => ({
    id: primary.id,
    label: t(primary.labelKey),
  }));

  const [narrowHeader, setNarrowHeader] = useState(
    () => typeof window !== "undefined" && window.matchMedia("(max-width: 900px)").matches,
  );
  const [contextDisclosureOpen, setContextDisclosureOpen] = useState(false);

  useEffect(() => {
    const media = window.matchMedia("(max-width: 900px)");
    const update = () => setNarrowHeader(media.matches);
    update();
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, []);

  const productLabel =
    deliveryProduct === "day-ahead"
      ? t("context.day_ahead")
      : deliveryProduct === "within-day"
        ? t("context.within_day")
        : deliveryProduct === "month-ahead"
          ? t("context.month_ahead")
          : t("context.all_products");

  return (
    <header
      className={`app-header cockpit-topbar workspace-topbar-only ${hasMapSearch ? "has-map-search" : "workspace-topbar-page"}`}
      data-shell-region="global-context"
    >
      <WorkspaceTabs
        idPrefix="workspace-primary"
        label={t("topbar.primary_navigation")}
        tabs={primaryTabs}
        activeId={activePrimaryWorkspace.id}
        panelId="workspace-primary-content"
        className="workspace-primary-tabs"
        shellRegion="navigation"
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
      <details
        className="topbar-context-disclosure"
        open={!narrowHeader || contextDisclosureOpen}
        onToggle={(event) => {
          if (narrowHeader) setContextDisclosureOpen(event.currentTarget.open);
        }}
      >
        <summary aria-label={t("topbar.context_status")}>
          <strong>{t("topbar.context_status")}</strong>
          <span>{gasDay} · {productLabel} · {hubId ?? t("context.no_hub_focus")}</span>
        </summary>
        {(!narrowHeader || contextDisclosureOpen) && (
          <div className="topbar-context-disclosure-content">
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
                ? `${t("context.updated")} ${formatUtcTimestamp(marketLastUpdatedAtUtc)}`
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
            t={t}
            onAcknowledge={monitoring.acknowledgeMonitoringAlert}
            onAnalyze={monitoring.analyzeMonitoringAlert}
          />
          <span
            className={`stream-status-badge ${streamingActive ? "stream-live" : "stream-fallback"}`}
            aria-label={streamingActive ? t("stream.live") : t("stream.polling_fallback")}
          >
            {streamingActive ? t("stream.live") : t("stream.polling_fallback")}
          </span>
          {/*
            The shell owns runtime/data status, so the badge stays - but it speaks
            the constitution's operational vocabulary (Ready / Partial /
            Unavailable) rather than the store's name, and it is the canonical
            StatusBadge, which reads as state instead of as a control beside the
            context selects. It is absent while loading: the source-posture block
            beside it already says "checking", and a badge that flipped to red
            mid-load would report a failure that has not happened.
          */}
          {!loading && (
            <StatusBadge
              variant="runtime-readiness-state"
              status={dataPlaneState(dataStatus)}
              className="topbar-data-status"
              title={t("data.runtime_detail")}
            >
              {t(dataPlaneLabelKey(dataPlaneState(dataStatus)))}
            </StatusBadge>
          )}
          <div className="topbar-user-menu">
            {currentUser ? (
              <>
                <span title={currentUser.name}>{currentUser.display_name ?? currentUser.name}</span>
                <small>{currentUser.role}</small>
                <HeaderPreferencesMenu
                  currentUser={currentUser}
                  language={language}
                  mode={mode}
                  t={t}
                  onLanguageChange={onLanguageChange}
                  onModeChange={onModeChange}
                  onOpenSettings={onOpenSettings}
                  onOpenAccess={onOpenAccess}
                  onSignOut={onSignOut}
                />
              </>
            ) : (
              <button type="button" onClick={onSignIn}>{t("topbar.sign_in")}</button>
            )}
          </div>
        </div>
  
          </div>
        )}
      </details>    </header>
  );
}
