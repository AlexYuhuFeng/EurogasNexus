import { useCallback, useEffect, useRef, useState } from "react";
import { useApiStore } from "@/stores/api";
import { isIdentityGateOpen } from "@/stores/workspaceLoading";
import {
  readSelectionContextUrl,
  resolveSelectionContext,
  selectionContextToSearchParams,
} from "./contextUrl.ts";
import {
  EMPTY_SELECTION_CONTEXT,
  normalizeSelectionId,
  selectionContextKey,
  type SelectionContext,
} from "./selectionContext.ts";

/**
 * Route/resource/strategy selection is workspace state: it is restored from the
 * URL only inside an authenticated session, and reset while identity is
 * unresolved or denied so a deep link cannot pre-select a protected view.
 */
function selectionFromLocation(): SelectionContext {
  if (typeof window === "undefined") return EMPTY_SELECTION_CONTEXT;
  if (!isIdentityGateOpen(useApiStore.getState().authState)) return EMPTY_SELECTION_CONTEXT;
  return resolveSelectionContext(readSelectionContextUrl(window.location.search));
}

export function useSelectionContext() {
  const authState = useApiStore((state) => state.authState);
  const [selection, setSelection] = useState<SelectionContext>(
    () => selectionFromLocation(),
  );
  const initialUrlSyncRef = useRef(true);
  const skipNextUrlSyncRef = useRef(false);
  const gateOpen = isIdentityGateOpen(authState);

  useEffect(() => {
    const nextSelection = selectionFromLocation();
    setSelection((current) =>
      selectionContextKey(current) === selectionContextKey(nextSelection) ? current : nextSelection,
    );
  }, [authState]);

  useEffect(() => {
    const skipUrlWrite = skipNextUrlSyncRef.current;
    skipNextUrlSyncRef.current = false;
    if (!gateOpen || skipUrlWrite) return;
    const nextUrl = new URL(window.location.href);
    nextUrl.search = selectionContextToSearchParams(window.location.search, selection);
    if (initialUrlSyncRef.current) {
      window.history.replaceState({ selection }, "", nextUrl);
      initialUrlSyncRef.current = false;
    } else {
      window.history.pushState({ selection }, "", nextUrl);
    }
  }, [selection, gateOpen]);

  useEffect(() => {
    function syncFromUrl() {
      skipNextUrlSyncRef.current = true;
      setSelection(selectionFromLocation());
    }
    window.addEventListener("popstate", syncFromUrl);
    return () => window.removeEventListener("popstate", syncFromUrl);
  }, [authState]);

  const setRouteId = useCallback((value: string | null) => {
    setSelection((current) => ({ ...current, routeId: normalizeSelectionId(value) }));
  }, []);

  const setResourceId = useCallback((value: string | null) => {
    setSelection((current) => ({ ...current, resourceId: normalizeSelectionId(value) }));
  }, []);

  const setStrategyRunId = useCallback((value: string | null) => {
    setSelection((current) => ({ ...current, strategyRunId: normalizeSelectionId(value) }));
  }, []);

  const setStrategyId = useCallback((value: string | null) => {
    setSelection((current) => ({ ...current, strategyId: normalizeSelectionId(value) }));
  }, []);

  const setStrategyVersionId = useCallback((value: string | null) => {
    setSelection((current) => ({
      ...current,
      strategyVersionId: normalizeSelectionId(value),
    }));
  }, []);

  const clearSelection = useCallback(() => {
    setSelection(EMPTY_SELECTION_CONTEXT);
  }, []);

  return {
    selection,
    routeId: selection.routeId,
    resourceId: selection.resourceId,
    strategyRunId: selection.strategyRunId,
    strategyId: selection.strategyId,
    strategyVersionId: selection.strategyVersionId,
    setRouteId,
    setResourceId,
    setStrategyRunId,
    setStrategyId,
    setStrategyVersionId,
    clearSelection,
  };
}

export type { SelectionContext };
