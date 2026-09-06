import { useCallback, useEffect, useRef, useState } from "react";
import {
  readSelectionContextUrl,
  resolveSelectionContext,
  selectionContextToSearchParams,
} from "./contextUrl.ts";
import {
  EMPTY_SELECTION_CONTEXT,
  normalizeSelectionId,
  type SelectionContext,
} from "./selectionContext.ts";

function initialSelectionContext(): SelectionContext {
  if (typeof window === "undefined") return EMPTY_SELECTION_CONTEXT;
  return resolveSelectionContext(readSelectionContextUrl(window.location.search));
}

export function useSelectionContext() {
  const [selection, setSelection] = useState<SelectionContext>(initialSelectionContext);
  const initialUrlSyncRef = useRef(true);
  const skipNextUrlSyncRef = useRef(false);

  useEffect(() => {
    if (skipNextUrlSyncRef.current) {
      skipNextUrlSyncRef.current = false;
      return;
    }
    const nextUrl = new URL(window.location.href);
    nextUrl.search = selectionContextToSearchParams(window.location.search, selection);
    if (initialUrlSyncRef.current) {
      window.history.replaceState({ selection }, "", nextUrl);
      initialUrlSyncRef.current = false;
    } else {
      window.history.pushState({ selection }, "", nextUrl);
    }
  }, [selection]);

  useEffect(() => {
    function syncFromUrl() {
      skipNextUrlSyncRef.current = true;
      setSelection(resolveSelectionContext(readSelectionContextUrl(window.location.search)));
    }
    window.addEventListener("popstate", syncFromUrl);
    return () => window.removeEventListener("popstate", syncFromUrl);
  }, []);

  const setRouteId = useCallback((value: string | null) => {
    setSelection((current) => ({ ...current, routeId: normalizeSelectionId(value) }));
  }, []);

  const setResourceId = useCallback((value: string | null) => {
    setSelection((current) => ({ ...current, resourceId: normalizeSelectionId(value) }));
  }, []);

  const setStrategyRunId = useCallback((value: string | null) => {
    setSelection((current) => ({ ...current, strategyRunId: normalizeSelectionId(value) }));
  }, []);

  const clearSelection = useCallback(() => {
    setSelection(EMPTY_SELECTION_CONTEXT);
  }, []);

  return {
    selection,
    routeId: selection.routeId,
    resourceId: selection.resourceId,
    strategyRunId: selection.strategyRunId,
    setRouteId,
    setResourceId,
    setStrategyRunId,
    clearSelection,
  };
}

export type { SelectionContext };
