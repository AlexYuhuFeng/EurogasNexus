/**
 * A page's sub-view (and the object it is about) held in the URL (#31).
 *
 * Choosing a view pushes a history entry, so Back returns to the previous view; Back and
 * Forward (popstate) and a refresh restore it. Selecting an object replaces the entry, so
 * stepping through rows does not fill the history.
 */
import { useCallback, useEffect, useState } from "react";
import type { WorkspacePageId } from "@/workspaceNavigation";
import { objectFromSearch, viewFromSearch, viewToSearch } from "./viewRegistry";

function currentSearch(): string {
  return typeof window === "undefined" ? "" : window.location.search;
}

function writeSearch(search: string, mode: "push" | "replace"): void {
  if (typeof window === "undefined") return;
  const url = `${window.location.pathname}?${search}${window.location.hash}`;
  if (`${window.location.pathname}${window.location.search}${window.location.hash}` === url) return;
  if (mode === "push") window.history.pushState(window.history.state, "", url);
  else window.history.replaceState(window.history.state, "", url);
}

export function useUrlView<View extends string>(
  page: WorkspacePageId,
  fallback: View,
): [View, (view: View) => void] {
  const read = () => (viewFromSearch(page, currentSearch()) as View | null) ?? fallback;
  const [view, setViewState] = useState<View>(read);
  useEffect(() => {
    if (typeof window === "undefined") return;
    const sync = () => setViewState(read());
    window.addEventListener("popstate", sync);
    return () => window.removeEventListener("popstate", sync);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page]);
  const setView = useCallback(
    (next: View) => {
      setViewState(next);
      const params = new URLSearchParams(currentSearch());
      const objects: Record<string, string | null> = {};
      // Keep the page's own object parameters across a view change.
      for (const [name, value] of params) objects[name] = value;
      writeSearch(viewToSearch(currentSearch(), page, next, objects), "push");
    },
    [page],
  );
  return [view, setView];
}

/** An object parameter (a selected source or contract) kept in the URL for this page. */
export function useUrlObject(
  page: WorkspacePageId,
  name: string,
): [string | null, (value: string | null) => void] {
  const [value, setValueState] = useState<string | null>(() => objectFromSearch(page, name, currentSearch()));
  useEffect(() => {
    if (typeof window === "undefined") return;
    const sync = () => setValueState(objectFromSearch(page, name, currentSearch()));
    window.addEventListener("popstate", sync);
    return () => window.removeEventListener("popstate", sync);
  }, [page, name]);
  const setValue = useCallback(
    (next: string | null) => {
      setValueState(next);
      const search = currentSearch();
      const view = viewFromSearch(page, search) ?? "";
      writeSearch(viewToSearch(search, page, view, { [name]: next }), "replace");
    },
    [page, name],
  );
  return [value, setValue];
}
