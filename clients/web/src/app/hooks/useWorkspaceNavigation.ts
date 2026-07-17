import { useEffect, useState } from "react";
import {
  coerceWorkspacePageId,
  DEFAULT_WORKSPACE_PAGE_ID,
  type WorkspacePageId,
} from "@/workspaceNavigation";

export function workspaceFromLocation(): WorkspacePageId {
  if (typeof window === "undefined") return DEFAULT_WORKSPACE_PAGE_ID;
  const requestedWorkspace = new URLSearchParams(window.location.search).get("workspace");
  return coerceWorkspacePageId(requestedWorkspace, DEFAULT_WORKSPACE_PAGE_ID);
}

export function useWorkspaceNavigation() {
  const [activeWorkspace, setActiveWorkspace] = useState<WorkspacePageId>(() => workspaceFromLocation());

  useEffect(() => {
    function syncWorkspaceFromUrl() {
      setActiveWorkspace(workspaceFromLocation());
    }

    window.addEventListener("popstate", syncWorkspaceFromUrl);
    return () => window.removeEventListener("popstate", syncWorkspaceFromUrl);
  }, []);

  function openWorkspace(page: WorkspacePageId) {
    setActiveWorkspace(page);
    const nextUrl = new URL(window.location.href);
    nextUrl.searchParams.set("workspace", page);
    window.history.pushState({ workspace: page }, "", nextUrl);
  }

  return { activeWorkspace, openWorkspace };
}
