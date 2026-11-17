/**
 * Four-mode navigation (WF-05): Desk, Deals, Book, Research. Every address that worked before keeps
 * working and lands in its new place; old area addresses redirect; a task the role cannot use is
 * absent; Decision Center is gone as an area and each of its tasks has a home.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import {
  PRODUCT_MODES,
  legacyAddresses,
  modeLanding,
  modeLocationFor,
  modeLocationFromSearch,
  pageTaskFromLocation,
  redirectSearch,
  visibleModes,
} from "../src/app/navigation/modeNavigation.ts";
import { workspacePageIds, type WorkspacePageId } from "../src/workspaceNavigation.ts";
import { registeredViews } from "../src/app/navigation/viewRegistry.ts";
import type { CurrentUserDTO } from "../src/api/client.ts";

const en = JSON.parse(readFileSync(new URL("../src/i18n/en.json", import.meta.url), "utf8")) as Record<string, string>;
const zh = JSON.parse(readFileSync(new URL("../src/i18n/zh.json", import.meta.url), "utf8")) as Record<string, string>;

/** Where a URL lands: the redirect applied, then the mode and task of the page address. */
function lands(search: string): string {
  const canonical = redirectSearch(search) ?? search.replace(/^\?/, "");
  const page = (new URLSearchParams(canonical).get("workspace") ?? "market") as WorkspacePageId;
  const location = modeLocationFromSearch(page, canonical);
  return location ? `${location.mode.id}/${location.task.id}` : `utility/${page}`;
}

test("the primary row is four modes in the plan's order, each with its tasks", () => {
  assert.deepEqual(PRODUCT_MODES.map((mode) => mode.id), ["desk", "deals", "book", "research"]);
  assert.deepEqual(PRODUCT_MODES.map((mode) => mode.tasks.map((task) => task.id)), [
    ["today", "prices", "network"],
    ["evaluate", "optimise", "routes", "contracts", "review"],
    ["position", "limits", "delivery", "nominations", "storage"],
    ["strategies", "reports", "data", "assistant"],
  ]);
});

test("every page address keeps working and lands in its mode (no page id redirects)", () => {
  const expected: Record<WorkspacePageId, string> = {
    market: "desk/prices",
    network: "desk/network",
    // "Outages & capacity" is the Network page's panel now; its page address lands there.
    capacity: "desk/network",
    scenario: "deals/evaluate",
    review: "deals/review",
    contracts: "book/position",
    orders: "book/limits",
    strategy: "research/strategies",
    research: "research/data",
    agents: "research/assistant",
    sources: "utility/sources",
    runtime: "utility/runtime",
    access: "utility/access",
    settings: "utility/settings",
    manual: "utility/manual",
    glossary: "utility/glossary",
  };
  assert.deepEqual(Object.keys(expected).sort(), [...workspacePageIds].sort());
  for (const page of workspacePageIds) {
    assert.equal(redirectSearch(`?workspace=${page}`), null, page);
    assert.equal(lands(`?workspace=${page}`), expected[page], page);
  }
});

test("every old task address lands on its new task; Decision Center's tasks each have a home", () => {
  const expected: Record<string, string> = {
    "market.overview": "desk/today",
    "market.curves": "desk/prices",
    "market.network": "desk/network",
    // The retired task lands on Network (its Capacity tab, networkPanelModel).
    "market.capacity": "desk/network",
    "contracts.overview": "book/position",
    "contracts.exposure": "book/limits",
    "contracts.delivery": "book/delivery",
    "contracts.resources": "deals/contracts",
    "contracts.routes": "deals/routes",
    // Decision Center dissolved: scenario and optimisation are Deals → Evaluate and Optimise;
    // review sits with the deals it approves; nomination and storage planning are Book views.
    "scenario.scenario": "deals/evaluate",
    "scenario.optimize": "deals/optimise",
    "scenario.review": "deals/review",
    "scenario.nomination": "book/nominations",
    "scenario.dispatch": "book/storage",
  };
  for (const [key, where] of Object.entries(expected)) {
    const [page, task] = key.split(".");
    assert.equal(redirectSearch(`?workspace=${page}&task=${task}`), null, key);
    assert.equal(lands(`?workspace=${page}&task=${task}`), where, key);
  }
  // Every task the URL registry declares on a mode page is covered above.
  for (const entry of registeredViews().filter((item) => item.param === "task" && ["market", "contracts", "scenario"].includes(item.page))) {
    assert.ok(`${entry.page}.${entry.view}` in expected, `${entry.page}.${entry.view} has no declared landing`);
  }
});

