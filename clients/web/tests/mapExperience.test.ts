/** Map zoom, labels, icons and the finder: the "zoom in and see where things are" experience. */
import assert from "node:assert/strict";
import test from "node:test";
import { findPlaces, type MapFinderPlace } from "../src/app/mapFinder.ts";
import { labelBudgetForZoom, mapZoomRange } from "../src/app/mapTileProviders.ts";
import { FACILITY_ICON, facilityIconId } from "../src/app/mapIcons.ts";

const place = (name: string, kind = "Hub"): MapFinderPlace => ({ id: name, name, kind, lon: 0, lat: 0, zoom: 6 });

test("detailed basemaps zoom to street level; outline and plain stop at regional scale", () => {
  assert.deepEqual(mapZoomRange("openfreemap"), { minZoom: 2, maxZoom: 17 });
  assert.deepEqual(mapZoomRange("tianditu"), { minZoom: 2, maxZoom: 17 });
  assert.equal(mapZoomRange("outline").maxZoom, 10);
  assert.equal(mapZoomRange("none").maxZoom, 10);
});

test("labels grow as the view narrows", () => {
  assert.ok(labelBudgetForZoom(4) < labelBudgetForZoom(6));
  assert.ok(labelBudgetForZoom(6) < labelBudgetForZoom(9));
});

test("finder ranks name starts, then word starts, then anywhere", () => {
  const places = [place("Isle of Grain", "LNG terminal"), place("Grain storage"), place("Gate terminal"), place("Bacton")];
  assert.deepEqual(findPlaces(places, "grain").map((p) => p.name), ["Grain storage", "Isle of Grain"]);
  assert.deepEqual(findPlaces(places, "at").map((p) => p.name), ["Gate terminal"]);
  assert.deepEqual(findPlaces(places, "  "), []);
});

test("every infrastructure type has a distinct, themed icon", () => {
  assert.equal(FACILITY_ICON.production_platform.shape, "triangle");
  assert.equal(FACILITY_ICON.lng_terminal.family, "lng");
  assert.equal(facilityIconId("storage", "dark"), "infra-storage-dark");
  assert.equal(facilityIconId("unknown_kind", "light"), "infra-power_plant-light");
});
