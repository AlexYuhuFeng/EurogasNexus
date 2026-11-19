/**
 * Action geography enforcement (Architecture V2 Wave 9).
 *
 * `app/experience/actionGeography.ts` states the rule, and the Wave 1 conformance test
 * already checks the rule itself. What nothing checked was the *application*: whether a
 * surface puts a lifecycle or destructive action where the geography forbids it, whether a
 * workspace has grown a second primary affordance, and whether shell utilities have leaked
 * into a workspace.
 *
 * These checks read the sources, so a violation fails here rather than in review. They are
 * deliberately conservative: they name the verbs the geography guards and the exact
 * affordances it constrains, and they say what they cannot see.
 */

import assert from "node:assert/strict";
import { readdirSync, readFileSync } from "node:fs";
import test from "node:test";

import {
  ACTION_CONSEQUENCES,
  actionGeography,
  mayOccupyPrimarySlot,
} from "../src/app/experience/actionGeography.ts";

function readWebSource(relativePath: string): string {
  return readFileSync(new URL(`../src/${relativePath}`, import.meta.url), "utf8");
}

/** Every surface source under `src`, so a new workspace is covered without being listed. */
function surfaceSources(): Array<{ path: string; source: string }> {
  const entries: Array<{ path: string; source: string }> = [];
  for (const directory of ["components", "app/shell", "app/workspaces"]) {
    const walk = (relative: string): void => {
      for (const item of readdirSync(new URL(`../src/${relative}/`, import.meta.url), {
        withFileTypes: true,
      })) {
        const next = `${relative}/${item.name}`;
        if (item.isDirectory()) {
          walk(next);
          continue;
        }
        if (!/\.tsx$/.test(item.name)) continue;
        entries.push({ path: next, source: readWebSource(next) });
      }
    };
    walk(directory);
  }
  return entries;
}

/** Verbs whose consequence the geography guards: they may never be a primary affordance. */
const GUARDED_VERBS = [
  "retire",
  "freeze",
  "delete",
  "remove",
  "revoke",
  "pause",
  "resume",
  "demote",
  "cancel",
  "acknowledge_hard",
];

