import { useEffect } from "react";
import { hydrateApiBaseUrlFromDesktopDeployment } from "@/api/client";
import type { WorkspacePageId } from "@/workspaceNavigation";

export const MARKET_REFRESH_INTERVAL_MS = 10_000;
const LIVE_MARKET_WORKSPACES = new Set<WorkspacePageId>([
  "network",
  "market",
  "strategy",
]);

interface WorkspaceRuntimeParams {
  activeWorkspace: WorkspacePageId;
  streamingActive: boolean;
  fetchWorkspace: () => Promise<void>;
  refreshMarketData: () => Promise<void>;
  refreshMonitoring: () => Promise<void>;
}

export function useWorkspaceRuntime({
  activeWorkspace,
  streamingActive,
  fetchWorkspace,
  refreshMarketData,
  refreshMonitoring,
}: WorkspaceRuntimeParams) {
  useEffect(() => {
    let active = true;
    void hydrateApiBaseUrlFromDesktopDeployment().then(() => {
      if (active) void fetchWorkspace();
    });
    return () => {
      active = false;
    };
  }, [fetchWorkspace]);

  useEffect(() => {
    if (!LIVE_MARKET_WORKSPACES.has(activeWorkspace)) return;
    void refreshMarketData();
    if (streamingActive) return;
    const intervalId = window.setInterval(() => {
      void refreshMarketData();
    }, MARKET_REFRESH_INTERVAL_MS);
    return () => window.clearInterval(intervalId);
  }, [activeWorkspace, refreshMarketData, streamingActive]);

  useEffect(() => {
    if (streamingActive) return;
    const intervalId = window.setInterval(() => {
      void refreshMonitoring();
    }, MARKET_REFRESH_INTERVAL_MS);
    return () => window.clearInterval(intervalId);
  }, [refreshMonitoring, streamingActive]);
}
