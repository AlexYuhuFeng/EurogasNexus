import { useSyncExternalStore } from "react";

/**
 * Whether Desk → Network lays out as a phone: the map on top, the controls and the panel in one
 * bottom sheet. network-desk.css draws that layout up to 900 px wide (iPad portrait included);
 * the page's markup (the toolbar inside the sheet, the layer chips) must switch at the same
 * width. It used to switch at the shell's compact width (719 px), so between 720 and 900 px the
 * page drew the sheet layout without its controls and the map in half the width (owner review
 * 2026-11-26, iPad portrait). One query, the same number as the stylesheet.
 */
export const NETWORK_SHEET_QUERY = "(max-width: 900px)";

function subscribe(onChange: () => void): () => void {
  const query = typeof window !== "undefined" ? window.matchMedia?.(NETWORK_SHEET_QUERY) : undefined;
  query?.addEventListener?.("change", onChange);
  return () => query?.removeEventListener?.("change", onChange);
}

function read(): boolean {
  return typeof window !== "undefined" ? Boolean(window.matchMedia?.(NETWORK_SHEET_QUERY).matches) : false;
}

export function useNetworkSheetLayout(): boolean {
  return useSyncExternalStore(subscribe, read, () => false);
}
