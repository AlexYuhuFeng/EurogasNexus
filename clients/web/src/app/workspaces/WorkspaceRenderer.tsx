import { tabLabels } from "@/components/ui/tabLabels";
import type { AppController } from "@/app/hooks/useAppController";
import { AccessCenter } from "@/components/AccessCenter";
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
import { ReportsWorkspace } from "@/components/ReportsWorkspace";
import { CargoStudy } from "@/components/research/CargoStudy";
import { FundamentalsWorkbench } from "@/components/research/FundamentalsWorkbench";
import { SpreadsWorkbench } from "@/components/research/SpreadsWorkbench";
import { pageTaskFromLocation } from "@/app/navigation/modeNavigation";
import { SettingsCenter } from "@/components/SettingsCenter";
import { SourceCenter } from "@/components/SourceCenter";
import { useModeHeader } from "@/app/navigation/useModeHeader";

interface WorkspaceRendererProps {
  controller: AppController;
}

export function WorkspaceRenderer({ controller }: WorkspaceRendererProps) {
  const {
    t,
    i18n,
    api,
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
  // Header composition is read from the Architecture V2 workspace-pattern
  // registry instead of a local list of primary ids, so the composition rule has
  // exactly one owner (docs/engineering/Architecture-V2/W1-02_*.md).
  const usesConsolidatedHeader = headerModeForPage(activeWorkspace) === "consolidated";
  // A page in a mode shows the mode's task row; a utility page (help, settings, administration)
  // keeps its own pages as tabs. Research names Reports, Fundamentals and Cargo & netback in the
  // URL (`task=reports`, `task=fundamentals`, `task=cargo`); Spreads is its first task.
  const researchTask =
    activeWorkspace === "research" && typeof window !== "undefined"
      ? pageTaskFromLocation("research", window.location.search)
      : undefined;
  const mode = useModeHeader(activeWorkspace, researchTask, navigation.openWorkspace, t);
  const localTabs = usesConsolidatedHeader
    ? []
    : mode.title
      ? mode.tabs
      : activePrimaryWorkspace.pages.map((page) => ({
          id: page,
          ...tabLabels(t, `nav.${page}`),
        }));
  const sectionLabel = mode.title ?? t(activePrimaryWorkspace.labelKey);

  // The page's own read lifecycle (`unread | loading | settled`), published so a measurement can
  // judge a surface after its read settled rather than mid-load. It is the batch's state, not
  // `api.loading`, which is also true while an on-demand action runs.
  const workspaceLoadState = api.workspaceLoading
    ? "loading"
    : api.workspaceLoadsCommitted > 0
      ? "settled"
      : "unread";
  return (
    <section
      className="workspace-page"
      id="workspace-active-panel"
      data-workspace-load-state={workspaceLoadState}
      aria-label={`${t("app.title")} — ${sectionLabel}`}
    >
      {!usesConsolidatedHeader && (
        <header className="workspace-page-header">
          <div className="workspace-page-heading">
            {/* One row (UX-04), as on every page: the area is the title, its tasks are the tabs;
                the active task is the selected tab, so its name is read by screen readers only. */}
            <span className="eyebrow visually-hidden">
              {mode.title && mode.activeTask ? t(mode.activeTask.labelKey) : t(`nav.${activeWorkspace}`)}
            </span>
            <h1>{sectionLabel}</h1>
          </div>
          {localTabs.length > 1 && (
            <WorkspaceTabs
              idPrefix={`${mode.modeId ?? activePrimaryWorkspace.id}-task`}
              label={mode.title ? mode.tabLabel : t(activePrimaryWorkspace.labelKey)}
              tabs={localTabs}
              activeId={mode.title ? mode.activeId : activeWorkspace}
              panelId="workspace-active-panel"
              className="workspace-page-tabs"
              onActivate={(id) => (mode.title ? mode.onActivate(id) : navigation.openWorkspace(id as WorkspacePageId))}
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

      {activeWorkspace === "sources" && (
        <SourceCenter
          t={t}
          sources={sources.visibleSources}
          testSourceCount={sources.testSourceCount}
          showTestSources={sources.showTestSources}
          onShowTestSourcesChange={sources.setShowTestSources}
          sourceCategories={sources.sourceCategories}
          sourceCategory={sources.sourceCategory}
          sourceCategoryCounts={sources.sourceCategoryCounts}
          sourceStats={sources.sourceStats}
          sourcePostureRows={sources.sourcePostureRows}
          filteredSources={sources.filteredSources}
          selectedSource={sources.selectedSource}
          missingSourceId={sources.missingSourceId}
          selectedCredentialProvider={sources.selectedCredentialProvider}
          credentialProviders={api.credentialProviders}
          credentialProvider={sources.credentialProvider}
          credentialLabel={sources.credentialLabel}
          credentialValue={sources.credentialValue}
          credentialMessage={api.credentialMessage}
          credentialConnection={sources.credentialConnection}
          credentialEntryReadonly={sources.credentialEntryReadonly}
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
          // The registry read's own state: the surface states pending, failure (with the store's
          // bounded retry) or a measured registry instead of printing counts it does not have.
          registryRead={sources.registryRead}
          onRegistryRetry={sources.retryRegistryRead}
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
          loading={api.workspaceLoading}
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

      {activeWorkspace === "research" && researchTask === "fundamentals" && (
        <FundamentalsWorkbench t={t} language={i18n.language} />
      )}

      {activeWorkspace === "research" && researchTask === "cargo" && <CargoStudy />}
      {activeWorkspace === "research" && researchTask !== "reports" && researchTask !== "fundamentals" && researchTask !== "cargo" && <SpreadsWorkbench />}

      {activeWorkspace === "research" && researchTask === "reports" && (
        <ReportsWorkspace t={t} language={i18n.language} />
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
          principalId={api.currentUser?.principal_id ?? null}
          canManageOrganisation={api.currentUser?.permissions.includes("identity.manage") ?? false}
          dataStatus={api.dataStatus}
          runtimeDb={api.runtimeDb}
          runtimeRelease={api.runtimeRelease}
          releaseCompatibility={api.releaseCompatibility}
          sources={api.sources}
          credentialProviders={api.credentialProviders}
          counts={{ nodes: api.nodes.length, edges: api.edges.length, routes: api.routes.length }}
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
