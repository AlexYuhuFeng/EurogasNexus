import assert from "node:assert/strict";
import { readdirSync, readFileSync, statSync } from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

// UX R3 (research/16B, P-20): one formatter per measure. A component names the measure
// (`formatMeasure` in app/time/valueFormat.ts), which writes the decimals, a true minus and the
// unit spacing the same way on every screen; a number for a machine (a form field, a CSV cell,
// an SVG coordinate, a CSS length) goes through `plainDecimal`. A hand-rolled `toFixed(` under
// components/ fails here. The baseline was 61 calls on 2026-11-24 and is now 0; it may not grow.
const COMPONENTS = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../src/components");
const BASELINE: Record<string, number> = {};

function sources(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const full = path.join(dir, name);
    if (statSync(full).isDirectory()) return sources(full);
    return /\.(ts|tsx)$/.test(name) ? [full] : [];
  });
}

test("no component formats a number with toFixed: it names the measure instead", () => {
  const over: string[] = [];
  for (const file of sources(COMPONENTS)) {
    const text = readFileSync(file, "utf8").replace(/\/\*[\s\S]*?\*\/|\/\/.*$/gm, "");
    const count = (text.match(/\.toFixed\(/g) ?? []).length;
    const key = path.relative(COMPONENTS, file).split(path.sep).join("/");
    if (count > (BASELINE[key] ?? 0)) over.push(`${key}: ${count} toFixed( (allowed ${BASELINE[key] ?? 0})`);
  }
  assert.deepEqual(over, []);
});

test("no component writes a hyphen-minus into a figure by hand", () => {
  // The old helpers patched toFixed with .replace("-", "−"); formatMeasure writes U+2212 itself.
  const patched = sources(COMPONENTS).filter((file) => /\.replace\("-", "−"\)/.test(readFileSync(file, "utf8")));
  assert.deepEqual(patched.map((file) => path.relative(COMPONENTS, file)), []);
});
