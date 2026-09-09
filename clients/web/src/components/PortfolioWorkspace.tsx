import { useEffect, useMemo, useState } from "react";
import { WorkspaceHeader } from "@/components/ui";
import { ContractWorkbench } from "@/components/ContractWorkbench";
import { MarketPositioningWorkspace } from "@/components/MarketPositioningWorkspace";
import type { AppController } from "@/app/hooks/useAppController";
import { warningLabels } from "@/app/warningLabel";
import {
  PORTFOLIO_TASKS,
  classifyRouteFeasibility,
  dedupeWarnings,
  portfolioTaskFromLocation,
  type PortfolioTask,
} from "@/app/model/commercialWorkflowModel";
import "./commercial-workflow.css";

function money(value: number | null | undefined, suffix = ""): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "n/a";
  return `GBP ${Math.round(value).toLocaleString()}${suffix}`;
}

function PortfolioOverview({ controller }: { controller: AppController }) {
  const { api, portfolio, selection, navigation, t } = controller;
  const resources = portfolio.portfolioResources;
  const totalVolume = portfolio.totalPoolVolume;
  const weightedCost = resources.length
    ? resources.reduce(
        (total, resource) =>
          total +
          resource.available_quantity_mwh_per_day *
            (resource.contract_cost_gbp_mwh + (resource.variable_cost_gbp_mwh ?? 0)),
        0,
      ) / Math.max(totalVolume, 1)
    : null;
  const warnings = dedupeWarnings(
    api.resourcePoolResult?.warnings,
    api.routeRecommendation?.warnings,
    api.resourcePoolOptions?.warnings,
    portfolio.poolInputBlockers,
  );

  return (
    <div className="commercial-overview">
      <section className="commercial-metric-strip" aria-label={t("portfolio.overview")}>
        <span><small>{t("home.pool_volume")}</small><strong>{totalVolume.toLocaleString()} MWh/d</strong></span>
        <span><small>{t("portfolio.weighted_cost")}</small><strong>{weightedCost === null ? "n/a" : `${weightedCost.toFixed(2)} GBP/MWh`}</strong></span>
        <span><small>{t("portfolio.allocated")}</small><strong>{api.resourcePoolResult?.total_allocated_mwh_per_day?.toLocaleString() ?? "n/a"} MWh/d</strong></span>
        <span><small>{t("portfolio.unallocated")}</small><strong>{api.resourcePoolResult?.total_unallocated_mwh_per_day?.toLocaleString() ?? "n/a"} MWh/d</strong></span>
        <span><small>{t("portfolio.net_indicative")}</small><strong>{money(api.resourcePoolResult?.total_net_pnl_gbp_per_day, "/d")}</strong></span>
        <span><small>{t("portfolio.warnings")}</small><strong>{warnings.length}</strong></span>
      </section>
      <section className="workspace-panel">
        <h2>{t("portfolio.resource_pool")}</h2>
        <div className="data-table">
          <div className="data-table-row header five">
            <span>{t("portfolio.resource")}</span><span>{t("portfolio.zone")}</span>
            <span>{t("portfolio.quantity")}</span><span>{t("portfolio.all_in_cost")}</span>
            <span>{t("portfolio.access")}</span>
          </div>
          {resources.slice(0, 25).map((resource) => (
            <button
              key={resource.resource_id}
              type="button"
              className={`data-table-row five ${selection.resourceId === resource.resource_id ? "selected" : ""}`}
              onClick={() => {
                selection.setResourceId(resource.resource_id);
                navigation.openWorkspace("contracts", "resources");
              }}
            >
              <strong>{resource.resource_name}</strong>
              <span>{resource.location_point_name}</span>
              <span>{resource.available_quantity_mwh_per_day.toLocaleString()} MWh/d</span>
              <span>{(resource.contract_cost_gbp_mwh + (resource.variable_cost_gbp_mwh ?? 0)).toFixed(2)} GBP/MWh</span>
              <span>{resource.required_tso_access?.join(", ") || t("home.none_declared")}</span>
            </button>
          ))}
        </div>
      </section>
      <section className="workspace-panel">
        <h2>{t("portfolio.review_warnings")}</h2>
        {warnings.length === 0 ? <p className="muted">{t("review.no_warnings")}</p> : (
          <ul className="commercial-warning-list">
            {warningLabels(warnings, t).slice(0, 8).map((warning) => <li key={warning}>{warning}</li>)}
          </ul>
        )}
      </section>
      <section className="workspace-panel">
        <h2>{t("portfolio.handoffs")}</h2>
        <div className="commercial-handoff-actions">
          <button type="button" onClick={() => navigation.openWorkspace("market")}>{t("portfolio.show_market_context")}</button>
          <button type="button" onClick={() => navigation.openWorkspace("strategy")}>{t("portfolio.inspect_strategy")}</button>
          <button type="button" onClick={() => navigation.openWorkspace("scenario")}>{t("portfolio.open_scenario")}</button>
        </div>
      </section>
    </div>
  );
}

