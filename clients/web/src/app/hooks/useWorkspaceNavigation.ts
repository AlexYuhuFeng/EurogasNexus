import { useEffect, useState } from "react";
import {
  defaultWorkspacePageForPrimary,
  primaryWorkspaceForPage,
  type PrimaryWorkspace,
  type PrimaryWorkspaceId,
} from "@/app/navigation/productNavigation";
import { useApiStore } from "@/stores/api";
import { credentialFreeEntryUrl, shouldScrubEntryUrl } from "@/stores/authGate";
import { isIdentityGateOpen } from "@/stores/workspaceLoading";
import {
  readMarketViewPreference,
  marketViewLandingPageCandidate,
} from "@/app/context/viewPreference";
import { marketTaskFromSearch } from "@/app/model/marketCockpitModel";
import {
  coerceWorkspacePageId,
  DEFAULT_WORKSPACE_PAGE_ID,
  workspaceTaskSearch,
  type WorkspacePageId,
} from "@/workspaceNavigation";

/** Principal whose persisted market view decides the landing page, if any. */
function marketViewPreferencePrincipalId(): string | null {
  return useApiStore.getState().currentUser?.principal_id ?? null;
}

/**
 * Resolve the requested workspace from the URL. The gate is deliberately inside
 * this function: while identity is unresolved or denied, a deep link cannot
 * select a workspace, so no protected panel can mount from `?workspace=`.
 *
 * An explicit `?workspace=` or `?task=` always wins. Only when the URL names
 * neither does the authenticated user's persisted market view preference
 * choose the landing page, and only when none is stored does the declared
 * default (`DEFAULT_WORKSPACE_PAGE_ID`) stand.
 */
export function workspaceFromLocation(): WorkspacePageId {
  if (typeof window === "undefined") return DEFAULT_WORKSPACE_PAGE_ID;
  if (!isIdentityGateOpen(useApiStore.getState().authState)) return DEFAULT_WORKSPACE_PAGE_ID;
  const requestedWorkspace = new URLSearchParams(window.location.search).get("workspace");
  if (requestedWorkspace === null) {
    const preferredLanding = marketViewLandingPageCandidate({
      task: marketTaskFromSearch(window.location.search),
      persisted: readMarketViewPreference(marketViewPreferencePrincipalId()),
    });
    if (preferredLanding) return preferredLanding;
  }
  return coerceWorkspacePageId(requestedWorkspace, DEFAULT_WORKSPACE_PAGE_ID);
}

export function useWorkspaceNavigation() {
  const authState = useApiStore((state) => state.authState);
  const authErrorKey = useApiStore((state) => state.authErrorKey);
  const authNoticeKey = useApiStore((state) => state.authNoticeKey);
  const [activeWorkspace, setActiveWorkspace] = useState<WorkspacePageId>(
    () => workspaceFromLocation(),
  );
  const [locationRevision, setLocationRevision] = useState(0);
  const activePrimaryWorkspace: PrimaryWorkspace = primaryWorkspaceForPage(activeWorkspace);

  // A deep link is honoured as soon as (and only when) the session is confirmed.
  useEffect(() => {
    setActiveWorkspace(workspaceFromLocation());
  }, [authState]);

  // An explicit sign-out or a lost session scrubs the protected context from the
  // entry URL, so browser Back cannot restore a protected view.
  //
  // A plain anonymous visit is deliberately left alone: nothing is mounted while
  // the gate is closed, and keeping `?workspace=`/`?task=` means the requested
  // deep link is honoured once authentication succeeds instead of silently
  // dropping the visitor on the default landing page.
  useEffect(() => {
    if (!shouldScrubEntryUrl(authState, authErrorKey, authNoticeKey)) return;
    const nextUrl = credentialFreeEntryUrl(window.location.href);
    if (nextUrl !== window.location.href) {
      window.history.replaceState(window.history.state, "", nextUrl);
      setLocationRevision((revision) => revision + 1);
    }
  }, [authState, authErrorKey, authNoticeKey]);

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
    // Activating the Market primary respects the persisted view preference so a
    // numeric-preferring user is not dropped on the map; every other primary
    // keeps its declared default page.
    if (primary === "market") {
      const preferredLanding = marketViewLandingPageCandidate({
        task: null,
        persisted: readMarketViewPreference(marketViewPreferencePrincipalId()),
      });
      if (preferredLanding) {
        openWorkspace(preferredLanding);
        return;
      }
    }
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
