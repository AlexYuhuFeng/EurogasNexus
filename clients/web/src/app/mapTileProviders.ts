import type { Map as MapLibreMap, StyleSpecification } from "maplibre-gl";

/**
 * The map's one basemap (owner review 2026-11-26: "OpenStreetMap is good enough").
 *
 * OpenStreetMap data, served through OpenFreeMap's vector styles: ODbL data, free for commercial
 * use, no key, no usage limit. Attribution "© OpenStreetMap contributors, © OpenMapTiles" is shown
 * on the map. The OSM Foundation's own tile servers are not used: their tile usage policy
 * excludes a commercial product (docs/legal/DATA_SOURCE_TERMS.md).
 *
 * The only other state is the bundled land outline (Natural Earth, public domain, served by the
 * application itself). It is never a choice: it is drawn automatically when OpenFreeMap cannot be
 * reached (no network, an office proxy, the desktop app offline) and, by the deployment profile,
 * in a mainland China installation, where a map with foreign-hosted borders may not be published.
 * The map says when it is showing the outline. There is no provider setting in Settings.
 */

export type MapTileProviderId = "openfreemap" | "outline";

/** Where a basemap can be used: reachable and lawful to display. */
export type MapTileAvailability = "anywhere" | "outside-mainland-china";

export interface MapTileProvider {
  id: MapTileProviderId;
  label: string;
  availability: MapTileAvailability;
  /** Vector style URL for light and dark themes (vector providers only). */
  styleUrl?: { light: string; dark: string };
  attribution: string;
}

/** The ODbL attribution the OpenStreetMap basemap carries (shown in the map's corner). */
export const OSM_ATTRIBUTION = "© OpenStreetMap contributors, © OpenMapTiles";

export const DEFAULT_MAP_TILE_PROVIDER_ID: MapTileProviderId = "openfreemap";

/** Land polygons built by scripts/ui/build_offline_basemap.py (Europe, North Africa, Middle East). */
export const OUTLINE_BASEMAP_PATH = "basemaps/land-trading-region.geojson";
/** Label glyphs built from the bundled Inter (scripts/ui/build_map_glyphs.mjs). */
export const BUNDLED_GLYPHS_PATH = "basemaps/glyphs/{fontstack}/{range}.pbf";
export const BUNDLED_FONTSTACK = "Inter Regular";

/** The application's own origin and base path, for style URLs MapLibre needs absolute. */
function ownAssetUrl(relative: string): string {
  const base = (import.meta.env?.BASE_URL as string | undefined) ?? "/";
  const prefix = base.endsWith("/") ? base : `${base}/`;
  const origin = typeof window !== "undefined" && window.location ? window.location.origin : "";
  return `${origin}${prefix.startsWith("/") ? prefix : `/${prefix}`}${relative}`;
}

export const MAP_TILE_PROVIDERS: MapTileProvider[] = [
  {
    id: "openfreemap",
    label: "OpenStreetMap",
    availability: "outside-mainland-china",
    styleUrl: {
      light: "https://tiles.openfreemap.org/styles/positron",
      dark: "https://tiles.openfreemap.org/styles/dark",
    },
    attribution: OSM_ATTRIBUTION,
  },
  {
    id: "outline",
    label: "Offline outline (Natural Earth)",
    availability: "anywhere",
    attribution: "Natural Earth",
  },
];

/** The files the offline outline needs (land and the first glyph range), to warm early. */
export function outlineAssetUrls(): string[] {
  return [
    OUTLINE_BASEMAP_PATH,
    BUNDLED_GLYPHS_PATH.replace("{fontstack}", encodeURIComponent(BUNDLED_FONTSTACK)).replace("{range}", "0-255"),
  ].map(ownAssetUrl);
}

/**
 * How far in the map may zoom. OpenStreetMap carries streets and places to street level; the
 * outline holds coastlines only, so zooming past regional scale would show nothing more.
 */
export function mapZoomRange(id: MapTileProviderId): { minZoom: number; maxZoom: number } {
  return id === "outline" ? { minZoom: 2, maxZoom: 10 } : { minZoom: 2, maxZoom: 17 };
}

/** The fonts the map's own labels are drawn in on each basemap (its glyph server's names). */
export function labelFont(id: MapTileProviderId, weight: "regular" | "bold" = "regular"): string[] {
  if (id === "outline") return [BUNDLED_FONTSTACK];
  return [weight === "bold" ? "Noto Sans Bold" : "Noto Sans Regular"];
}

/** The provider record for an id, or `undefined` when the id is not one this build knows. */
export function mapTileProviderById(id: string | null | undefined): MapTileProvider | undefined {
  if (!id) return undefined;
  return MAP_TILE_PROVIDERS.find((provider) => provider.id === id);
}

let deploymentDefault: MapTileProviderId | null = null;

