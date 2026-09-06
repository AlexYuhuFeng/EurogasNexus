import assert from "node:assert/strict";
import test from "node:test";
import {
  defaultWorkspacePageForPrimary,
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
  assert.equal(seen.size, 15);
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
    system: "sources",
  });
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
    sources: "system",
    runtime: "system",
    settings: "system",
    manual: "system",
    glossary: "system",
    research: "system",
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
  ]) {
    assert.equal(isWorkspacePageId(page), true);
  }
});
