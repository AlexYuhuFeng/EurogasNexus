/** Source wiring contracts; computed layout is verified in the browser. */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { primaryWorkspaceForPage } from "../src/app/navigation/productNavigation.ts";
import { headerModeForPage } from "../src/app/experience/workspacePatterns.ts";

function source(path: string): string {
  return readFileSync(new URL(`../src/${path}`, import.meta.url), "utf8");
}

test("the composed network page declares its visible flex layout", () => {
  assert.match(source("styles/app.css"),
    /\.cockpit-app\.workspace-network \.workspace-page\s*\{\s*display: flex;/);
});

test("the legacy map hiding rule excludes the network layout", () => {
  assert.match(source("styles/app.css"),
    /\.cockpit-app:not\(\.workspace-network\) \.map-stage,/);
});

test("the network task wrappers share the flex column declaration", () => {
  assert.match(source("components/market-cockpit.css"),
    /\.workspace-network \.market-cockpit,\s*\.workspace-network \.market-cockpit-panel\s*\{\s*display: flex;\s*flex-direction: column;\s*flex: 1 1 auto;/);
});

test("rendered network wrappers retain their stylesheet hooks", () => {
  const cockpit = source("components/MarketCockpit.tsx");
  assert.match(cockpit, /<div className="market-cockpit">/);
  assert.match(cockpit, /<div id="market-cockpit-panel" className="market-cockpit-panel">/);
  const network = source("components/NetworkWorkspace.tsx");
  assert.match(network, /<div className="network-workspace-shell">/);
  assert.ok(network.includes('className="map-container map-stage network-map-stage"'));
});

test("one renderer composes the market task with its resolved layout", () => {
  assert.equal(primaryWorkspaceForPage("network").id, "market");
  assert.equal(headerModeForPage("network"), "consolidated");
  const shell = source("app/shell/AppShell.tsx");
  assert.match(shell, /className=\{`app cockpit-app workspace-\$\{layoutPage\}`\}/);
  assert.match(shell, /task: marketView.task/);
  assert.match(shell, /<main className="app-main"[\s\S]*?<WorkspaceRenderer controller=\{controller\} \/>/);
  const renderer = source("app/workspaces/WorkspaceRenderer.tsx");
  assert.match(renderer, /className="workspace-page"/);
  assert.match(renderer, /activePrimaryWorkspace\.id === "market" && \(\s*<MarketCockpit controller=\{controller\} \/>/);
});
