import assert from "node:assert/strict";
import { readdirSync, readFileSync, statSync } from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

// docs/ux/DESIGN_SYSTEM.md: one token set, one type scale. These counts may only go down.
const SRC = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../src");
const MAX_LEGACY_COLOUR_LITERALS = 300;

function cssFiles(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const full = path.join(dir, name);
    if (statSync(full).isDirectory()) return cssFiles(full);
    return name.endsWith(".css") ? [full] : [];
  });
}

const files = cssFiles(SRC).filter((file) => !file.endsWith("design-system.css"));

test("every legacy stylesheet sits in the legacy cascade layer", () => {
  for (const file of files) {
    assert.ok(readFileSync(file, "utf8").trimStart().startsWith("@layer legacy {"), file);
  }
});

test("font sizes come from the type scale, not pixel literals", () => {
  for (const file of files) {
    const literals = readFileSync(file, "utf8").match(/font-size:\s*\d+(\.\d+)?px/g) ?? [];
    assert.deepEqual(literals, [], file);
  }
});

test("hard-coded colours only shrink", () => {
  const count = files
    .map((file) => (readFileSync(file, "utf8").match(/#[0-9a-fA-F]{3,8}\b|rgba?\([^)]*\)/g) ?? []).length)
    .reduce((a, b) => a + b, 0);
  assert.ok(count <= MAX_LEGACY_COLOUR_LITERALS, `${count} colour literals; use var(--ds-*) tokens`);
});

test("the design system loads first and declares the layer order", () => {
  const main = readFileSync(path.join(SRC, "main.tsx"), "utf8");
  assert.ok(main.indexOf("design-system.css") < main.indexOf("from \"./App\""));
  const ds = readFileSync(path.join(SRC, "styles/design-system.css"), "utf8");
  assert.match(ds, /@layer ds-base, legacy, ds-theme, ds-components, ds-motion;/);
  assert.match(ds, /prefers-reduced-motion: reduce/);
});
