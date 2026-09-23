import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

function readWebSource(relativePath: string): string {
  return readFileSync(new URL(`../src/${relativePath}`, import.meta.url), "utf8");
}

function block(source: string, startMarker: string, endMarker: string): string {
  const start = source.indexOf(startMarker);
  assert.notEqual(start, -1, `missing marker: ${startMarker}`);
  const end = source.indexOf(endMarker, start + startMarker.length);
  assert.notEqual(end, -1, `missing marker after ${startMarker}: ${endMarker}`);
  return source.slice(start, end);
}

const NUMERIC_TASK = '{task === "curves" && (';
const MAP_TASK = '{task === "network" && (';
const CAPACITY_TASK = '{task === "capacity" && (';

test("the numeric task mounts no map while the map task mounts the map", () => {
  const market = readWebSource("components/MarketCockpit.tsx");
  const numeric = block(market, NUMERIC_TASK, MAP_TASK);
  const mapView = block(market, MAP_TASK, CAPACITY_TASK);

  assert.match(numeric, /<MarketTerminal/);
  assert.equal(numeric.includes("GasNetworkMap"), false);
  assert.match(mapView, /<NetworkWorkspace/);

  // The fused overview dashboard is the only map mount inside the market shell,
  // and it is not the implicit landing task.
  assert.equal((market.match(/<GasNetworkMap/g) ?? []).length, 1);
  const mapMountIndex = market.indexOf("<GasNetworkMap");
  assert.ok(mapMountIndex > market.indexOf("function MarketOverview("));
  assert.ok(mapMountIndex < market.indexOf("export function MarketCockpit("));

  // The numeric terminal itself never mounts a map.
  assert.equal(readWebSource("components/MarketTerminal.tsx").includes("GasNetworkMap"), false);

  // The map view keeps its map, its legend and its verified/indicative gate.
  const network = readWebSource("components/NetworkWorkspace.tsx");
  assert.match(network, /<GasNetworkMap/);
  assert.match(network, /map-visual-legend/);
  assert.match(network, /buildVisibleMapNetworkLines/);
  assert.match(network, /networkGeometryState/);
});

