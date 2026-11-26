/**
 * Start the map's own files (its worker, and the basemap's style or the offline outline) before
 * the map asks for them. On a first visit they then arrive ahead of the page's burst of reads
 * instead of queueing behind it on the browser's few connections per host.
 */
import mapLibreWorkerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url";
import { configuredMapTileProvider, outlineAssetUrls } from "@/app/mapTileProviders";

let warmed = false;

export function warmMapAssets(): void {
  if (warmed || typeof window === "undefined" || typeof fetch !== "function") return;
  warmed = true;
  const provider = configuredMapTileProvider();
  const dark = window.matchMedia?.("(prefers-color-scheme: dark)").matches;
  const basemap = provider.styleUrl ? [provider.styleUrl[dark ? "dark" : "light"]] : outlineAssetUrls();
  for (const url of [mapLibreWorkerUrl, ...basemap]) void fetch(url).catch(() => undefined);
}
