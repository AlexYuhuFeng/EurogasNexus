import { PriceCharts } from "@/components/PriceCharts";
import { openDeskBrief } from "@/components/DeskBriefDialog";
import { useEffect, useState } from "react";
import { WorkspaceHeader } from "@/components/ui";
import { MarketTerminal } from "@/components/MarketTerminal";
import { DESK_NETWORK_KEPT } from "@/components/DeskNetworkTask";
import { KeptSlot } from "@/app/data/keepAlive";
import { warmMapAssets } from "@/app/mapAssetWarmup";
import { MarketContextStrip } from "@/components/MarketContextStrip";
import { SimulatedScope, simulatedScopeOf } from "@/components/ui/SimulatedScope";
import { FirstUseHints } from "@/components/ui/FirstUseHints";
import { FIRST_USE_HINTS } from "@/app/experience/firstUseHints";
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

  // The Desk's map is one tab away: its own files load when the browser is idle.
  useEffect(() => {
    const idle = window.requestIdleCallback ?? ((run: () => void) => window.setTimeout(run, 2000));
    idle(() => warmMapAssets());
  }, []);

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
        purpose={mode.purpose}
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
        {task === "overview" && <FirstUseHints hints={FIRST_USE_HINTS["desk.today"]} />}
        <MarketContextStrip
          projection={api.marketContext}
          t={t}
          // No filter strip on Today: it is about today, my hubs and my book (design basis 2, E.1).
          // Its one header line is this strip: gas day and front month, as of, data feeds, brief.
          controls={
            task === "overview"
              ? <TodayHeadline today={desk.today} language={controller.i18n.language} t={t} />
              : // On Prices the board's tenor selector is the product choice: no second one here.
                tradingContextControlsFor(traderContext, t, { product: task !== "curves" })
          }
          variant={task === "overview" ? "line" : "strip"}
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
        {/* A public source the ingestion gate holds back is operator information: an
            administrator sees it here and in Data feeds; a desk user does not. */}
        {api.currentUser?.permissions.includes("identity.manage") && <SourceApprovalNotice
          sources={api.sources}
          t={t}
          onOpen={() => navigation.openWorkspace("sources", "attention")}
        />}
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
            // The full storage and balance charts are Research → Fundamentals (CP-17).
            onOpenFundamentals={(view) => {
              navigation.openWorkspace("research", "fundamentals");
              const next = new URLSearchParams(window.location.search);
              next.set("view", view);
              window.history.replaceState(window.history.state, "", `?${next.toString()}`);
            }}
            // My gas day: each line opens where it is acted on or evidenced (Book → Delivery,
            // Planning or Position; a prompt trade on Prices with its hub chosen).
            canRecordGasDay={Array.isArray(api.currentUser?.permissions) && api.currentUser.permissions.includes("portfolio.write")}
            onOpenGasDay={(target) => {
              if (target.mode === "desk") {
                if (target.params.hub) traderContext.setHubId(target.params.hub);
                openTask("curves");
                return;
              }
              const entry = PRODUCT_MODES.find((mode) => mode.id === target.mode)?.tasks.find((item) => item.id === target.task);
              if (entry?.page) navigation.openWorkspace(entry.page, entry.pageTask);
            }}
            onOpenNeed={(item) => {
              if (item.kind === "outage") {
                openTask("network");
                window.history.replaceState(window.history.state, "", `?${networkPanelToSearch(window.location.search, "outages")}`);
              } else if (item.kind === "limit") {
                navigation.openWorkspace("contracts", "exposure");
              } else if (item.kind === "nomination") {
                // The checklist step: where it is evidenced (Book → Delivery or Planning).
                const entry = PRODUCT_MODES.find((mode) => mode.id === item.target?.mode)?.tasks.find((task) => task.id === item.target?.task);
                if (entry?.page) navigation.openWorkspace(entry.page, entry.pageTask);
              } else if (item.kind === "strategy") {
                // Research → Spreads, where the tracked strategy and its paper book are shown.
                navigation.openWorkspace("research", "spreads");
              } else {
                // Deals → Opportunities (CP-14) with the opportunity selected (`opportunity=`, the
                // item's target); until the page exists, Deals → Contracts.
                const task = PRODUCT_MODES.find((mode) => mode.id === "deals")?.tasks.find((entry) => entry.id === "opportunities");
                const opportunityId = item.target?.params?.opportunity;
                if (task?.page && opportunityId) {
                  const params = new URLSearchParams(window.location.search);
                  params.set("opportunity", opportunityId);
                  window.history.replaceState(window.history.state, "", `?${params.toString()}`);
                }
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
          {/* The board above says once that every price is simulated; the curve card shares it. */}
          <SimulatedScope scope={simulatedScopeOf(api.normalizedMarkets.map((row) => /_sim/i.test(row.source_system ?? "")))}>
            <PriceCharts markets={api.normalizedMarkets} t={t} />
          </SimulatedScope>
          </>
        )}
        {task === "network" && (
          // The map is rendered once at the shell and kept (app/data/keepAlive.tsx): this slot
          // shows it; leaving parks it, hidden, so returning finds it as it was (camera,
          // selection, layers, data) with no reload and no blank frame, from any page.
          <KeptSlot id={DESK_NETWORK_KEPT} />
        )}
      </div>
    </div>
  );
}
