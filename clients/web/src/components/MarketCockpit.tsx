import { tabLabels } from "@/components/ui/tabLabels";
import { useEffect, useMemo, useState } from "react";
import { WorkspaceHeader } from "@/components/ui";
import { CapacityWorkspace } from "@/components/CapacityWorkspace";
import { OutagesPanel } from "@/components/OutagesPanel";
import { GasForPowerPanel } from "@/components/GasForPowerPanel";
import { NweBalancePanel } from "@/components/NweBalancePanel";
import { capacityOperatingBoardRead } from "@/app/model/capacityOperatingBoardRead";
import { MarketTerminal } from "@/components/MarketTerminal";
import { TraderDeskPanel } from "@/components/TraderDeskPanel";
import { NetworkWorkspace } from "@/components/NetworkWorkspace";
import { ReferenceNetworkCatalogue } from "@/components/ReferenceNetworkCatalogue";
import { IntradayDecisionFeed } from "@/components/IntradayDecisionFeed";
import { MarketContextStrip } from "@/components/MarketContextStrip";
import { tradingContextControlsFor } from "@/components/TradingContextControls";
import { marketObservationSubject } from "@/app/model/inspectorDetail";
import { copilotOffers } from "@/app/model/copilotModel";
import { CopilotHost } from "@/components/CopilotPanel";
import { useCopilotSources } from "@/app/hooks/useCopilot";
import type { AiActionKind } from "@/app/experience/vocabulary";
import { useInspectorStore } from "@/stores/inspector";
import type { AppController } from "@/app/hooks/useAppController";
import { useMapSituation } from "@/app/hooks/useMapSituation";
import { situationSummary } from "@/app/mapSituation";
import { hubPrices } from "@/app/mapSelection";
import "./market-cockpit.css";

import {
  MAJOR_MARKET_HUBS as MAJOR_HUBS,
  MARKET_TASKS,
  type MarketTask,
} from "@/app/model/marketCockpitModel";

import {
  buildMarketOverviewComparisons,
  formatQuoteBidAsk,
  nextMarketOverviewExpiryMs,
} from "@/app/model/marketOverviewModel";

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

function formatAge(value: string | null | undefined): string {
  if (!value) return "n/a";
  const seconds = Math.max((Date.now() - new Date(value).getTime()) / 1000, 0);
  if (seconds < 60) return `${Math.round(seconds)}s`;
  if (seconds < 3600) return `${Math.round(seconds / 60)}m`;
  if (seconds < 86400) return `${Math.round(seconds / 3600)}h`;
  return `${Math.round(seconds / 86400)}d`;
}

function formatPrice(value: number | null | undefined, unit: string | null): string {
  return value === null || value === undefined || !unit ? "n/a" : `${value.toFixed(2)} ${unit}`;
}

function formatSpread(value: number | null, unit: string | null): string {
  if (value === null || !unit) return "n/a";
  return `${value >= 0 ? "+" : ""}${value.toFixed(2)} ${unit}`;
}

function observationContextTitle(observation: {
  product: string;
  currency: string;
  unit: string;
  period_start_utc: string;
  period_end_utc: string;
  metadata_json?: Record<string, unknown>;
} | undefined): string | undefined {
  if (!observation) return undefined;
  const metadata = observation.metadata_json ?? {};
  const basis = ["price_basis", "basis", "price_level", "price_timing"]
    .map((key) => metadata[key])
    .find((value): value is string => typeof value === "string" && value.trim().length > 0);
  return [
    `product=${observation.product}`,
    `delivery=${observation.period_start_utc}/${observation.period_end_utc}`,
    `basis=${basis ?? "unavailable"}`,
    `price_unit=${observation.currency}/${observation.unit}`,
    "spread_source=unavailable",
  ].join("; ");
}

interface MarketOverviewProps {
  controller: AppController;
  task: MarketTask;
}

