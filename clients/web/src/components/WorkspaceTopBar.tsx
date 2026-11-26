import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { showsKeyboardHints, useShellLayout } from "@/app/shell/useShellLayout";
import { needsCommercialWorkspaceReads } from "@/stores/workspaceReadScope";
import {
  primaryWorkspaces,
  type PrimaryWorkspace,
  type PrimaryWorkspaceId,
} from "@/app/navigation/productNavigation";
import { visibleModes, type ModeId } from "@/app/navigation/modeNavigation";
import {
  compositionFromProfile,
  compositionSeesAdministration,
} from "@/app/experience/experienceProfile";
import { BrandMark, LiveIndicator, WorkspaceTabs } from "@/components/ui";
import type { WorkspacePageId } from "@/workspaceNavigation";
import { useApiStore, type ApiState } from "@/stores/api";
import type { ThemeMode } from "@/stores/theme";
import type { CurrentUserDTO } from "@/api/client";
import { buildSourceSummary, type SourceStats } from "@/app/workspaceDerivedData";
import {
  dataPlaneState,
  runtimeDataAvailability,
  runtimeDataAvailabilityLabelKey,
} from "@/app/model/dataPlaneStatus";
import type { EndpointFailureSurface, EndpointRetrySurface } from "@/app/model/endpointFailures";
import { AlertCenter } from "./AlertCenter";
import { heldApprovalSources } from "./PublicSourceApprovals";
import { HeaderPreferencesMenu } from "./HeaderPreferencesMenu";
import { ReportProblemDialog } from "./ReportProblemDialog";
import { TopBarStatus, dataHealth } from "./TopBarStatus";
import { ViewFreshnessNote } from "./ViewFreshnessNote";
import { requestFeedback, requestProblemReport } from "@/app/model/supportReport";
import { resolveComposition } from "@/app/experience/roleComposition";
import { useDeskToday } from "@/app/hooks/useDeskToday";
import { focusFigure } from "./TodayScreen";
import "./WorkspaceTopBar.css";
import { Icon } from "@/components/ui/Icon";

interface WorkspaceTopBarProps {
  activeWorkspace: WorkspacePageId;
  activePrimaryWorkspace: PrimaryWorkspace;
  /** The mode the user is in (null on a utility page: help, settings, administration). */
  activeMode: ModeId | null;
  dataStatus: string;
  loading: boolean;
  streamingActive: boolean;
  /** Current interface language; persisted by the shared language writer. */
  language: string;
  mode: ThemeMode;
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
  onOpenPrimaryWorkspace: (primary: PrimaryWorkspaceId) => void;
  /** Open one of the four modes (the primary row). */
  onOpenMode: (mode: ModeId) => void;
  onSignIn: () => void;
  onSignOut: () => void;
  onOpenAccess: () => void;
  onOpenSettings: () => void;
  /** Opens the command palette: search and jump to any workspace or action. */
  onOpenCommandPalette?: () => void;
  /** Opens Today (the status panel's list of figures not current leads there). */
  onOpenToday?: () => void;
  onLanguageChange: (language: string) => void;
  onModeChange: (mode: ThemeMode) => void;
  /** Reads that did not load (the status indicator lists them; app/model/endpointFailures.ts). */
  endpointFailures?: EndpointFailureSurface;
  endpointRetry?: EndpointRetrySurface;
  onRetryEndpoints?: () => void;
  /** Administration → Data sources (offered only to whoever administers). */
  onOpenDataSources?: () => void;
}

