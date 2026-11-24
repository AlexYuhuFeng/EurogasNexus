/**
 * UX R11 (research/16B): a Comfortable/Compact row density. Compact re-points the row tokens
 * only (32 → 28, header 28 → 24); control heights, the touch height, type and spacing are the
 * same in both, so the geometry budgets and the "no control under 24 px" rule hold.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { applyDensity, DENSITIES, isDensity } from "../src/app/model/density.ts";

const SRC = new URL("../src/", import.meta.url);
const tokens = readFileSync(new URL("styles/tokens.css", SRC), "utf8").replace(/\/\*[\s\S]*?\*\//g, "");

function block(selector: string): Record<string, string> {
  const start = tokens.indexOf(`${selector} {`);
  assert.ok(start >= 0, `${selector} block in tokens.css`);
  const body = tokens.slice(tokens.indexOf("{", start) + 1, tokens.indexOf("}", start));
  return Object.fromEntries([...body.matchAll(/(--[\w-]+)\s*:\s*([^;]+);/g)].map((m) => [m[1], m[2].trim()]));
}

test("two densities, comfortable by default; anything else falls back to comfortable", () => {
  assert.deepEqual(DENSITIES, ["comfortable", "compact"]);
  assert.equal(isDensity("compact"), true);
  assert.equal(isDensity("cozy"), false);
  const root = { dataset: {} as DOMStringMap };
  assert.equal(applyDensity("compact", root), "compact");
  assert.equal(root.dataset.density, "compact");
  assert.equal(applyDensity("cozy", root), "comfortable");
  assert.equal(root.dataset.density, "comfortable");
});

test("compact changes the row heights and nothing else", () => {
  const base = block(":root");
  const compact = block(':root[data-density="compact"]');
  assert.deepEqual(Object.keys(compact).sort(), ["--ds-row", "--ds-row-header"]);
  assert.equal(base["--ds-row"], "32px");
  assert.equal(base["--ds-row-header"], "28px");
  assert.equal(compact["--ds-row"], "28px");
  assert.equal(compact["--ds-row-header"], "24px");
  // Rows stay at or above the smallest target size (WCAG 2.5.8, 24 px).
  for (const value of Object.values(compact)) assert.ok(Number.parseFloat(value) >= 24);
});

test("the choice is offered in Settings and in the account menu's appearance, and follows the person", () => {
  const panels = readFileSync(new URL("components/PreferencesPanels.tsx", SRC), "utf8");
  assert.match(panels, /density: \[\s*\{ value: "comfortable", labelKey: "preferences\.density\.comfortable" \},\s*\{ value: "compact", labelKey: "preferences\.density\.compact" \},/);
  assert.match(panels, /const GENERAL_KEYS: ChoiceKey\[\] = \[[^\]]*"density"/);
  const menu = readFileSync(new URL("components/HeaderPreferencesMenu.tsx", SRC), "utf8");
  assert.match(menu, /DENSITIES\.map\(/);
  assert.match(menu, /saveRemotePreference\("density", choice\)/);
  const remote = readFileSync(new URL("app/preferences/remotePreferences.ts", SRC), "utf8");
  assert.match(remote, /useDensityStore\.getState\(\)\.setDensity\(effective\.density/);
  const main = readFileSync(new URL("main.tsx", SRC), "utf8");
  assert.match(main, /applyStoredDensity\(\);/, "the stored density applies before the first paint");
});

test("every density string exists in English and Chinese", () => {
  for (const language of ["en", "zh"]) {
    const strings = JSON.parse(readFileSync(new URL(`i18n/${language}.json`, SRC), "utf8")) as Record<string, string>;
    for (const key of ["preferences.density", "preferences.density.comfortable", "preferences.density.compact"]) {
      assert.ok(strings[key], `${language}: ${key}`);
    }
  }
});