test("old area addresses and mode addresses redirect to a page address, keeping the context", () => {
  const cases: Record<string, string> = {
    "?workspace=decision": "workspace=scenario&task=scenario",
    "?workspace=portfolio": "workspace=contracts&task=overview",
    "?workspace=system": "workspace=manual",
    "?workspace=administration": "workspace=sources",
    "?workspace=optimize": "workspace=scenario&task=optimize",
    "?workspace=nomination": "workspace=scenario&task=nomination",
    "?workspace=dispatch": "workspace=scenario&task=dispatch",
    "?workspace=exposure": "workspace=contracts&task=exposure",
    "?workspace=desk": "workspace=market&task=overview",
    "?workspace=deals": "workspace=scenario&task=scenario",
    "?workspace=book": "workspace=contracts&task=overview",
    "?workspace=research": null as unknown as string,
    "?workspace=book&task=limits": "workspace=contracts&task=exposure",
    "?mode=deals&task=review": "workspace=scenario&task=review",
    "?mode=book&task=storage": "workspace=scenario&task=dispatch",
    "?mode=research&task=assistant": "workspace=agents",
  };
  for (const [from, to] of Object.entries(cases)) {
    // `research` is a page id (Research Data) as well as a mode: the page address wins.
    assert.equal(redirectSearch(from), to, from);
    if (to) assert.equal(redirectSearch(`?${to}`), null, `${from} is stable after one redirect`);
  }
  for (const address of legacyAddresses()) assert.ok(`?workspace=${address}` in cases, address);
  // Gas day, hub and other context ride along.
  assert.equal(redirectSearch("?workspace=decision&gasDay=2026-11-15&hub=TTF"), "workspace=scenario&task=scenario&gasDay=2026-11-15&hub=TTF");
  // An unknown mode is dropped, the page address stands.
  assert.equal(redirectSearch("?mode=zzz&workspace=market&task=curves"), "workspace=market&task=curves");
  assert.equal(redirectSearch("?workspace=unknown"), null);
});

function user(roles: string[], permissions: string[] | undefined, commercial = true): CurrentUserDTO {
  return {
    principal_id: "p",
    role: roles[0],
    roles,
    permissions,
    experience: { commercial_capabilities: commercial ? ["market.read"] : [] },
  } as unknown as CurrentUserDTO;
}

test("a mode or task the role cannot use is absent; a mode never grants anything", () => {
  const viewer = ["me.read", "market.read", "portfolio.read", "strategy.read", "review.read", "source.read", "runtime.read", "capability.read", "agent.read"];
  const reviewer = [...viewer, "review.record"];
  const analyst = [...viewer, "portfolio.write", "strategy.create", "scenario.create", "optimization.run", "analysis.query", "agent.research"];
  const ids = (u: CurrentUserDTO | null) => visibleModes(u).map((mode) => `${mode.id}:${mode.tasks.map((task) => task.id).join(",")}`);

  // An administrator without a commercial role sees no mode (separation of duties).
  assert.deepEqual(ids(user(["ADMIN"], ["identity.manage", "source.read"], false)), []);
  // A reviewer reviews and reads, but prepares no nomination or storage plan.
  assert.deepEqual(ids(user(["REVIEWER"], reviewer)), [
    "desk:today,prices,network",
    "deals:evaluate,optimise,routes,contracts,review",
    "book:position,limits,delivery",
    "research:strategies,reports,data,assistant",
  ]);
  assert.equal(modeLanding("book", user(["REVIEWER"], reviewer))?.id, "position");
  // An analyst has everything.
  assert.equal(visibleModes(user(["ANALYST"], analyst)).reduce((sum, mode) => sum + mode.tasks.length, 0), 17);
  // No identity, or an older server without a permission list: what it had before.
  assert.equal(visibleModes(null).length, 4);
  assert.equal(visibleModes(user(["TRADER"], undefined)).length, 4);
  // The module makes no access decision of its own.
  const source = readFileSync(new URL("../src/app/navigation/modeNavigation.ts", import.meta.url), "utf8");
  assert.doesNotMatch(source, /fetch\(|api\.|localStorage/);
});

test("every mode and task label exists in English and Chinese, in words", () => {
  const keys = PRODUCT_MODES.flatMap((mode) => [mode.labelKey, mode.descriptionKey, ...mode.tasks.map((task) => task.labelKey)]);
  for (const key of [...keys, "nav.mode.tasks", "topbar.open_help", "topbar.utilities"]) {
    assert.ok(en[key]?.trim(), `en ${key}`);
    assert.ok(zh[key]?.trim(), `zh ${key}`);
    assert.doesNotMatch(zh[key], /\?/, `zh ${key} has an ASCII question mark`);
    assert.notEqual(zh[key], en[key], `zh ${key} is untranslated`);
  }
  // Old names stay translatable: the palette finds them as aliases.
  for (const key of PRODUCT_MODES.flatMap((mode) => [...mode.aliasKeys, ...mode.tasks.flatMap((task) => task.aliasKeys ?? [])])) {
    assert.ok(en[key] && zh[key], key);
  }
});

test("Reports is a task of the Research page, held in the URL (task=reports)", () => {
  assert.equal(pageTaskFromLocation("research", "?workspace=research&task=reports"), "reports");
  assert.equal(pageTaskFromLocation("research", "?workspace=research&view=features"), undefined);
  assert.equal(modeLocationFor("research", "reports")?.task.id, "reports");
  assert.equal(modeLocationFor("research", undefined)?.task.id, "data");
});
