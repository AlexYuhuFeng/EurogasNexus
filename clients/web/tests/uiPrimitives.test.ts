import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import {
  getNextWorkspaceTabIndex,
  workspaceTabButtonId,
} from "../src/components/ui/tabKeyboard.ts";
import {
  statusBadgeClass,
  type StatusBadgeVariant,
} from "../src/components/ui/statusBadgeClass.ts";

test("workspace tab keyboard movement wraps arrows and honors Home/End", () => {
  assert.equal(getNextWorkspaceTabIndex(0, 4, "ArrowRight"), 1);
  assert.equal(getNextWorkspaceTabIndex(3, 4, "ArrowRight"), 0);
  assert.equal(getNextWorkspaceTabIndex(0, 4, "ArrowLeft"), 3);
  assert.equal(getNextWorkspaceTabIndex(2, 4, "ArrowLeft"), 1);
  assert.equal(getNextWorkspaceTabIndex(2, 4, "Home"), 0);
  assert.equal(getNextWorkspaceTabIndex(2, 4, "End"), 3);
  assert.equal(getNextWorkspaceTabIndex(1, 4, "Enter"), null);
  assert.equal(getNextWorkspaceTabIndex(-1, 4, "ArrowRight"), null);
});

test("workspace tab ids preserve the existing DOM contract", () => {
  assert.equal(workspaceTabButtonId("source-tab", "catalog"), "source-tab-catalog");
  assert.equal(workspaceTabButtonId("runtime-tab", "delivery"), "runtime-tab-delivery");
});

test("status badge class generation preserves existing CSS modifiers", () => {
  const cases: Array<[StatusBadgeVariant, string, string]> = [
    ["source", "active_simulated", "source-status source-status-active_simulated"],
    ["pipeline", "succeeded", "pipeline-status pipeline-status-succeeded"],
    ["runtime-readiness-state", "partial", "runtime-readiness-state partial"],
  ];
  for (const [variant, status, expected] of cases) {
    assert.equal(statusBadgeClass(variant, status), expected);
  }
});

function readWebSource(relativePath: string): string {
  return readFileSync(new URL(`../src/${relativePath}`, import.meta.url), "utf8");
}

test("Source Center delegates tablist semantics to WorkspaceTabs", () => {
  const source = readWebSource("components/SourceCenter.tsx");
  for (const symbol of ["MetricStrip", "PanelHeader", "StatusBadge", "WorkspaceTabs"]) {
    assert.match(source, new RegExp(`from "@/components/ui"`));
    assert.match(source, new RegExp(`<${symbol}`));
  }
  assert.match(source, /<WorkspaceTabs[\s\S]*?role="tablist"/);
  assert.doesNotMatch(source, /handleViewKeyDown/);
  assert.doesNotMatch(source, /<button[\s\S]*?role="tab"/);
  assert.doesNotMatch(source, /Tab semantics are owned/);
});

test("Runtime delegates tablist semantics to WorkspaceTabs", () => {
  const source = readWebSource("components/RuntimeWorkspace.tsx");
  for (const symbol of ["MetricStrip", "PanelHeader", "StatusBadge", "WorkspaceTabs"]) {
    assert.match(source, new RegExp(`from "@/components/ui"`));
    assert.match(source, new RegExp(`<${symbol}`));
  }
  assert.match(source, /<WorkspaceTabs[\s\S]*?role="tablist"/);
  assert.match(source, /variant="runtime-readiness-state"/);
  assert.doesNotMatch(source, /handleViewKeyDown/);
  assert.doesNotMatch(source, /<button[\s\S]*?role="tab"/);
  assert.doesNotMatch(source, /StatusBadge owns/);
});

test("Capacity, Network rail, and Strategy shadow delegate tab semantics to WorkspaceTabs", () => {
  const cases = [
    ["components/CapacityWorkspace.tsx", "capacity-view"],
    ["components/NetworkWorkspace.tsx", "network-rail-tab"],
  ] as const;

  for (const [path, prefix] of cases) {
    const source = readWebSource(path);
    assert.match(source, /import \{[^}]*WorkspaceTabs[^}]*\} from "@\/components\/ui"/s);
    assert.match(source, /<WorkspaceTabs/);
    assert.match(source, new RegExp(`idPrefix="${prefix}"`));
    assert.doesNotMatch(source, /<button[\s\S]*?role="tab"/);
  }

  const strategy = readWebSource("components/strategy/StrategyShadowRunDetail.tsx");
  // The shadow detail renders panels only: no tab set of its own, and no hand-rolled tab keyboard
  // handling, because the task's views belong to the workspace shell.
  assert.doesNotMatch(strategy, /handleViewKeyDown/);
  assert.doesNotMatch(strategy, /<WorkspaceTabs/);
  assert.doesNotMatch(strategy, /role="tab"/);
});

