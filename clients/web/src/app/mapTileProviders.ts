import type { StyleSpecification } from "maplibre-gl";

/**
 * Basemap providers, and the licence each one carries.
 *
 * Owner decision **D4** (finding C12), taken from the audience this file serves: a deployment IT and
 * commercial team handing over a commercially licensed product. The previous default was
 * `tile.openstreetmap.org` for international browsers and AMap's public raster endpoint for Chinese
 * ones, with CARTO's public basemaps as a fallback - and **none of those three is licensed for
 * commercial embedding**: OpenStreetMap's tile service is volunteer-run and its usage policy forbids
 * heavy or commercial use, CARTO's public basemaps are not a production entitlement, and AMap's
 * terms require a key or an enterprise agreement. A product that ships one of them as its *default*
 * hands its customer a licence problem it never agreed to, and a basemap the vendor may block by
 * referrer at any time.
 *
 * So the decision is: **the platform ships no third-party basemap by default.** The map draws the
 * network on a background colour and says that no basemap is configured, which is honest - the
 * geometry is what this product is for, and the projection does not need a raster under it. A
 * deployment that wants imagery configures a source *it* has the right to use: its own tile service,
 * or a named provider it has licensed, with its own key.
 *
 * The presets stay in the list, because an operator who *has* the licence should not have to
 * hand-write a URL template - but each now declares its licence state, and the two whose public
 * endpoints are not a commercial entitlement say so where the operator chooses them.
 */

export type MapTileProviderId =
  | "none"
  | "bundled"
  | "outline"
  | "custom"
  | "openfreemap"
  | "tianditu";

/**
 * Whether a provider may be used in a commercial deployment as-is.
 *
 * `licensed-by-deployment` means the *operator* holds the entitlement (their own service, or a
 * provider they have an agreement and a key with); `not-for-commercial-use` means the endpoint's own
 * terms exclude production commercial use, so selecting it is a deliberate, recorded deployment
 * choice rather than something the product does on the operator's behalf.
 */
export type MapTileLicenceState =
  | "licensed-by-deployment"
  | "open-licence"
  | "not-for-commercial-use";

/** Where a basemap can be used: reachable and lawful to display. */
export type MapTileAvailability = "anywhere" | "outside-mainland-china" | "mainland-china";

export interface MapTileProvider {
  id: MapTileProviderId;
  label: string;
  labelZh: string;
  requiresToken: boolean;
  licence: MapTileLicenceState;
  availability: MapTileAvailability;
  description: string;
  /** Vector style URL for light and dark themes (vector providers only). */
  styleUrl?: { light: string; dark: string };
  attribution?: string;
}

export const MAP_TILE_STORAGE_KEY = "eurogas.settings.map_tile_provider";
const MAP_TILE_TOKEN_KEY = "eurogas.settings.map_tile_token";

/**
 * The default: no third-party basemap. The bundled outline (Natural Earth land, public domain,
 * served by the application itself) gives the network a coastline without fetching anything
 * from a third party, so it is safe in every jurisdiction and in air-gapped networks.
 */
export const DEFAULT_MAP_TILE_PROVIDER_ID: MapTileProviderId = "bundled";

/** Land polygons built by scripts/ui/build_offline_basemap.py (Europe, North Africa, Middle East). */
export const OUTLINE_BASEMAP_PATH = "basemaps/land-trading-region.geojson";
/** Country borders and place names for the bundled basemap (same script, Natural Earth). */
export const BUNDLED_BORDERS_PATH = "basemaps/borders-trading-region.geojson";
export const BUNDLED_PLACES_PATH = "basemaps/places-trading-region.geojson";
/** Label glyphs built from the bundled Inter (scripts/ui/build_map_glyphs.mjs). */
export const BUNDLED_GLYPHS_PATH = "basemaps/glyphs/{fontstack}/{range}.pbf";
export const BUNDLED_FONTSTACK = "Inter Regular";

/** The bundled basemap's colours in each theme (also used to recolour it in place). */
export function bundledPalette(theme: "light" | "dark") {
  return theme === "dark"
    ? { land: "#18181b", coast: "#3f3f46", border: "#52525b", country: "#6b6b74", city: "#8b8b94", halo: "#0b0b0d" }
    : { land: "#ffffff", coast: "#d4d4d8", border: "#c4c4cc", country: "#a8a8b0", city: "#8a8a93", halo: "#ffffff" };
}

