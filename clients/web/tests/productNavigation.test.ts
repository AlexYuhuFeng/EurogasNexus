import assert from "node:assert/strict";
import test from "node:test";
import {
  controlPlanePrimaries,
  defaultWorkspacePageForPrimary,
  isControlPlanePage,
  isPrimaryWorkspaceId,
  primaryWorkspaceForId,
  primaryWorkspaceForPage,
  primaryWorkspaces,
} from "../src/app/navigation/productNavigation.ts";
import {
  coerceWorkspacePageId,
  DEFAULT_WORKSPACE_PAGE_ID,
  isWorkspacePageId,
} from "../src/workspaceNavigation.ts";

test("every technical workspace resolves to exactly one primary", () => {
  const seen = new Set<string>();
  for (const primary of primaryWorkspaces) {
    for (const page of primary.pages) {
      assert.equal(primaryWorkspaceForPage(page).id, primary.id);
      assert.equal(seen.has(page), false, `duplicate child: ${page}`);
      seen.add(page);
    }
  }
  assert.equal(seen.size, 16);
});

test("primary workspace defaults match the accepted architecture", () => {
  const defaults = Object.fromEntries(
    primaryWorkspaces.map((primary) => [primary.id, defaultWorkspacePageForPrimary(primary)]),
  );
  assert.deepEqual(defaults, {
    market: "network",
    portfolio: "contracts",
    strategy: "strategy",
    decision: "scenario",
    system: "research",
    administration: "sources",
  });
});

test("the administration surface is the declared control plane", () => {
  assert.deepEqual(
    controlPlanePrimaries().map((primary) => primary.id),
    ["administration"],
  );
  assert.deepEqual(primaryWorkspaceForId("administration")?.pages, [
    "sources",
    "runtime",
    "access",
  ]);

  for (const page of ["sources", "runtime", "access"] as const) {
    assert.equal(isControlPlanePage(page), true, page);
  }
  for (const page of [
    "market",
    "network",
    "contracts",
    "strategy",
    "review",
    "research",
    "agents",
    "settings",
    "manual",
    "glossary",
  ] as const) {
    assert.equal(isControlPlanePage(page), false, page);
  }
});

test("old technical workspace ids continue to resolve", () => {
  const expected = {
    network: "market",
    market: "market",
    capacity: "market",
    contracts: "portfolio",
    orders: "portfolio",
    strategy: "strategy",
    scenario: "decision",
    review: "decision",
    sources: "administration",
    runtime: "administration",
    settings: "system",
    manual: "system",
    glossary: "system",
    research: "system",
    agents: "system",
  };
  for (const [page, primary] of Object.entries(expected)) {
    assert.equal(primaryWorkspaceForPage(page as keyof typeof expected).id, primary);
  }
});

test("invalid workspace values fall back to the centralized default", () => {
  assert.equal(coerceWorkspacePageId("does-not-exist"), DEFAULT_WORKSPACE_PAGE_ID);
  assert.equal(coerceWorkspacePageId(null), DEFAULT_WORKSPACE_PAGE_ID);
  assert.equal(coerceWorkspacePageId(""), DEFAULT_WORKSPACE_PAGE_ID);
  assert.equal(DEFAULT_WORKSPACE_PAGE_ID, "network");
});

test("primary workspace guard helpers are strict", () => {
  assert.equal(isPrimaryWorkspaceId("market"), true);
  assert.equal(isPrimaryWorkspaceId("system"), true);
  assert.equal(isPrimaryWorkspaceId("orders"), false);
  assert.equal(primaryWorkspaceForId("strategy")?.labelKey, "nav.primary.strategy");
  assert.equal(primaryWorkspaceForId("missing"), undefined);
});

test("technical page guard helpers preserve all old route ids", () => {
  for (const page of [
    "network",
    "capacity",
    "market",
    "scenario",
    "contracts",
    "strategy",
    "review",
    "orders",
    "sources",
    "glossary",
    "runtime",
    "settings",
    "manual",
    "research",
    "agents",
  ]) {
    assert.equal(isWorkspacePageId(page), true);
  }
});
