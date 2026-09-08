import { useEffect, useState } from "react";
import {
  defaultWorkspacePageForPrimary,
  primaryWorkspaceForPage,
  type PrimaryWorkspace,
  type PrimaryWorkspaceId,
} from "@/app/navigation/productNavigation";
import {
  coerceWorkspacePageId,
  DEFAULT_WORKSPACE_PAGE_ID,
  workspaceTaskSearch,
  type WorkspacePageId,
} from "@/workspaceNavigation";

export function workspaceFromLocation(): WorkspacePageId {
  if (typeof window === "undefined") return DEFAULT_WORKSPACE_PAGE_ID;
  const requestedWorkspace = new URLSearchParams(window.location.search).get("workspace");
  return coerceWorkspacePageId(requestedWorkspace, DEFAULT_WORKSPACE_PAGE_ID);
}

export function useWorkspaceNavigation() {
  const [activeWorkspace, setActiveWorkspace] = useState<WorkspacePageId>(() => workspaceFromLocation());
  const [locationRevision, setLocationRevision] = useState(0);
  const activePrimaryWorkspace: PrimaryWorkspace = primaryWorkspaceForPage(activeWorkspace);

  useEffect(() => {
    function syncWorkspaceFromUrl() {
      setActiveWorkspace(workspaceFromLocation());
      setLocationRevision((revision) => revision + 1);
    }

    window.addEventListener("popstate", syncWorkspaceFromUrl);
    return () => window.removeEventListener("popstate", syncWorkspaceFromUrl);
  }, []);

  function openWorkspace(page: WorkspacePageId, task?: string) {
    setActiveWorkspace(page);
    const nextUrl = new URL(window.location.href);
    nextUrl.search = workspaceTaskSearch(window.location.search, page, task);
    window.history.pushState({ workspace: page }, "", nextUrl);
    setLocationRevision((revision) => revision + 1);
  }

  function openPrimaryWorkspace(primary: PrimaryWorkspaceId) {
    openWorkspace(defaultWorkspacePageForPrimary(primary));
  }

  return {
    activeWorkspace,
    activePrimaryWorkspace,
    locationRevision,
    openWorkspace,
    openPrimaryWorkspace,
  };
}
