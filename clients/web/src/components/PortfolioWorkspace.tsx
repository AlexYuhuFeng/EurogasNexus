import { useModeHeader } from "@/app/navigation/useModeHeader";
import { PRODUCT_MODES } from "@/app/navigation/modeNavigation";
import { tradingContextControlsFor } from "@/components/TradingContextControls";
import { useEffect, useMemo, useRef, useState } from "react";
import { useUrlObject } from "@/app/navigation/useUrlView";
import { DataGrid, PanelHeader, WorkspaceHeader } from "@/components/ui";
import { buttonClass } from "@/components/ui/Button";
import { SimulatedScope } from "@/components/ui/SimulatedScope";
import { FirstUseHints } from "@/components/ui/FirstUseHints";
import { FIRST_USE_HINTS } from "@/app/experience/firstUseHints";
import { ContractWorkbench, type ContractTaskView } from "@/components/ContractWorkbench";
import { MarketPositioningWorkspace } from "@/components/MarketPositioningWorkspace";
import { PositionLadderPanel } from "@/components/PositionLadderPanel";
import { TradingBooksPanel } from "@/components/TradingBooksPanel";
import { RiskLimitsPanel } from "@/components/RiskLimitsPanel";
import { DeliveryPerformancePanel } from "@/components/DeliveryPerformancePanel";
import { DailyBalancePanel } from "@/components/DailyBalancePanel";
import { DealHedgeApprovalsPanel } from "@/components/DealHedgeApprovalsPanel";
import { SellDownPanel } from "@/components/SellDownPanel";
import { PortfolioContextStrip } from "@/components/PortfolioContextStrip";
import { TodayFreshness } from "@/components/TodayScreen";
import { useDeskToday } from "@/app/hooks/useDeskToday";
import type { AppController } from "@/app/hooks/useAppController";
import { CommercialWarningList } from "@/components/CommercialWarningList";
import {
  contractSaveState,
  contractViewFacts,
} from "@/app/model/contractDraftModel";
import {
  portfolioTaskFromLocation,
  type PortfolioTask,
} from "@/app/model/commercialWorkflowModel";
import "./commercial-workflow.css";
import { formatMeasure } from "@/app/time/valueFormat";

function money(value: number | null | undefined, suffix = ""): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "n/a";
  return `GBP ${Math.round(value).toLocaleString()}${suffix}`;
}

