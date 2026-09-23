import { CommandPalette } from "@/components/CommandPalette";
import { InspectorPanel } from "@/components/InspectorPanel";
import { RestrictedSurface } from "@/components/RestrictedSurface";
import { SignInScreen } from "@/components/SignInScreen";
import { WorkspaceTopBar } from "@/components/WorkspaceTopBar";
import type { AppController } from "@/app/hooks/useAppController";
import { useCommandPalette } from "@/app/hooks/useCommandPalette";
import {
  describeEndpointFailures,
  describeEndpointRetry,
} from "@/app/model/endpointFailures";
import {
  compositionFromProfile,
  compositionSeesAdministration,
} from "@/app/experience/experienceProfile";
import type { PaletteCommand } from "@/app/experience/commandPalette";
import { paletteUnavailableReasonKey } from "@/app/experience/commandPalette";
import { isControlPlanePage } from "@/app/navigation/productNavigation";
import { inspectorDetailFor } from "@/app/model/inspectorDetail";
import { useInspectorStore } from "@/stores/inspector";
import { WorkspaceRenderer } from "@/app/workspaces/WorkspaceRenderer";
import { isBlockingCompatibility } from "@/app/releaseCompatibility";
import { changeAppLanguage } from "@/i18n";
import { layoutWorkspacePage } from "@/app/context/viewPreference";

interface AppShellProps {
  controller: AppController;
}

export function AppShell({ controller }: AppShellProps) {
  const {
    t,
    i18n,
    api,
    theme,
    navigation,
    traderContext,
    selection,
    controls,
    portfolio,
    sources,
  } = controller;

  const compatibility = api.releaseCompatibility;
  const blockingCompatibility = compatibility && isBlockingCompatibility(compatibility.state);
  if (blockingCompatibility && compatibility) {
    return (
      <div className="release-compatibility-blocker" role="alert">
        <div className="release-compatibility-card">
          <span className="eyebrow">{t("release.compat_blocked_eyebrow")}</span>
          <h1>{t(compatibility.messageKey)}</h1>
          <p>{t("release.compat_blocked_body")}</p>
          <dl className="release-compatibility-facts">
            <div><dt>{t("release.client_version")}</dt><dd>{compatibility.clientVersion}</dd></div>
            <div><dt>{t("release.server_version")}</dt><dd>{compatibility.serverVersion}</dd></div>
            <div>
              <dt>{t("release.min_supported_client")}</dt>
              <dd>{compatibility.minimumSupportedClient ?? t("release.not_reported")}</dd>
            </div>
            <div>
              <dt>{t("release.api_contract")}</dt>
              <dd>{compatibility.apiContractVersion ?? t("release.not_reported")}</dd>
            </div>
          </dl>
          <button type="button" className="primary-button" onClick={() => window.location.reload()}>
            {t("release.compat_retry")}
          </button>
        </div>
      </div>
    );
  }

  // Authentication-first entry: the terminal, its panels and every protected
  // read stay unmounted until the backend confirms the identity. This holds on
  // reload, on deep links and after history navigation, because the store's
  // authState - not the URL - decides what may mount.
  //
  // The authenticated shell is its own component on purpose: the hooks below
  // used to be called in this body after this return, so the same instance
  // rendered with a hook list that depended on the auth state, and React
  // reported that as `Internal React error: Expected static flag was missing`
  // on the sign-in transition.
  if (api.authState !== "authenticated") {
    return (
      <SignInScreen
        t={t}
        authState={api.authState}
        authStatus={api.authStatus}
        authErrorKey={api.authErrorKey}
        authNoticeKey={api.authNoticeKey}
        authBusy={api.authBusy}
        language={i18n.language}
        onLanguageChange={(language) => void changeAppLanguage(language)}
        onOidcSignIn={() => void api.signIn()}
        onDevLogin={(username, password) => void api.login(username, password)}
        onRetryIdentity={() => void api.bootstrapIdentity()}
      />
    );
  }

  return <AuthenticatedShell controller={controller} />;
}

interface AuthenticatedShellProps {
  controller: AppController;
}

/**
 * The authenticated terminal: one shell for every page, composed only once the
 * backend confirmed the identity. Every hook in this component runs on every
 * render of it (it mounts when the gate opens and unmounts when it closes), so
 * the sign-in transition changes which component is mounted rather than the
 * number of hooks one component calls.
 */
