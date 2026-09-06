import { useMemo, useState } from "react";
import { WorkspaceTabs } from "@/components/ui";
import { CapacityWorkspace } from "@/components/CapacityWorkspace";
import { MarketTerminal } from "@/components/MarketTerminal";
import { NetworkWorkspace } from "@/components/NetworkWorkspace";
import { GasNetworkMap } from "@/components/GasNetworkMap";
import { IntradayDecisionFeed } from "@/components/IntradayDecisionFeed";
import type { AppController } from "@/app/hooks/useAppController";
import "./market-cockpit.css";

import {
  MAJOR_MARKET_HUBS as MAJOR_HUBS,
  MARKET_TASKS,
  marketTaskFromLocation,
  marketTaskToSearch,
  type MarketTask,
} from "@/app/model/marketCockpitModel";

function writeTask(task: MarketTask): void {
  const next = new URL(window.location.href);
  next.search = marketTaskToSearch(window.location.search, task);
  window.history.pushState({ task }, "", next);
}

function timestampMs(value: string | null | undefined): number {
  if (!value) return 0;
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

function latestByHub<T extends { hub: string; observed_at_utc?: string | null }>(
  rows: T[],
): Map<string, T> {
  const latest = new Map<string, T>();
  [...rows]
    .sort((left, right) => timestampMs(right.observed_at_utc) - timestampMs(left.observed_at_utc))
    .forEach((row) => {
      if (!latest.has(row.hub.toUpperCase())) latest.set(row.hub.toUpperCase(), row);
    });
  return latest;
}

function quoteMid(quote: { bid_price?: number | null; ask_price?: number | null; last_price?: number | null } | undefined): number | null {
  if (!quote) return null;
  if (quote.last_price != null) return quote.last_price;
  if (quote.bid_price != null && quote.ask_price != null) return (quote.bid_price + quote.ask_price) / 2;
  return quote.bid_price ?? quote.ask_price ?? null;
}

function formatAge(value: string | null | undefined): string {
  if (!value) return "n/a";
  const seconds = Math.max((Date.now() - new Date(value).getTime()) / 1000, 0);
  if (seconds < 60) return `${Math.round(seconds)}s`;
  if (seconds < 3600) return `${Math.round(seconds / 60)}m`;
  if (seconds < 86400) return `${Math.round(seconds / 3600)}h`;
  return `${Math.round(seconds / 86400)}d`;
}

function formatPrice(value: number | null | undefined, unit: string): string {
  return value === null || value === undefined ? "n/a" : `${value.toFixed(2)} ${unit}`;
}

interface MarketOverviewProps {
  controller: AppController;
  task: MarketTask;
}

function MarketOverview({ controller }: MarketOverviewProps) {
  const { api, portfolio, traderContext, selection, controls, t, navigation, i18n, theme } = controller;
  const markets = api.normalizedMarkets;
  const quotes = api.marketQuotes;
  const spreads = api.marketSpreads;
  const latestMarketByHub = useMemo(() => latestByHub(markets), [markets]);
  const latestQuoteByHub = useMemo(() => latestByHub(quotes), [quotes]);
  const focusedHub = traderContext.hubId;
  const relevantResources = portfolio.portfolioResources.filter(
    (resource) =>
      !focusedHub ||
      String(resource.location_point_name ?? "").toUpperCase().includes(focusedHub) ||
      String(resource.resource_name ?? "").toUpperCase().includes(focusedHub),
  );

  const spreadRows = useMemo(() => {
    const rows: Array<{ hub: string; spread: number | null; unit: string }> = [];
    MAJOR_HUBS.forEach((hub) => {
      const spread = spreads.find(
        (row) => row.from_hub?.toUpperCase() === hub && row.to_hub?.toUpperCase() === "TTF",
      );
      const quote = latestQuoteByHub.get(hub);
      const ttf = latestQuoteByHub.get("TTF");
      const liveSpread = hub === "TTF" ? 0 : quoteMid(quote) !== null && quoteMid(ttf) !== null ? (quoteMid(quote) ?? 0) - (quoteMid(ttf) ?? 0) : null;
      rows.push({
        hub,
        spread: spread?.spread_eur_mwh ?? liveSpread,
        unit: spread ? "EUR/MWh" : "GBP/MWh",
      });
    });
    return rows;
  }, [latestQuoteByHub, spreads]);

  return (
    <div className="market-cockpit-overview">
      <section className="market-context-strip" aria-label={controller.t("context.title")}>
        <span><small>{t("context.gas_day")}</small><strong>{traderContext.gasDay}</strong></span>
        <span><small>{t("context.product")}</small><strong>{traderContext.deliveryProduct}</strong></span>
        <span><small>{t("context.hub")}</small><strong>{focusedHub ?? t("context.all_hubs")}</strong></span>
        <span className={api.dataStatus === "runtime" ? "ready" : "issue"}>
          <small>{t("context.source_posture")}</small><strong>{api.dataStatus}</strong>
        </span>
        <button type="button" onClick={() => void api.refreshMarketData()}>{t("market.refresh")}</button>
      </section>

      <aside className="market-hub-board" aria-label={t("market.hub_board")}>
        <div className="data-table">
          <div className="data-table-row header six">
            <span>{t("market.hub")}</span><span>{t("market.bid_ask")}</span>
            <span>{t("market.mid")}</span><span>{t("market.spread_to_ttf")}</span>
            <span>{t("market.source")}</span><span>{t("market.freshness")}</span>
          </div>
          {MAJOR_HUBS.map((hub) => {
            const observation = latestMarketByHub.get(hub);
            const quote = latestQuoteByHub.get(hub);
            const spreadRow = spreadRows.find((row) => row.hub === hub);
            const selected = focusedHub === hub;
            return (
              <button
                key={hub}
                type="button"
                className={`data-table-row six ${selected ? "selected" : ""}`}
                onClick={() => traderContext.setHubId(selected ? null : hub)}
                aria-pressed={selected}
              >
                <strong>{hub}</strong>
                <span>{quote ? `${formatPrice(quote.bid_price, quote.currency)} / ${formatPrice(quote.ask_price, quote.currency)}` : "n/a"}</span>
                <span>{quote ? formatPrice(quoteMid(quote), quote.currency) : formatPrice(observation?.price_gbp_mwh, "GBP/MWh")}</span>
                <span>{spreadRow?.spread === null || spreadRow?.spread === undefined ? "n/a" : `${spreadRow.spread >= 0 ? "+" : ""}${spreadRow.spread.toFixed(2)}`}</span>
                <span>{quote?.source_system ?? observation?.source_system ?? "n/a"}</span>
                <span>{formatAge(quote?.observed_at_utc ?? observation?.observed_at_utc)}</span>
              </button>
            );
          })}
        </div>
      </aside>

      <section className="market-overview-map" aria-label={t("market.overview_map")}>
        <GasNetworkMap
          nodes={api.nodes}
          edges={api.edges}
          routes={api.routes}
          themeMode={theme.mode}
          activeLayers={["hubs", "network"]}
          searchTerm={controls.searchTerm}
          t={t}
          highlightedRoute={portfolio.highlightedRoute}
        />
        <div className="market-overview-map-note">{t("market.map_context_note")}</div>
      </section>

      <aside className="market-context-rail" aria-label={t("market.context_rail")}>
        <section className="workspace-panel">
          <h3>{t("market.physical_context")}</h3>
          <div className="metric-grid two-column compact-metrics">
            <div><span>{t("market.flows")}</span><strong>{api.flows.length}</strong></div>
            <div><span>{t("market.capacity")}</span><strong>{api.capacity.length}</strong></div>
            <div><span>{t("market.storage")}</span><strong>{api.storage.length}</strong></div>
            <div><span>{t("market.lng")}</span><strong>{api.lng.length}</strong></div>
            <div><span>{t("market.routes")}</span><strong>{api.routeCandidates.length}</strong></div>
            <div><span>{t("market.tso_access")}</span><strong>{api.tsoAccess.length}</strong></div>
          </div>
        </section>
        <section className="workspace-panel">
          <h3>{t("market.opportunities")}</h3>
          <IntradayDecisionFeed
            opportunities={api.intradayOpportunities.slice(0, 3)}
            lastUpdatedAtUtc={api.marketLastUpdatedAtUtc}
            t={t}
            compact
          />
        </section>
        <section className="workspace-panel">
          <h3>{t("market.portfolio_relevance")}</h3>
          {relevantResources.length === 0 ? (
            <p className="muted">{t("market.no_relevant_resources")}</p>
          ) : (
            <ul className="market-relevant-resources">
              {relevantResources.slice(0, 4).map((resource) => (
                <li key={resource.resource_id}>
                  <button
                    type="button"
                    onClick={() => {
                      selection.setResourceId(resource.resource_id);
                      navigation.openWorkspace("contracts");
                    }}
                  >
                    <span>{resource.resource_name}</span>
                    <strong>{resource.available_quantity_mwh_per_day} MWh/d</strong>
                  </button>
                </li>
              ))}
            </ul>
          )}
          <div className="market-handoff-actions">
            <button type="button" onClick={() => navigation.openWorkspace("scenario")}>{t("market.open_in_scenario")}</button>
            <button
              type="button"
              onClick={() => {
                if (focusedHub) traderContext.setHubId(focusedHub);
                navigation.openWorkspace("strategy");
              }}
            >
              {t("market.inspect_in_strategy")}
            </button>
          </div>
        </section>
      </aside>

      <section className="market-spread-strip" aria-label={t("market.spread_strip")}>
        {spreadRows.map((row) => (
          <div key={row.hub}>
            <span>{row.hub} → TTF</span>
            <strong>{row.spread === null || row.spread === undefined ? "n/a" : `${row.spread >= 0 ? "+" : ""}${row.spread.toFixed(2)} ${row.unit}`}</strong>
          </div>
        ))}
      </section>
    </div>
  );
}

export function MarketCockpit({ controller }: { controller: AppController }) {
  const { navigation, t, api, theme, portfolio, traderContext, controls, selection } = controller;
  const activeWorkspace = navigation.activeWorkspace;
  const [task, setTask] = useState<MarketTask>(() => marketTaskFromLocation(window.location.search, activeWorkspace));

  const openTask = (next: MarketTask) => {
    setTask(next);
    writeTask(next);
  };

  const tabs = MARKET_TASKS.map((id) => ({ id, label: t(`market.task.${id}`) }));

  return (
    <div className="market-cockpit">
      <WorkspaceTabs
        idPrefix="market-cockpit-task"
        label={t("nav.primary.market")}
        tabs={tabs}
        activeId={task}
        panelId="market-cockpit-panel"
        className="market-cockpit-tabs"
        onActivate={openTask}
      />
      <div id="market-cockpit-panel">
        {task === "overview" && <MarketOverview controller={controller} task={task} />}
        {task === "curves" && (
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
        )}
        {task === "network" && (
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
            sourceStats={controller.sources.sourceStats}
            optimizerContextMismatch={portfolio.optimizerContextMismatch}
            onResetSearch={() => controls.setSearchTerm("")}
            onToggleLayer={controls.toggleLayer}
            onOptimizePool={portfolio.optimizeResourcePoolForCurrentContext}
            onOpenReview={() => navigation.openWorkspace("review")}
            onOpenScenario={() => navigation.openWorkspace("scenario")}
          />
        )}
        {task === "capacity" && (
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
      </div>
    </div>
  );
}