/** The application's own origin and base path, for style URLs MapLibre needs absolute. */
function ownAssetUrl(relative: string): string {
  const base = (import.meta.env?.BASE_URL as string | undefined) ?? "/";
  const prefix = base.endsWith("/") ? base : `${base}/`;
  const origin = typeof window !== "undefined" && window.location ? window.location.origin : "";
  return `${origin}${prefix.startsWith("/") ? prefix : `/${prefix}`}${relative}`;
}

/** The bundled basemap's own files (land, borders, places, the first glyph range), to warm early. */
export function bundledBasemapAssetUrls(): string[] {
  return [
    OUTLINE_BASEMAP_PATH,
    BUNDLED_BORDERS_PATH,
    BUNDLED_PLACES_PATH,
    BUNDLED_GLYPHS_PATH.replace("{fontstack}", encodeURIComponent("Inter Regular")).replace("{range}", "0-255"),
  ].map(ownAssetUrl);
}

export const MAP_TILE_PROVIDERS: MapTileProvider[] = [
  {
    id: "bundled",
    label: "Bundled basemap (Natural Earth)",
    labelZh: "内置底图（Natural Earth，默认）",
    requiresToken: false,
    licence: "open-licence",
    availability: "outside-mainland-china",
    description:
      "The default. Land, coastlines, country borders and place names of Europe, North Africa and "
      + "the Middle East from Natural Earth (public domain), labels in the bundled Inter, all served "
      + "by the application itself: no request leaves for a third party and it works offline. "
      + "Draws country borders, so a mainland China installation uses the outline instead.",
    attribution: "Natural Earth",
  },
  {
    id: "none",
    label: "No basemap",
    labelZh: "无底图",
    requiresToken: false,
    licence: "licensed-by-deployment",
    availability: "anywhere",
    description:
      "The network draws on a plain background, so no third-party licence is implied by using "
      + "the platform and nothing has to be reachable from the browser.",
  },
  {
    id: "outline",
    label: "Offline outline (Natural Earth)",
    labelZh: "离线轮廓底图（Natural Earth，中国大陆默认）",
    requiresToken: false,
    licence: "open-licence",
    availability: "anywhere",
    description:
      "Coastlines of Europe, North Africa and the Middle East from Natural Earth (public domain), "
      + "served by the application itself. Works offline and in mainland China: it fetches nothing "
      + "from a third party and draws no country borders.",
    attribution: "Natural Earth",
  },
  {
    id: "custom",
    label: "Your own tile service",
    labelZh: "自建/自有瓦片服务",
    requiresToken: false,
    licence: "licensed-by-deployment",
    availability: "anywhere",
    description:
      "A raster tile URL template you operate or license ({z}/{x}/{y} placeholders), with the "
      + "attribution text your licence requires. Recommended for a commercial deployment.",
  },
  {
    id: "openfreemap",
    label: "OpenFreeMap",
    labelZh: "OpenFreeMap（开放许可，可商用）",
    requiresToken: false,
    licence: "open-licence",
    availability: "outside-mainland-china",
    description:
      "Free vector basemap with no key and no usage limit, permitted for commercial use. Data © "
      + "OpenStreetMap contributors (ODbL), schema by OpenMapTiles; attribution is shown on the map. "
      + "Hosted outside mainland China.",
    styleUrl: {
      light: "https://tiles.openfreemap.org/styles/positron",
      dark: "https://tiles.openfreemap.org/styles/dark",
    },
    attribution: "OpenFreeMap © OpenMapTiles Data from OpenStreetMap",
  },
  {
    id: "tianditu",
    label: "Tianditu / 天地图",
    labelZh: "天地图（需 operator token）",
    requiresToken: true,
    licence: "licensed-by-deployment",
    availability: "mainland-china",
    description:
      "CGCS2000-compatible WMTS basemap operated in mainland China. Requires an operator-provided "
      + "Tianditu token; coordinate alignment with the network WGS84 data is display-safe.",
  },
];

