/**
 * Converted stylesheets take every colour, font size, radius, control height and weight from
 * the design tokens (scripts/cssTokenLint.mjs). Files not yet converted are listed in
 * scripts/css-token-baseline.json with their count of raw values; the count may only go down
 * and the list may not grow. docs/product/DESIGN_TOKENS.md says how to convert a file.
 */
import assert from "node:assert/strict";
import test from "node:test";

import { check, lintCss, readBaseline } from "../scripts/cssTokenLint.mjs";

// The ratchet's ceiling. Lower these when a conversion lands; never raise them.
const MAX_BASELINE_FILES = 1;
const MAX_BASELINE_VALUES = 292;

test("no stylesheet regresses, and the baseline matches what is measured", () => {
  const result = check();
  console.log(
    `CSS token lint: ${result.converted} of ${result.total} stylesheets clean; ${result.remaining} raw values remain in ${result.legacyFiles} file(s)`,
  );
  assert.deepEqual(result.failures, []);
});

test("the baseline can only shrink", () => {
  const baseline = readBaseline();
  assert.ok(Object.keys(baseline).length <= MAX_BASELINE_FILES, "a file was added to the baseline");
  const total = Object.values(baseline).reduce((a, b) => a + b, 0);
  assert.ok(total <= MAX_BASELINE_VALUES, `baseline total ${total} > ${MAX_BASELINE_VALUES}`);
});

test("the lint catches each kind of raw value", () => {
  const rules = (text: string) => lintCss(text).map((p) => p.rule.split(":")[0]);
  assert.deepEqual(rules(".a { color: #fff; }"), ["raw colour"]);
  assert.deepEqual(rules(".a { background: rgb(0 0 0 / 40%); }"), ["raw colour"]);
  assert.deepEqual(rules(".a { border-color: white; }"), ["raw colour"]);
  assert.deepEqual(rules(".a { font-size: 13px; }"), ["font size off the type scale"]);
  assert.deepEqual(rules(".a { font-size: 0.85em; }"), ["font size off the type scale"]);
  assert.deepEqual(rules(".a { border-radius: 6px; }"), ["radius off the scale"]);
  assert.deepEqual(rules(".a { min-height: 34px; }"), ["control-sized height"]);
  assert.deepEqual(rules(".a { font-weight: 700; }"), ["weight off the scale"]);
  assert.deepEqual(rules(".a { color: var(--eg-muted); }"), ["legacy variable --eg-muted"]);
  assert.deepEqual(rules(".a { font-size: var(--ds-text-lg); }"), ["font size off the type scale", "deprecated token --ds-text-lg"]);
});

test("token-only CSS passes", () => {
  const clean = `
    .a:hover { color: var(--ds-text-1); background: color-mix(in srgb, var(--ds-accent) 10%, transparent); }
    .b { font-size: var(--ds-text-sm); border-radius: var(--ds-radius-sm) 0; min-height: var(--ds-control-sm); }
    .c { --local: 4px; height: 1px; width: 200px; font-weight: 600; grid-template-columns: var(--local); }
    .d { mask-image: linear-gradient(90deg, transparent, black 24px); color: var(--pnl-profit); }
    @media (max-width: 600px) { .e { border-radius: 0; } }`;
  assert.deepEqual(lintCss(clean), []);
});
