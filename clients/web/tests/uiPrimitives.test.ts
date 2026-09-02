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

test("WorkspaceTabs forwards its role prop and defaults to tablist", () => {
  const component = readWebSource("components/ui/WorkspaceTabs.tsx");
  assert.match(component, /role\?: "tablist"/);
  assert.match(component, /role = "tablist"/);
  assert.match(component, /<nav className=\{className} role=\{role} aria-label=\{label}>/);
});