/**
 * How far in the map may zoom. A detailed basemap (vector or raster tiles) carries streets
 * and places to street level, so the map zooms like a city map; the bundled outline and the
 * plain background hold coastlines only, so zooming past regional scale would show nothing
 * more and only exaggerate the error of approximate positions.
 */
export function mapZoomRange(id: MapTileProviderId): { minZoom: number; maxZoom: number } {
  return id === "none" || id === "outline" || id === "bundled" ? { minZoom: 2, maxZoom: 10 } : { minZoom: 2, maxZoom: 17 };
}

/** How many place labels the map shows at a zoom: more as the view narrows. */
export function labelBudgetForZoom(zoom: number): number {
  if (zoom < 5) return 12;
  if (zoom < 7) return 24;
  return 60;
}

/** The provider record for an id, or `undefined` when the id is not one this build knows. */
export function mapTileProviderById(id: string | null | undefined): MapTileProvider | undefined {
  if (!id) return undefined;
  return MAP_TILE_PROVIDERS.find((provider) => provider.id === id);
}

/** Whether a selection is one the product may make on an operator's behalf. */
export function mapTileProviderNeedsOperatorLicence(provider: MapTileProvider): boolean {
  return provider.licence === "not-for-commercial-use";
}

function envMapToken(): string {
  const value = import.meta.env.VITE_EUROGAS_MAP_TILE_TOKEN as string | undefined;
  return (value ?? "").trim();
}

/**
 * The deployment's own tile source, when it configured one.
 *
 * `{z}/{x}/{y}` are the placeholders maplibre expects; `{r}` is accepted too and left to maplibre.
 * An empty template means the deployment configured nothing, which is the default state and not an
 * error: the map draws without a basemap and states that.
 */
export function configuredCustomTileTemplate(): string {
  const value = import.meta.env.VITE_EUROGAS_MAP_TILE_URL as string | undefined;
  return (value ?? "").trim();
}

/** The attribution the deployment's own licence requires for its tile source. */
export function configuredCustomTileAttribution(): string {
  const value = import.meta.env.VITE_EUROGAS_MAP_TILE_ATTRIBUTION as string | undefined;
  return (value ?? "").trim();
}

let deploymentDefault: MapTileProviderId | null = null;

/** Set from the server's deployment profile (`GET /api/runtime/release` → `deployment`). */
export function setDeploymentMapDefault(id: string | null | undefined): void {
  deploymentDefault = mapTileProviderById(id)?.id ?? null;
}

export function configuredMapTileProviderId(): MapTileProviderId {
  try {
    const stored = localStorage.getItem(MAP_TILE_STORAGE_KEY);
    if (mapTileProviderById(stored)) {
      return stored as MapTileProviderId;
    }
  } catch {
    // storage unavailable: fall through to build-time env
  }
  if (deploymentDefault) return deploymentDefault;
  const env = import.meta.env.VITE_EUROGAS_MAP_TILE_PROVIDER as string | undefined;
  const fromEnv = mapTileProviderById(env);
  if (fromEnv) {
    return fromEnv.id;
  }
  // D4: no locale-dependent default. A browser's language previously selected AMap's public
  // endpoint on the operator's behalf; now an unconfigured deployment gets no basemap at all.
  return configuredCustomTileTemplate() ? "custom" : DEFAULT_MAP_TILE_PROVIDER_ID;
}

export function configuredMapTileProvider(): MapTileProvider {
  const id = configuredMapTileProviderId();
  return mapTileProviderById(id) ?? MAP_TILE_PROVIDERS[0];
}

/**
 * Whether the configured basemap can actually be drawn.
 *
 * A provider that needs a token and has none, or `custom` with no template, cannot - and the map
 * states that rather than silently drawing nothing over a blank background. `none` is *configured*
 * (the deployment chose no basemap), which is a different statement from *unavailable*.
 */
export function mapTileBasemapState(
  provider: MapTileProvider,
  token: string,
): "configured" | "no-basemap" | "unavailable" {
  if (provider.id === "none") return "no-basemap";
  if (provider.id === "outline" || provider.id === "bundled") return "configured";
  if (provider.id === "custom") {
    return configuredCustomTileTemplate() ? "configured" : "unavailable";
  }
  if (provider.requiresToken && !token.trim()) return "unavailable";
  return "configured";
}

