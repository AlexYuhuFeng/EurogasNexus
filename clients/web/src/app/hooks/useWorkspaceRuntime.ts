import { useCallback, useEffect, useRef } from "react";
import { hydrateApiBaseUrlFromDesktopDeployment } from "@/api/client";
import { liveStatus } from "@/app/data/liveStream";
import { useLiveTopics } from "@/app/hooks/useLive";
import { isIdentityGateOpen, type AuthState } from "@/stores/workspaceLoading";
import type { WorkspacePageId } from "@/workspaceNavigation";

export const MARKET_REFRESH_INTERVAL_MS = 10_000;
/** While the live stream is up the market is re-read on its notices; this is the safety net. */
export const MARKET_LIVE_SAFETY_MS = 60_000;
/** The market and the alert count re-read at most this often on a burst of notices. */
const LIVE_REREAD_MS = 2_000;
const LIVE_MARKET_WORKSPACES = new Set<WorkspacePageId>([
  "network",
  "market",
]);

interface WorkspaceRuntimeParams {
  authState: AuthState;
  activeWorkspace: WorkspacePageId;
  streamingActive: boolean;
  bootstrapIdentity: () => Promise<void>;
  fetchWorkspace: () => Promise<void>;
  refreshMarketData: () => Promise<void>;
  refreshMonitoring: () => Promise<void>;
}

export function useWorkspaceRuntime({
  authState,
  activeWorkspace,
  streamingActive,
  bootstrapIdentity,
  fetchWorkspace,
  refreshMarketData,
  refreshMonitoring,
}: WorkspaceRuntimeParams) {
  const authenticated = isIdentityGateOpen(authState);

  // Identity resolves first; every protected read below waits for it.
  useEffect(() => {
    let active = true;
    void hydrateApiBaseUrlFromDesktopDeployment().then(() => {
      if (active) void bootstrapIdentity();
    });
    return () => {
      active = false;
    };
  }, [bootstrapIdentity]);

  useEffect(() => {
    if (!authenticated) return;
    void fetchWorkspace();
  }, [authenticated, fetchWorkspace]);

  const lastMarketRead = useRef(0);
  const readMarket = useCallback(() => {
    lastMarketRead.current = Date.now();
    void refreshMarketData();
  }, [refreshMarketData]);
  const marketShown = authenticated && LIVE_MARKET_WORKSPACES.has(activeWorkspace);

  // Prices, FX and sources push a notice when they change (app/data/liveStream.ts): the board
  // re-reads then, not on a clock. The poll below runs only while the stream is not live.
  useLiveTopics(["prices", "sources"], readMarket, { enabled: marketShown, minIntervalMs: LIVE_REREAD_MS });

  useEffect(() => {
    if (!authenticated) return;
    if (!LIVE_MARKET_WORKSPACES.has(activeWorkspace)) return;
    readMarket();
    const intervalId = window.setInterval(() => {
      // Only while the browser tab is visible: a background tab reads nothing (its reads are
      // conditional, a 304 when unchanged, but an unseen page needs none at all).
      if (document.visibilityState !== "visible") return;
      if (liveStatus().state === "live" && Date.now() - lastMarketRead.current < MARKET_LIVE_SAFETY_MS) return;
      readMarket();
    }, MARKET_REFRESH_INTERVAL_MS);
    return () => window.clearInterval(intervalId);
  }, [authenticated, activeWorkspace, readMarket]);

  // The alert stream carries the rows; the count and summary re-read on the alerts notice.
  useLiveTopics(["alerts"], () => void refreshMonitoring(), {
    enabled: authenticated && streamingActive,
    minIntervalMs: LIVE_REREAD_MS,
  });

  useEffect(() => {
    if (!authenticated) return;
    if (streamingActive) return;
    const intervalId = window.setInterval(() => {
      void refreshMonitoring();
    }, MARKET_REFRESH_INTERVAL_MS);
    return () => window.clearInterval(intervalId);
  }, [authenticated, refreshMonitoring, streamingActive]);
}
