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

test("a workspace header declares at most one primary action, and only a permitted one", () => {
  const surfaces = surfaceSources().map((entry) => entry.path);
  const passing = surfaces.filter((path) => readWebSource(path).includes("primaryAction="));

  // The inventory is asserted so the slot's use cannot grow silently. A surface that starts
  // passing one belongs in this list *with* a `compute` or `persist` action.
  assert.deepEqual(passing.sort(), [
    "components/DecisionWorkspace.tsx",
    "components/PortfolioWorkspace.tsx",
  ]);

  const decision = readWebSource("components/DecisionWorkspace.tsx");
  // Book → Planning owns two `compute` acts, one per view behind its switch: assessing the
  // nominations and assessing the storage dispatch. Each is in the slot for its own view.
  assert.match(decision, /const primaryAction =\s*task === "nomination" \? \([\s\S]*?\) : task === "dispatch" \? \(/);
  assert.match(decision, /onClick=\{\(\) => void nomination\.run\(\)\}/);
  assert.match(decision, /onClick=\{\(\) => void dispatch\.run\(\)\}/);
  // Exactly one `primaryAction=` binding, so the header cannot end up with two.
  assert.equal((decision.match(/primaryAction=\{/g) ?? []).length, 1);
  assert.equal(mayOccupyPrimarySlot("compute"), true);
  assert.equal(mayOccupyPrimarySlot("lifecycle"), false);
  // Scenario and Optimise left with CP-00: neither run is offered from the header any more.
  assert.equal(decision.includes("optimizeResourcePoolForCurrentContext"), false);
  assert.equal(decision.includes("recommendRouteAllocationForCurrentContext"), false);

  const portfolio = readWebSource("components/PortfolioWorkspace.tsx");
  assert.equal((portfolio.match(/primaryAction=\{/g) ?? []).length, 1);
  // The action it passes is writing a reviewed contract draft: a `persist` consequence,
  // permitted in the primary slot, and disabled by the shared save rule rather than by a
  // second opinion computed in the header.
  assert.match(portfolio, /const primaryAction =\s*task === "resources" \? \(/);
  assert.match(portfolio, /onClick=\{\(\) =>\s*contractSaveStateForDraft\.canSave/);
  assert.match(portfolio, /disabled=\{!contractSaveStateForDraft\.canSave\}/);
  assert.equal(mayOccupyPrimarySlot("persist"), true);
  // The panel reports the validation verdict and the save outcome; it no longer saves.
  assert.equal(readWebSource("components/ContractWorkbench.tsx").includes("contracts.action.save"), false);
  assert.equal(
    (portfolio.match(/contracts\.action\.save/g) ?? []).length,
    1,
    "the primary action exists once",
  );
});

test("a primary action is moved into the header, not copied beside it", () => {
  // The failure mode this guards is quiet: apply the geography by adding the action to the
  // header while leaving the panel's copy in place, and the surface ends up with two
  // primaries for one act. Moving it means the label appears exactly once in the file.
  const passing = surfaceSources().filter((entry) => entry.source.includes("primaryAction="));
  assert.ok(passing.length > 0, "no surface passes a primary action, so this check proves nothing");

  for (const { path, source } of passing) {
    const start = source.indexOf("const primaryAction");
    assert.ok(start > 0, path);
    // The blank line that ends the expression is matched with a newline-agnostic pattern. It used
    // to be a literal "\n\n", which silently does not match a CRLF file: the slice then ran to the
    // end of the component and every label key in the file was counted as if the primary action had
    // declared it - a false failure that depended on the checkout's line endings rather than on the
    // code, and one this check must not be able to produce.
    const blankLine = /\r?\n\s*\r?\n/.exec(source.slice(start));
    assert.ok(blankLine, `${path}: the primary action expression is not followed by a blank line`);
    const expression = source.slice(start, start + blankLine.index);
    const labelKeys = [...expression.matchAll(/t\("([^"]+)"\)/g)].map((match) => match[1]);
    assert.ok(labelKeys.length > 0, `${path}: the primary action declares no label`);
    for (const key of labelKeys) {
      const occurrences = source.split(`t("${key}")`).length - 1;
      assert.equal(occurrences, 1, `${path}: '${key}' is rendered ${occurrences} times`);
    }
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
