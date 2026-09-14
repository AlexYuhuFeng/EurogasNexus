import { useEffect, useState } from "react";
import {
  defaultWorkspacePageForPrimary,
  primaryWorkspaceForPage,
  type PrimaryWorkspace,
  type PrimaryWorkspaceId,
} from "@/app/navigation/productNavigation";
import { useApiStore } from "@/stores/api";
import { credentialFreeEntryUrl } from "@/stores/authGate";
import { isIdentityGateOpen, isUnauthenticated } from "@/stores/workspaceLoading";
import {
  coerceWorkspacePageId,
  DEFAULT_WORKSPACE_PAGE_ID,
  workspaceTaskSearch,
  type WorkspacePageId,
} from "@/workspaceNavigation";

/**
 * Resolve the requested workspace from the URL. The gate is deliberately inside
 * this function: while identity is unresolved or denied, a deep link cannot
 * select a workspace, so no protected panel can mount from `?workspace=`.
 */
export function workspaceFromLocation(): WorkspacePageId {
  if (typeof window === "undefined") return DEFAULT_WORKSPACE_PAGE_ID;
  if (!isIdentityGateOpen(useApiStore.getState().authState)) return DEFAULT_WORKSPACE_PAGE_ID;
  const requestedWorkspace = new URLSearchParams(window.location.search).get("workspace");
  return coerceWorkspacePageId(requestedWorkspace, DEFAULT_WORKSPACE_PAGE_ID);
}

export function useWorkspaceNavigation() {
  const authState = useApiStore((state) => state.authState);
  const [activeWorkspace, setActiveWorkspace] = useState<WorkspacePageId>(
    () => workspaceFromLocation(),
  );
  const [locationRevision, setLocationRevision] = useState(0);
  const activePrimaryWorkspace: PrimaryWorkspace = primaryWorkspaceForPage(activeWorkspace);

  // A deep link is honoured as soon as (and only when) the session is confirmed.
  useEffect(() => {
    setActiveWorkspace(workspaceFromLocation());
  }, [authState]);

  // A denied session scrubs the protected context from the current entry so
  // browser Back cannot restore a protected view. While identity is still
  // unresolved the URL is left alone - and still unmounted - so a deep link
  // survives the check and is honoured only after authentication.
  useEffect(() => {
    if (!isUnauthenticated(authState)) return;
    const nextUrl = credentialFreeEntryUrl(window.location.href);
    if (nextUrl !== window.location.href) {
      window.history.replaceState(window.history.state, "", nextUrl);
      setLocationRevision((revision) => revision + 1);
    }
  }, [authState]);

  useEffect(() => {
    function syncWorkspaceFromUrl() {
      setActiveWorkspace(workspaceFromLocation());
      setLocationRevision((revision) => revision + 1);
    }

    window.addEventListener("popstate", syncWorkspaceFromUrl);
    return () => window.removeEventListener("popstate", syncWorkspaceFromUrl);
  }, [authState]);

  function openWorkspace(page: WorkspacePageId, task?: string) {
    if (!isIdentityGateOpen(authState)) return;
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
