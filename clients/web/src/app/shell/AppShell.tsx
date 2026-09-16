import { NetworkWorkspace } from "@/components/NetworkWorkspace";
import { SignInScreen } from "@/components/SignInScreen";
import { WorkspaceTopBar } from "@/components/WorkspaceTopBar";
import type { AppController } from "@/app/hooks/useAppController";
import {
  describeEndpointFailures,
  describeEndpointRetry,
} from "@/app/model/endpointFailures";
import { WorkspaceRenderer } from "@/app/workspaces/WorkspaceRenderer";
import { isBlockingCompatibility } from "@/app/releaseCompatibility";
import { changeAppLanguage } from "@/i18n";

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

  return (
    <div className={`app cockpit-app workspace-${navigation.activeWorkspace}`}>
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

      <main className="app-main" id="workspace-primary-content">
        {navigation.activeWorkspace === "network" ? (
          <NetworkWorkspace
            t={t}
            nodes={api.nodes}
            edges={api.edges}
            routes={api.routes}
            mode={theme.mode}
            activeLayers={controls.activeLayers}
            searchTerm={controls.searchTerm}
            highlightedRoute={portfolio.highlightedRoute}
            resourcePoolMapPaths={portfolio.resourcePoolMapPaths}
            poolInputBlockers={portfolio.poolInputBlockers}
            commercialDiagnostics={portfolio.commercialDiagnostics}
            error={api.error}
            loading={api.loading}
            saleOptions={portfolio.saleOptions}
            canRunPoolOptimizer={portfolio.canRunPoolOptimizer}
            portfolioResources={portfolio.portfolioResources}
            totalPoolVolume={portfolio.totalPoolVolume}
            portfolioSummary={api.portfolioSummary}
            screenOrderCount={api.screenOrders.length}
            upstreamContractCount={api.upstreamContracts.length}
            networkGeometryState={portfolio.networkGeometryState}
            routeRecommendation={api.routeRecommendation}
            decisionPnl={portfolio.decisionPnl}
            resourcePoolResult={api.resourcePoolResult}
            poolAllocations={portfolio.poolAllocations}
            saleOptionById={portfolio.saleOptionById}
            hasPortfolioResources={portfolio.hasPortfolioResources}
            selectedAllocation={portfolio.selectedAllocation}
            purchasePrice={portfolio.purchasePrice}
            salePrice={portfolio.salePrice}
            routeCharge={portfolio.routeCharge}
            firstPoolAllocation={portfolio.firstPoolAllocation}
            firstStrategyTarget={portfolio.firstStrategyTarget}
            strategyResult={api.strategyResult}
            activeWarning={portfolio.activeWarning}
            reviewEvidenceItems={portfolio.reviewEvidenceItems}
            marketLastUpdatedAtUtc={api.marketLastUpdatedAtUtc}
            intradayOpportunities={api.intradayOpportunities}
            optimizerContextMismatch={portfolio.optimizerContextMismatch}
            onResetSearch={() => controls.setSearchTerm("")}
            onToggleLayer={controls.toggleLayer}
            onOptimizePool={portfolio.optimizeResourcePoolForCurrentContext}
            onOpenReview={() => navigation.openWorkspace("review")}
            onOpenScenario={() => {
              const routeId =
                portfolio.selectedAllocation?.route_id ??
                portfolio.highlightedRoute?.routeId ??
                null;
              if (routeId) selection.setRouteId(routeId);
              navigation.openWorkspace("scenario");
            }}
          />
        ) : (
          <WorkspaceRenderer controller={controller} />
        )}
      </main>
    </div>
  );
}
