/**
 * The basemap (owner review 2026-11-26: "OpenStreetMap is good enough").
 *
 * One basemap: OpenStreetMap data through OpenFreeMap's vector styles (ODbL, commercial use
 * allowed, no key), with the ODbL attribution on the map. The bundled Natural Earth outline is
 * never a choice: it is drawn when OpenFreeMap cannot be reached and in a mainland China
 * installation. No endpoint whose terms exclude a commercial product is offered, and Settings
 * holds no provider choice.
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const web = resolve(here, "..");

function readWebSource(relativePath: string): string {
  return readFileSync(resolve(web, relativePath), "utf8");
}

function locale(name: "en" | "zh"): Record<string, string> {
  return JSON.parse(readWebSource(`src/i18n/${name}.json`)) as Record<string, string>;
}

test("one basemap: OpenStreetMap through OpenFreeMap, with its attribution", async () => {
  const providers = await import("../src/app/mapTileProviders.ts");
  assert.deepEqual(providers.MAP_TILE_PROVIDERS.map((item) => item.id), ["openfreemap", "outline"]);
  assert.equal(providers.DEFAULT_MAP_TILE_PROVIDER_ID, "openfreemap");
  const osm = providers.mapTileProviderById("openfreemap")!;
  assert.equal(osm.styleUrl?.light, "https://tiles.openfreemap.org/styles/positron");
  assert.equal(osm.styleUrl?.dark, "https://tiles.openfreemap.org/styles/dark");
  assert.equal(providers.OSM_ATTRIBUTION, "© OpenStreetMap contributors, © OpenMapTiles");
  // The map rewrites the source's credit to the ODbL wording.
  assert.match(readWebSource("src/components/GasNetworkMap.tsx"), /source\.attribution = OSM_ATTRIBUTION/);
});

test("no endpoint whose terms exclude a commercial product, no second provider", () => {
  const source = readWebSource("src/app/mapTileProviders.ts");
  for (const host of ["tile.openstreetmap.org", "basemaps.cartocdn.com", "autonavi", "tianditu", "versatiles"]) {
    assert.ok(!source.toLowerCase().includes(host), host);
  }
  assert.doesNotMatch(source, /VITE_EUROGAS_MAP_TILE_(URL|TOKEN|PROVIDER)|localStorage/);
  // Settings shows no provider choice at all.
  assert.doesNotMatch(readWebSource("src/components/SettingsCenter.tsx"), /map_tile|MAP_TILE|mapTileProviders/);
  for (const name of ["en", "zh"] as const) {
    assert.ok(!Object.keys(locale(name)).some((key) => key.startsWith("settings.map_tile")), name);
  }
});

test("the outline is the automatic fallback: offline, unreachable, or a China installation", async () => {
  const providers = await import("../src/app/mapTileProviders.ts");
  providers.setDeploymentMapDefault("outline");
  assert.equal(providers.configuredMapTileProviderId(), "outline");
  // Any retired value from an older server keeps OpenStreetMap.
  for (const retired of ["bundled", "tianditu", "custom", "none", null]) {
    providers.setDeploymentMapDefault(retired);
    assert.equal(providers.configuredMapTileProviderId(), "openfreemap", String(retired));
  }
  // The outline is served by the application itself and carries the label glyphs.
  const outline = providers.buildMapStyle("outline", { background: "#000" }, "dark") as unknown as {
    glyphs: string;
    sources: Record<string, { data: string }>;
  };
  assert.match(outline.glyphs, /basemaps\/glyphs\/\{fontstack\}\/\{range\}\.pbf$/);
  assert.match(outline.sources.land.data, /basemaps\/land-trading-region\.geojson$/);
  assert.ok(readWebSource("public/basemaps/land-trading-region.geojson").includes("Natural Earth"));
  // A style that never arrives falls back, and the map says so (only then).
  const map = readWebSource("src/components/GasNetworkMap.tsx");
  assert.match(map, /setUnreachableBasemap\(mapTileProvider\.id\)/);
  assert.match(map, /mapTileProviderById\("outline"\)/);
  assert.match(map, /showingOfflineOutline && \(/);
  for (const name of ["en", "zh"] as const) assert.ok(locale(name)["map.basemap.offline"], name);
});

test("the basemap stays quiet under the network", async () => {
  const { quietBasemapMinZoom, hiddenBasemapLayer } = await import("../src/app/mapTileProviders.ts");
  for (const id of ["label_country_1", "label_city_capital", "place_city_large", "water_name_point_label"]) {
    assert.equal(quietBasemapMinZoom(id, 3), null, id);
  }
  assert.equal(quietBasemapMinZoom("label_city", 3), 5.5);
  assert.equal(quietBasemapMinZoom("label_town", 6), 7.5);
  assert.equal(quietBasemapMinZoom("label_state", 5), 6);
  assert.equal(quietBasemapMinZoom("label_other", 8), 8);
  // Points of interest and buildings carry nothing a gas desk reads.
  assert.ok(hiddenBasemapLayer("poi_r1"));
  assert.ok(hiddenBasemapLayer("building"));
  assert.ok(!hiddenBasemapLayer("water"));
});