test("narrow scroll regions are explicitly keyboard focusable", () => {
  const cases = [
    ["components/CapacityWorkspace.tsx", /className="capacity-operating-table"[\s\S]*?tabIndex=\{0\}/],
    // The hub board is an interactive DataGrid: its rows are the Tab stop (one at a time).
    ["components/ui/DataGrid.tsx", /tabIndex=\{interactive \|\| anySortable \? undefined : 0\}/],
    ["components/ContractWorkbench.tsx", /className="contract-command-actions" tabIndex=\{0\}/],
    ["components/ContractWorkbench.tsx", /className="contract-clause-nav"[\s\S]*?tabIndex=\{0\}/],
    ["components/ReviewWorkspace.tsx", /<DataGrid[\s\S]*?id="review-decisions"/],
    // Screen orders and P&L snapshots are DataGrids (UX-06): the grid's scroll box takes focus.
    ["components/MarketPositioningWorkspace.tsx", /<DataGrid[\s\S]*?id="screen-orders"[\s\S]*?maxHeight=/],
    ["components/AccessCenter.tsx", /className="data-table" tabIndex=\{0\}/],
    ["components/AgentsWorkspace.tsx", /className="research-table data-table" tabIndex=\{0\}/],
    // The decision rail scrolls (`overflow-y: auto`) and holds text, not controls: without a focus
    // stop of its own the keyboard cannot reach the rest of the rail (axe
    // `scrollable-region-focusable`, measured on `#network-rail-panel` in run 35888959943).
    ["components/NetworkWorkspace.tsx", /id="network-rail-panel"[\s\S]*?tabIndex=\{0\}/],
  ] as const;

  for (const [path, pattern] of cases) {
    assert.match(readWebSource(path), pattern, path);
  }
});

test("the scrollable network rail panel keeps its tabpanel contract and a token-based focus ring", () => {
  const source = readWebSource("components/NetworkWorkspace.tsx");
  assert.match(
    source,
    /id="network-rail-panel"[\s\S]*?role="tabpanel"[\s\S]*?aria-labelledby=\{`network-rail-tab-\$\{activeRailView\}`\}[\s\S]*?tabIndex=\{0\}/,
  );

  const css = readFileSync(new URL("../src/styles/app.css", import.meta.url), "utf8");
  const rule = /\.workspace-network \.network-rail-view:focus-visible \{([^}]*)\}/.exec(css);
  assert.ok(rule, "the rail panel declares a :focus-visible rule");
  assert.match(rule[1], /outline: 2px solid var\(--ds-accent\);/);
  assert.match(rule[1], /outline-offset: -2px;/);
  // The outline must resolve through a declared palette token, not a literal colour.
  const tokens = readFileSync(new URL("../src/styles/tokens.css", import.meta.url), "utf8");
  assert.match(tokens, /--ds-accent:\s*#[0-9a-f]{3,8};/i);
});

test("WorkspaceTabs is the Tabs primitive as a nav landmark holding the tablist", () => {
  const component = readWebSource("components/ui/WorkspaceTabs.tsx");
  const tabs = readWebSource("components/ui/Tabs.tsx");
  assert.match(component, /role\?: "tablist"/);
  assert.match(component, /<Tabs\s+landmark/);
  // The optional Architecture V2 shell-region marker only adds a data attribute.
  assert.match(component, /dataAttributes=\{\{ "data-shell-region": shellRegion \}\}/);
  assert.match(component, /shellRegion\?: ShellRegionMarker;/);
  // Tabs owns the semantics: one tablist, roving tabindex, the selected tab marked.
  assert.match(tabs, /role="tablist"/);
  assert.match(tabs, /role="tab"/);
  assert.match(tabs, /aria-selected=\{selected\}/);
  // One Tab stop: the selected tab, or the first when none is selected (a utility page).
  assert.match(tabs, /tabIndex=\{index === stopIndex \? 0 : -1\}/);
  assert.match(tabs, /const stopIndex = Math\.max\(0, activeIndex\);/);
});
