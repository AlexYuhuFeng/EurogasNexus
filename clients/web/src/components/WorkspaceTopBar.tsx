import { useEffect, useState } from "react";
import { needsCommercialWorkspaceReads } from "@/stores/workspaceReadScope";
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
import { pageUsesTradingContext, type WorkspacePageId } from "@/workspaceNavigation";
import type { ApiState } from "@/stores/api";
import type { ThemeMode } from "@/stores/theme";
import type { CurrentUserDTO } from "@/api/client";
import { buildSourceSummary, type SourceStats } from "@/app/workspaceDerivedData";
import {
  dataPlaneState,
  runtimeDataAvailability,
  runtimeDataAvailabilityLabelKey,
} from "@/app/model/dataPlaneStatus";
import { formatUtcTimestamp } from "@/app/model/evidencePresentation";
import { AlertCenter } from "./AlertCenter";
import { HeaderPreferencesMenu } from "./HeaderPreferencesMenu";
import { ReportProblemDialog } from "./ReportProblemDialog";
import { requestProblemReport } from "@/app/model/supportReport";
import "./WorkspaceTopBar.css";

interface WorkspaceTopBarProps {
  activeWorkspace: WorkspacePageId;
  activePrimaryWorkspace: PrimaryWorkspace;
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
  t: (key: string, options?: Record<string, unknown>) => string;
  onGasDayChange: (gasDay: string) => void;
  onDeliveryProductChange: (product: string) => void;
  onHubChange: (hubId: string | null) => void;
  onOpenPrimaryWorkspace: (primary: PrimaryWorkspaceId) => void;
  onSignIn: () => void;
  onSignOut: () => void;
  onOpenAccess: () => void;
  onOpenSettings: () => void;
  /** Opens the command palette: search and jump to any workspace or action. */
  onOpenCommandPalette?: () => void;
  onLanguageChange: (language: string) => void;
  onModeChange: (mode: ThemeMode) => void;
}

