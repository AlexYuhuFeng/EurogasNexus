/**
 * Colour roles meet WCAG 2.1 AA in both themes, computed from the token values themselves
 * (src/styles/tokens.css), so a palette change that loses contrast fails here rather than on
 * a trader's screen. The dark-theme palette once drew the selected row white on white; role
 * pairs are what components use, so checking the pairs checks every component that uses them.
 *
 * 4.5:1 for text, 3:1 for the focus ring and chart series (non-text marks, WCAG 1.4.11).
 * Disabled text is exempt (1.4.3) and not tested.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const css = readFileSync(new URL("../src/styles/tokens.css", import.meta.url), "utf8").replace(/\/\*[\s\S]*?\*\//g, "");

function block(selector: string): Record<string, string> {
  const start = css.indexOf(`${selector} {`);
  assert.ok(start >= 0, `${selector} block in tokens.css`);
  const body = css.slice(css.indexOf("{", start) + 1, css.indexOf("\n}", start));
  const out: Record<string, string> = {};
  for (const m of body.matchAll(/(--[\w-]+)\s*:\s*([^;]+);/g)) out[m[1]] = m[2].trim();
  return out;
}

const light = block(":root");
const themes: Record<string, Record<string, string>> = { light, dark: { ...light, ...block(":root.dark") } };

function resolve(theme: Record<string, string>, name: string, depth = 0): string {
  const value = theme[name];
  assert.ok(value !== undefined, `token ${name} is defined`);
  const ref = value.match(/^var\((--[\w-]+)\)$/);
  if (ref && depth < 8) return resolve(theme, ref[1], depth + 1);
  return value;
}

function rgb(hex: string): [number, number, number] {
  const m = hex.match(/^#([0-9a-f]{6})$/i);
  assert.ok(m, `${hex} is an opaque #rrggbb colour`);
  return [0, 2, 4].map((i) => parseInt(m[1].slice(i, i + 2), 16)) as [number, number, number];
}

function luminance(hex: string): number {
  const [r, g, b] = rgb(hex).map((c) => {
    const s = c / 255;
    return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

export function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

const SURFACES = ["--ds-bg", "--ds-surface", "--ds-surface-2", "--ds-surface-3"];
const STATUSES = ["ok", "watch", "breach", "info", "simulated", "stale"];
const TEXT_ROLES = [
  "--ds-text-1",
  "--ds-text-2",
  "--ds-text-3",
  "--ds-accent",
  "--ds-positive",
  "--ds-negative",
  "--pnl-up",
  "--pnl-down",
  ...STATUSES.map((s) => `--ds-status-${s}`),
];

function pairs(): Array<[string, string, number]> {
  const out: Array<[string, string, number]> = [];
  for (const fg of TEXT_ROLES) for (const bg of SURFACES) out.push([fg, bg, 4.5]);
  // Selected rows and current items sit on accent-soft.
  for (const fg of ["--ds-text-1", "--ds-text-2", "--ds-text-3", "--ds-accent"]) out.push([fg, "--ds-accent-soft", 4.5]);
  for (const s of STATUSES) {
    out.push([`--ds-status-${s}`, `--ds-status-${s}-soft`, 4.5]);
    out.push(["--ds-text-1", `--ds-status-${s}-soft`, 4.5]);
    out.push(["--ds-text-2", `--ds-status-${s}-soft`, 4.5]);
  }
  out.push(["--ds-on-accent", "--ds-accent", 4.5]);
  out.push(["--ds-on-accent", "--ds-accent-hover", 4.5]);
  out.push(["--ds-on-ink", "--ds-ink", 4.5]);
  out.push(["--ds-on-negative", "--ds-negative", 4.5]);
  for (const bg of [...SURFACES, "--ds-accent-soft"]) out.push(["--ds-focus-ring", bg, 3]);
  for (let i = 1; i <= 8; i += 1) for (const bg of ["--ds-bg", "--ds-surface", "--ds-surface-2"]) out.push([`--ds-series-${i}`, bg, 3]);
  return out;
}

test("the contrast function is the WCAG one", () => {
  assert.equal(Math.round(contrast("#000000", "#ffffff") * 10) / 10, 21);
  assert.equal(contrast("#777777", "#777777"), 1);
  assert.ok(Math.abs(contrast("#767676", "#ffffff") - 4.54) < 0.01);
});

for (const [theme, values] of Object.entries(themes)) {
  test(`every role pair meets WCAG AA in the ${theme} theme`, () => {
    const failures = pairs()
      .map(([fg, bg, min]) => ({ fg, bg, min, ratio: contrast(resolve(values, fg), resolve(values, bg)) }))
      .filter((p) => p.ratio < p.min)
      .map((p) => `${p.fg} on ${p.bg}: ${p.ratio.toFixed(2)} < ${p.min}`);
    assert.deepEqual(failures, []);
  });
}

test("both themes define the same roles", () => {
  const dark = block(":root.dark");
  const colourRoles = Object.keys(light).filter((name) => /^#[0-9a-f]{6}$/i.test(light[name]));
  const missing = colourRoles.filter((name) => !(name in dark) && !name.startsWith("--ds-brand") && !name.startsWith("--ds-on-brand"));
  assert.deepEqual(missing, [], "a colour role set for light only would carry the light value into dark");
});

test("the P&L convention swaps meaning, not colours", () => {
  const swap = block(':root[data-pnl="red_up"]');
  assert.equal(swap["--pnl-profit"], "var(--pnl-down)");
  assert.equal(swap["--pnl-loss"], "var(--pnl-up)");
  assert.equal(light["--pnl-profit"], "var(--pnl-up)");
});

test("the brand lock-ups read as text on the grounds they are made for", () => {
  // Colour (navy and blue) is for light grounds: the light theme's surfaces, print, reports.
  // Reverse (white and light blue) is for the navy panel. The name is text, so 4.5:1 throughout.
  const brandPairs: Array<[string, string]> = [];
  for (const bg of SURFACES) for (const fg of ["--ds-brand-navy", "--ds-brand-blue"]) brandPairs.push([fg, bg]);
  for (const bg of ["--ds-brand-navy", "--ds-brand-navy-deep"]) for (const fg of ["--ds-on-brand", "--ds-brand-blue-light"]) brandPairs.push([fg, bg]);
  const failures = brandPairs
    .map(([fg, bg]) => ({ fg, bg, ratio: contrast(resolve(light, fg), resolve(light, bg)) }))
    .filter((p) => p.ratio < 4.5)
    .map((p) => `${p.fg} on ${p.bg}: ${p.ratio.toFixed(2)}`);
  assert.deepEqual(failures, []);
});
