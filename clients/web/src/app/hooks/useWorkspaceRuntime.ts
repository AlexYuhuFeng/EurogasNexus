import { useEffect } from "react";
import { hydrateApiBaseUrlFromDesktopDeployment } from "@/api/client";
import type { WorkspacePageId } from "@/workspaceNavigation";

export const MARKET_REFRESH_INTERVAL_MS = 15_000;

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
    if (activeWorkspace !== "market") return;
    void refreshMarketData();
    const intervalId = window.setInterval(() => {
      void refreshMarketData();
    }, MARKET_REFRESH_INTERVAL_MS);
    return () => window.clearInterval(intervalId);
  }, [activeWorkspace, refreshMarketData]);
}
