/**
 * The shell's situational strip: gathers the reads the person's strip audience needs and hands
 * the situation to `SituationStrip` (role-first redesign §5).
 *
 * Each read is made only for an audience that uses it, so a finance user asks for nothing and an
 * administrator without a commercial role is never asked for outages or cases:
 *
 * | Read | Audiences |
 * |---|---|
 * | open monitoring alerts (the store's) | all commercial |
 * | outage events, one row per event (the server's grouping) | trader, analyst, operations, desk head |
 * | Today (book hubs, limit counts, day P&L) | trader, operations, risk, desk head |
 * | decision cases | originator, risk, compliance, desk head |
 * | nomination windows | trader, operations |
 * | ETRM trades (booked today, read-only) | trader |
 * | sources (the store's) | platform |
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { api, type DecisionCaseSummaryDTO, type NominationWindowOccurrenceDTO, type ScreenOrderObservationDTO } from "@/api/client";
import { resolveComposition, type StripAudience } from "@/app/experience/roleComposition";
import { connectorCard } from "@/app/model/connectorCatalogModel";
import {
  buildSituation,
  canAcknowledgeAlerts,
  hideKey,
  pruneHidden,
  qualifyingItems,
  todayFacts,
  type SituationInputs,
  type SituationItem,
  type SituationTarget,
  type StripSource,
  type TickerOutage,
} from "@/app/model/tickerItems";
import { useDeskToday } from "@/app/hooks/useDeskToday";
import { saveStripHidden } from "@/app/preferences/remotePreferences";
import { useStripPreferences } from "@/app/preferences/stripPreferences";
import { useShellLayout } from "@/app/shell/useShellLayout";
import type { WorkspacePageId } from "@/workspaceNavigation";
import { SituationStrip, phraseText } from "@/components/BreakingTicker";
import { useApiStore } from "@/stores/api";
import { needsCommercialWorkspaceReads } from "@/stores/workspaceReadScope";

const REFRESH_MS = 120_000;
const SLOW_REFRESH_MS = 300_000;
const CLOCK_MS = 30_000;
const FLASH_MS = 4_000;

type Translate = (key: string, options?: Record<string, unknown>) => string;

const USES: Record<"outages" | "today" | "cases" | "windows" | "trades", readonly StripAudience[]> = {
  outages: ["trader", "analyst", "operations", "desk_head"],
  today: ["trader", "operations", "risk", "desk_head"],
  cases: ["originator", "risk", "compliance", "desk_head"],
  windows: ["trader", "operations"],
  trades: ["trader"],
};

/** A periodic read for one audience: null until it answers, kept on a failed refresh. */
function usePeriodicRead<T>(enabled: boolean, load: () => Promise<T>, everyMs: number, key: string): T | null {
  const [value, setValue] = useState<T | null>(null);
  const loader = useRef(load);
  loader.current = load;
  useEffect(() => {
    setValue(null);
    if (!enabled) return undefined;
    let live = true;
    const run = () =>
      loader
        .current()
        .then((next) => {
          if (live) setValue(next);
        })
        .catch(() => undefined);
    run();
    const timer = window.setInterval(run, everyMs);
    return () => {
      live = false;
      window.clearInterval(timer);
    };
  }, [enabled, everyMs, key]);
  return value;
}