/**
 * Set from the server's deployment profile (`GET /api/runtime/release` → `deployment`): a mainland
 * China installation draws the outline. Any other or unknown value keeps OpenStreetMap.
 */
export function setDeploymentMapDefault(id: string | null | undefined): void {
  deploymentDefault = id === "outline" ? "outline" : null;
}

function browserOffline(): boolean {
  return typeof navigator !== "undefined" && navigator.onLine === false;
}

export function configuredMapTileProviderId(): MapTileProviderId {
  if (deploymentDefault) return deploymentDefault;
  // No network at all (the desktop app offline): the outline at once, not after a timeout.
  if (browserOffline()) return "outline";
  return DEFAULT_MAP_TILE_PROVIDER_ID;
}

export function configuredMapTileProvider(): MapTileProvider {
  return mapTileProviderById(configuredMapTileProviderId()) ?? MAP_TILE_PROVIDERS[0];
}

export function transformCoordinate(
  providerId: MapTileProviderId,
  lon: number,
  lat: number,
): [number, number] {
  // Both basemaps are drawn in WGS84, so no point is shifted; the hook stays for a provider that
  // would need it.
  void providerId;
  return [lon, lat];
}

export interface MapStyleOptions {
  /** Sea colour of the outline. */
  background: string;
}

/** The outline's colours in each theme (also used to recolour it in place). */
export function outlinePalette(theme: "light" | "dark") {
  return theme === "dark" ? { land: "#18181b", coast: "#3f3f46" } : { land: "#ffffff", coast: "#d4d4d8" };
}

export function buildMapStyle(
  providerId: MapTileProviderId,
  options: MapStyleOptions,
  theme: "light" | "dark" = "light",
): StyleSpecification | string {
  const vector = mapTileProviderById(providerId)?.styleUrl;
  if (vector) {
    // OpenFreeMap ships its own style, glyphs and attribution; the network layers are added on
    // top once it has loaded, and the style is quietened (muteVectorBasemap).
    return vector[theme];
  }
  // The outline: the sea is the background, land a lifted surface with a hairline coast, no
  // borders and no place names. Everything from the application's own origin.
  const palette = outlinePalette(theme);
  return {
    version: 8,
    glyphs: ownAssetUrl(BUNDLED_GLYPHS_PATH),
    sources: {
      land: { type: "geojson", data: ownAssetUrl(OUTLINE_BASEMAP_PATH), attribution: "Natural Earth" },
    },
    layers: [
      { id: "background", type: "background", paint: { "background-color": options.background } },
      { id: "outline-land", type: "fill", source: "land", paint: { "fill-color": palette.land } },
      { id: "outline-coast", type: "line", source: "land", paint: { "line-color": palette.coast, "line-width": 0.6 } },
    ],
  };
}

/**
 * Keep a vector basemap quiet under the network, as a control-room map does: at overview
 * only countries, seas and capitals are named, so a basemap city never competes with a hub,
 * terminal or field label. Smaller places appear as the view narrows.
 *
 * Returns the zoom from which a basemap symbol layer should show, or null to leave it.
 */
export function quietBasemapMinZoom(layerId: string, minzoom: number | undefined): number | null {
  const id = layerId.toLowerCase();
  if (/country|capital|city_large|water_name/.test(id)) return null;
  if (/state/.test(id)) return Math.max(minzoom ?? 0, 6);
  if (/city/.test(id)) return Math.max(minzoom ?? 0, 5.5);
  if (/town|village|suburb|other|airport/.test(id)) return Math.max(minzoom ?? 0, 7.5);
  return null;
}

/** Basemap layers that carry nothing a gas desk reads: points of interest, house numbers. */
export function hiddenBasemapLayer(layerId: string): boolean {
  return /poi|housenum|aeroway|building/.test(layerId.toLowerCase());
}

/**
 * Mute the OpenStreetMap style (desaturated, low contrast, light and dark): points of interest
 * and buildings hidden, roads thin and faint, place names quiet and later. The network, our
 * positions and prices are the content; the basemap is where they are.
 */
export function muteVectorBasemap(map: MapLibreMap): void {
  for (const layer of map.getStyle().layers ?? []) {
    try {
      if (hiddenBasemapLayer(layer.id)) {
        map.setLayoutProperty(layer.id, "visibility", "none");
        continue;
      }
      if (layer.type === "symbol") {
        const from = quietBasemapMinZoom(layer.id, layer.minzoom);
        if (from !== null) map.setLayerZoomRange(layer.id, from, layer.maxzoom ?? 24);
        map.setPaintProperty(layer.id, "text-opacity", 0.6);
        map.setPaintProperty(layer.id, "icon-opacity", 0.5);
      } else if (layer.type === "line" && /road|highway|street|bridge|tunnel|rail|transit/.test(layer.id)) {
        map.setPaintProperty(layer.id, "line-opacity", 0.45);
      }
    } catch {
      // A layer the style shapes differently keeps its own look.
    }
  }
}
