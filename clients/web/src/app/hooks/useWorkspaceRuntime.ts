import { useEffect } from "react";
import { hydrateApiBaseUrlFromDesktopDeployment } from "@/api/client";
import { isIdentityGateOpen, type AuthState } from "@/stores/workspaceLoading";
import type { WorkspacePageId } from "@/workspaceNavigation";

export const MARKET_REFRESH_INTERVAL_MS = 10_000;
const LIVE_MARKET_WORKSPACES = new Set<WorkspacePageId>([
  "network",
  "market",
  "strategy",
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

  useEffect(() => {
    if (!authenticated) return;
    if (!LIVE_MARKET_WORKSPACES.has(activeWorkspace)) return;
    void refreshMarketData();
    const intervalId = window.setInterval(() => {
      void refreshMarketData();
    }, MARKET_REFRESH_INTERVAL_MS);
    return () => window.clearInterval(intervalId);
  }, [authenticated, activeWorkspace, refreshMarketData]);

  useEffect(() => {
    if (!authenticated) return;
    if (streamingActive) return;
    const intervalId = window.setInterval(() => {
      void refreshMonitoring();
    }, MARKET_REFRESH_INTERVAL_MS);
    return () => window.clearInterval(intervalId);
  }, [authenticated, refreshMonitoring, streamingActive]);
}