function PortfolioOverview({ controller }: { controller: AppController }) {
  const { api, portfolio, selection, navigation, t } = controller;
  const resources = portfolio.portfolioResources;
  const totalVolume = portfolio.totalPoolVolume;
  // The pool metrics are statements about the current inputs, so they read the provenanced
  // payload only: a stale result is withheld (n/a) and announced below, never displayed as
  // this context's figures and never substituted with 0.
  const poolResult = portfolio.currentResourcePoolResult;
  const weightedCost = resources.length
    ? resources.reduce(
        (total, resource) =>
          total +
          resource.available_quantity_mwh_per_day *
            (resource.contract_cost_gbp_mwh + (resource.variable_cost_gbp_mwh ?? 0)),
        0,
      ) / Math.max(totalVolume, 1)
    : null;
  const diagnostics = portfolio.commercialDiagnostics;
  const resultsStale =
    portfolio.resultsContextMismatch &&
    (api.resourcePoolResult !== null || api.routeRecommendation !== null);

  return (
    <div className="commercial-overview">
      <section className="commercial-metric-strip" aria-label={t("portfolio.overview")}>
        <span><small>{t("portfolio.scope.quantity")}</small><strong>{totalVolume.toLocaleString()} MWh/d</strong></span>
        <span><small>{t("portfolio.weighted_cost")}</small><strong>{weightedCost === null ? "n/a" : formatMeasure("unit_value", weightedCost, { unit: "GBP/MWh" })}</strong></span>
        {/* Allocation figures exist only after a scenario run; before one, three "n/a" cells
            become one statement (#69). */}
        {poolResult ? (
          <>
            <span><small>{t("portfolio.scope.allocated")}</small><strong>{poolResult.total_allocated_mwh_per_day?.toLocaleString() ?? "n/a"} MWh/d</strong></span>
            <span><small>{t("portfolio.scope.unallocated")}</small><strong>{poolResult.total_unallocated_mwh_per_day?.toLocaleString() ?? "n/a"} MWh/d</strong></span>
            <span><small>{t("portfolio.net_indicative")}</small><strong>{money(poolResult.total_net_pnl_gbp_per_day, "/d")}</strong></span>
          </>
        ) : (
          <span><small>{t("portfolio.scope.allocated")}</small><strong className="muted">{t("portfolio.no_scenario_run")}</strong></span>
        )}
        <span><small>{t("portfolio.warnings")}</small><strong>{diagnostics.length}</strong></span>
      </section>
      {resultsStale && (
        <div className="runtime-blocker-list compact" role="status">
          <strong>{t("context.result_mismatch")}</strong>
          <span>{t("context.result_mismatch_hint")}</span>
        </div>
      )}
      <section className="workspace-panel">
        <PanelHeader
          title={t("portfolio.scope.register")}
          meta={`${resources.length} ${t("home.resources")}`}
        />
        <DataGrid
          id="portfolio-resources"
          label={t("portfolio.scope.register")}
          rows={resources.slice(0, 25)}
          rowKey={(resource) => resource.resource_id}
          density="compact"
          selectedKey={selection.resourceId ?? null}
          onRowAction={(resource) => {
            selection.setResourceId(resource.resource_id);
            navigation.openWorkspace("contracts", "resources");
          }}
          // The pool row carries the contract's own id (`portfolio_resource_from_contract` maps
          // `contract_id` to `resource_id`), so the acceptance sweep can compare the row with the
          // upstream-terms read it renders (`scripts/uat/readToRender.mjs`).
          rowAttributes={(resource) => ({ "data-record": "portfolio-resource", "data-record-id": resource.resource_id })}
          columns={[
            { id: "resource", header: t("portfolio.resource"), rowHeader: true, sortable: true, value: (resource) => resource.resource_name },
            { id: "zone", header: t("portfolio.zone"), sortable: true, value: (resource) => resource.location_point_name },
            { id: "quantity", header: t("portfolio.quantity"), unit: "MWh/d", type: "number", sortable: true, value: (resource) => resource.available_quantity_mwh_per_day, format: (value) => (value as number).toLocaleString("en-GB") },
            { id: "cost", header: t("portfolio.all_in_cost"), unit: "GBP/MWh", type: "number", sortable: true, value: (resource) => resource.contract_cost_gbp_mwh + (resource.variable_cost_gbp_mwh ?? 0), format: (value) => formatMeasure("unit_value", value as number) },
            { id: "access", header: t("portfolio.access"), value: (resource) => resource.required_tso_access?.join(", ") || t("home.none_declared") },
          ]}
        />
      </section>
      <section className="workspace-panel">
        <PanelHeader
          title={t("portfolio.review_warnings")}
          meta={String(diagnostics.length)}
        />
        <CommercialWarningList
          items={diagnostics}
          t={t}
          limit={8}
          emptyLabel={t("review.no_warnings")}
        />
      </section>
      {/* Three links do not need a panel and a heading of their own (#69). */}
      <nav className="commercial-handoff-actions inline-links" aria-label={t("portfolio.handoffs")}>
        <button type="button" className="link-button" onClick={() => navigation.openWorkspace("market")}>{t("portfolio.show_market_context")}</button>
      </nav>
    </div>
  );
}

