import { openDeskBrief } from "@/components/DeskBriefDialog";
import { tabLabels } from "@/components/ui/tabLabels";
import { useEffect, useState } from "react";
import { WorkspaceHeader } from "@/components/ui";
import { CapacityWorkspace } from "@/components/CapacityWorkspace";
import { OutagesPanel } from "@/components/OutagesPanel";
import { capacityOperatingBoardRead } from "@/app/model/capacityOperatingBoardRead";
import { MarketTerminal } from "@/components/MarketTerminal";
import { TraderDeskPanel } from "@/components/TraderDeskPanel";
import { NetworkWorkspace } from "@/components/NetworkWorkspace";
import { ReferenceNetworkCatalogue } from "@/components/ReferenceNetworkCatalogue";
import { MarketContextStrip } from "@/components/MarketContextStrip";
import { TodayFreshness, TodayScreen } from "@/components/TodayScreen";
import { tradingContextControlsFor } from "@/components/TradingContextControls";
import { useDeskToday } from "@/app/hooks/useDeskToday";
import type { AppController } from "@/app/hooks/useAppController";
import "./market-cockpit.css";

import {
  MARKET_TASKS,
  type MarketTask,
} from "@/app/model/marketCockpitModel";

/** Age words on Today move on without a refetch: a minute clock, paused while hidden. */
function useMinuteClock(): number {
  const [nowMs, setNowMs] = useState(() => Date.now());
  useEffect(() => {
    const id = window.setInterval(() => {
      if (document.visibilityState === "visible") setNowMs(Date.now());
    }, 60_000);
    return () => window.clearInterval(id);
  }, []);
  return nowMs;
}

