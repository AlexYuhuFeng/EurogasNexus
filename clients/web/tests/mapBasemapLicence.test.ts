/**
 * D4: the basemap decision, held to what the audience it serves needs.
 *
 * The audience is a deployment IT and commercial team receiving a commercially licensed product.
 * What it needs from this file is that the product never implies a licence the customer does not
 * hold, that an unconfigured basemap is a *stated* state rather than a blank map, and that a
 * provider whose terms exclude commercial use cannot be reached without the operator choosing it.
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

test("no third-party basemap is the default", () => {
  const source = readWebSource("src/app/mapTileProviders.ts");

  assert.match(source, /export const DEFAULT_MAP_TILE_PROVIDER_ID: MapTileProviderId = "none";/);
  // The old default was chosen from the browser's language, which put AMap's public endpoint in
  // front of a Chinese-locale operator without anybody deciding it.
  assert.doesNotMatch(source, /navigator\.language/);
  // And the endpoint the policy excludes is no longer the fallback branch of the style builder.
  assert.match(source, /if \(providerId === "none"\)/);
});

test("every provider declares its licence state, and the excluded ones say so", () => {
  const source = readWebSource("src/app/mapTileProviders.ts");

  const restricted = ["osm", "carto", "amap"];
  for (const id of restricted) {
    // Each of the three carries the state on its own record rather than in prose.
    const block = source.slice(source.indexOf(`id: "${id}"`));
    const record = block.slice(0, block.indexOf("},"));
    assert.match(record, /licence: "not-for-commercial-use"/, id);
  }
  for (const id of ["none", "custom", "tianditu"]) {
    const block = source.slice(source.indexOf(`id: "${id}"`));
    const record = block.slice(0, block.indexOf("},"));
    assert.match(record, /licence: "licensed-by-deployment"/, id);
  }

  const settings = readWebSource("src/components/SettingsCenter.tsx");
  // The licence travels to the control that selects the provider, not only to a document.
  assert.match(settings, /settings\.map_tile_licence_evaluation/);
  assert.match(settings, /settings\.map_tile_licence_deployment/);
  assert.match(settings, /settings\.map_tile_provider_\$\{selectedMapTileProvider\.id\}/);
});

test("the map states an absent or unusable basemap instead of drawing nothing", () => {
  const map = readWebSource("src/components/GasNetworkMap.tsx");

  assert.match(map, /mapTileBasemapState\(mapTileProvider, configuredMapTileToken\(\)\)/);
  assert.match(map, /basemapState !== "configured"/);
  assert.match(map, /t\(\s*basemapState === "no-basemap"\s*\?\s*"map\.basemap\.none"\s*:\s*"map\.basemap\.unavailable",?\s*\)/);
  assert.match(map, /map\.basemap\.none_detail/);
  assert.match(map, /map\.basemap\.unavailable_detail/);

  // "No basemap chosen" and "the chosen basemap cannot be drawn" are different sentences, and
  // neither is an empty state.
  const keys = locale("en");
  assert.notEqual(keys["map.basemap.none"], keys["map.basemap.unavailable"]);
  assert.ok(keys["map.basemap.none_detail"].length > 40);
  assert.ok(keys["map.basemap.unavailable_detail"].length > 40);
});

test("a custom source is drawn only with a configured template", () => {
  const source = readWebSource("src/app/mapTileProviders.ts");

  assert.match(source, /VITE_EUROGAS_MAP_TILE_URL/);
  assert.match(source, /VITE_EUROGAS_MAP_TILE_ATTRIBUTION/);
  // An operator's licence decides the attribution, so it is taken from configuration and only
  // attached when it is declared.
  assert.match(source, /\(attribution \? \{ attribution \} : \{\}\)/);
  // Without a template the custom provider cannot be drawn, and says so rather than drawing empty.
  assert.match(
    source,
    /if \(providerId === "custom"\) \{\s*const template = configuredCustomTileTemplate\(\);\s*if \(!template\) \{/,
  );
});

test("every basemap sentence exists in both locales, distinguishable and without a question mark", () => {
  const en = locale("en");
  const zh = locale("zh");
  const keys = [
    "map.basemap.none",
    "map.basemap.none_detail",
    "map.basemap.unavailable",
    "map.basemap.unavailable_detail",
    "settings.map_tile_licence_deployment",
    "settings.map_tile_licence_evaluation",
    "settings.map_tile_provider_none",
    "settings.map_tile_provider_custom",
    "settings.map_tile_provider_tianditu",
    "settings.map_tile_provider_osm",
    "settings.map_tile_provider_carto",
    "settings.map_tile_provider_amap",
    "settings.map_tile_custom_detail",
  ];

  for (const key of keys) {
    assert.ok(en[key], `en missing ${key}`);
    assert.ok(zh[key], `zh missing ${key}`);
    assert.notEqual(en[key], zh[key], `untranslated ${key}`);
    assert.ok(!en[key].includes("?"), `en carries a question mark: ${key}`);
    assert.ok(!zh[key].includes("?"), `zh carries a question mark: ${key}`);
  }
});

test("the deployment can choose its own source without touching code", () => {
  const source = readWebSource("src/app/mapTileProviders.ts");

  // Configuration channels: build-time env for the provider, the URL, the attribution and the
  // token; a stored preference for the operator's own choice in the UI.
  for (const variable of [
    "VITE_EUROGAS_MAP_TILE_PROVIDER",
    "VITE_EUROGAS_MAP_TILE_URL",
    "VITE_EUROGAS_MAP_TILE_ATTRIBUTION",
    "VITE_EUROGAS_MAP_TILE_TOKEN",
  ]) {
    assert.ok(source.includes(variable), variable);
  }
  assert.match(source, /MAP_TILE_STORAGE_KEY/);
});
