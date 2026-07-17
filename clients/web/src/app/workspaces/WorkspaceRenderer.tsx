import type { AppController } from "@/app/hooks/useAppController";
import { CapacityWorkspace } from "@/components/CapacityWorkspace";
import { ContractWorkbench } from "@/components/ContractWorkbench";
import { GlossaryWiki } from "@/components/GlossaryWiki";
import { ManualWorkspace } from "@/components/ManualWorkspace";
import { MarketPositioningWorkspace } from "@/components/MarketPositioningWorkspace";
import { MarketTerminal } from "@/components/MarketTerminal";
import { ReviewWorkspace } from "@/components/ReviewWorkspace";
import { RuntimeWorkspace } from "@/components/RuntimeWorkspace";
import { ScenarioWorkspace } from "@/components/ScenarioWorkspace";
import { SettingsCenter } from "@/components/SettingsCenter";
import { SourceCenter } from "@/components/SourceCenter";
import { StrategyShadowRunTerminal } from "@/components/StrategyShadowRunTerminal";

interface WorkspaceRendererProps {
  controller: AppController;
}

export function WorkspaceRenderer({ controller }: WorkspaceRendererProps) {
  const {
    t,
    i18n,
    api,
    theme,
    navigation,
    controls,
    contractEditor,
    portfolio,
    review,
    glossary,
    sources,
  } = controller;
  const activeWorkspace = navigation.activeWorkspace;

  return (
    <section className="workspace-page" aria-label={t(`nav.${activeWorkspace}`)}>
      <div className="workspace-page-header">
        <div>
          <span className="eyebrow">{t("app.title")}</span>
          <h1>{t(`nav.${activeWorkspace}`)}</h1>
        </div>
        <span className={`status-badge status-${api.dataStatus}`}>{t(`data.${api.dataStatus}`)}</span>
      </div>

      {activeWorkspace === "capacity" && (
        <CapacityWorkspace
          flows={api.flows}
          capacity={api.capacity}
          tsoAccess={api.tsoAccess}
          tsoTariffs={api.tsoTariffs}
          storage={api.storage}
          lng={api.lng}
          t={t}
        />
      )}

      {activeWorkspace === "market" && (
        <MarketTerminal
          markets={portfolio.contextMarkets}
          fxRates={api.fxRates}
          sources={api.sources}
          lastUpdatedAtUtc={api.marketLastUpdatedAtUtc}
          onRefresh={api.refreshMarketData}
          t={t}
        />
      )}

      {activeWorkspace === "contracts" && (
        <ContractWorkbench
          contract={contractEditor.contract}
          contractPayload={contractEditor.contractPayload}
          upstreamContracts={api.upstreamContracts}
          portfolioResources={portfolio.portfolioResources}
          totalPoolVolume={portfolio.totalPoolVolume}
          firstPoolAllocation={portfolio.firstPoolAllocation}
          runtimeDbReady={portfolio.runtimeDbReady}
          loading={api.loading}
          contractImportRef={contractEditor.contractImportRef}
          contractImportMessage={contractEditor.contractImportMessage}
          contractSaveMessage={api.contractSaveMessage}
          t={t}
          updateContractText={contractEditor.updateContractText}
          updateContractNumber={contractEditor.updateContractNumber}
          saveDraftContract={api.saveDraftContract}
          resetContractDraft={contractEditor.resetContractDraft}
          importContractDraftFile={contractEditor.importContractDraftFile}
          loadPersistedContract={contractEditor.loadPersistedContract}
        />
      )}

      {activeWorkspace === "scenario" && (
        <ScenarioWorkspace
          routeCandidates={api.routeCandidates}
          purchasePrice={portfolio.purchasePrice}
          salePrice={portfolio.salePrice}
          routeCharge={portfolio.routeCharge}
          routeRecommendation={api.routeRecommendation}
          contract={contractEditor.contract}
          canRunPoolOptimizer={portfolio.canRunPoolOptimizer}
          canCompareRoutes={portfolio.hasPortfolioResources && portfolio.saleOptions.length > 0}
          poolInputBlockers={portfolio.poolInputBlockers}
          resourcePoolResult={api.resourcePoolResult}
          saleOptionById={portfolio.saleOptionById}
          t={t}
          updateContractNumber={contractEditor.updateContractNumber}
          onOptimize={() => api.optimizeResourcePool(portfolio.resourcePoolOptimizationRequest)}
          onCompare={() => api.recommendRouteAllocation(portfolio.routeRecommendationRequest)}
        />
      )}

      {activeWorkspace === "strategy" && (
        <StrategyShadowRunTerminal
          strategyScenario={portfolio.strategyScenario}
          strategyResult={api.strategyResult}
          portfolioResources={portfolio.portfolioResources}
          marketObservations={portfolio.contextMarkets}
          fxRates={api.fxRates}
          language={i18n.language}
          loading={api.loading}
          t={t}
          onEvaluate={() => api.evaluateStrategyLab(portfolio.strategyScenario)}
        />
      )}

      {activeWorkspace === "review" && (
        <ReviewWorkspace
          allocations={portfolio.poolAllocations}
          saleOptionById={portfolio.saleOptionById}
          reviewWarnings={portfolio.reviewWarnings}
          analysisQuestion={review.analysisQuestion}
          invokeDeepSeek={review.invokeDeepSeek}
          analysisResult={api.analysisResult}
          language={i18n.language}
          t={t}
          onAnalysisQuestionChange={review.setAnalysisQuestion}
          onInvokeDeepSeekChange={review.setInvokeDeepSeek}
          onAnalyze={() => api.askAnalysis(review.analysisPayload)}
          onGenerateReport={() => api.generatePortfolioReport(review.analysisPayload)}
        />
      )}

      {activeWorkspace === "orders" && (
        <MarketPositioningWorkspace
          portfolioSummary={api.portfolioSummary}
          screenOrders={api.screenOrders}
          pnlSnapshots={api.pnlSnapshots}
          formatTimestamp={sources.formatSourceTimestamp}
          t={t}
        />
      )}

      {activeWorkspace === "sources" && (
        <SourceCenter
          t={t}
          sources={api.sources}
          sourceCategories={sources.sourceCategories}
          sourceCategory={sources.sourceCategory}
          sourceCategoryCounts={sources.sourceCategoryCounts}
          sourceStats={sources.sourceStats}
          sourcePostureRows={sources.sourcePostureRows}
          filteredSources={sources.filteredSources}
          selectedSource={sources.selectedSource}
          selectedCredentialProvider={sources.selectedCredentialProvider}
          selectedSourceCredentialProvider={sources.selectedSourceCredentialProvider}
          credentialProviders={api.credentialProviders}
          credentialProvider={sources.credentialProvider}
          credentialLabel={sources.credentialLabel}
          credentialValue={sources.credentialValue}
          credentialMessage={api.credentialMessage}
          flows={api.flows}
          capacity={api.capacity}
          storage={api.storage}
          lng={api.lng}
          tsoAccessCount={api.tsoAccess.length}
          tsoTariffs={api.tsoTariffs}
          latestCapacityRows={portfolio.latestCapacityRows}
          onSourceCategoryChange={sources.selectSourceCategory}
          onSourceSelect={sources.selectSource}
          onCredentialProviderChange={sources.setCredentialProvider}
          onCredentialLabelChange={sources.setCredentialLabel}
          onCredentialValueChange={sources.setCredentialValue}
          onCredentialSubmit={sources.submitCredential}
          sourceLabel={sources.sourceLabel}
          categoryProviderSummary={sources.categoryProviderSummary}
          sourceNextAction={sources.sourceNextAction}
          formatSourceTimestamp={sources.formatSourceTimestamp}
        />
      )}

      {activeWorkspace === "glossary" && (
        <GlossaryWiki
          terms={glossary.terms}
          context={api.glossaryContext}
          selectedTerm={glossary.selectedTermRecord}
          categories={glossary.categories}
          activeCategory={glossary.category}
          query={glossary.query}
          language={i18n.language}
          durationStart={glossary.durationStart}
          durationEnd={glossary.durationEnd}
          shortcutTerms={glossary.shortcutTerms}
          loading={api.loading}
          t={t}
          onCategoryChange={glossary.setCategory}
          onQueryChange={glossary.setQuery}
          onDurationStartChange={glossary.setDurationStart}
          onDurationEndChange={glossary.setDurationEnd}
          onSelectTerm={glossary.selectTerm}
          onOpenContext={glossary.openContext}
          formatContextValue={glossary.formatContextValue}
        />
      )}

      {activeWorkspace === "runtime" && (
        <RuntimeWorkspace meta={api.meta} runtimeDb={api.runtimeDb} t={t} />
      )}

      {activeWorkspace === "settings" && (
        <SettingsCenter
          t={t}
          language={i18n.language}
          mode={theme.mode}
          dataStatus={api.dataStatus}
          runtimeDb={api.runtimeDb}
          sources={api.sources}
          credentialProviders={api.credentialProviders}
          counts={{ nodes: api.nodes.length, edges: api.edges.length, routes: api.routes.length }}
          onLanguageChange={(language) => void i18n.changeLanguage(language)}
          onModeChange={theme.setMode}
          onOpenSources={() => navigation.openWorkspace("sources")}
          onBackendBaseChanged={api.fetchWorkspace}
        />
      )}

      {activeWorkspace === "manual" && (
        <ManualWorkspace
          runtimeDb={api.runtimeDb}
          activeSourceCount={sources.sourceStats.active}
          tariffCount={api.tsoTariffs.length}
          openOrderCount={api.portfolioSummary?.open_order_count ?? api.screenOrders.length}
          t={t}
        />
      )}
    </section>
  );
}
