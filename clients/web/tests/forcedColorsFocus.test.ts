import assert from "node:assert/strict";
import { readdirSync, readFileSync, statSync } from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

// UX R5 (research/16B): in Windows High Contrast the browser drops box-shadow, so a focus ring
// drawn only with box-shadow disappears. Every focus rule keeps a transparent outline that the
// forced palette paints, and a small forced-colors block covers what else relies on shadow.
const SRC = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../src");

function cssFiles(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const full = path.join(dir, name);
    if (statSync(full).isDirectory()) return cssFiles(full);
    return name.endsWith(".css") ? [full] : [];
  });
}

function rules(text: string): { selector: string; body: string }[] {
  const clean = text.replace(/\/\*[\s\S]*?\*\//g, "");
  return [...clean.matchAll(/([^{};]+)\{([^{}]*)\}/g)].map((m) => ({ selector: m[1].trim(), body: m[2] }));
}

test("no focus rule removes the outline: forced colours need it to show focus", () => {
  const offenders: string[] = [];
  for (const file of cssFiles(SRC)) {
    for (const { selector, body } of rules(readFileSync(file, "utf8"))) {
      if (!/:focus(-visible)?\b/.test(selector)) continue;
      if (/outline\s*:\s*(none|0)\s*;/.test(body)) offenders.push(`${path.relative(SRC, file)}: ${selector}`);
    }
  }
  // A programmatic focus target (tabindex -1, never reached by keyboard) may drop it.
  assert.deepEqual(offenders.filter((o) => !o.includes(".source-detail-focus:focus")), []);
});

test("the global focus rule and every rule that sets its own outline use the transparent token", () => {
  const ds = readFileSync(path.join(SRC, "styles/design-system.css"), "utf8");
  const global = rules(ds).find((r) => r.selector === ":focus-visible");
  assert.ok(global, "design-system.css has a global :focus-visible rule");
  assert.match(global.body, /outline:\s*var\(--ds-focus-outline\);/);
  const offenders: string[] = [];
  for (const file of cssFiles(SRC)) {
    for (const { selector, body } of rules(readFileSync(file, "utf8"))) {
      if (!/:focus-visible/.test(selector)) continue;
      const outline = body.match(/outline\s*:\s*([^;]+);/)?.[1].trim();
      if (!outline) continue;
      // --ds-focus is a box-shadow list: as an outline colour it is invalid and drops the ring.
      if (/var\(--ds-focus\)/.test(outline)) offenders.push(`${path.relative(SRC, file)}: ${selector} (outline uses the shadow token)`);
      else if (/var\(--ds-focus\)/.test(body) && outline !== "var(--ds-focus-outline)") offenders.push(`${path.relative(SRC, file)}: ${selector}`);
    }
  }
  assert.deepEqual(offenders, []);
});

test("the tokens define a transparent focus outline, and a forced-colors block exists", () => {
  const tokens = readFileSync(path.join(SRC, "styles/tokens.css"), "utf8");
  assert.match(tokens, /--ds-focus-outline:\s*2px solid transparent;/);
  assert.match(tokens, /--ds-focus-offset:\s*2px;/);
  const ds = readFileSync(path.join(SRC, "styles/design-system.css"), "utf8");
  const block = ds.slice(ds.indexOf("@media (forced-colors: active)"));
  assert.ok(block.length > 0, "design-system.css has a forced-colors block");
  assert.match(block, /:focus-visible\s*\{\s*outline-color:\s*Highlight;/);
  assert.match(block, /\.ds-status[\s\S]*border:\s*1px solid CanvasText/);
  assert.match(block, /aria-selected="true"\][\s\S]*outline:\s*2px solid Highlight/);
});