export function MarketCockpit({ controller }: { controller: AppController }) {
  const {
    navigation,
    t,
    api,
    theme,
    portfolio,
    traderContext,
    controls,
    selection,
    marketView,
  } = controller;
  // The landing task is the authenticated user's persisted view preference:
  // URL task > persisted view > numeric default. The numeric (`curves`) and map
  // (`network`) views stay separate tasks, the fused `overview` dashboard is
  // only ever reached by an explicit URL task or tab choice, and switching
  // between the two views keeps gas-day, product, hub and selection context
  // because every switch is a workspace/task URL update that preserves the
  // other query keys. The resolution is owned by `useAppController`, so the
  // task rendered here and the shell's layout class cannot disagree.
  const { task, rememberTask } = marketView;

  const openTask = (next: MarketTask) => {
    rememberTask(next);
    navigation.openWorkspace("market", next);
  };

  const tabs = MARKET_TASKS.map((id) => ({ id, ...tabLabels(t, `market.task.${id}`) }));
  // One read for the first screen; the context line on every market task uses it to say
  // "Demo data" once on the demo desk instead of counting a static store's feeds as stale.
  const desk = useDeskToday();
  const nowMs = useMinuteClock();

  return (
    <div className="market-cockpit">
      <WorkspaceHeader
        title={t("nav.primary.market")}
        taskLabel={t(`market.task.${task}`)}
        idPrefix="market-cockpit-task"
        tabs={tabs}
        activeId={task}
        panelId="market-cockpit-panel"
        tabLabel={t("nav.primary.market")}
        tabsClassName="market-cockpit-tabs"
        onActivate={openTask}
      />
      {/* The panel owns the task views. It carries its own class because the map task's layout
          (app.css `.workspace-network`) expects the viewport height to arrive through the page,
          the cockpit and this element. */}
      <div id="market-cockpit-panel" className="market-cockpit-panel">
        <MarketContextStrip
          projection={api.marketContext}
          t={t}
          controls={tradingContextControlsFor(traderContext, t)}
          freshness={
            task === "overview" || desk.today?.simulated ? (
              <TodayFreshness today={desk.today} t={t} nowMs={nowMs} />
            ) : undefined
          }
        />
        {task === "overview" && (
          <TodayScreen
            today={desk.today}
            loading={desk.loading}
            error={desk.error}
            t={t}
            language={controller.i18n.language}
            nowMs={nowMs}
            onRefresh={() => {
              desk.refresh();
              void api.refreshMarketData();
            }}
            // Before noon the desk writes its morning brief; after, its end-of-day report.
            onOpenBrief={() => openDeskBrief(new Date().getHours() < 12 ? "morning" : "eod")}
            onOpenLimits={() => navigation.openWorkspace("contracts", "exposure")}
            onOpenOutages={() => openTask("capacity")}
          />
        )}
        {task === "curves" && (
          <>
          <MarketTerminal
            markets={api.normalizedMarkets}
            marketSpreads={api.marketSpreads}
            marketQuotes={api.marketQuotes}
            intradayOpportunities={api.intradayOpportunities}
            fxRates={api.fxRates}
            sources={api.sources}
            lastUpdatedAtUtc={api.marketLastUpdatedAtUtc}
            focusedHub={traderContext.hubId}
            onHubChange={traderContext.setHubId}
            onRefresh={api.refreshMarketData}
            t={t}
          />
          {/* Desk conventions beside the board: product strip, hub price conversion and the
              storage-target trajectory, all computed by the backend. */}
          <TraderDeskPanel t={t} />
          </>
        )}
        {task === "network" && (
          <>
          <NetworkWorkspace
            t={t}
            nodes={api.nodes}
            edges={api.edges}
            routes={api.routes}
            mode={theme.mode}
            activeLayers={controls.activeLayers}
            searchTerm={controls.searchTerm}
            highlightedRoute={portfolio.highlightedRoute}
            routesInUse={portfolio.routesInUse}
            resourcePoolMapPaths={portfolio.resourcePoolMapPaths}
            poolInputBlockers={portfolio.poolInputBlockers}
            commercialDiagnostics={portfolio.commercialDiagnostics}
            error={api.error}
            loading={api.workspaceLoading}
            saleOptions={portfolio.saleOptions}
            portfolioResources={portfolio.portfolioResources}
            totalPoolVolume={portfolio.totalPoolVolume}
            portfolioSummary={api.portfolioSummary}
            screenOrderCount={api.screenOrders.length}
            upstreamContractCount={api.upstreamContracts.length}
            networkGeometryState={portfolio.networkGeometryState}
            routeRecommendation={portfolio.currentRouteRecommendation}
            decisionPnl={portfolio.decisionPnl}
            resourcePoolResult={portfolio.currentResourcePoolResult}
            poolAllocations={portfolio.poolAllocations}
            saleOptionById={portfolio.saleOptionById}
            hasPortfolioResources={portfolio.hasPortfolioResources}
            selectedAllocation={portfolio.selectedAllocation}
            purchasePrice={portfolio.purchasePrice}
            salePrice={portfolio.salePrice}
            routeCharge={portfolio.routeCharge}
            firstPoolAllocation={portfolio.firstPoolAllocation}
            firstStrategyTarget={portfolio.firstStrategyTarget}
            strategyResult={portfolio.currentStrategyResult}
            strategyContextMismatch={portfolio.strategyContextMismatch}
            activeWarning={portfolio.activeWarning}
            reviewEvidenceItems={portfolio.reviewEvidenceItems}
            intradayOpportunities={api.intradayOpportunities}
            resultsContextMismatch={portfolio.resultsContextMismatch}
            onResetSearch={() => controls.setSearchTerm("")}
            onToggleLayer={controls.toggleLayer}
            onOpenReview={() => navigation.openWorkspace("review")}
            onOpenScenario={() => {
              // Carried from the shell when the map-first network route moved into this
              // composition: the hand-off keeps the selected or highlighted route, so the
              // scenario workspace opens on the route the user was looking at.
              const routeId =
                portfolio.selectedAllocation?.route_id ??
                portfolio.highlightedRoute?.routeId ??
                null;
              if (routeId) selection.setRouteId(routeId);
              navigation.openWorkspace("scenario");
            }}
          />
          {/* The register the map's topology is drawn against, on the same task as the map: what
              the deployment declares, including the rows the map does not place (slice D). */}
          <ReferenceNetworkCatalogue t={t} />
          </>
        )}
        {/* Outages first: they are the time-critical events on this task (#69). */}
        {task === "capacity" && <OutagesPanel t={t} />}
        {task === "capacity" && (
          <CapacityWorkspace
            flows={api.flows}
            capacity={api.capacity}
            tsoAccess={api.tsoAccess}
            tsoTariffs={api.tsoTariffs}
            storage={api.storage}
            lng={api.lng}
            // The operating board joins the `flows` and `capacity` reads, so it states which of
            // them answered from the store's own facts - the batch's failure records, its
            // committed passes and the bounded retry's bookkeeping - as the Source Center does for
            // its registry lane (`app/model/capacityOperatingBoardRead.ts`).
            boardRead={capacityOperatingBoardRead(
              {
                flows: {
                  rows: api.flows.length,
                  error: api.endpointErrors.flows,
                  errorCode: api.endpointErrorCodes.flows,
                },
                capacity: {
                  rows: api.capacity.length,
                  error: api.endpointErrors.capacity,
                  errorCode: api.endpointErrorCodes.capacity,
                },
                loading: api.workspaceLoading,
                committedPasses: api.workspaceLoadsCommitted,
                retry: {
                  busy: api.endpointRetryBusy,
                  attempts: api.endpointRetryAttempts,
                  lastAttemptAtUtc: api.endpointRetryLastAttemptAtUtc,
                },
              },
              t,
            )}
            onRetryBoardRead={() => void api.retryFailedWorkspaceEndpoints()}
            t={t}
          />
        )}
      </div>
    </div>
  );
}
