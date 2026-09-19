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

export type MapTileProviderId = "none" | "custom" | "osm" | "carto" | "amap" | "tianditu";

/**
 * Whether a provider may be used in a commercial deployment as-is.
 *
 * `licensed-by-deployment` means the *operator* holds the entitlement (their own service, or a
 * provider they have an agreement and a key with); `not-for-commercial-use` means the endpoint's own
 * terms exclude production commercial use, so selecting it is a deliberate, recorded deployment
 * choice rather than something the product does on the operator's behalf.
 */
export type MapTileLicenceState = "licensed-by-deployment" | "not-for-commercial-use";

export interface MapTileProvider {
  id: MapTileProviderId;
  label: string;
  labelZh: string;
  requiresToken: boolean;
  licence: MapTileLicenceState;
  description: string;
}

export const MAP_TILE_STORAGE_KEY = "eurogas.settings.map_tile_provider";
const MAP_TILE_TOKEN_KEY = "eurogas.settings.map_tile_token";

/** The default: no third-party basemap, and the map says so. */
export const DEFAULT_MAP_TILE_PROVIDER_ID: MapTileProviderId = "none";

export const MAP_TILE_PROVIDERS: MapTileProvider[] = [
  {
    id: "none",
    label: "No basemap",
    labelZh: "无底图（默认）",
    requiresToken: false,
    licence: "licensed-by-deployment",
    description:
      "The default. The network draws on a plain background, so no third-party licence is implied "
      + "by using the platform and nothing has to be reachable from the browser.",
  },
  {
    id: "custom",
    label: "Your own tile service",
    labelZh: "自建/自有瓦片服务",
    requiresToken: false,
    licence: "licensed-by-deployment",
    description:
      "A raster tile URL template you operate or license ({z}/{x}/{y} placeholders), with the "
      + "attribution text your licence requires. Recommended for a commercial deployment.",
  },
  {
    id: "tianditu",
    label: "Tianditu / 天地图",
    labelZh: "天地图（需 operator token）",
    requiresToken: true,
    licence: "licensed-by-deployment",
    description:
      "CGCS2000-compatible WMTS basemap operated in mainland China. Requires an operator-provided "
      + "Tianditu token; coordinate alignment with the network WGS84 data is display-safe.",
  },
  {
    id: "osm",
    label: "OpenStreetMap",
    labelZh: "OpenStreetMap（仅非商业/评估）",
    requiresToken: false,
    licence: "not-for-commercial-use",
    description:
      "Volunteer-run tile service. Its usage policy excludes heavy and commercial use, so this is "
      + "for evaluation only: a production deployment must configure its own source.",
  },
  {
    id: "carto",
    label: "CARTO Voyager",
    labelZh: "CARTO Voyager（仅非商业/评估）",
    requiresToken: false,
    licence: "not-for-commercial-use",
    description:
      "Public basemaps endpoint, not a production entitlement under CARTO's terms. Evaluation only.",
  },
  {
    id: "amap",
    label: "AMap / 高德地图",
    labelZh: "高德地图（仅非商业/评估）",
    requiresToken: false,
    licence: "not-for-commercial-use",
    description:
      "Public raster endpoint whose terms require a key or an enterprise agreement for production "
      + "use. Evaluation only. AMap uses GCJ-02 coordinates; the client transforms WGS84 network "
      + "data to GCJ-02 for display alignment.",
  },
];

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