function MarketOverview({ controller }: MarketOverviewProps) {
  const { api, portfolio, traderContext, selection, t, navigation } = controller;
  const markets = api.normalizedMarkets;
  const quotes = api.marketQuotes;
  const inspector = useInspectorStore();
  const [aiAction, setAiAction] = useState<AiActionKind | null>(null);
  // The Copilot reads the same canonical sources the shell and the palette use, so an
  // action offered here carries the context and evidence a run would actually use.
  const copilotSources = useCopilotSources({
    selection: {
      routeId: selection.routeId,
      resourceId: selection.resourceId,
      strategyVersionId: selection.strategyVersionId,
      strategyRunId: selection.strategyRunId,
    },
  });
  const [nowMs, setNowMs] = useState(() => Date.now());

  useEffect(() => {
    const nextExpiryMs = nextMarketOverviewExpiryMs(api.intradayOpportunities, nowMs);
    if (nextExpiryMs === null) return undefined;
    const timeoutId = window.setTimeout(
      () => setNowMs(Date.now()),
      Math.max(0, Math.min(2_147_483_647, nextExpiryMs - Date.now())),
    );
    return () => window.clearTimeout(timeoutId);
  }, [api.intradayOpportunities, nowMs]);

  const latestMarketByHub = useMemo(() => latestByHub(markets), [markets]);
  const comparisonRows = useMemo(
    () => buildMarketOverviewComparisons(MAJOR_HUBS, quotes, api.intradayOpportunities, nowMs),
    [api.intradayOpportunities, nowMs, quotes],
  );
  const comparisonByHub = useMemo(
    () => new Map(comparisonRows.map((row) => [row.hub, row])),
    [comparisonRows],
  );
  const focusedHub = traderContext.hubId;
  // Wave 9 hand-over: the Inspector shows the object the hub board actually
  // displayed for the focused hub - the quote when one exists, otherwise the
  // normalized observation. It resolves detail from data this surface already
  // received, so opening it fetches nothing.
  const inspectedObservation = focusedHub
    ? comparisonByHub.get(focusedHub)?.quote ?? latestMarketByHub.get(focusedHub) ?? null
    : null;
  const { situation } = useMapSituation();
  const networkToday = useMemo(() => {
    const summary = situationSummary(situation);
    if (!summary || !situation) return null;
    const entries = situation.flows.filter((flow) => flow.direction === "entry" && flow.gwh_d != null);
    return { ...summary, flowGwhD: entries.length ? entries.reduce((sum, flow) => sum + (flow.gwh_d ?? 0), 0) : null };
  }, [situation]);
  const relevantResources = portfolio.portfolioResources.filter(
    (resource) =>
      !focusedHub ||
      String(resource.location_point_name ?? "").toUpperCase().includes(focusedHub) ||
      String(resource.resource_name ?? "").toUpperCase().includes(focusedHub),
  );

  // Hubs with no price from any source collapse into one line: six rows of "n/a" said less
  // than one sentence does (#69). Bid/offer and spread columns appear only when some hub has
  // a live quote, because without one every cell in them would be empty.
  const pricedHubs = MAJOR_HUBS.filter(
    (hub) => comparisonByHub.get(hub)?.quote || hubPrices(hub, markets)[0] || latestMarketByHub.get(hub),
  );
  const unpricedHubs = MAJOR_HUBS.filter((hub) => !pricedHubs.includes(hub));
  const showQuotes = comparisonRows.some((row) => row.quote);
  const showSpread = comparisonRows.some((row) => row.spread != null);
  const boardColumns = [
    "minmax(56px, 0.6fr)",
    ...(showQuotes ? ["minmax(150px, 1.5fr)"] : []),
    "minmax(150px, 1.4fr)",
    ...(showSpread ? ["minmax(110px, 1fr)"] : []),
    "minmax(100px, 1fr)",
    "minmax(56px, 0.5fr)",
  ].join(" ");

  return (
    <div className="market-cockpit-overview">
      {/* Gas day, product and hub are already in the top bar; the board carries only what the
          top bar does not: whether the runtime store answered, and a refresh. */}
      <div className="market-overview-main">
      <aside className="market-hub-board" aria-label={t("market.hub_board")}>
        <div className="market-hub-board-head">
          <h2>{t("market.hub_board")}</h2>
          <button type="button" className="link-button" onClick={() => void api.refreshMarketData()}>{t("market.refresh")}</button>
        </div>
        <div className="data-table" style={{ ["--board-columns" as string]: boardColumns }}>
          <div className="data-table-row header board-row">
            <span>{t("market.hub")}</span>
            {showQuotes && <span>{t("market.bid_ask")}</span>}
            <span>{t("market.price")}</span>
            {showSpread && <span>{t("market.spread_to_ttf")}</span>}
            <span>{t("market.source")}</span><span>{t("market.freshness")}</span>
          </div>
          {pricedHubs.map((hub) => {
            const observation = latestMarketByHub.get(hub);
            // Day-ahead, else month-ahead, named: the same rows and rule as the hub board and
            // the map's hub card, so one hub never shows two unexplained prices.
            const boardPrice = hubPrices(hub, markets)[0] ?? null;
            const comparison = comparisonByHub.get(hub);
            const quote = comparison?.quote;
            const selected = focusedHub === hub;
            return (
              <button
                key={hub}
                type="button"
                className={`data-table-row board-row ${selected ? "selected" : ""}`}
                onClick={() => traderContext.setHubId(selected ? null : hub)}
                aria-pressed={selected}
                title={quote ? comparison?.contextTitle : observationContextTitle(observation) ?? comparison?.contextTitle}
              >
                <strong>{hub}</strong>
                {showQuotes && <span>{quote ? formatQuoteBidAsk(comparison.bid, comparison.ask, comparison.priceUnit) : "–"}</span>}
                {/* Each hub in its own unit (TTF in EUR/MWh, NBP in GBP/MWh), as on the hub
                    board: a converted price would give the same hub two numbers. */}
                <span>
                  {quote
                    ? formatPrice(comparison.mid, comparison.priceUnit)
                    : boardPrice
                      ? <>{formatPrice(boardPrice.price, boardPrice.unit)} <small className="muted">{t(boardPrice.tenor === "day-ahead" ? "map.detail.day_ahead" : "map.detail.month_ahead")}</small></>
                      : "–"}
                </span>
                {showSpread && <span>{formatSpread(comparison?.spread ?? null, comparison?.spreadUnit ?? null)}</span>}
                <span>{quote?.source_system ?? boardPrice?.source ?? observation?.source_system ?? "–"}</span>
                <span>{formatAge(quote?.observed_at_utc ?? boardPrice?.observedAt ?? observation?.observed_at_utc)}</span>
              </button>
            );
          })}
        </div>
        {unpricedHubs.length > 0 && (
          <p className="market-hub-board-missing">
            <span>{t("market.no_price_hubs")}</span>
            {unpricedHubs.map((hub) => (
              <button
                key={hub}
                type="button"
                className="link-button"
                aria-pressed={focusedHub === hub}
                onClick={() => traderContext.setHubId(focusedHub === hub ? null : hub)}
              >
                {hub}
              </button>
            ))}
          </p>
        )}
      </aside>

      {/* Fundamentals sit under the prices they explain. The map lives on the Network task
          only: a second, smaller copy here repeated it without adding a reading (#69). */}
      <div className="market-overview-fundamentals">
        <NweBalancePanel t={t} />
        <GasForPowerPanel t={t} />
      </div>
      </div>

      <aside className="market-context-rail" aria-label={t("market.context_rail")}>
        {/* What is happening on the network now, from the same live read as the map, instead
            of counts of loaded rows. */}
        <section className="workspace-panel">
          <h2>{t("market.network_today")}</h2>
          {networkToday ? (
            <div className="metric-grid two-column compact-metrics">
              <div className={networkToday.outagesNow ? "is-alert" : undefined}><span>{t("map.situation.outages_now")}</span><strong>{networkToday.outagesNow}</strong></div>
              <div><span>{t("map.situation.outages_scheduled")}</span><strong>{networkToday.outagesScheduled}</strong></div>
              <div><span>{t("map.situation.cargoes_at_sea")}</span><strong>{networkToday.cargoesAtSea}</strong></div>
              <div><span>{t("map.situation.slots")}</span><strong>{networkToday.slots}</strong></div>
              <div><span>{t("market.flows_measured")}</span><strong>{networkToday.flowGwhD == null ? "–" : `${Math.round(networkToday.flowGwhD).toLocaleString("en-GB")} GWh/d`}</strong></div>
              <div><span>{t("map.situation.contracts")}</span><strong>{networkToday.contracts}</strong></div>
            </div>
          ) : (
            <p className="muted">{t("market.network_today_none")}</p>
          )}
          <button type="button" className="link-button" onClick={() => navigation.openWorkspace("network")}>{t("market.open_map")}</button>
        </section>
        {/* The intraday scan earns a panel only when it returned candidates; otherwise one
            line says so, instead of a badge, a heading and an empty-state card. */}
        {api.intradayOpportunities.length > 0 ? (
          <section className="workspace-panel">
            <h2>{t("market.opportunities")}</h2>
            <IntradayDecisionFeed
              opportunities={api.intradayOpportunities}
              t={t}
              compact
            />
          </section>
        ) : (
          <p className="muted market-rail-note">{t("market.no_opportunities")}</p>
        )}
        <section className="workspace-panel">
          <h2>{t("market.portfolio_relevance")}</h2>
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
            <button type="button" className="link-button" onClick={() => navigation.openWorkspace("scenario")}>{t("market.open_in_scenario")}</button>
            <button
              type="button"
              className="link-button"
              onClick={() => {
                if (focusedHub) traderContext.setHubId(focusedHub);
                navigation.openWorkspace("strategy");
              }}
            >
              {t("market.inspect_in_strategy")}
            </button>
            <button
              type="button"
              className="link-button"
              hidden={!inspectedObservation}
              onClick={() => {
                const subject = marketObservationSubject(
                  inspectedObservation,
                  "market",
                  focusedHub ?? "",
                );
                if (subject) inspector.open(subject);
              }}
            >
              {t("market.inspect_observation")}
            </button>
          </div>
        </section>
        {(() => {
          // Five disabled buttons said only "not now"; when no action is available the
          // Copilot is one line with the reason the first action gives (#69).
          const offers = copilotOffers(copilotSources.context, copilotSources.evidenceRefs);
          const withheld = offers.every((offer) => !offer.available);
          return (
            <section className="workspace-panel" aria-label={t("experience.copilot.title")}>
              <h2 title={t("experience.copilot.subtitle")}>{t("experience.copilot.title")}</h2>
              {withheld ? (
                <p className="muted market-rail-note">
                  {offers[0]?.withheldReasonKey ? t(offers[0].withheldReasonKey) : t("experience.copilot.subtitle")}
                </p>
              ) : (
                <div className="market-handoff-actions">
                  {/* Wave 7 convergence on this workspace: the five canonical actions are
                      offered here, gated by the same rule the palette and the Copilot apply. */}
                  {offers.map((offer) => (
                    <button
                      key={offer.action}
                      type="button"
                      disabled={!offer.available}
                      title={offer.withheldReasonKey ? t(offer.withheldReasonKey) : undefined}
                      onClick={() => setAiAction(offer.action)}
                    >
                      {t(offer.labelKey)}
                    </button>
                  ))}
                </div>
              )}
            </section>
          );
        })()}
      </aside>

      {comparisonRows.some((row) => row.spread != null) && (
      <section className="market-spread-strip" aria-label={t("market.spread_strip")}>
        {comparisonRows.map((row) => (
          <div key={row.hub} title={row.contextTitle}>
            <span>{row.hub} → TTF</span>
            <strong>{formatSpread(row.spread, row.spreadUnit)}</strong>
          </div>
        ))}
      </section>
      )}

      {aiAction && (
        <CopilotHost
          action={aiAction}
          t={t}
          onClose={() => setAiAction(null)}
          onSelectAction={setAiAction}
        />
      )}
    </div>
  );
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
        />
        {task === "overview" && <MarketOverview controller={controller} task={task} />}
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