export function WorkspaceTopBar({
  activeWorkspace,
  activePrimaryWorkspace,
  activeMode,
  dataStatus,
  loading,
  streamingActive,
  language,
  mode,
  marketLastUpdatedAtUtc,
  sourceStats,
  sourceEndpointError,
  currentUser,
  monitoring,
  t,
  onOpenPrimaryWorkspace,
  onOpenMode,
  onSignIn,
  onSignOut,
  onOpenAccess,
  onOpenSettings,
  onOpenCommandPalette,
  onOpenToday,
  onLanguageChange,
  onModeChange,
  endpointFailures,
  endpointRetry,
  onRetryEndpoints,
  onOpenDataSources,
}: WorkspaceTopBarProps) {
  // Today's read, when a page has made it: the status panel names the same figures that are not
  // current. Cache only: the bar never sends a request of its own.
  const deskToday = useDeskToday(false);
  const openFigure = (key: string) => {
    if (focusFigure(key)) return;
    onOpenToday?.();
    // Today mounts and reads; focus the figure once it is drawn.
    let tries = 0;
    const retry = () => {
      if (focusFigure(key) || ++tries > 40) return;
      window.setTimeout(retry, 100);
    };
    window.setTimeout(retry, 100);
  };
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
  // The primary row is the four working modes (WF-05): Desk, Deals, Book, Research, each offered
  // only when the caller's identity can use at least one of its tasks (presentation only: the
  // backend authorises every request, and a mode never grants anything).
  const modes = visibleModes(currentUser);
  const modeTabs = modes.map((mode) => ({ id: mode.id, label: t(mode.labelKey) }));
  // Help & Settings and Administration are utilities in the account area, not modes. The
  // Architecture V2 control-plane boundary still applies: administration is offered only to an
  // identity whose composition includes an administration capability, and fails closed. Separation
  // of duties the other way round: an administrator without a commercial role sees no mode.
  const composition = compositionFromProfile(currentUser?.experience);
  const seesCommercial = needsCommercialWorkspaceReads(currentUser);
  const visiblePrimaries = primaryWorkspaces.filter(
    (primary) =>
      (primary.controlPlane !== true || compositionSeesAdministration(composition)) &&
      (primary.commercial !== true || seesCommercial),
  );
  const utilities = visiblePrimaries.filter((primary) => primary.commercial !== true);
  const seesAdministration = utilities.some((primary) => primary.id === "administration");
  const activeUtility = activeMode ? null : activePrimaryWorkspace;
  const menuLabel = activeMode
    ? t(modes.find((mode) => mode.id === activeMode)?.labelKey ?? "nav.mode.desk")
    : t(activePrimaryWorkspace.labelKey);

  // Compact width (docs/product/ADAPTIVE_CLIENT.md): one row - menu, search, alerts, status dot,
  // account - and a drawer holding the lines of work and the trading context (#39, #40).
  const shellLayout = useShellLayout();
  const { widthClass } = shellLayout;
  const keyboardHints = showsKeyboardHints(shellLayout);
  const compact = widthClass === "compact";
  // The drawer holds the lines of work below 1024 px (phones, tablet portrait); the trading
  // context joins it only at compact width, where the bar has no room for its disclosure.
  const drawerNav = shellLayout.drawerNav;
  const [drawerOpen, setDrawerOpen] = useState(false);
  const menuButtonRef = useRef<HTMLButtonElement>(null);
  const drawerRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!drawerNav) setDrawerOpen(false);
  }, [drawerNav]);
  useEffect(() => {
    if (!drawerOpen) return;
    drawerRef.current?.querySelector<HTMLElement>("button, select, input")?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setDrawerOpen(false);
        menuButtonRef.current?.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [drawerOpen]);
  const shortcutLabel = /Mac|iPhone|iPad/.test(globalThis.navigator?.platform ?? "") ? "⌘K" : "Ctrl K";
  // A deployment valued on simulated prices: its static store's figures are not counted stale.
  // Each simulated figure carries its own source mark; the shell adds no badge for it.
  const simulatedPrices = useApiStore((state) => state.runtimeRelease?.demo_marks === true) || deskToday.today?.simulated === true;
  const storeSources = useApiStore((state) => state.sources);
  const heldSources = heldApprovalSources(storeSources ?? []).length;
  const closeDrawer = () => {
    setDrawerOpen(false);
    menuButtonRef.current?.focus();
  };

  return (
    <header
      // The network map has its own finder ("Find a hub, terminal, field or vessel"); the top bar no
      // longer carries a second map search, which pushed the account menu off a 1440 px screen.
      className="app-header cockpit-topbar workspace-topbar-only workspace-topbar-page"
      data-shell-region="global-context"
    >
      {/* Top-left: the mark. Where the lines of work live in the drawer (below 1024 px) the mark
          is the one control that opens it, not a logo beside a separate hamburger. */}
      {drawerNav ? (
        <button
          ref={menuButtonRef}
          type="button"
          className="topbar-menu-button topbar-brand-menu"
          aria-expanded={drawerOpen}
          aria-controls="topbar-drawer"
          aria-label={t("topbar.menu")}
          title={t("topbar.menu")}
          onClick={() => setDrawerOpen((open) => !open)}
        >
          <BrandMark variant="mark" size="md" tone="mono" className="topbar-brand" />
          {!compact ? (
            <span className="topbar-menu-label">
              <span>{menuLabel}</span>
            </span>
          ) : null}
          <Icon name="chevron-down" size="xs" className="topbar-menu-chevron" />
        </button>
      ) : (
        <span className="topbar-brand-group">
          <BrandMark variant={widthClass === "wide" ? "wordmark" : "mark"} size="md" tone="mono" className="topbar-brand" />
        </span>
      )}
      {drawerNav && drawerOpen && createPortal(
        // Portalled to <body>: the header's backdrop blur would otherwise contain the fixed
        // drawer inside the header's own box.
        <div className="topbar-drawer-backdrop" onClick={closeDrawer}>
          <div
            id="topbar-drawer"
            ref={drawerRef}
            className="topbar-drawer"
            role="dialog"
            aria-modal="true"
            aria-label={t("topbar.menu")}
            onClick={(event) => event.stopPropagation()}
          >
            <nav aria-label={t("topbar.primary_navigation")}>
              {/* The same four modes as the wide bar, each with its tasks one tap away. */}
              <ul data-drawer-modes="true">
                {modes.map((mode) => (
                  <li key={mode.id}>
                    <button
                      type="button"
                      data-mode={mode.id}
                      aria-current={mode.id === activeMode ? "page" : undefined}
                      onClick={() => {
                        onOpenMode(mode.id);
                        closeDrawer();
                      }}
                    >
                      <strong>{t(mode.labelKey)}</strong>
                      <small>{mode.tasks.map((task) => t(task.labelKey)).join(" · ")}</small>
                    </button>
                  </li>
                ))}
              </ul>
              {utilities.length > 0 && (
                <ul className="topbar-drawer-utilities" aria-label={t("topbar.utilities")}>
                  {utilities.map((primary) => (
                    <li key={primary.id}>
                      <button
                        type="button"
                        data-utility={primary.id}
                        aria-current={primary.id === activeUtility?.id ? "page" : undefined}
                        onClick={() => {
                          onOpenPrimaryWorkspace(primary.id);
                          closeDrawer();
                        }}
                      >
                        <strong>{t(primary.labelKey)}</strong>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </nav>
          </div>
        </div>,
        document.body,
      )}
      {!drawerNav && (
      <WorkspaceTabs
        idPrefix="workspace-primary"
        label={t("topbar.primary_navigation")}
        tabs={modeTabs}
        // On a utility page no mode is selected; the row keeps one Tab stop.
        activeId={activeMode ?? ""}
        panelId="workspace-primary-content"
        className="workspace-primary-tabs"
        shellRegion="navigation"
        onActivate={(mode) => onOpenMode(mode as ModeId)}
      />
      )}
      {onOpenCommandPalette && (
        <button
          type="button"
          className="topbar-command"
          aria-label={t("topbar.command")}
          title={keyboardHints ? `${t("topbar.command")} (${shortcutLabel})` : t("topbar.command")}
          onClick={onOpenCommandPalette}
          aria-keyshortcuts={keyboardHints ? "Control+K Meta+K" : undefined}
        >
          <Icon name="search" className="topbar-command-icon" />
          {/* Search says so in words wherever there is room (a magnifier alone was unclear). */}
          <span className="topbar-command-label">{widthClass === "wide" ? t("topbar.command") : t("topbar.search")}</span>
          {keyboardHints && <kbd aria-hidden="true">{shortcutLabel}</kbd>}
        </button>
      )}
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
          {/* Live updates: a quiet "Live" while they arrive, the age of the last one when not. */}
          <LiveIndicator t={t} />
          {/* Said while figures on screen are a kept result being recomputed (meta.view). */}
          <ViewFreshnessNote t={t} />
          {/* One data-status chip; the store, the push connection and the source counts
              are in the panel it opens, not on the bar a trader reads all day. */}
          <TopBarStatus
            t={t}
            health={dataHealth(sourceSummary, dataPlaneState(dataStatus), loading)}
            sourceSummary={sourceSummary}
            storeState={dataPlaneState(dataStatus)}
            storeLabel={t(runtimeDataAvailabilityLabelKey(runtimeAvailability))}
            storeDetail={t("data.runtime_detail")}
            streamingActive={streamingActive}
            marketLastUpdatedAtUtc={marketLastUpdatedAtUtc}
            showSourceCounts={compositionSeesAdministration(composition)}
            simulatedPrices={simulatedPrices}
            staleFigures={seesCommercial ? deskToday.today?.stale_figures ?? [] : []}
            onOpenFigure={openFigure}
            endpointFailures={endpointFailures}
            endpointRetry={endpointRetry}
            onRetry={onRetryEndpoints}
            onOpenDataSources={seesAdministration ? onOpenDataSources : undefined}
            heldSources={heldSources}
            onReportProblem={currentUser ? () =>
              requestProblemReport({
                category: "data",
                severity: "P2",
                summary: t("support.hint_summary", { state: t(runtimeDataAvailabilityLabelKey(runtimeAvailability)) }),
              }) : undefined}
          />
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
                  onOpenHelp={() => onOpenPrimaryWorkspace("system")}
                  onOpenAdministration={seesAdministration ? () => onOpenPrimaryWorkspace("administration") : undefined}
                  onReportProblem={() => requestProblemReport({})}
                  onSendFeedback={() => requestFeedback(resolveComposition(currentUser).composition.id)}
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
