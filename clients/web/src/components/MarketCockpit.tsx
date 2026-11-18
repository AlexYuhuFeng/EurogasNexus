import { PriceCharts } from "@/components/PriceCharts";
import { openDeskBrief } from "@/components/DeskBriefDialog";
import { useEffect, useState } from "react";
import { WorkspaceHeader } from "@/components/ui";
import { capacityOperatingBoardRead } from "@/app/model/capacityOperatingBoardRead";
import { MarketTerminal } from "@/components/MarketTerminal";
import { NetworkWorkspace } from "@/components/NetworkWorkspace";
import { MarketContextStrip } from "@/components/MarketContextStrip";
import { SourceApprovalNotice } from "@/components/PublicSourceApprovals";
import { TodayFreshness, TodayHeadActions, TodayHeadline, TodayScreen } from "@/components/TodayScreen";
import { tradingContextControlsFor } from "@/components/TradingContextControls";
import { useDeskToday } from "@/app/hooks/useDeskToday";
import { useModeHeader } from "@/app/navigation/useModeHeader";
import { PRODUCT_MODES } from "@/app/navigation/modeNavigation";
import { resolveComposition } from "@/app/experience/roleComposition";
import { marketObservationSubject } from "@/app/model/inspectorDetail";
import { useInspectorStore } from "@/stores/inspector";
import type { TodayPriceDTO } from "@/api/client";
import type { AppController } from "@/app/hooks/useAppController";
import "./market-cockpit.css";