/** Classes that present an affordance as the primary one. */
const PRIMARY_AFFORDANCE = /className="[^"]*primary[^"]*"/;

test("no guarded action is presented as a primary affordance", () => {
  const offenders: string[] = [];

  for (const { path, source } of surfaceSources()) {
    // Buttons rendered with a primary class...
    for (const match of source.matchAll(/<button[^>]*>([\s\S]{0,200}?)<\/button>/g)) {
      const [element, body] = [match[0], match[1]];
      if (!PRIMARY_AFFORDANCE.test(element)) continue;
      for (const key of body.matchAll(/t\("([^"]+)"\)/g)) {
        const label = key[1].toLowerCase();
        if (GUARDED_VERBS.some((verb) => label.includes(verb))) {
          offenders.push(`${path}: ${key[1]}`);
        }
      }
    }
  }

  assert.deepEqual(offenders, [], "a guarded action was presented as the primary affordance");
});

test("the tab row holds tabs only: no page passes an action to the header (UX_REFERENCE rule 26)", () => {
  const passing = surfaceSources().filter((entry) => /primaryAction=|actions=\{/.test(entry.source) && entry.source.includes("<WorkspaceHeader"));
  assert.deepEqual(passing.map((entry) => entry.path), [], "a page puts an action in its tab row");
  const header = readWebSource("components/ui/WorkspaceHeader.tsx");
  assert.equal(header.includes("primaryAction"), false, "the header has no action slot");

  // Each page's action lives in the page, beside what it acts on, once.
  const portfolio = readWebSource("components/PortfolioWorkspace.tsx");
  assert.match(portfolio, /const saveAction =\s*task === "resources" \? \(/);
  assert.match(portfolio, /saveAction=\{saveAction\}/);
  assert.match(portfolio, /onClick=\{\(\) =>\s*contractSaveStateForDraft\.canSave/);
  assert.match(portfolio, /disabled=\{!contractSaveStateForDraft\.canSave\}/);
  assert.equal((portfolio.match(/contracts\.action\.save/g) ?? []).length, 1, "the save action exists once");
  assert.equal(readWebSource("components/ContractWorkbench.tsx").includes("contracts.action.save"), false);
  // The supply editor's save sits with the open contract it saves; a typed kind's form (contract
  // kinds, docs/product/CONTRACT_TYPES.md) carries its own. New and Import are the list's actions.
  assert.match(readWebSource("components/ContractWorkbench.tsx"), /<div className="contract-detail-actions">\{saveAction\}<\/div>/);
  assert.match(readWebSource("components/ContractWorkbench.tsx"), /<div className="contract-command-actions"[^>]*>\s*<button[^>]*data-page-action="contract-new"/);

  for (const [file, key] of [["components/decision/NominationWindowPanel.tsx", "nomination"], ["components/decision/StorageDispatchPanel.tsx", "dispatch"]]) {
    const panel = readWebSource(file);
    assert.match(panel, /onClick=\{\(\) => void assessment\.run\(\)\}/, file);
    assert.equal((panel.match(new RegExp(`t\\("decision\\.${key}\\.assess"\\)`, "g")) ?? []).length, 1, file);
  }
  const decision = readWebSource("components/DecisionWorkspace.tsx");
  assert.equal(decision.includes("decision.nomination.assess") || decision.includes("decision.dispatch.assess"), false);
  assert.equal(decision.includes("optimizeResourcePoolForCurrentContext"), false);
  assert.equal(decision.includes("recommendRouteAllocationForCurrentContext"), false);
});
test("a page action's label is rendered once in its file (moved, not copied)", () => {
  for (const [path, key] of [
    ["components/PortfolioWorkspace.tsx", "contracts.action.save"],
    ["components/decision/NominationWindowPanel.tsx", "decision.nomination.assess"],
    ["components/decision/StorageDispatchPanel.tsx", "decision.dispatch.assess"],
  ]) {
    const source = readWebSource(path);
    assert.equal(source.split(`t("${key}")`).length - 1, 1, `${path}: '${key}'`);
  }
});
test("no surface starts the retired pool optimiser or route comparison", () => {
  // Deals → Evaluate and Optimise left with CP-00 (design basis 2, I.1). The engines stay in the
  // backend for the Opportunities evaluators; no client surface starts either run.
  const acts = {
    optimizeResourcePoolForCurrentContext: "runs the pool optimiser",
    recommendRouteAllocationForCurrentContext: "compares route options",
  };
  const offenders: string[] = [];
  for (const { path, source } of surfaceSources()) {
    for (const [handler, description] of Object.entries(acts)) {
      if (source.includes(handler)) offenders.push(`${path}: ${description}`);
    }
  }
  assert.deepEqual(offenders, [], "a surface starts a retired run");
  assert.equal(readWebSource("components/NetworkWorkspace.tsx").includes("network.optimizer_location"), false);
});

test("shell utilities stay in the shell", () => {
  const offenders: string[] = [];
  const utilityCalls = ["signOut", "changeAppLanguage", "theme.setMode"];

  // Surfaces only. The composition layer (`app/workspaces/`) is what wires the settings
  // page to the shell's preference controls, and the settings page is where they belong;
  // a *workspace* growing its own sign-out, language or theme control is the violation.
  for (const { path, source } of surfaceSources()) {
    if (!path.startsWith("components/")) continue;
    for (const call of utilityCalls) {
      if (source.includes(call)) offenders.push(`${path}: ${call}`);
    }
  }

  assert.deepEqual(offenders, [], "a workspace reached for a shell utility");
});

test("every consequence the geography names has a rule, and the guarded ones stay guarded", () => {
  // The rules themselves are the Wave 1 contract; this pins that the enforcement above
  // matches them rather than inventing a second list.
  assert.equal(actionGeography.length, ACTION_CONSEQUENCES.length);
  for (const consequence of ACTION_CONSEQUENCES) {
    const rule = actionGeography.find((item) => item.consequence === consequence);
    assert.ok(rule, consequence);
  }
  for (const guarded of ["lifecycle", "destructive"] as const) {
    assert.equal(mayOccupyPrimarySlot(guarded), false, guarded);
  }
});