export function ShellTicker({
  language,
  t,
  openWorkspace,
}: {
  language: string;
  t: Translate;
  /** The shell's navigation: the page and its task; the strip adds the object parameter. */
  openWorkspace: (page: WorkspacePageId, task?: string) => void;
}) {
  const user = useApiStore((state) => state.currentUser);
  const alerts = useApiStore((state) => state.monitoringAlerts);
  const sources = useApiStore((state) => state.sources);
  const contextHub = useApiStore((state) => state.tradingContext.hubId);
  const acknowledge = useApiStore((state) => state.acknowledgeMonitoringAlert);
  const preferences = useStripPreferences();
  const compact = useShellLayout().widthClass === "compact";

  const audience = resolveComposition(user).composition.stripAudience;
  const commercial = Boolean(user) && needsCommercialWorkspaceReads(user);
  const principal = user?.principal_id ?? "";
  const permissions = user?.permissions;
  const uses = (read: keyof typeof USES) => commercial && USES[read].includes(audience);
  const readsCases = uses("cases") && Boolean(permissions?.includes("review.read"));

  const outages = usePeriodicRead<TickerOutage[]>(
    uses("outages"),
    // One line per outage event (the server's grouping), as the Network list and Today.
    () => api.outages(14, undefined, { grouped: true }).then((response) => (Array.isArray(response.data) ? (response.data as unknown as TickerOutage[]) : [])),
    REFRESH_MS,
    principal,
  );
  const cases = usePeriodicRead<DecisionCaseSummaryDTO[]>(
    readsCases,
    () => api.decisionCases({ limit: "100" }).then((response) => response.data ?? []),
    REFRESH_MS,
    principal,
  );
  const windows = usePeriodicRead<NominationWindowOccurrenceDTO[]>(
    uses("windows"),
    () => api.nominationWindows().then((response) => response.data?.windows ?? []),
    SLOW_REFRESH_MS,
    principal,
  );
  const trades = usePeriodicRead<ScreenOrderObservationDTO[]>(
    uses("trades") && Boolean(permissions?.includes("portfolio.read")),
    () => api.screenOrders().then((response) => response.data ?? []),
    SLOW_REFRESH_MS,
    principal,
  );
  const desk = useDeskToday(uses("today"));

  const [nowMs, setNowMs] = useState(() => Date.now());
  useEffect(() => {
    const timer = window.setInterval(() => setNowMs(Date.now()), CLOCK_MS);
    return () => window.clearInterval(timer);
  }, []);

  const stripSources = useMemo<StripSource[] | null>(() => {
    if (audience !== "platform") return null;
    return sources.map((source) => {
      const card = connectorCard({
        source_id: source.source_id,
        connectivity_status: source.connectivity_status,
        operational_status: source.operational_status ?? source.connectivity_status,
        integration: source.integration,
        credential_state: source.credential_state,
        scheduler_enabled: source.scheduler_enabled ?? false,
        last_success_at_utc: source.last_success_at_utc ?? null,
        effective_last_success_at_utc: source.effective_last_success_at_utc ?? null,
        consecutive_failures: source.consecutive_failures ?? 0,
        approval: source.approval,
      });
      return {
        source_id: source.source_id,
        source_system: source.source_system,
        attention: card.group === "attention",
        statusKey: card.statusKey,
        last_failure_at_utc: source.last_failure_at_utc ?? null,
      };
    });
  }, [audience, sources]);

  const inputs = useMemo<SituationInputs>(
    () => ({
      alerts: commercial ? alerts : [],
      outages,
      cases,
      windows,
      bookedTrades: trades,
      sources: stripSources,
      today: desk.today ? todayFacts(desk.today) : null,
    }),
    [alerts, cases, commercial, desk.today, outages, stripSources, trades, windows],
  );
  const context = useMemo(
    () => ({
      audience,
      person: { name: user?.name ?? "", principalId: principal, permissions: permissions ?? [], dataScopes: user?.data_scopes ?? [] },
      thresholds: preferences.thresholds,
      contextHub,
      nowMs,
      hidden: new Set(preferences.hidden),
    }),
    [audience, contextHub, nowMs, permissions, preferences, principal, user?.data_scopes, user?.name],
  );
  const situation = useMemo(() => buildSituation(inputs, context), [inputs, context]);

  // Settled: every read this audience uses has answered once. Before that nothing is news.
  const settled =
    (!uses("outages") || outages !== null) &&
    (!readsCases || cases !== null) &&
    (!uses("today") || desk.today !== null || desk.error !== null);

  // Announce a new urgent item once; the state the person signed in to is not news.
  const seen = useRef<Set<string> | null>(null);
  const [announcement, setAnnouncement] = useState("");
  const [flash, setFlash] = useState(false);
  useEffect(() => {
    if (!settled) return undefined;
    const ids = situation.items.map((item) => item.id);
    if (seen.current === null) {
      seen.current = new Set(ids);
      return undefined;
    }
    const fresh = situation.items.filter((item) => !seen.current?.has(item.id));
    for (const id of ids) seen.current.add(id);
    if (!fresh.length) return undefined;
    setAnnouncement(t("strip.announce", { text: phraseText(fresh[0].headline, t, language, Date.now()) }));
    setFlash(true);
    const timer = window.setTimeout(() => setFlash(false), FLASH_MS);
    return () => window.clearTimeout(timer);
  }, [language, settled, situation.items, t]);
  useEffect(() => {
    seen.current = null;
  }, [principal]);

  const open = useCallback(
    (target: SituationTarget) => {
      openWorkspace(target.page, target.task);
      if (!target.params) return;
      // The object the job continues with (an outage on Network, a source on Connectors).
      const url = new URL(window.location.href);
      for (const [name, value] of Object.entries(target.params)) url.searchParams.set(name, value);
      window.history.replaceState(window.history.state, "", url);
      window.dispatchEvent(new PopStateEvent("popstate", { state: window.history.state }));
    },
    [openWorkspace],
  );

  const hide = useCallback(
    (item: SituationItem) => {
      // Keep only entries that still name a current item, so the list never grows stale.
      const current = settled ? pruneHidden(preferences.hidden, qualifyingItems(inputs, context).items) : [...preferences.hidden];
      saveStripHidden([...current, hideKey(item)]);
    },
    [context, inputs, preferences.hidden, settled],
  );

  return (
    <>
      <SituationStrip
        situation={situation}
        t={t}
        language={language}
        nowMs={nowMs}
        compact={compact}
        canAcknowledge={canAcknowledgeAlerts(user)}
        flash={flash}
        onOpen={open}
        onHide={hide}
        onAcknowledge={acknowledge}
      />
      {/* Outside the strip, so a hidden strip leaves no band and the next item is still heard. */}
      <span className="visually-hidden" role="status" aria-live="polite" data-strip-announcer>
        {announcement}
      </span>
    </>
  );
}
