/**
 * Start the map's own files (its worker and the bundled basemap) before the map asks for them.
 * On a first visit they then arrive ahead of the page's burst of reads instead of queueing behind
 * it on the browser's few connections per host. They are cached (the worker immutably, the
 * basemap for the session; api/web_client.py), so the map then reads them from the cache.
 */
import mapLibreWorkerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url";
import { bundledBasemapAssetUrls, configuredMapTileProvider } from "@/app/mapTileProviders";

let warmed = false;

export function warmMapAssets(): void {
  if (warmed || typeof window === "undefined" || typeof fetch !== "function") return;
  warmed = true;
  const basemap = configuredMapTileProvider().id === "bundled" ? bundledBasemapAssetUrls() : [];
  for (const url of [mapLibreWorkerUrl, ...basemap]) void fetch(url).catch(() => undefined);
}