test("the task switcher stays the shared primitive and remembers the chosen view", () => {
  const market = readWebSource("components/MarketCockpit.tsx");
  const controller = readWebSource("app/hooks/useAppController.ts");

  assert.match(market, /<WorkspaceHeader/);
  assert.match(market, /onActivate=\{openTask\}/);
  assert.match(market, /rememberTask\(next\)/);
  // One resolution, owned above the shell: the cockpit renders the task it returns and the shell
  // keys its layout class on the same value, so neither may resolve the preference again.
  assert.match(market, /const \{ task, rememberTask \} = marketView;/);
  assert.equal(market.includes("useMarketViewPreference("), false);
  assert.match(controller, /useMarketViewPreference\(\{/);
  assert.match(controller, /principalId: api\.currentUser\?\.principal_id \?\? null/);
  assert.equal(market.includes('role="tab"'), false);
  assert.equal(market.includes('role="tablist"'), false);
  // Resolving the task straight from the raw location would ignore the
  // persisted view, so the shell must not do it.
  assert.equal(market.includes("marketTaskFromLocation("), false);
});

test("neither view resets trader context when it mounts", () => {
  const market = readWebSource("components/MarketCockpit.tsx");

  assert.equal(market.includes("traderContext.setGasDay("), false);
  assert.equal(market.includes("traderContext.setDeliveryProduct("), false);

  const effects = market.match(/useEffect\(\(\) => \{[\s\S]*?\n  \}, \[[\s\S]*?\]\);/g) ?? [];
  assert.ok(effects.length >= 1, "expected the market shell effects to be discoverable");
  for (const effect of effects) {
    assert.equal(effect.includes("traderContext.set"), false);
    assert.equal(effect.includes("setGasDay"), false);
    assert.equal(effect.includes("setDeliveryProduct"), false);
    assert.equal(effect.includes("setHubId"), false);
  }

  const mapView = block(market, MAP_TASK, CAPACITY_TASK);
  assert.doesNotMatch(mapView, /gasDay=\{traderContext\.gasDay\}/);
  assert.doesNotMatch(mapView, /deliveryProduct=\{traderContext\.deliveryProduct\}/);
  assert.doesNotMatch(mapView, /hubId=\{traderContext\.hubId\}/);

  // Context stays owned by the global shell rather than being re-declared by
  // the map task. The map still consumes market evidence and selection state.
  const topbar = readWebSource("components/WorkspaceTopBar.tsx");
  assert.match(topbar, /value=\{gasDay\}/);
  assert.match(topbar, /value=\{deliveryProduct\}/);
  assert.match(topbar, /value=\{hubId \?\? ""\}/);

  const numeric = block(market, NUMERIC_TASK, MAP_TASK);
  assert.match(numeric, /focusedHub=\{traderContext\.hubId\}/);
  assert.match(numeric, /onHubChange=\{traderContext\.setHubId\}/);

  for (const component of ["components/MarketTerminal.tsx", "components/NetworkWorkspace.tsx"]) {
    const source = readWebSource(component);
    assert.equal(source.includes("traderContext"), false, `${component} takes context as props`);
    assert.equal(source.includes("setGasDay"), false, `${component} never resets the gas day`);
    assert.equal(source.includes("setDeliveryProduct"), false, `${component} never resets the product`);
  }
});

test("the map note and view labels are bilingual, explicit and placeholder-free", () => {
  const en = JSON.parse(readWebSource("i18n/en.json")) as Record<string, string>;
  const zh = JSON.parse(readWebSource("i18n/zh.json")) as Record<string, string>;
  const keys = [
    "market.view.numeric",
    "market.view.map",
    "market.map_context_note",
    "settings.market_default_view",
    "settings.market_default_view_help",
  ];

  for (const key of keys) {
    for (const [locale, catalogue] of [["en", en], ["zh", zh]] as const) {
      const value = catalogue[key];
      assert.equal(typeof value, "string", `${key} missing in ${locale}`);
      assert.ok(value.trim().length > 0, `${key} empty in ${locale}`);
      assert.equal(value.includes("?"), false, `${key} ${locale} uses an ASCII question mark`);
      assert.equal(value.includes("\uFFFD"), false, `${key} ${locale} carries a replacement character`);
    }
  }

  const noteEn = en["market.map_context_note"];
  const noteZh = zh["market.map_context_note"];
  assert.notEqual(noteEn, noteZh);
  assert.match(noteEn, /map/i);
  assert.match(noteEn, /numeric/i);
  assert.match(noteEn, /price evidence/i);
  assert.match(noteZh, /地图/);
  assert.match(noteZh, /数值/);
  // The old footnote wording is gone in both locales.
  assert.equal(noteEn.includes("use Network task for deep inspection"), false);
  assert.equal(noteZh.includes("地图为上下文视图"), false);
});

test("the market primary landing follows the persisted view without changing declared defaults", () => {
  const navigation = readWebSource("app/hooks/useWorkspaceNavigation.ts");
  const product = readWebSource("app/navigation/productNavigation.ts");

  // The declared product IA defaults are unchanged.
  assert.match(
    product,
    /id: "market",[\s\S]*?pages: \["network", "market", "capacity"\],[\s\S]*?defaultPage: "network"/,
  );
  assert.match(navigation, /coerceWorkspacePageId\(requestedWorkspace, DEFAULT_WORKSPACE_PAGE_ID\)/);
  assert.match(navigation, /defaultWorkspacePageForPrimary\(primary\)/);

  // An explicit URL wins; otherwise the persisted view; otherwise the default.
  assert.match(navigation, /requestedWorkspace === null/);
  assert.match(navigation, /marketViewLandingPageCandidate\(/);
  assert.match(navigation, /readMarketViewPreference\(marketViewPreferencePrincipalId\(\)\)/);
});

test("settings owns an explicit per-user default view choice", () => {
  const settings = readWebSource("components/SettingsCenter.tsx");
  const renderer = readWebSource("app/workspaces/WorkspaceRenderer.tsx");

  assert.match(settings, /market_default_view/);
  assert.match(settings, /readMarketViewPreference\(principalId\)/);
  assert.match(settings, /writeMarketViewPreference\(principalId, view\)/);
  assert.match(settings, /t\("settings\.market_default_view"\)/);
  assert.match(settings, /<option value="curves">\{t\("market\.view\.numeric"\)\}<\/option>/);
  assert.match(settings, /<option value="network">\{t\("market\.view\.map"\)\}<\/option>/);
  assert.match(settings, /eurogas\.settings\.preferences/);
  assert.match(renderer, /principalId=\{api\.currentUser\?\.principal_id \?\? null\}/);
});

test("the view preference module and hook are exported through the context boundary", () => {
  const barrel = readWebSource("app/context/index.ts");

  assert.match(barrel, /export \* from "\.\/viewPreference"/);
  assert.match(barrel, /export \{ useMarketViewPreference \} from "\.\/useMarketViewPreference"/);
});
