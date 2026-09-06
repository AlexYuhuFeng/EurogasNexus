import type { AppController } from "@/app/hooks/useAppController";
import { primaryWorkspaceForPage } from "@/app/navigation/productNavigation";
import { WorkspaceTabs } from "@/components/ui";
import type { WorkspacePageId } from "@/workspaceNavigation";
import { ContractWorkbench } from "@/components/ContractWorkbench";
import { GlossaryWiki } from "@/components/GlossaryWiki";
import { ManualWorkspace } from "@/components/ManualWorkspace";
import { MarketPositioningWorkspace } from "@/components/MarketPositioningWorkspace";
import { MarketCockpit } from "@/components/MarketCockpit";
import { ReviewWorkspace } from "@/components/ReviewWorkspace";
import { RuntimeWorkspace } from "@/components/RuntimeWorkspace";
import { ScenarioWorkspace } from "@/components/ScenarioWorkspace";
import { SettingsCenter } from "@/components/SettingsCenter";
import { SourceCenter } from "@/components/SourceCenter";
import { StrategyLabWorkspace } from "@/components/strategy/StrategyLabWorkspace";
import { useStrategyLab } from "@/app/model/useStrategyLab";

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
    traderContext,
    selection,
    controls,
    contractEditor,
    portfolio,
    review,
    glossary,
    sources,
  } = controller;
  const activeWorkspace = navigation.activeWorkspace;
  const activePrimaryWorkspace = primaryWorkspaceForPage(activeWorkspace);
  const strategyLab = useStrategyLab({
    gasDay: traderContext.gasDay,
    selection: {
      strategyId: selection.strategyId,
      strategyVersionId: selection.strategyVersionId,
      strategyRunId: selection.strategyRunId,
      setStrategyId: selection.setStrategyId,
      setStrategyVersionId: selection.setStrategyVersionId,
      setStrategyRunId: selection.setStrategyRunId,
    },
  });
  const localTabs = activePrimaryWorkspace.id === "market"
    ? []
    : activePrimaryWorkspace.pages.map((page) => ({
        id: page,
        label: t(`nav.${page}`),
      }));

  return (
    <section
      className="workspace-page"
      id="workspace-active-panel"
      aria-label={t(`nav.${activeWorkspace}`)}
    >
      <header className="workspace-page-header">
        <div className="workspace-page-heading">
          <span className="eyebrow">{t(activePrimaryWorkspace.labelKey)}</span>
          <h1>{t(`nav.${activeWorkspace}`)}</h1>
        </div>
        {localTabs.length > 1 && (
          <WorkspaceTabs
            idPrefix={`${activePrimaryWorkspace.id}-task`}
            label={t(activePrimaryWorkspace.labelKey)}
            tabs={localTabs}
            activeId={activeWorkspace}
            panelId="workspace-active-panel"
            className="workspace-page-tabs"
            onActivate={(page) => navigation.openWorkspace(page as WorkspacePageId)}
          />
        )}
      </header>

      {activePrimaryWorkspace.id === "market" && (
        <MarketCockpit controller={controller} />
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
          selectedResourceId={selection.resourceId}
          onOpenStrategyForResource={(resourceId) => {
            selection.setResourceId(resourceId);
            navigation.openWorkspace("strategy");
          }}
          contractImportRef={contractEditor.contractImportRef}
          contractImportMessage={contractEditor.contractImportMessage}
          contractSaveMessage={api.contractSaveMessage}
          t={t}
          updateContractText={contractEditor.updateContractText}
          updateContractNumber={contractEditor.updateContractNumber}
          updateContractList={contractEditor.updateContractList}
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
          carriedRouteId={selection.routeId}
          contextMismatch={portfolio.routeContextMismatch}
          t={t}
          updateContractNumber={contractEditor.updateContractNumber}
          onOptimize={portfolio.optimizeResourcePoolForCurrentContext}
          onCompare={portfolio.recommendRouteAllocationForCurrentContext}
        />
      )}

      {activeWorkspace === "strategy" && (
        <StrategyLabWorkspace
          controller={strategyLab}
          selection={{
            strategyId: selection.strategyId,
            strategyVersionId: selection.strategyVersionId,
            strategyRunId: selection.strategyRunId,
            setStrategyId: selection.setStrategyId,
            setStrategyVersionId: selection.setStrategyVersionId,
            setStrategyRunId: selection.setStrategyRunId,
          }}
          gasDay={traderContext.gasDay}
          language={i18n.language}
          t={t}
        />
      )}

      {activeWorkspace === "review" && (
        <ReviewWorkspace
          allocations={portfolio.poolAllocations}
          saleOptionById={portfolio.saleOptionById}
          reviewWarnings={portfolio.reviewWarnings}
          resourcePoolResult={api.resourcePoolResult}
          analysisQuestion={review.analysisQuestion}
          invokeDeepSeek={review.invokeDeepSeek}
          analysisResult={api.analysisResult}
          language={i18n.language}
          reviewDecisions={api.reviewDecisions}
          reviewMessage={api.reviewMessage}
          latestStrategyRunId={api.strategyRuns[0]?.run_id ?? null}
          carriedStrategyRunId={selection.strategyRunId}
          t={t}
          onAnalysisQuestionChange={review.setAnalysisQuestion}
          onInvokeDeepSeekChange={review.setInvokeDeepSeek}
          onAnalyze={() => api.askAnalysis(review.analysisPayload)}
          onGenerateReport={() => api.generatePortfolioReport(review.analysisPayload)}
          onRecordDecision={api.recordReviewDecision}
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
          onCredentialConnectionTest={sources.testProviderConnection}
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
        <RuntimeWorkspace
          meta={api.meta}
          runtimeDb={api.runtimeDb}
          pipelineHealth={api.pipelineHealth}
          sources={api.sources}
          streamingActive={api.streamingActive}
          endpointErrors={api.endpointErrors}
          t={t}
          onRefreshHealth={api.refreshMonitoring}
          onOpenSources={() => navigation.openWorkspace("sources")}
        />
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