function AuthenticatedShell({ controller }: AuthenticatedShellProps) {
  const {
    t,
    i18n,
    api,
    theme,
    navigation,
    marketView,
    traderContext,
    selection,
    controls,
    portfolio,
    sources,
  } = controller;

  // The one bounded failure surface. Loader keys and backend messages stay in
  // the store: only translated endpoint labels, safe failure codes and one
  // "showing N of M" summary are rendered, so the banner cannot leak internals
  // and cannot grow past five detail rows however much fails.
  const endpointFailures = describeEndpointFailures(api.endpointErrors, api.endpointErrorCodes, t);
  const endpointRetry = describeEndpointRetry(
    {
      busy: api.endpointRetryBusy,
      attempts: api.endpointRetryAttempts,
      lastAttemptAtUtc: api.endpointRetryLastAttemptAtUtc,
    },
    t,
  );

  // Architecture V2 control-plane boundary: a page that belongs to the
  // administration surface is refused for an identity without an administration
  // capability, instead of mounting a surface whose requests the backend will
  // reject. Navigation is not a security boundary; this is honest presentation.
  const composition = compositionFromProfile(api.currentUser?.experience);
  const controlPlaneRestricted =
    isControlPlanePage(navigation.activeWorkspace) &&
    !compositionSeesAdministration(composition);

  // The layout class names the page whose layout is on screen, not only the page the URL named:
  // the market primary resolves a task inside its own shell, so the map task - chosen by tab, by
  // deep link or by the persisted view - has to bring the `.workspace-network` rules with it.
  // Keying the class on the URL alone left the map column unsized and its stage hidden.
  const layoutPage = layoutWorkspacePage({
    activeWorkspace: navigation.activeWorkspace,
    task: marketView.task,
  });

  // Wave 9 shell surfaces: the canonical Inspector (object detail in one place)
  // and the command palette (one keyboard entry point to the derived command set).
  const inspector = useInspectorStore();
  const palette = useCommandPalette({
    activeWorkspace: navigation.activeWorkspace,
    context: {
      routeId: selection.routeId,
      resourceId: selection.resourceId,
      strategyVersionId: selection.strategyVersionId,
      strategyRunId: selection.strategyRunId,
    },
    capabilities: composition.effectiveCapabilities,
    activeContextComplete: Boolean(composition.available),
    labels: (command: PaletteCommand) => t(command.labelKey),
    onNavigate: (command: PaletteCommand) => {
      const page = command.target.page;
      if (page) navigation.openWorkspace(page);
    },
    onInspect: (kind, ref) =>
      inspector.open({
        kind,
        ref,
        label: ref,
        originPage: navigation.activeWorkspace,
      }),
    onUtility: (utility) => {
      if (utility === "access-identity") navigation.openWorkspace("access");
      else void api.signOut();
    },
  });

  return (
    <div className={`app cockpit-app workspace-${layoutPage}`}>
      <WorkspaceTopBar
        activeWorkspace={navigation.activeWorkspace}
        activePrimaryWorkspace={navigation.activePrimaryWorkspace}
        searchTerm={controls.searchTerm}
        dataStatus={api.dataStatus}
        loading={api.loading}
        streamingActive={api.streamingActive}
        language={i18n.language}
        mode={theme.mode}
        gasDay={traderContext.gasDay}
        deliveryProduct={traderContext.deliveryProduct}
        hubId={traderContext.hubId}
        marketLastUpdatedAtUtc={api.marketLastUpdatedAtUtc}
        sourceStats={sources.sourceStats}
        sourceEndpointError={api.endpointErrors.sources}
        currentUser={api.currentUser}
        monitoring={api}
        t={t}
        onSearchTermChange={controls.setSearchTerm}
        onGasDayChange={traderContext.setGasDay}
        onDeliveryProductChange={traderContext.setDeliveryProduct}
        onHubChange={traderContext.setHubId}
        onOpenPrimaryWorkspace={navigation.openPrimaryWorkspace}
        onSignIn={() => void api.signIn()}
        onSignOut={() => void api.signOut()}
        onOpenAccess={() => navigation.openWorkspace("access")}
        onOpenSettings={() => navigation.openWorkspace("settings")}
        onLanguageChange={(language) => void changeAppLanguage(language)}
        onModeChange={theme.setMode}
      />

      {endpointFailures.total > 0 && (
        <div
          className="endpoint-error-banner"
          role="status"
          aria-live="polite"
          aria-busy={endpointRetry.busy}
        >
          <div className="endpoint-error-summary">
            <span className="endpoint-error-eyebrow">{t("workspace.partial_load")}</span>
            <strong>{endpointFailures.summary}</strong>
            <ul className="endpoint-error-detail-list">
              {endpointFailures.entries.map((entry) => (
                <li className="endpoint-error-detail" key={entry.key}>
                  <span className="endpoint-error-detail-label">{entry.label}</span>
                  <code className="endpoint-error-detail-code">{entry.code}</code>
                  <span className="endpoint-error-detail-message">{entry.message}</span>
                </li>
              ))}
            </ul>
            {endpointFailures.truncatedSummary && (
              <p className="endpoint-error-overflow">{endpointFailures.truncatedSummary}</p>
            )}
          </div>
          <div className="endpoint-error-actions">
            <button
              type="button"
              disabled={endpointRetry.disabled}
              aria-busy={endpointRetry.busy}
              onClick={() => void api.retryFailedWorkspaceEndpoints()}
            >
              {t("workspace.retry_failed")}
            </button>
            <span className="endpoint-error-retry-meta">
              {endpointRetry.attemptsLabel}
              {endpointRetry.lastAttemptLabel ? ` · ${endpointRetry.lastAttemptLabel}` : ""}
              {endpointRetry.runningLabel ? ` · ${endpointRetry.runningLabel}` : ""}
            </span>
          </div>
        </div>
      )}

      <main className="app-main" id="workspace-primary-content" data-shell-region="primary-workspace">
        {/* One composition path for every page: the shell owns the regions, the workspace
            composition owns its pages. The map-first network route used to be intercepted
            here, which meant its surface was mounted outside the registry that declares it;
            it is now composed by the market primary like every other page of that primary
            (conflicting register C9). */}
        {controlPlaneRestricted ? <RestrictedSurface t={t} /> : <WorkspaceRenderer controller={controller} />}
      </main>

      {inspector.subject && (
        <InspectorPanel
          subject={inspector.subject}
          detail={inspectorDetailFor(api, inspector.subject)}
          canGoBack={inspector.history.length > 0}
          t={t}
          onClose={inspector.close}
          onBack={inspector.back}
        />
      )}

      <CommandPalette
        open={palette.open}
        query={palette.query}
        results={palette.results}
        activeIndex={palette.activeIndex}
        unavailable={palette.unavailable}
        labelFor={(command) => t(command.labelKey)}
        reasonFor={(command) => paletteUnavailableReasonKey(command, palette.availability)}
        t={t}
        onQueryChange={palette.setQuery}
        onMove={palette.move}
        onRunActive={palette.runActive}
        onRun={palette.run}
        onClose={() => palette.setOpen(false)}
      />
    </div>
  );
}