export function saveMapTileProvider(id: MapTileProviderId): void {
  try {
    localStorage.setItem(MAP_TILE_STORAGE_KEY, id);
  } catch {
    // non-sensitive preference; ignore unavailable storage
  }
}

export function configuredMapTileToken(): string {
  try {
    const stored = localStorage.getItem(MAP_TILE_TOKEN_KEY);
    if (stored !== null) return stored.trim();
  } catch {
    // ignore storage errors
  }
  return envMapToken();
}

export function saveMapTileToken(value: string): void {
  try {
    if (value.trim()) {
      localStorage.setItem(MAP_TILE_TOKEN_KEY, value.trim());
    } else {
      localStorage.removeItem(MAP_TILE_TOKEN_KEY);
    }
  } catch {
    // non-sensitive preference; ignore unavailable storage
  }
}

function tiandituTiles(layer: "vec" | "cva", token: string): string[] {
  const subdomains = ["0", "1", "2", "3", "4", "5", "6", "7"];
  return subdomains.map(
    (subdomain) =>
      `https://t${subdomain}.tianditu.gov.cn/${layer}_w/wmts?SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0&LAYER=${layer}&STYLE=default&TILEMATRIXSET=w&FORMAT=tiles&TILEMATRIX={z}&TILEROW={y}&TILECOL={x}&tk=${encodeURIComponent(token)}`,
  );
}

function isOutsideChina(lon: number, lat: number): boolean {
  return lon < 72.004 || lon > 137.8347 || lat < 0.8293 || lat > 55.8271;
}

export function transformCoordinate(
  providerId: MapTileProviderId,
  lon: number,
  lat: number,
): [number, number] {
  // Every offered basemap is drawn in WGS84 (Tianditu's CGCS2000 agrees with it at map scale), so
  // no point is shifted; the hook stays for a provider that would need it.
  void providerId;
  return [lon, lat];
}

export interface MapStyleOptions {
  background: string;
  /** App language for the bundled basemap's place names (English or Chinese). */
  language?: string;
  rasterOpacity: number;
  rasterSaturation: number;
  rasterContrast: number;
  rasterBrightnessMin: number;
  rasterBrightnessMax: number;
}

