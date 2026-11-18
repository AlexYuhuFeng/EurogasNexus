import assert from "node:assert/strict";
import test from "node:test";

import { navigationKeyFor, navigationStep } from "../src/app/shell/navigationKey.ts";

// A floating surface never outlives the page it was opened on (UX_REFERENCE rule 22).

test("the place is the page, task, view and panel; other parameters are not a move", () => {
  assert.equal(navigationKeyFor("?workspace=market&task=network&gasDay=2026-11-18"), "market|network||");
  assert.equal(navigationKeyFor("?workspace=market&task=network&gasDay=2026-11-19"), "market|network||");
  assert.notEqual(navigationKeyFor("?workspace=market&task=network"), navigationKeyFor("?workspace=market&task=curves"));
});

test("an open surface closes when the place changes, and only then", () => {
  let step = navigationStep(null, true, "market|network||");
  assert.deepEqual(step, { openedAt: "market|network||", close: false });
  step = navigationStep(step.openedAt, true, "market|network||");
  assert.equal(step.close, false);
  step = navigationStep(step.openedAt, true, "contracts|exposure||");
  assert.equal(step.close, true);
  assert.deepEqual(navigationStep("market|network||", false, "contracts|exposure||"), { openedAt: null, close: false });
});

test("every floating primitive applies the rule", async () => {
  const { readFileSync } = await import("node:fs");
  for (const file of ["Popover.tsx", "Dialog.tsx"]) {
    const source = readFileSync(new URL(`../src/components/ui/${file}`, import.meta.url), "utf8");
    assert.match(source, /useCloseOnNavigation\(open,/, file);
  }
});
