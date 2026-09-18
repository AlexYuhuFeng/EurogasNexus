import type { AppController } from "@/app/hooks/useAppController";
import { changeAppLanguage } from "@/i18n";
import { AccessCenter } from "@/components/AccessCenter";
import { AgentsWorkspace } from "@/components/AgentsWorkspace";
import { primaryWorkspaceForPage } from "@/app/navigation/productNavigation";
import { headerModeForPage } from "@/app/experience/workspacePatterns";
import { sourceRunReadiness, sourceRunReason } from "@/app/model/sourceRunModel";
import { WorkspaceTabs } from "@/components/ui";
import type { WorkspacePageId } from "@/workspaceNavigation";
import { GlossaryWiki } from "@/components/GlossaryWiki";
import { ManualWorkspace } from "@/components/ManualWorkspace";
import { MarketPositioningWorkspace } from "@/components/MarketPositioningWorkspace";
import { MarketCockpit } from "@/components/MarketCockpit";
import { PortfolioWorkspace } from "@/components/PortfolioWorkspace";
import { DecisionWorkspace } from "@/components/DecisionWorkspace";
import { ReviewWorkspace } from "@/components/ReviewWorkspace";
import { RuntimeWorkspace } from "@/components/RuntimeWorkspace";
import { ResearchDataWorkspace } from "@/components/ResearchDataWorkspace";
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
    locationRevision: navigation.locationRevision,
    selection: {
      strategyId: selection.strategyId,
      strategyVersionId: selection.strategyVersionId,
      strategyRunId: selection.strategyRunId,
      setStrategyId: selection.setStrategyId,
      setStrategyVersionId: selection.setStrategyVersionId,
      setStrategyRunId: selection.setStrategyRunId,
    },
  });
  // Header composition is read from the Architecture V2 workspace-pattern
  // registry instead of a local list of primary ids, so the composition rule has
  // exactly one owner (docs/engineering/Architecture-V2/W1-02_*.md).
  const usesConsolidatedHeader = headerModeForPage(activeWorkspace) === "consolidated";
  const localTabs = usesConsolidatedHeader
    ? []
    : activePrimaryWorkspace.pages.map((page) => ({
        id: page,
        label: t(`nav.${page}`),
      }));

  return (
    <section
      className="workspace-page"
      id="workspace-active-panel"
      aria-label={`${t("app.title")} — ${t(activePrimaryWorkspace.labelKey)}`}
    >
      {!usesConsolidatedHeader && (
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
      )}

      {activePrimaryWorkspace.id === "market" && (
        <MarketCockpit controller={controller} />
      )}

      {activePrimaryWorkspace.id === "portfolio" && (
        <PortfolioWorkspace controller={controller} />
      )}

      {activePrimaryWorkspace.id === "decision" && (
        <DecisionWorkspace controller={controller} />
      )}

      {activePrimaryWorkspace.id === "strategy" && (
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
          // Wave 4/8: the source surface recommended an ingestion run it had no way to start. The
          // route queues a MANUAL run for the dataops worker; the rule that decides whether the
          // control is offered - and what the platform's guards are doing - lives in
          // `app/model/sourceRunModel.ts`.
          runtimeDbReady={
            api.runtimeDb?.database_url_present === true && api.runtimeDb.connectivity.ok
          }
          runReadiness={sourceRunReadiness({
            subject: sources.selectedSource
              ? {
                  sourceId: sources.selectedSource.source_id,
                  sourceSystem: sources.selectedSource.source_system,
                  schedulerEnabled: sources.selectedSource.scheduler_enabled,
                  workflowReady: sources.selectedSource.workflow_ready,
                  credentialState: sources.selectedSource.credential_state,
                  connectivityStatus: sources.selectedSource.connectivity_status,
                  circuitState: sources.selectedSource.circuit_state,
                  consecutiveFailures: sources.selectedSource.consecutive_failures,
                  lastIngestionStatus: sources.selectedSource.last_ingestion_status,
                }
              : null,
            runtimeDbReady:
              api.runtimeDb?.database_url_present === true && api.runtimeDb.connectivity.ok,
            running: false,
          })}
          sourceRunOutcome={api.sourceRunOutcome}
          onRequestSourceRun={() => {
            const source = sources.selectedSource;
            if (!source) return;
            void api.requestSourceRun(
              source.source_id,
              sourceRunReason({
                sourceId: source.source_id,
                sourceSystem: source.source_system,
                schedulerEnabled: source.scheduler_enabled,
                workflowReady: source.workflow_ready,
                credentialState: source.credential_state,
                connectivityStatus: source.connectivity_status,
                circuitState: source.circuit_state,
                consecutiveFailures: source.consecutive_failures,
                lastIngestionStatus: source.last_ingestion_status,
              }),
            );
          }}
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

      {activeWorkspace === "access" && (
        <AccessCenter currentUser={api.currentUser} t={t} />
      )}

      {activeWorkspace === "research" && (
        <ResearchDataWorkspace t={t} />
      )}

      {activeWorkspace === "agents" && (
        <AgentsWorkspace
          t={t}
          principalId={api.currentUser?.principal_id ?? null}
          // A research run persists its own rows, so the route refuses it with 503 until the
          // runtime database is configured and reachable. The action is gated on the same
          // fact the portfolio optimiser uses instead of being offered and then failing.
          runtimeDbReady={
            api.runtimeDb?.database_url_present === true && api.runtimeDb.connectivity.ok
          }
        />
      )}

      {activeWorkspace === "runtime" && (
        <RuntimeWorkspace
          meta={api.meta}
          runtimeDb={api.runtimeDb}
          pipelineHealth={api.pipelineHealth}
          runtimeDependencies={api.runtimeDependencies}
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
          principalId={api.currentUser?.principal_id ?? null}
          dataStatus={api.dataStatus}
          runtimeDb={api.runtimeDb}
          runtimeRelease={api.runtimeRelease}
          releaseCompatibility={api.releaseCompatibility}
          sources={api.sources}
          credentialProviders={api.credentialProviders}
          counts={{ nodes: api.nodes.length, edges: api.edges.length, routes: api.routes.length }}
          onLanguageChange={(language) => void changeAppLanguage(language)}
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
