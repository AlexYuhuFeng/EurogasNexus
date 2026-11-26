/**
 * One selection links the Network panel and the map, both ways, and the object's card lives in
 * the panel. The rules are tested in networkPanelModel.test.ts; this pins the wiring, by its
 * behaviour hooks rather than copy.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const read = (file: string) => readFileSync(new URL(`../src/${file}`, import.meta.url), "utf8");

test("the map reports its selection and view, takes a focus and a hover ring, and can leave the card to the page", () => {
  const map = read("components/GasNetworkMap.tsx");
  for (const prop of ["selection?: MapSelection | null;", "onSelectionChange?:", "detailCard?: boolean;", "onViewChange?:", "hoverAt?:", "at?: [number, number] | null;"]) {
    assert.ok(map.includes(prop), prop);
  }
  // Controlled when the page passes a selection; every change is reported either way.
  assert.match(map, /const selection = selectionControlled \? selectionProp : ownSelection;/);
  assert.match(map, /selectionOwnerRef\.current\.report\?\.\(next\);/);
  assert.match(map, /\{selection && detailCard && \(\s*<MapDetailPanel/);
  assert.match(map, /map\.on\("moveend", report\);/);
  assert.match(map, /element\.className = "map-hover-ring";/);
});

test("the Network page holds one selection for map and panel", () => {
  const page = read("components/NetworkWorkspace.tsx");
  assert.match(page, /selection=\{selection\}\s*\n[\s\S]*?onSelectionChange=\{selectOnMap\}/);
  assert.match(page, /detailCard=\{false\}/);
  assert.match(page, /onViewChange=\{setBounds\}/);
  // A row focuses the map on its object (or its place) ...
  assert.match(page, /setFocus\(\{ refId: target\.refId, at: target\.at/);
  // ... a map object filters the panel and its card heads it, without repeating its outages.
  assert.match(page, /selectionScope\(selection,/);
  assert.match(page, /<MapDetailPanel[\s\S]*?outagesListed/);
  // Phone width: a selected row brings the map back into view.
  assert.match(page, /if \(compactLayout\) shellRef\.current\?\.scrollIntoView/);
  // The book's panels are the fourth tab, in the book view, with book permission only.
  assert.match(page, /const showBookTab = mapView === "book" && canReadBook\(currentUser\?\.permissions\);/);
  assert.match(page, /book=\{bookPanels\}/);
  // Expanded keeps the whole instrument, by CSS: never the browser's Fullscreen API, which
  // blocks typing in the finder on macOS WebKit and the Tauri WebView.
  assert.match(page, /const expandedView = useExpandedView\(\);/);
  assert.doesNotMatch(page, /requestFullscreen|fullscreenElement/);
});

test("the panel's tabs count the current filter and its rows link to the map", () => {
  const panel = read("components/NetworkInfoPanel.tsx");
  assert.match(panel, /idPrefix="network-panel-tab"/);
  assert.match(panel, /data-panel-count=\{id\}/);
  assert.match(panel, /data-follow-map=/);
  assert.match(panel, /data-panel-scope=/);
  for (const grid of ["network-outages", "network-flows"]) assert.match(panel, new RegExp(`id="${grid}"`));
  assert.match(panel, /onRowAction=\{\(row\) => onSelectRow\(\{ tab: "outages"/);
  assert.match(panel, /onMouseOver: \(event/);
  // One unit per column, the desk's: GWh/d through the server's unit authority.
  assert.match(panel, /id: "offline",[\s\S]*?unit: "GWh\/d"/);
  // The server collapses messages to events; the list asks for that and for recently ended.
  assert.match(panel, /grouped: true, endedDays: OUTAGE_ENDED_DAYS/);
  // A row the map cannot place says so; it is not hidden.
  assert.match(panel, /data-outage-placement=\{row\.placement\}/);
});

test("the ticker, the list and a hub's card count the same outage events", () => {
  // The ticker reads the server's events, not its messages.
  assert.match(read("components/ShellTicker.tsx"), /\.outages\(14, undefined, \{ grouped: true \}\)/);
  // The page reads the events once; the panel lists them and a selected hub's card counts the
  // zone's events from the same rows, placed on the map or not.
  const page = read("components/NetworkWorkspace.tsx");
  assert.match(page, /const outageEvents = useOutageEvents\(\);/);
  assert.match(page, /outages=\{outageEvents\}/);
  assert.match(page, /inScope\(scope, \{ refId: row\.refId, name: row\.asset, country: row\.country, zone: row\.zone \}\)/);
  assert.match(page, /zoneOutages=\{zoneOutages\}/);
  const card = read("components/MapDetailPanel.tsx");
  assert.match(card, /const zone = \{ \.\.\.hubZone\(hub, situation, \{ nodes, edges \}\), \.\.\.\(zoneOutages \?\? \{\}\) \};/);
});