export function buildMapStyle(
  providerId: MapTileProviderId,
  token: string,
  options: MapStyleOptions,
  /** Theme for vector providers' light or dark style. */
  theme: "light" | "dark" = "light",
): StyleSpecification | string {
  const vector = mapTileProviderById(providerId)?.styleUrl;
  if (vector) {
    // Open vector basemaps ship their own style (and attribution); the network layers are
    // added on top once it has loaded.
    return vector[theme];
  }
  const paint = {
    "raster-opacity": options.rasterOpacity,
    "raster-saturation": options.rasterSaturation,
    "raster-contrast": options.rasterContrast,
    "raster-brightness-min": options.rasterBrightnessMin,
    "raster-brightness-max": options.rasterBrightnessMax,
  };

  const style: StyleSpecification = {
    version: 8,
    sources: {},
    layers: [
      {
        id: "background",
        type: "background",
        paint: { "background-color": options.background },
      },
    ],
  };

  if (providerId === "none") {
    // The deployment chose no basemap, so the background layer is the whole style and the map
    // states that. Nothing is fetched from a third party on the operator's behalf.
    return style;
  }

  if (providerId === "bundled") {
    // Everything from the application's own origin: land, coast, borders, place names and the
    // Inter glyphs they are drawn with. The land starts transparent and is revealed on load
    // (GasNetworkMap), so the map fades in rather than popping.
    const palette = bundledPalette(theme);
    const nameField = String(options.language ?? "").toLowerCase().startsWith("zh") ? "name_zh" : "name_en";
    style.glyphs = ownAssetUrl(BUNDLED_GLYPHS_PATH);
    style.sources = {
      land: { type: "geojson", data: ownAssetUrl(OUTLINE_BASEMAP_PATH), attribution: "Natural Earth" },
      borders: { type: "geojson", data: ownAssetUrl(BUNDLED_BORDERS_PATH) },
      places: { type: "geojson", data: ownAssetUrl(BUNDLED_PLACES_PATH) },
    };
    style.layers.push(
      { id: "outline-land", type: "fill", source: "land", paint: { "fill-color": palette.land, "fill-opacity": 0 } },
      { id: "outline-coast", type: "line", source: "land", paint: { "line-color": palette.coast, "line-width": 0.6, "line-opacity": 0 } },
      {
        id: "bundled-borders",
        type: "line",
        source: "borders",
        paint: { "line-color": palette.border, "line-width": ["interpolate", ["linear"], ["zoom"], 3, 0.5, 7, 1], "line-opacity": 0 },
      },
      {
        id: "bundled-country-labels",
        type: "symbol",
        source: "places",
        filter: ["==", ["get", "kind"], "country"],
        // The larger countries name first; small ones as the view narrows.
        minzoom: 3,
        layout: {
          "text-field": ["get", nameField],
          "text-font": [BUNDLED_FONTSTACK],
          // Context, not content: quieter than the network's own names.
          "text-size": ["interpolate", ["linear"], ["zoom"], 3, 9.5, 7, 12],
          "text-transform": "uppercase",
          "text-letter-spacing": 0.08,
          "text-max-width": 8,
          "symbol-sort-key": ["get", "rank"],
          "text-optional": true,
        },
        paint: { "text-color": palette.country, "text-halo-color": palette.halo, "text-halo-width": 1.2, "text-opacity": 0 },
      },
      {
        id: "bundled-city-labels",
        type: "symbol",
        source: "places",
        filter: ["all", ["!=", ["get", "kind"], "country"], ["<=", ["get", "rank"], ["step", ["zoom"], 1, 4.5, 3, 5.5, 5, 6.5, 7]]],
        minzoom: 4,
        layout: {
          "text-field": ["get", nameField],
          "text-font": [BUNDLED_FONTSTACK],
          "text-size": 11,
          "text-anchor": "left",
          "text-offset": [0.5, 0],
          "symbol-sort-key": ["get", "rank"],
        },
        paint: { "text-color": palette.city, "text-halo-color": palette.halo, "text-halo-width": 1.2, "text-opacity": 0 },
      },
    );
    return style;
  }

  if (providerId === "outline") {
    // Bundled land polygons served from the application's own origin: sea is the background,
    // land a slightly lifted surface with a hairline coast. No borders are drawn.
    const base = (import.meta.env?.BASE_URL as string | undefined) ?? "/";
    style.sources = {
      land: {
        type: "geojson",
        data: `${base.endsWith("/") ? base : `${base}/`}${OUTLINE_BASEMAP_PATH}`,
        attribution: "Natural Earth",
      },
    };
    style.layers.push(
      {
        id: "outline-land",
        type: "fill",
        source: "land",
        paint: { "fill-color": theme === "dark" ? "#18181b" : "#ffffff" },
      },
      {
        id: "outline-coast",
        type: "line",
        source: "land",
        paint: { "line-color": theme === "dark" ? "#3f3f46" : "#d4d4d8", "line-width": 0.6 },
      },
    );
    return style;
  }

  if (providerId === "tianditu" && token) {
    style.sources = {
      ...style.sources,
      "tianditu-vec": {
        type: "raster",
        tiles: tiandituTiles("vec", token),
        tileSize: 256,
        attribution: "Tianditu / 天地图",
      },
      "tianditu-label": {
        type: "raster",
        tiles: tiandituTiles("cva", token),
        tileSize: 256,
        attribution: "Tianditu / 天地图",
      },
    };
    style.layers.push(
      { id: "tianditu-vec-raster", type: "raster", source: "tianditu-vec", paint },
      { id: "tianditu-label-raster", type: "raster", source: "tianditu-label", paint },
    );
    return style;
  }

  if (providerId === "custom") {
    const template = configuredCustomTileTemplate();
    if (!template) {
      // Stated as unconfigured rather than drawn as an empty basemap: the map keeps its background
      // and the surface says no tile source is configured.
      return style;
    }
    const attribution = configuredCustomTileAttribution();
    style.sources = {
      ...style.sources,
      basemap: {
        type: "raster",
        tiles: [template],
        tileSize: 256,
        ...(attribution ? { attribution } : {}),
      },
    };
    style.layers.push({ id: "basemap-raster", type: "raster", source: "basemap", paint });
    return style;
  }

  // "none": the background layer is the whole style.
  return style;
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