import {
  type MarketTask,
} from "@/app/model/marketCockpitModel";
import { networkPanelToSearch } from "@/app/model/networkPanelModel";

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
  // The map stays mounted once the Network task was opened (see the network block below).
  const [networkKept, setNetworkKept] = useState(task === "network");
  useEffect(() => {
    if (task === "network") setNetworkKept(true);
  }, [task]);

  const openTask = (next: MarketTask) => {
    rememberTask(next);
    navigation.openWorkspace("market", next);
  };

  // The Desk mode's task row (WF-05): Today, Prices and Network are this page's tasks.
  const mode = useModeHeader("market", task, navigation.openWorkspace, t);
  // One read for the first screen; the context line on every market task uses it to say
  // "Demo data" once on the demo desk instead of counting a static store's feeds as stale.
  const desk = useDeskToday();
  const nowMs = useMinuteClock();
  // Selecting a price hands its observation to the inspector (source, time, state), through
  // the Wave 1 contract: the page may only inspect the subject kinds it declares.
  const inspector = useInspectorStore();
  const inspectObservation = (ref: string | null, label: string) => {
    const subject = marketObservationSubject(ref ? { quote_id: ref } : null, "market", label);
    if (subject) inspector.open(subject);
  };
  /** The observation behind a Today price: the latest of that hub and tenor this desk holds. */
  const priceObservation = (price: TodayPriceDTO): string | null => {
    const hub = price.hub.toUpperCase();
    const tenor = String(price.tenor ?? "").toLowerCase();
    const latest = api.normalizedMarkets
      .filter((row) => row.is_gas_price && row.hub?.toUpperCase() === hub && row.tenor === tenor)
      .sort((left, right) => String(right.observed_at_utc ?? "").localeCompare(String(left.observed_at_utc ?? "")))[0];
    return latest?.observation_id ?? null;
  };

  return (
    <div className="market-cockpit">
      <WorkspaceHeader
        title={mode.title ?? t("nav.mode.desk")}
        taskLabel={t(`market.task.${task}`)}
        idPrefix="market-cockpit-task"
        tabs={mode.tabs}
        activeId={mode.activeId}
        panelId="market-cockpit-panel"
        tabLabel={mode.tabLabel}
        tabsClassName="market-cockpit-tabs"
        onActivate={(id) => {
          // A Desk task on this page also becomes the remembered market view.
          const target = PRODUCT_MODES.find((item) => item.id === "desk")?.tasks.find((item) => item.id === id);
          if (target?.page === "market" && target.pageTask) openTask(target.pageTask as MarketTask);
          else mode.onActivate(id);
        }}
      />
      {/* The panel owns the task views. It carries its own class because the map task's layout
          (app.css `.workspace-network`) expects the viewport height to arrive through the page,
          the cockpit and this element. */}
      <div id="market-cockpit-panel" className="market-cockpit-panel">
        <MarketContextStrip
          projection={api.marketContext}
          t={t}
          // No filter strip on Today: it is about today, my hubs and my book (design basis 2, E.1).
          // Its one header line is this strip: gas day and front month, as of, data feeds, brief.
          controls={
            task === "overview"
              ? <TodayHeadline today={desk.today} language={controller.i18n.language} t={t} />
              : tradingContextControlsFor(traderContext, t)
          }
          freshness={
            task === "overview" || desk.today?.simulated ? (
              <TodayFreshness today={desk.today} t={t} nowMs={nowMs} />
            ) : undefined
          }
        >
          {task === "overview" && (
            <TodayHeadActions
              t={t}
              loading={desk.loading}
              onOpenBrief={() => openDeskBrief(new Date().getHours() < 12 ? "morning" : "eod")}
              onRefresh={() => {
                desk.refresh();
                void api.refreshMarketData();
              }}
            />
          )}
        </MarketContextStrip>
        {/* A public source the ingestion gate holds back is never a silent gap on the desk. */}
        <SourceApprovalNotice
          sources={api.sources}
          t={t}
          onOpen={() => navigation.openWorkspace("sources", "attention")}
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
            // Outages live on Network, in the panel beside the map (its default tab).
            onOpenOutages={() => {
              openTask("network");
              window.history.replaceState(window.history.state, "", `?${networkPanelToSearch(window.location.search, "outages")}`);
            }}
            headInStrip={Boolean(api.marketContext)}
            rows={resolveComposition(api.currentUser).composition.todayRows}
            canSeeBook={!Array.isArray(api.currentUser?.permissions) || api.currentUser.permissions.includes("portfolio.read")}
            onOpenPrices={() => openTask("curves")}
            onOpenNeed={(item) => {
              if (item.kind === "outage") {
                openTask("network");
                window.history.replaceState(window.history.state, "", `?${networkPanelToSearch(window.location.search, "outages")}`);
              } else if (item.kind === "limit") {
                navigation.openWorkspace("contracts", "exposure");
              } else {
                // Deals → Opportunities (CP-14) when it exists; until then Deals → Contracts.
                const task = PRODUCT_MODES.find((mode) => mode.id === "deals")?.tasks.find((entry) => entry.id === "opportunities");
                if (task?.page) navigation.openWorkspace(task.page, task.pageTask);
                else navigation.openWorkspace("contracts", "resources");
              }
            }}
            onInspectPrice={(price) => {
              const ref = priceObservation(price);
              return ref ? () => inspectObservation(ref, `${price.hub} ${price.product}`) : null;
            }}
          />
        )}
        {task === "curves" && (
          <>
          <MarketTerminal
            markets={api.normalizedMarkets}
            marketSpreads={api.marketSpreads}
            marketQuotes={api.marketQuotes}
            fxRates={api.fxRates}
            sources={api.sources}
            lastUpdatedAtUtc={api.marketLastUpdatedAtUtc}
            focusedHub={traderContext.hubId}
            onHubChange={traderContext.setHubId}
            onInspect={inspectObservation}
            onRefresh={api.refreshMarketData}
            t={t}
          />
          {/* Term structure and the link into Spreads (CP-20). The price converter is the
              answer bar ("78 p/th in eur/mwh jan27"); a tenor's delivery window is on its
              header; the storage-target trajectory belongs to the storage chart. */}
          <PriceCharts markets={api.normalizedMarkets} t={t} />
          </>
        )}
        {(task === "network" || networkKept) && (
          // Kept mounted once visited and hidden while another task shows, so returning to
          // the map finds it as it was (camera, selection, layers, data): no reload, no blank
          // frame. `display: contents` keeps the page layout as if the wrapper were absent.
          <div style={{ display: task === "network" ? "contents" : "none" }} data-kept-task="network">
          <NetworkWorkspace
            t={t}
            nodes={api.nodes}
            edges={api.edges}
            routes={api.routes}
            mode={theme.mode}
            activeLayers={controls.activeLayers}
            searchTerm={controls.searchTerm}
            networkGeometryState={portfolio.networkGeometryState}
            onResetSearch={() => controls.setSearchTerm("")}
            onToggleLayer={controls.toggleLayer}
            // Hidden while another Desk task shows: nothing it opened stays above that page.
            active={task === "network"}
            language={controller.i18n.language}
            // The Capacity tab beside the map: the operating board joins the `flows` and
            // `capacity` reads, so it states which of them answered from the store's own facts
            // (`app/model/capacityOperatingBoardRead.ts`), as the Source Center does.
            capacity={{
              flows: api.flows,
              capacity: api.capacity,
              tsoAccess: api.tsoAccess,
              tsoTariffs: api.tsoTariffs,
              storage: api.storage,
              lng: api.lng,
              boardRead: capacityOperatingBoardRead(
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
              ),
              onRetryBoardRead: () => void api.retryFailedWorkspaceEndpoints(),
            }}
          />
          </div>
        )}
      </div>
    </div>
  );
}