function PortfolioRoutes({ controller }: { controller: AppController }) {
  const { api, portfolio, selection, navigation, t } = controller;
  const routes = api.routeCandidates;
  return (
    <section className="workspace-panel commercial-routes-panel">
      <div className="section-heading">
        <span className="eyebrow">{t("panel.routes")}</span>
        <strong>{t("portfolio.route_comparison")}</strong>
      </div>
      <div className="data-table commercial-route-table">
        <div className="data-table-row header six">
          <span>{t("portfolio.route")}</span><span>{t("portfolio.path")}</span>
          <span>{t("portfolio.access")}</span><span>{t("portfolio.feasibility")}</span>
          <span>{t("portfolio.quantity")}</span><span>{t("portfolio.margin")}</span>
        </div>
        {routes.map((route) => {
          const allocation = api.resourcePoolResult?.allocations.find(
            (item) => item.option_id === route.route_id,
          );
          const feasibility = classifyRouteFeasibility(
            route,
            api.routeRecommendation,
            api.resourcePoolResult,
            api.resourcePoolOptions,
          );
          return (
            <button
              key={route.route_id}
              type="button"
              className={`data-table-row six ${selection.routeId === route.route_id ? "selected" : ""}`}
              onClick={() => {
                selection.setRouteId(route.route_id);
                navigation.openWorkspace("scenario");
              }}
            >
              <strong>{route.route_name}</strong>
              <span>{route.start_point_name} → {route.target_point_name}</span>
              <span>{route.required_tso_access?.join(", ") || t("home.none_declared")}</span>
              <span className={`status-badge status-${feasibility.toLowerCase()}`}>{feasibility}</span>
              <span>{allocation?.allocated_quantity_mwh_per_day?.toLocaleString() ?? "n/a"} MWh/d</span>
              <span>{allocation ? money(allocation.net_pnl_gbp_per_day) : "n/a"}</span>
            </button>
          );
        })}
        {routes.length === 0 && (
          <div className="data-table-row six"><span>{t("data.unavailable")}</span><span>n/a</span><span>n/a</span><span>UNKNOWN</span><span>n/a</span><span>n/a</span></div>
        )}
      </div>
    </section>
  );
}

export function PortfolioWorkspace({ controller }: { controller: AppController }) {
  const { t, api, portfolio, selection, navigation, contractEditor } = controller;
  const [task, setTask] = useState<PortfolioTask>(() =>
    portfolioTaskFromLocation(window.location.search),
  );

  useEffect(() => {
    setTask(portfolioTaskFromLocation(window.location.search));
  }, [navigation.locationRevision]);

  function openTask(next: PortfolioTask) {
    setTask(next);
    navigation.openWorkspace("contracts", next);
  }

  const tabs = PORTFOLIO_TASKS.map((id) => ({ id, label: t(`portfolio.task.${id}`) }));

  return (
    <div className="commercial-workspace">
      <WorkspaceHeader
        title={t("nav.primary.portfolio")}
        taskLabel={t(`portfolio.task.${task}`)}
        idPrefix="portfolio-task"
        tabs={tabs}
        activeId={task}
        panelId="portfolio-task-panel"
        tabLabel={t("nav.primary.portfolio")}
        tabsClassName="commercial-task-tabs"
        onActivate={openTask}
      />
      <div id="portfolio-task-panel">
        {task === "overview" && <PortfolioOverview controller={controller} />}
        {task === "resources" && (
          <ContractWorkbench
            contract={contractEditor.contract}
            contractPayload={contractEditor.contractPayload}
            upstreamContracts={api.upstreamContracts}
            portfolioResources={portfolio.portfolioResources}
            totalPoolVolume={portfolio.totalPoolVolume}
            firstPoolAllocation={portfolio.firstPoolAllocation}
            runtimeDbReady={portfolio.runtimeDbReady}
            loading={api.loading}
            draftDirty={contractEditor.draftDirty}
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
        {task === "routes" && <PortfolioRoutes controller={controller} />}
        {task === "exposure" && (
          <MarketPositioningWorkspace
            portfolioSummary={api.portfolioSummary}
            screenOrders={api.screenOrders}
            pnlSnapshots={api.pnlSnapshots}
            formatTimestamp={controller.sources.formatSourceTimestamp}
            t={t}
          />
        )}
      </div>
    </div>
  );
}