export function PortfolioWorkspace({ controller }: { controller: AppController }) {
  const { t, api, portfolio, selection, navigation, contractEditor } = controller;
  const currentUser = api.currentUser;
  const canMaintainRisk = currentUser?.role === "REVIEWER"
    || (currentUser?.roles.includes("REVIEWER") ?? false);
  const [task, setTask] = useState<PortfolioTask>(() =>
    portfolioTaskFromLocation(window.location.search),
  );
  // The resource sub-view is one fact with one owner: this workspace decides it, the panel
  // renders it, and the header's save action is derived from it. Keeping it here is what
  // lets the action and the panel it acts on agree without either re-deriving the other.
  // Contracts opens on the list (owner, 2026-11-19): "library" is the read view of the list and
  // the open contract; "terms" is editing or a new contract.
  const [contractView, setContractView] = useState<ContractTaskView>("library");
  const deskToday = useDeskToday();

  useEffect(() => {
    setTask(portfolioTaskFromLocation(window.location.search));
  }, [navigation.locationRevision]);

  useEffect(() => {
    if (selection.resourceId) setContractView("library");
  }, [selection.resourceId]);

  // The contract open in the workbench is in the URL (#31): a link or a refresh reopens it.
  const [contractParam, setContractParam] = useUrlObject("contracts", "contract");
  const openedFromUrl = useRef<string | null>(null);
  useEffect(() => {
    if (!contractParam || openedFromUrl.current === contractParam) return;
    const stored = api.upstreamContracts.find((item) => item.contract_id === contractParam);
    if (!stored) return;
    openedFromUrl.current = contractParam;
    if (contractEditor.contract.contract_id !== contractParam) contractEditor.loadPersistedContract(stored);
    setTask("resources");
    selection.setResourceId(contractParam);
    setContractView("library");
  }, [api.upstreamContracts, contractEditor, contractParam]);
  const loadPersistedContractAndLink = (saved: Parameters<typeof contractEditor.loadPersistedContract>[0]) => {
    contractEditor.loadPersistedContract(saved);
    // The opened contract is the selected resource, so the next page (review) carries it (#32).
    selection.setResourceId(saved.contract_id);
    openedFromUrl.current = saved.contract_id;
    setContractParam(saved.contract_id);
  };

  function openTask(next: PortfolioTask) {
    setTask(next);
    navigation.openWorkspace("contracts", next);
  }

  // This page serves two modes (WF-05): Position, Limits and Delivery are Book; Contracts is
  // Deals. The header is the row of whichever mode the task belongs to.
  const mode = useModeHeader(navigation.activeWorkspace, task, navigation.openWorkspace, t);

  // Action geography (`app/experience/actionGeography.ts`): writing a reviewed contract
  // draft is a `persist` consequence, so it occupies this workspace's single primary slot
  // instead of sitting among the panel's local controls. The panel keeps reporting the
  // validation verdict and the save outcome; the act that writes to PostgreSQL is here.
  const contractViewFactsForSelection = contractViewFacts({
    selectedResourceId: selection.resourceId,
    readOnlyLibrary: contractView === "library",
    resourceIds: portfolio.portfolioResources.map((resource) => resource.resource_id),
    contractIds: api.upstreamContracts.map((item) => item.contract_id),
  });
  const contractSaveStateForDraft = contractSaveState({
    contract: contractEditor.contract,
    runtimeDbReady: portfolio.runtimeDbReady,
    runtimeDbKnown: portfolio.runtimeDbKnown,
    loading: api.loading,
    viewFacts: contractViewFactsForSelection,
  });
  // The draft's own action, in its command row: the tab row holds tabs only (UX_REFERENCE rule 26).
  const saveAction =
    task === "resources" ? (
      <button
        type="button"
        className={buttonClass("primary", "md")}
        data-page-action="contract-save"
        disabled={!contractSaveStateForDraft.canSave}
        title={t(contractSaveStateForDraft.statusKey)}
        onClick={() =>
          contractSaveStateForDraft.canSave && void contractEditor.saveContract()
        }
      >
        {t("contracts.action.save")}
      </button>
    ) : undefined;

  return (
    <div className="commercial-workspace">
      <WorkspaceHeader
        title={mode.title ?? t("nav.mode.book")}
        taskLabel={t(`portfolio.task.${task}`)}
        idPrefix={`${mode.modeId ?? "book"}-task`}
        tabs={mode.tabs}
        activeId={mode.activeId}
        panelId="portfolio-task-panel"
        tabLabel={mode.tabLabel}
        purpose={mode.purpose}
        tabsClassName="commercial-task-tabs"
        onActivate={(id) => {
          // A task on this page switches in place; one on another page opens it.
          const target = PRODUCT_MODES.flatMap((item) => item.tasks).find((item) => item.id === id && item.page === "contracts");
          if (target?.pageTask) openTask(target.pageTask as PortfolioTask);
          else mode.onActivate(id);
        }}
      />
      <div id="portfolio-task-panel">
        {/* The demo desk's book is simulated end to end: said once at the top, not per figure
            (UX_REFERENCE rule 17; components/ui/SimulatedScope.tsx). */}
        <SimulatedScope scope={deskToday.today?.simulated ? "all" : "none"} notice={t("today.all_simulated")}>
        <PortfolioContextStrip
          projection={api.portfolioSnapshot}
          t={t}
          // Only where the context changes the page (the pool's results on Position and Contracts),
          // as one quiet summary; Limits & P&L and Delivery read nothing from it (owner: no filters
          // that change nothing).
          controls={task === "overview" ? tradingContextControlsFor(controller.traderContext, t, { summary: true }) : undefined}
          // The demo desk says "Demo data" once instead of counting a static store's feeds as stale.
          freshness={deskToday.today?.simulated ? <TodayFreshness today={deskToday.today} t={t} nowMs={Date.parse(deskToday.today.as_of)} /> : undefined}
        />
        {/* One number, one place: Position owns the ladder, its totals and the exposure by tenor;
            Limits & P&L owns limits, mandates, credit and P&L and links here for the ladder. */}
        {task === "overview" && <PositionLadderPanel t={t} />}
        {task === "overview" && <PortfolioOverview controller={controller} />}
        {task === "resources" && (
          <>
          <FirstUseHints hints={FIRST_USE_HINTS["deals.contracts"]} />
          <ContractWorkbench
            saveAction={saveAction}
            saveTypedContract={api.saveDraftContract}
            onCloseDetail={() => {
              selection.setResourceId(null);
              openedFromUrl.current = null;
              setContractParam(null);
            }}
            contract={contractEditor.contract}
            upstreamContracts={api.upstreamContracts}
            portfolioResources={portfolio.portfolioResources}
            totalPoolVolume={portfolio.totalPoolVolume}
            firstPoolAllocation={portfolio.firstPoolAllocation}
            runtimeDbReady={portfolio.runtimeDbReady}
            runtimeDbKnown={portfolio.runtimeDbKnown}
            loading={api.loading}
            draftDirty={contractEditor.draftDirty}
            selectedResourceId={selection.resourceId}
            taskView={contractView}
            onTaskViewChange={setContractView}
            viewFacts={contractViewFactsForSelection}
            saveState={contractSaveStateForDraft}
            contractImportRef={contractEditor.contractImportRef}
            contractImportMessage={contractEditor.contractImportMessage}
            contractImportBusy={contractEditor.contractImportBusy}
            contractIntake={contractEditor.contractIntake}
            onDismissContractIntake={contractEditor.dismissContractIntake}
            onContractLifecycle={api.setContractLifecycle}
            contractSaveMessage={api.contractSaveMessage}
            contractSaveConflict={api.contractSaveConflict}
            t={t}
            updateContractText={contractEditor.updateContractText}
            updateContractNumber={contractEditor.updateContractNumber}
            updateContractList={contractEditor.updateContractList}
            updateContractTranches={contractEditor.updateContractTranches}
            routeCandidates={api.routeCandidates}
            resetContractDraft={contractEditor.resetContractDraft}
            importContractDraftFile={contractEditor.importContractDraftFile}
            loadPersistedContract={loadPersistedContractAndLink}
          />
          </>
        )}
        {/* Book → Delivery (WF-05): what was delivered against what was nominated, the day's
            balance and the sell-down plan, apart from the contract terms they used to sit under. */}
        {task === "delivery" && <DeliveryPerformancePanel t={t} />}
        {task === "delivery" && <DailyBalancePanel t={t} />}
        {task === "delivery" && <SellDownPanel t={t} />}
        {task === "exposure" && <RiskLimitsPanel t={t} canMaintainRisk={canMaintainRisk} />}
        {task === "exposure" && <DealHedgeApprovalsPanel t={t} canMaintainRisk={canMaintainRisk} />}
        {task === "exposure" && <TradingBooksPanel t={t} />}
        {task === "exposure" && (
          <MarketPositioningWorkspace
            portfolioSummary={api.portfolioSummary}
            screenOrders={api.screenOrders}
            pnlSnapshots={api.pnlSnapshots}
            formatTimestamp={controller.sources.formatSourceTimestamp}
            t={t}
          />
        )}
        </SimulatedScope>
      </div>
    </div>
  );
}
