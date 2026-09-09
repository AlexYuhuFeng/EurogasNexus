import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { marketTaskFromLocation } from "../src/app/model/marketCockpitModel.ts";
import {
  decisionTaskFromLocation,
  portfolioTaskFromLocation,
} from "../src/app/model/commercialWorkflowModel.ts";

function readWebSource(relativePath: string): string {
  return readFileSync(new URL(`../src/${relativePath}`, import.meta.url), "utf8");
}

test("consolidated headers expose the primary workspace and actual task labels", () => {
  const market = readWebSource("components/MarketCockpit.tsx");
  const portfolio = readWebSource("components/PortfolioWorkspace.tsx");
  const decision = readWebSource("components/DecisionWorkspace.tsx");

  assert.match(market, /title=\{t\("nav\.primary\.market"\)\}/);
  assert.match(market, /taskLabel=\{t\(`market\.task\.\$\{task\}`\)\}/);
  assert.match(portfolio, /title=\{t\("nav\.primary\.portfolio"\)\}/);
  assert.match(portfolio, /taskLabel=\{t\(`portfolio\.task\.\$\{task\}`\)\}/);
  assert.match(decision, /title=\{t\("nav\.primary\.decision"\)\}/);
  assert.match(decision, /taskLabel=\{t\(`decision\.task\.\$\{task\}`\)\}/);
});

test("initial, deep-link, and history task locations resolve the labels used by headers", () => {
  assert.equal(marketTaskFromLocation("", "market"), "overview");
  assert.equal(marketTaskFromLocation("?workspace=market&task=network", "market"), "network");
  assert.equal(portfolioTaskFromLocation(""), "overview");
  assert.equal(portfolioTaskFromLocation("?workspace=contracts&task=exposure"), "exposure");
  assert.equal(decisionTaskFromLocation("?workspace=scenario&task=optimize"), "optimize");
  assert.equal(decisionTaskFromLocation("?workspace=review&task=review"), "review");
});

test("only WorkspaceHeader owns the consolidated primary h1 and shared tab semantics remain delegated", () => {
  const header = readWebSource("components/ui/WorkspaceHeader.tsx");
  const renderer = readWebSource("app/workspaces/WorkspaceRenderer.tsx");

  assert.equal((header.match(/<h1>/g) ?? []).length, 1);
  assert.match(header, /<WorkspaceTabs/);
  assert.match(header, /idPrefix=\{idPrefix\}/);
  assert.match(header, /panelId=\{panelId\}/);
  assert.match(renderer, /usesConsolidatedHeader/);
  assert.match(renderer, /!usesConsolidatedHeader/);
  assert.match(renderer, /!usesConsolidatedHeader\s*&&\s*\(\s*<header/);
});
