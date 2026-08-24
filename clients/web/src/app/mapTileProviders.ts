import type { StyleSpecification } from "maplibre-gl";

export type MapTileProviderId = "osm" | "carto" | "amap" | "tianditu";

export interface MapTileProvider {
  id: MapTileProviderId;
  label: string;
  labelZh: string;
  requiresToken: boolean;
  description: string;
}

export const MAP_TILE_STORAGE_KEY = "eurogas.settings.map_tile_provider";
const MAP_TILE_TOKEN_KEY = "eurogas.settings.map_tile_token";

export const MAP_TILE_PROVIDERS: MapTileProvider[] = [
  {
    id: "osm",
    label: "OpenStreetMap",
    labelZh: "OpenStreetMap（国际默认）",
    requiresToken: false,
    description:
      "OpenStreetMap raster tiles. Suitable outside mainland China where the tile endpoint is reachable.",
  },
  {
    id: "carto",
    label: "CARTO Voyager",
    labelZh: "CARTO Voyager（国际备用）",
    requiresToken: false,
    description:
      "Permissive raster basemap. May still be slow or unreachable in mainland China and is only a secondary international fallback.",
  },
  {
    id: "amap",
    label: "AMap / 高德地图",
    labelZh: "高德地图（中国大陆免 key 备用）",
    requiresToken: false,
    description:
      "AMap raster tiles are generally reachable in mainland China without a key. AMap uses GCJ-02 coordinates; the client transforms WGS84 network data to GCJ-02 for display alignment.",
  },
  {
    id: "tianditu",
    label: "Tianditu / 天地图",
    labelZh: "天地图（中国大陆推荐）",
    requiresToken: true,
    description:
      "CGCS2000-compatible WMTS basemap operated in mainland China. Requires an operator-provided Tianditu token; coordinate alignment with the network WGS84 data is display-safe.",
  },
];

function envMapToken(): string {
  const value = import.meta.env.VITE_EUROGAS_MAP_TILE_TOKEN as string | undefined;
  return (value ?? "").trim();
}

export function configuredMapTileProviderId(): MapTileProviderId {
  try {
    const stored = localStorage.getItem(MAP_TILE_STORAGE_KEY) as MapTileProviderId | null;
    if (stored && MAP_TILE_PROVIDERS.some((provider) => provider.id === stored)) {
      return stored;
    }
  } catch {
    // storage unavailable: fall through to build-time env
  }
  const env = import.meta.env.VITE_EUROGAS_MAP_TILE_PROVIDER as string | undefined;
  if (env === "tianditu" || env === "carto" || env === "amap" || env === "osm") {
    return env;
  }
  // Mainland-China browsers default to AMap, which is generally reachable
  // without a key and avoids the OSM accessibility problem.
  try {
    if (typeof navigator !== "undefined" && navigator.language?.toLowerCase().startsWith("zh")) {
      return "amap";
    }
  } catch {
    // SSR/test environment: use the international default.
  }
  return "osm";
}

export function configuredMapTileProvider(): MapTileProvider {
  const id = configuredMapTileProviderId();
  return MAP_TILE_PROVIDERS.find((provider) => provider.id === id) ?? MAP_TILE_PROVIDERS[0];
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
  } else {
    style.sources = {
      ...style.sources,
      basemap: {
        type: "raster",
        tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
        tileSize: 256,
        attribution: "OpenStreetMap contributors",
      },
    };
  }
  style.layers.push({ id: "basemap-raster", type: "raster", source: "basemap", paint });
  return style;
}
