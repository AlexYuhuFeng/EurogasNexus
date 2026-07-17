import { NetworkWorkspace } from "@/components/NetworkWorkspace";
import { WorkspaceTopBar } from "@/components/WorkspaceTopBar";
import type { AppController } from "@/app/hooks/useAppController";
import { WorkspaceRenderer } from "@/app/workspaces/WorkspaceRenderer";

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
    controls,
    portfolio,
    sources,
  } = controller;

  return (
    <div className={`app cockpit-app workspace-${navigation.activeWorkspace}`}>
      <WorkspaceTopBar
        activeWorkspace={navigation.activeWorkspace}
        searchTerm={controls.searchTerm}
        dataStatus={api.dataStatus}
        loading={api.loading}
        language={i18n.language}
        mode={theme.mode}
        gasDay={controls.gasDay}
        deliveryProduct={controls.deliveryProduct}
        marketLastUpdatedAtUtc={api.marketLastUpdatedAtUtc}
        sourceIssueCount={sources.sourceStats.issues}
        t={t}
        onSearchTermChange={controls.setSearchTerm}
        onLanguageChange={(language) => void i18n.changeLanguage(language)}
        onModeChange={theme.setMode}
        onGasDayChange={controls.setGasDay}
        onDeliveryProductChange={controls.setDeliveryProduct}
      />

      <main className="app-main">
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
          gasDay={controls.gasDay}
          deliveryProduct={controls.deliveryProduct}
          marketLastUpdatedAtUtc={api.marketLastUpdatedAtUtc}
          sourceStats={sources.sourceStats}
          onResetSearch={() => controls.setSearchTerm("")}
          onToggleLayer={controls.toggleLayer}
          onOptimizePool={() => api.optimizeResourcePool(portfolio.resourcePoolOptimizationRequest)}
          onOpenReview={() => navigation.openWorkspace("review")}
        />
        <WorkspaceRenderer controller={controller} />
      </main>
    </div>
  );
}
