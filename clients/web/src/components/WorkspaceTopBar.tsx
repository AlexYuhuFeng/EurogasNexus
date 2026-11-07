import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { showsKeyboardHints, useShellLayout } from "@/app/shell/useShellLayout";
import { needsCommercialWorkspaceReads } from "@/stores/workspaceReadScope";
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
import { useApiStore, type ApiState } from "@/stores/api";
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
import { TopBarStatus, dataHealth } from "./TopBarStatus";
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
  marketLastUpdatedAtUtc,
  sourceStats,
  sourceEndpointError,
  currentUser,
  monitoring,
  t,
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
      {drawerNav && (
        <button
          ref={menuButtonRef}
          type="button"
          className="topbar-menu-button"
          aria-expanded={drawerOpen}
          aria-controls="topbar-drawer"
          aria-label={t("topbar.menu")}
          // The Active Context in machine-readable form, as on the wide bar's disclosure.
          onClick={() => setDrawerOpen((open) => !open)}
        >
          <svg aria-hidden="true" width="18" height="18" viewBox="0 0 18 18"><path d="M2 4h14M2 9h14M2 14h14" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" /></svg>
          <span className="topbar-menu-label">
            <span>{t(activePrimaryWorkspace.labelKey)}</span>
          </span>
        </button>
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
              <ul>
                {visiblePrimaries.map((primary) => (
                  <li key={primary.id}>
                    <button
                      type="button"
                      aria-current={primary.id === activePrimaryWorkspace.id ? "page" : undefined}
                      onClick={() => {
                        onOpenPrimaryWorkspace(primary.id);
                        closeDrawer();
                      }}
                    >
                      <strong>{t(primary.labelKey)}</strong>
                      <small>{t(primary.descriptionKey)}</small>
                    </button>
                  </li>
                ))}
              </ul>
            </nav>
          </div>
        </div>,
        document.body,
      )}
      {!drawerNav && (
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
      )}
      {onOpenCommandPalette && (
        <button
          type="button"
          className="topbar-command"
          aria-label={t("topbar.command")}
          onClick={onOpenCommandPalette}
          aria-keyshortcuts={keyboardHints ? "Control+K Meta+K" : undefined}
        >
          <svg className="topbar-command-icon" aria-hidden="true" width="16" height="16" viewBox="0 0 18 18"><circle cx="8" cy="8" r="5.2" fill="none" stroke="currentColor" strokeWidth="1.6" /><path d="M12 12l4 4" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" /></svg>
          {!compact && (
          <>
          <span>{t("topbar.command")}</span>
          {keyboardHints && <kbd aria-hidden="true">{/Mac|iPhone|iPad/.test(globalThis.navigator?.platform ?? "") ? "⌘K" : "Ctrl K"}</kbd>}
          </>
          )}
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
            demoPrices={useApiStore((state) => state.runtimeRelease?.demo_marks === true)}
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