export function WorkspaceTopBar({
  activeWorkspace,
  activePrimaryWorkspace,
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
  onGasDayChange,
  onDeliveryProductChange,
  onHubChange,
  onOpenPrimaryWorkspace,
  onSignIn,
  onSignOut,
  onOpenAccess,
  onOpenSettings,
  onOpenCommandPalette,
  onLanguageChange,
  onModeChange,
}: WorkspaceTopBarProps) {
  const sourceSummary = buildSourceSummary(sourceStats, {
    loading,
    sourceError: sourceEndpointError,
    dataStatus,
  });
  /**
   * The badge states what the workspace batch reported about the runtime store's own
   * data. It is not the shell's, the market's or a decision's readiness: a runtime
   * store can answer while the readings inside it are stale or missing.
   */
  const runtimeAvailability = runtimeDataAvailability(dataStatus);
  // Gas day, product and hub only where the page's reads take them (#35).
  const usesTradingContext = pageUsesTradingContext(activeWorkspace);
  // Architecture V2 control-plane boundary: the administration primary is only
  // offered to an identity whose composition includes an administration
  // capability. Presentation only - the backend authorises every request - and it
  // fails closed, so an absent profile hides the surface instead of showing it.
  const composition = compositionFromProfile(currentUser?.experience);
  // Separation of duties, the other way round: an administrator without a commercial role is
  // not offered the business workspaces whose reads the backend would refuse.
  const seesCommercial = needsCommercialWorkspaceReads(currentUser);
  const visiblePrimaries = primaryWorkspaces.filter(
    (primary) =>
      (primary.controlPlane !== true || compositionSeesAdministration(composition)) &&
      (primary.commercial !== true || seesCommercial),
  );
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
      // The network map has its own finder ("Find a hub, terminal, field or vessel"); the top bar no
      // longer carries a second map search, which pushed the account menu off a 1440 px screen.
      className="app-header cockpit-topbar workspace-topbar-only workspace-topbar-page"
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
      {onOpenCommandPalette && (
        <button
          type="button"
          className="topbar-command"
          aria-label={t("topbar.command")}
          onClick={onOpenCommandPalette}
          aria-keyshortcuts="Control+K Meta+K"
        >
          <span>{t("topbar.command")}</span>
          <kbd aria-hidden="true">{/Mac|iPhone|iPad/.test(globalThis.navigator?.platform ?? "") ? "⌘K" : "Ctrl K"}</kbd>
        </button>
      )}
      {/* The Active Context this shell is displaying, in machine-readable form. It is the context
          every projection read is issued for (`app/model/projectionContext.ts`), so the browser
          sweep can read the context the surfaces are showing and compare a payload read for that
          context instead of a generic, unfiltered one. The labels beside it stay the display. */}
      <details
        className="topbar-context-disclosure"
        data-context-gas-day={gasDay}
        data-context-product={deliveryProduct}
        data-context-hub={hubId ?? ""}
        open={!narrowHeader || contextDisclosureOpen}
        onToggle={(event) => {
          if (narrowHeader) setContextDisclosureOpen(event.currentTarget.open);
        }}
      >
        <summary aria-label={t("topbar.context_status")}>
          <strong>{t("topbar.context_status")}</strong>
          {usesTradingContext && <span>{gasDay} · {productLabel} · {hubId ?? t("context.no_hub_focus")}</span>}
        </summary>
        {(!narrowHeader || contextDisclosureOpen) && (
          <div className="topbar-context-disclosure-content">
        <div className="topbar-trading-context" aria-label={t("context.title")}>
          {usesTradingContext && (<>
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
          </>)}
          <span
            className={sourceSummary.viewState === "ready" ? "context-freshness" : "context-freshness issue"}
            title={t(`context.sources_${sourceSummary.viewState}`)}
          >
            <strong>
              {sourceSummary.viewState === "partial" && sourceSummary.showCounts && sourceSummary.issues > 0
                ? t("context.sources_need_action", { count: sourceSummary.issues })
                : t(`context.sources_${sourceSummary.viewState}`)}
            </strong>
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
          </div>
        )}
      </details>
      {/* Alerts, status and the account menu stay on the bar at every width: on a phone the
          context disclosure is folded, and the account menu (Settings, language, sign out)
          used to fold away with it (#39). */}
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
          {/* Polling is normal operation, so only a live stream earns a chip; the polling
              state stays in the data-status chip's title instead of a second badge. */}
          {streamingActive && (
            <span className="stream-status-badge stream-live" aria-label={t("stream.live")}>
              {t("stream.live")}
            </span>
          )}
          {/*
            The shell owns runtime/data status, so the badge stays - but it names
            runtime data availability rather than an overall readiness, and it is
            the canonical StatusBadge, which reads as state instead of as a control
            beside the context selects. The store is named in the title detail
            only. It is absent while loading: the source-posture block beside it
            already says "checking", and a badge that flipped to red mid-load would
            report a failure that has not happened.
          */}
          {!loading && (
            <StatusBadge
              variant="runtime-readiness-state"
              status={dataPlaneState(dataStatus)}
              className="topbar-data-status"
              title={`${t("data.runtime_detail")} · ${streamingActive ? t("stream.live") : t("stream.polling_fallback")}`}
            >
              {t(runtimeDataAvailabilityLabelKey(runtimeAvailability))}
            </StatusBadge>
          )}
          {!loading && currentUser && dataPlaneState(dataStatus) !== "ready" && (
            <button
              type="button"
              className="link-button topbar-report-hint"
              title={t("support.hint_title")}
              onClick={() =>
                requestProblemReport({
                  category: "data",
                  severity: "P2",
                  summary: t("support.hint_summary", { state: t(runtimeDataAvailabilityLabelKey(runtimeAvailability)) }),
                })
              }
            >
              {t("support.hint")}
            </button>
          )}
          <div className="topbar-user-menu">
            {currentUser ? (
              <>
                <ReportProblemDialog t={t} />
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
    </header>
  );
}
