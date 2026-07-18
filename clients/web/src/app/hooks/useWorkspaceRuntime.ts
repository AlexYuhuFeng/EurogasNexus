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
  fetchWorkspace: () => Promise<void>;
  refreshMarketData: () => Promise<void>;
}

export function useWorkspaceRuntime({
  activeWorkspace,
  fetchWorkspace,
  refreshMarketData,
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
    const intervalId = window.setInterval(() => {
      void refreshMarketData();
    }, MARKET_REFRESH_INTERVAL_MS);
    return () => window.clearInterval(intervalId);
  }, [activeWorkspace, refreshMarketData]);
}
