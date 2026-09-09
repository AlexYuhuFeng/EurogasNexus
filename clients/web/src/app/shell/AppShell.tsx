import { NetworkWorkspace } from "@/components/NetworkWorkspace";
import { WorkspaceTopBar } from "@/components/WorkspaceTopBar";
import type { AppController } from "@/app/hooks/useAppController";
import { WorkspaceRenderer } from "@/app/workspaces/WorkspaceRenderer";
import { isBlockingCompatibility } from "@/app/releaseCompatibility";

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
        onLanguageChange={(language) => void i18n.changeLanguage(language)}
        onModeChange={theme.setMode}
        onGasDayChange={traderContext.setGasDay}
        onDeliveryProductChange={traderContext.setDeliveryProduct}
        onHubChange={traderContext.setHubId}
        onOpenPrimaryWorkspace={navigation.openPrimaryWorkspace}
        onSignIn={() => void api.signIn()}
        onSignOut={() => void api.signOut()}
        onOpenAccess={() => navigation.openWorkspace("access")}
      />

      {Object.keys(api.endpointErrors).length > 0 && (
        <div className="endpoint-error-banner" role="status" aria-live="polite">
          <span>{t("workspace.partial_load")}</span>
          <strong>
            {t("workspace.failed_endpoints")}: {Object.keys(api.endpointErrors).join(", ")}
          </strong>
          <button type="button" onClick={() => void api.retryFailedWorkspaceEndpoints()}>
            {t("workspace.retry_failed")}
          </button>
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
            gasDay={traderContext.gasDay}
            deliveryProduct={traderContext.deliveryProduct}
            hubId={traderContext.hubId}
            marketLastUpdatedAtUtc={api.marketLastUpdatedAtUtc}
            intradayOpportunities={api.intradayOpportunities}
            sourceStats={sources.sourceStats}
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