export function configuredMapTileProviderId(): MapTileProviderId {
  try {
    const stored = localStorage.getItem(MAP_TILE_STORAGE_KEY);
    if (mapTileProviderById(stored)) {
      return stored as MapTileProviderId;
    }
  } catch {
    // storage unavailable: fall through to build-time env
  }
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

export function wgs84ToGcj02(lon: number, lat: number): [number, number] {
  if (isOutsideChina(lon, lat)) return [lon, lat];
  const a = 6378245.0;
  const ee = 0.00669342162296594323;
  let dLat = transformLatitude(lon - 105.0, lat - 35.0);
  let dLon = transformLongitude(lon - 105.0, lat - 35.0);
  const radLat = (lat / 180.0) * Math.PI;
  let magic = Math.sin(radLat);
  magic = 1 - ee * magic * magic;
  const sqrtMagic = Math.sqrt(magic);
  dLat = (dLat * 180.0) / (((a * (1 - ee)) / (magic * sqrtMagic)) * Math.PI);
  dLon = (dLon * 180.0) / ((a / sqrtMagic) * Math.cos(radLat) * Math.PI);
  return [lon + dLon, lat + dLat];
}

function transformLatitude(x: number, y: number): number {
  let ret = -100.0 + 2.0 * x + 3.0 * y + 0.2 * y * y + 0.1 * x * y + 0.2 * Math.sqrt(Math.abs(x));
  ret += ((20.0 * Math.sin(6.0 * x * Math.PI) + 20.0 * Math.sin(2.0 * x * Math.PI)) * 2.0) / 3.0;
  ret += ((20.0 * Math.sin(y * Math.PI) + 40.0 * Math.sin((y / 3.0) * Math.PI)) * 2.0) / 3.0;
  ret += ((160.0 * Math.sin((y / 12.0) * Math.PI) + 320 * Math.sin((y * Math.PI) / 30.0)) * 2.0) / 3.0;
  return ret;
}

function transformLongitude(x: number, y: number): number {
  let ret = 300.0 + x + 2.0 * y + 0.1 * x * x + 0.1 * x * y + 0.1 * Math.sqrt(Math.abs(x));
  ret += ((20.0 * Math.sin(6.0 * x * Math.PI) + 20.0 * Math.sin(2.0 * x * Math.PI)) * 2.0) / 3.0;
  ret += ((20.0 * Math.sin(x * Math.PI) + 40.0 * Math.sin((x / 3.0) * Math.PI)) * 2.0) / 3.0;
  ret += ((150.0 * Math.sin((x / 12.0) * Math.PI) + 300.0 * Math.sin((x / 30.0) * Math.PI)) * 2.0) / 3.0;
  return ret;
}

export function transformCoordinate(
  providerId: MapTileProviderId,
  lon: number,
  lat: number,
): [number, number] {
  return providerId === "amap" ? wgs84ToGcj02(lon, lat) : [lon, lat];
}

export interface MapStyleOptions {
  background: string;
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
): StyleSpecification {
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
    // The default: the deployment chose no basemap, so the background layer is the whole style and
    // the map states that. Nothing is fetched from a third party on the operator's behalf.
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

  if (providerId === "amap") {
    style.sources = {
      ...style.sources,
      basemap: {
        type: "raster",
        tiles: ["1", "2", "3", "4"].map(
          (subdomain) =>
            `https://webrd0${subdomain}.is.autonavi.com/appmaptile?lang=zh_cn&size=1&scale=1&style=8&x={x}&y={y}&z={z}`,
        ),
        tileSize: 256,
        attribution: "AMap / 高德地图",
      },
    };
  } else if (providerId === "carto") {
    style.sources = {
      ...style.sources,
      basemap: {
        type: "raster",
        tiles: [
          "https://a.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png",
          "https://b.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png",
          "https://c.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png",
          "https://d.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png",
        ],
        tileSize: 256,
        attribution: "CARTO basemaps © OpenStreetMap contributors",
      },
    };
  } else if (providerId === "osm") {
    style.sources = {
      ...style.sources,
      basemap: {
        type: "raster",
        tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
        tileSize: 256,
        attribution: "OpenStreetMap contributors",
      },
    };
  } else {
    // "none", or a provider whose endpoints are not a commercial entitlement and which therefore
    // draws nothing: the background layer is the whole style.
    return style;
  }
  style.layers.push({ id: "basemap-raster", type: "raster", source: "basemap", paint });
  return style;
}
