import assert from "node:assert/strict";
import test from "node:test";
import {
  PAGE_VIEW_REGISTRY,
  objectFromSearch,
  registeredViews,
  viewFromSearch,
  viewToSearch,
} from "../src/app/navigation/viewRegistry.ts";
import { workspaceTaskSearch } from "../src/workspaceNavigation.ts";

test("every registered sub-view round-trips through the URL (#31)", () => {
  const views = registeredViews();
  assert.ok(views.length >= 30, `only ${views.length} registered views`);
  for (const { page, view } of views) {
    const search = viewToSearch("gasDay=2026-11-05&hub=NBP", page, view);
    assert.equal(viewFromSearch(page, search), view, `${page}/${view}`);
    // Encoding again yields the same URL, and the trading context survives.
    assert.equal(viewToSearch(search, page, view), search, `${page}/${view} is stable`);
    const params = new URLSearchParams(search);
    assert.equal(params.get("gasDay"), "2026-11-05");
    assert.equal(params.get("hub"), "NBP");
  }
});

test("an unknown or stale sub-view falls back to the page's default", () => {
  for (const [page, entry] of Object.entries(PAGE_VIEW_REGISTRY)) {
    const search = `workspace=${page}&${entry!.param}=no-such-view`;
    assert.equal(viewFromSearch(page as never, search), entry!.defaultView, page);
  }
});

test("the admin and research pages keep their view in the URL", () => {
  for (const [page, view] of [
    ["sources", "catalog"],
    ["runtime", "support"],
    ["access", "api_keys"],
    ["research", "targets"],
    ["agents", "runs"],
  ] as const) {
    assert.equal(viewFromSearch(page, `workspace=${page}&view=${view}`), view);
  }
});

test("an object id belongs to its page and is dropped elsewhere", () => {
  const sources = viewToSearch("", "sources", "catalog", { source: "src-ecb" });
  assert.equal(objectFromSearch("sources", "source", sources), "src-ecb");
  // Another page's view does not inherit the selected source.
  const market = viewToSearch(sources, "market", "curves");
  assert.equal(new URLSearchParams(market).get("source"), null);
  // Opening a workspace from the shell clears it too, and the stale sub-view.
  const opened = new URLSearchParams(workspaceTaskSearch(sources, "contracts", "resources"));
  assert.equal(opened.get("source"), null);
  assert.equal(opened.get("view"), null);
  assert.equal(opened.get("task"), "resources");
  // The contract a link names is kept on its own page.
  const contract = viewToSearch("", "contracts", "resources", { contract: "ttf-supply-2026" });
  assert.equal(objectFromSearch("contracts", "contract", contract), "ttf-supply-2026");
  assert.equal(objectFromSearch("market", "contract", contract), null);
});

test("a secret never has a place in the URL model", () => {
  const params = Object.values(PAGE_VIEW_REGISTRY).flatMap((entry) => entry?.objectParams ?? []);
  for (const name of params) assert.equal(/key|token|secret|password/i.test(name), false, name);
});

test("the palette offers every registered sub-view under a translated label (#31)", async () => {
  const { navigationCommands, paletteLabel } = await import("../src/app/experience/commandPalette.ts");
  const en = (await import("../src/i18n/en.json", { with: { type: "json" } })).default as Record<string, string>;
  const zh = (await import("../src/i18n/zh.json", { with: { type: "json" } })).default as Record<string, string>;
  const commands = navigationCommands().filter((command) => command.target.view);
  const expected = registeredViews().filter((entry) => entry.page !== "glossary");
  assert.equal(commands.length, expected.length);
  for (const entry of expected) {
    assert.ok(en[entry.labelKey], `missing en label ${entry.labelKey}`);
    assert.ok(zh[entry.labelKey], `missing zh label ${entry.labelKey}`);
  }
  const catalog = commands.find((command) => command.id === "navigate.view.sources.catalog")!;
  assert.equal(paletteLabel(catalog, (key) => en[key] ?? key), "Data Sources · Catalog");
});
