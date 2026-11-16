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
  modeLanding,
  modeLocationFromSearch,
  redirectSearch,
  type ModeId,
} from "@/app/navigation/modeNavigation";
import {
  coerceWorkspacePageId,
  isWorkspacePageId,
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
/**
 * Rewrite an old address in place (WF-05): an old area (`?workspace=decision`) or a mode
 * (`?workspace=book&task=limits`, `?mode=deals`) becomes the page address it now lands on, so
 * Back, a refresh and a copied link all name one location. Only the URL changes; nothing mounts.
 */
export function applyAddressRedirect(): boolean {
  if (typeof window === "undefined") return false;
  const next = redirectSearch(window.location.search);
  if (next === null) return false;
  window.history.replaceState(
    window.history.state,
    "",
    `${window.location.pathname}${next ? `?${next}` : ""}${window.location.hash}`,
  );
  return true;
}

export function workspaceFromLocation(): WorkspacePageId {
  if (typeof window === "undefined") return DEFAULT_WORKSPACE_PAGE_ID;
  applyAddressRedirect();
  if (!isIdentityGateOpen(useApiStore.getState().authState)) return DEFAULT_WORKSPACE_PAGE_ID;
  const requestedWorkspace = new URLSearchParams(window.location.search).get("workspace");
  if (requestedWorkspace === null) {
    const preferredLanding = marketViewLandingPageCandidate({
      task: marketTaskFromSearch(window.location.search),
      persisted: readMarketViewPreference(marketViewPreferencePrincipalId()),
    });
    if (preferredLanding) return preferredLanding;
    // No URL and no personal preference: the declared job function's home (a risk
    // manager lands on exposure, a trader on prices). Composition only; the page is
    // authorised like any other.
    const personaLanding = personaHome(useApiStore.getState().currentUser?.experience?.home);
    if (personaLanding) {
      if (personaLanding.task && !new URLSearchParams(window.location.search).get("task")) {
        const next = new URLSearchParams(window.location.search);
        next.set("workspace", personaLanding.page);
        next.set("task", personaLanding.task);
        window.history.replaceState(window.history.state, "", `${window.location.pathname}?${next}`);
      }
      return personaLanding.page;
    }
  }
  return coerceWorkspacePageId(requestedWorkspace, DEFAULT_WORKSPACE_PAGE_ID);
}

/** The persona home the backend declared, when it names a known page. */
export function personaHome(
  home: { workspace: string; task: string } | null | undefined,
): { page: WorkspacePageId; task: string | null } | null {
  if (!home || !isWorkspacePageId(home.workspace)) return null;
  return { page: home.workspace, task: home.task || null };
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
  // The mode the user is in, derived from where they are (null on a utility page).
  const activeMode: ModeId | null =
    typeof window === "undefined"
      ? null
      : modeLocationFromSearch(activeWorkspace, window.location.search)?.mode.id ?? null;

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

  /** Open a mode at its first task the caller can use; the Desk keeps the remembered market view. */
  function openMode(mode: ModeId) {
    if (mode === "desk") {
      openPrimaryWorkspace("market");
      return;
    }
    const landing = modeLanding(mode, useApiStore.getState().currentUser);
    if (landing) openWorkspace(landing.page, landing.pageTask);
  }

  return {
    activeWorkspace,
    activePrimaryWorkspace,
    activeMode,
    openMode,
    locationRevision,
    openWorkspace,
    openPrimaryWorkspace,
  };
}
