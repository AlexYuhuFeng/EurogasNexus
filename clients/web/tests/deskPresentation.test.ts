/**
 * Desk presentation refinements (design pass round 3): lineage in words, the tenor Prices opens
 * on, one Today request per navigation, and figures that keep one height with their notes.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test, { after } from "node:test";
import { createElement as h } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { lineageNames, resourceName } from "../src/app/model/lineageNames.ts";
import { boardTenorFromSearch, boardTenorToSearch, openingBoardTenor } from "../src/app/model/marketCockpitModel.ts";
import type { DeskTodayDTO } from "../src/api/client.ts";
import { closeApiStoreHarness, loadApiStore } from "./support/apiStoreHarness.ts";

after(closeApiStoreHarness);

async function deskCache() {
  const { load } = await loadApiStore();
  return load<typeof import("../src/app/hooks/useDeskToday.ts")>("/src/app/hooks/useDeskToday.ts");
}

const t = (key: string, options?: Record<string, unknown>) =>
  options && Object.keys(options).length ? `${key}(${Object.entries(options).map(([k, v]) => `${k}=${String(v)}`).join(",")})` : key;

test("lineage references read as names; the identifiers stay available", () => {
  const lookup = {
    resources: new Map([["demo-haldor-24", "Haldor supply (Easington)"]]),
    routes: new Map([["demo-route-ttf-local", "TTF local disposal"]]),
  };
  const names = lineageNames(
    [
      "upstream_resource_contract:demo-haldor-24",
      "route_candidate:demo-route-ttf-local",
      "market_observation:demo-TTF-ma-1",
      "demo_route_template",
      "upstream_resource_contract:demo-haldor-24",
      "upstream_resource_contract:unknown-7",
    ],
    lookup,
    t,
  );
  assert.deepEqual(names.map((entry) => entry.name), [
    "Haldor supply (Easington) lineage.kind.contract",
    "TTF local disposal",
    "lineage.price_of(name=TTF MA)",
    "lineage.kind.route_template",
    "lineage.kind.contract unknown-7",
  ]);
  // Duplicates collapse; every visible name keeps its identifier for the disclosure.
  assert.equal(names[0].ref, "upstream_resource_contract:demo-haldor-24");
  for (const entry of names) assert.doesNotMatch(entry.name, /^[a-z_]+:/);
  assert.equal(resourceName("demo-haldor-24", lookup), "Haldor supply (Easington)");
  assert.equal(resourceName("other", lookup), "other");
});

test("Prices opens on the first tenor the desk has prices for; an explicit choice wins", () => {
  assert.equal(openingBoardTenor(null, new Set(["month-ahead"])), "month-ahead");
  assert.equal(openingBoardTenor(null, new Set(["month-ahead", "day-ahead"])), "day-ahead");
  assert.equal(openingBoardTenor(null, new Set(["weekend", "within-day"])), "within-day");
  assert.equal(openingBoardTenor(null, new Set()), "day-ahead");
  assert.equal(openingBoardTenor("weekend", new Set(["month-ahead"])), "weekend");
  // The URL carries the choice; an unknown tenor is no choice.
  assert.equal(boardTenorFromSearch("?workspace=market&tenor=weekend"), "weekend");
  assert.equal(boardTenorFromSearch("?workspace=market&tenor=bogus"), null);
  assert.equal(boardTenorFromSearch(boardTenorToSearch("workspace=market&task=curves", "month-ahead")), "month-ahead");
});

test("Today is one request per navigation: concurrent readers share it, a refresh asks again", async () => {
  const { clearDeskTodayCache, deskTodayKey, deskTodaySnapshot, loadDeskToday, setDeskTodayFetcher } = await deskCache();
  clearDeskTodayCache();
  let calls = 0;
  let resolve: (value: { data: DeskTodayDTO }) => void = () => undefined;
  setDeskTodayFetcher(() => {
    calls += 1;
    return new Promise((done) => {
      resolve = done;
    });
  });
  const key = deskTodayKey("p-1", Date.parse("2026-11-15T10:00:00Z"));
  assert.equal(key, "p-1|2026-11-15");
  // Four readers mount (StrictMode doubles two components): one request.
  const pending = [loadDeskToday(key), loadDeskToday(key), loadDeskToday(key), loadDeskToday(key)];
  assert.equal(calls, 1);
  assert.equal(deskTodaySnapshot(key).loading, true);
  resolve({ data: { gas_day: "2026-11-15" } as DeskTodayDTO });
  await Promise.all(pending);
  assert.equal(deskTodaySnapshot(key).today?.gas_day, "2026-11-15");
  // Within the same navigation the read is reused.
  await loadDeskToday(key);
  assert.equal(calls, 1);
  // Another caller never sees it.
  assert.equal(deskTodaySnapshot(deskTodayKey("p-2", Date.parse("2026-11-15T10:00:00Z"))).today, null);
  // Refresh is explicit and asks again.
  const again = loadDeskToday(key, true);
  assert.equal(calls, 2);
  resolve({ data: { gas_day: "2026-11-15" } as DeskTodayDTO });
  await again;
  clearDeskTodayCache();
  assert.equal(deskTodaySnapshot(key).today, null);
});

test("a figure's notes sit on its label line as quiet links", async () => {
  const { load } = await loadApiStore();
  const { KeyFigure } = await load<typeof import("../src/components/ui/index.ts")>("/src/components/ui/index.ts");
  const html = renderToStaticMarkup(
    h(KeyFigure, {
      label: "Mark-to-market",
      value: "1",
      notes: h("button", { type: "button", className: "ds-inline-link" }, "Method"),
    }),
  );
  assert.match(html, /<span class="key-figure-head"><span id="[^"]+" title="Mark-to-market">Mark-to-market<\/span><span class="key-figure-notes"><button type="button" class="ds-inline-link">Method<\/button><\/span><\/span><strong>/);
  assert.doesNotMatch(html, /key-figure-action/);
  // The inline link is a dense control for the pointer that gives the line back.
  const css = readFileSync(new URL("../src/components/ui/controls.css", import.meta.url), "utf8");
  assert.match(css, /\.ds-inline-link \{[^}]*height: var\(--ds-control-sm\);[^}]*margin-block: calc\(\(var\(--ds-line-xs\) - var\(--ds-control-sm\)\) \/ 2\);/);
});

test("positions read by their sign in neutral ink; only P&L takes colour", () => {
  const grid = readFileSync(new URL("../src/components/ui/datagrid.css", import.meta.url), "utf8");
  assert.match(grid, /\.ds-grid \.is-long,\s*\.ds-grid \.is-short \{ color: var\(--ds-text-1\); \}/);
  assert.doesNotMatch(grid, /\.is-long[^{]*\{[^}]*--ds-positive/);
  const today = readFileSync(new URL("../src/components/today.css", import.meta.url), "utf8");
  assert.doesNotMatch(today, /\.is-long|\.is-short/);
});
