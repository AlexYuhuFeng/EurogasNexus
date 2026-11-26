/**
 * The Market page's gas day, hub and product controls live in its context strip. They stay on
 * screen while the market-context read is loading or has failed: a trader is never left without
 * the filters, and the acceptance sweep can always read the Active Context it shows (hosted CI,
 * 20 Nov: "the displayed Active Context could not be read from '[data-context-gas-day]'").
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const source = readFileSync(new URL("../src/components/MarketContextStrip.tsx", import.meta.url), "utf8");

test("the strip keeps the page controls when the context read is absent or empty", () => {
  const absent = source.indexOf("if (!projection || sliceReadings(projection).length === 0)");
  assert.ok(absent > 0, "the absent-read branch exists");
  const branch = source.slice(absent, source.indexOf("\n  return (", absent + 1));
  assert.match(branch, /\{controls\}/);
  assert.doesNotMatch(source, /if \(!projection\) return null;/);
});
