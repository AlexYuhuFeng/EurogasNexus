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

const SURFACES = ["--ds-bg", "--ds-surface", "--ds-surface-2", "--ds-surface-3", "--ds-surface-raised", "--ds-surface-overlay"];
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

// ---------------------------------------------------------------------------------------------
// Colour-vision deficiency (UX R1, research/16B). Up to 8 % of men of Northern European
// ancestry have a red-green deficiency. Each colour is passed through the Machado, Oliveira and
// Fernandes (2009) simulation at full severity (linear RGB) and compared in CIELAB with
// CIEDE2000; below about 10, small marks are hard to tell apart.

type Vision = "normal" | "deutan" | "protan" | "tritan";
const VISIONS: Vision[] = ["normal", "deutan", "protan", "tritan"];
const MACHADO: Record<Exclude<Vision, "normal">, number[][]> = {
  protan: [
    [0.152286, 1.052583, -0.204868],
    [0.114503, 0.786281, 0.099216],
    [-0.003882, -0.048116, 1.051998],
  ],
  deutan: [
    [0.367322, 0.860646, -0.227968],
    [0.280085, 0.672501, 0.047413],
    [-0.01182, 0.04294, 0.968881],
  ],
  tritan: [
    [1.255528, -0.076749, -0.178779],
    [-0.078411, 0.930809, 0.147602],
    [0.004733, 0.691367, 0.3039],
  ],
};

function linearRgb(hex: string): number[] {
  return rgb(hex).map((c) => {
    const s = c / 255;
    return s <= 0.04045 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
  });
}

function simulate(hex: string, vision: Vision): number[] {
  const c = linearRgb(hex);
  if (vision === "normal") return c;
  return MACHADO[vision].map((row) => Math.min(1, Math.max(0, row[0] * c[0] + row[1] * c[1] + row[2] * c[2])));
}

function lab([r, g, b]: number[]): [number, number, number] {
  const x = (0.4124564 * r + 0.3575761 * g + 0.1804375 * b) / 0.95047;
  const y = 0.2126729 * r + 0.7151522 * g + 0.072175 * b;
  const z = (0.0193339 * r + 0.119192 * g + 0.9503041 * b) / 1.08883;
  const f = (t: number) => (t > 216 / 24389 ? Math.cbrt(t) : (24389 / 27 * t + 16) / 116);
  return [116 * f(y) - 16, 500 * (f(x) - f(y)), 200 * (f(y) - f(z))];
}

export function ciede2000([L1, a1, b1]: number[], [L2, a2, b2]: number[]): number {
  const rad = Math.PI / 180;
  const Cbar = (Math.hypot(a1, b1) + Math.hypot(a2, b2)) / 2;
  const G = 0.5 * (1 - Math.sqrt(Cbar ** 7 / (Cbar ** 7 + 25 ** 7)));
  const a1p = (1 + G) * a1;
  const a2p = (1 + G) * a2;
  const C1p = Math.hypot(a1p, b1);
  const C2p = Math.hypot(a2p, b2);
  const hue = (a: number, b: number) => (a === 0 && b === 0 ? 0 : ((Math.atan2(b, a) / rad) % 360 + 360) % 360);
  const h1p = hue(a1p, b1);
  const h2p = hue(a2p, b2);
  const dLp = L2 - L1;
  const dCp = C2p - C1p;
  let dhp = 0;
  if (C1p * C2p !== 0) {
    dhp = h2p - h1p;
    if (dhp > 180) dhp -= 360;
    else if (dhp < -180) dhp += 360;
  }
  const dHp = 2 * Math.sqrt(C1p * C2p) * Math.sin((dhp / 2) * rad);
  const Lbp = (L1 + L2) / 2;
  const Cbp = (C1p + C2p) / 2;
  let hbp = h1p + h2p;
  if (C1p * C2p !== 0) {
    if (Math.abs(h1p - h2p) <= 180) hbp = (h1p + h2p) / 2;
    else hbp = h1p + h2p < 360 ? (h1p + h2p + 360) / 2 : (h1p + h2p - 360) / 2;
  }
  const T =
    1 -
    0.17 * Math.cos((hbp - 30) * rad) +
    0.24 * Math.cos(2 * hbp * rad) +
    0.32 * Math.cos((3 * hbp + 6) * rad) -
    0.2 * Math.cos((4 * hbp - 63) * rad);
  const dTheta = 30 * Math.exp(-(((hbp - 275) / 25) ** 2));
  const Rc = 2 * Math.sqrt(Cbp ** 7 / (Cbp ** 7 + 25 ** 7));
  const Sl = 1 + (0.015 * (Lbp - 50) ** 2) / Math.sqrt(20 + (Lbp - 50) ** 2);
  const Sc = 1 + 0.045 * Cbp;
  const Sh = 1 + 0.015 * Cbp * T;
  const Rt = -Math.sin(2 * dTheta * rad) * Rc;
  return Math.sqrt((dLp / Sl) ** 2 + (dCp / Sc) ** 2 + (dHp / Sh) ** 2 + Rt * (dCp / Sc) * (dHp / Sh));
}

/** The smallest CIEDE2000 distance between two colours over normal vision and the three simulations. */
function cvdDistance(a: string, b: string): { min: number; vision: Vision } {
  return VISIONS.map((vision) => ({ vision, min: ciede2000(lab(simulate(a, vision)), lab(simulate(b, vision))) })).reduce((x, y) =>
    y.min < x.min ? y : x,
  );
}

/** Neighbouring chart series, and any two of the first four, stay apart for every reader. */
const SERIES_FLOOR = 10;
/** Profit against loss, and ok against breach, in the colour-vision friendly scheme. */
const CVD_PAIR_FLOOR = 20;

const blueOrange = {
  light: { ...light, ...block(':root[data-pnl="blue_orange"]') },
  dark: { ...light, ...block(":root.dark"), ...block(':root[data-pnl="blue_orange"]'), ...block(':root.dark[data-pnl="blue_orange"]') },
};

test("the CIEDE2000 and simulation code reproduces the measured values in research/16B", () => {
  // Sharma, Wu and Dalal (2005) test pair 1, and the dark P&L pair measured for deuteranopia.
  assert.ok(Math.abs(ciede2000([50, 2.6772, -79.7751], [50, 0, -82.7485]) - 2.0425) < 1e-3);
  assert.ok(Math.abs(ciede2000(lab(simulate("#4cc38a", "deutan")), lab(simulate("#ff8a80", "deutan"))) - 7.8) < 0.1);
});

for (const [theme, values] of Object.entries(themes)) {
  test(`chart series stay apart under colour-vision deficiency in the ${theme} theme`, () => {
    const series = Array.from({ length: 8 }, (_, i) => resolve(values, `--ds-series-${i + 1}`));
    const pairs: Array<[number, number]> = [];
    for (let i = 0; i < 7; i += 1) pairs.push([i, i + 1]);
    for (let i = 0; i < 4; i += 1) for (let j = i + 2; j < 4; j += 1) pairs.push([i, j]);
    const failures = pairs
      .map(([i, j]) => ({ i, j, ...cvdDistance(series[i], series[j]) }))
      .filter((p) => p.min < SERIES_FLOOR)
      .map((p) => `series ${p.i + 1} / ${p.j + 1}: ${p.min.toFixed(1)} (${p.vision})`);
    assert.deepEqual(failures, []);
  });
}

for (const [theme, values] of Object.entries(blueOrange)) {
  test(`the colour-vision friendly scheme keeps profit, loss and status apart and legible in the ${theme} theme`, () => {
    const failures: string[] = [];
    for (const [a, b] of [
      ["--pnl-profit", "--pnl-loss"],
      ["--ds-positive", "--ds-negative"],
      ["--ds-status-ok", "--ds-status-breach"],
    ]) {
      const { min, vision } = cvdDistance(resolve(values, a), resolve(values, b));
      if (min < CVD_PAIR_FLOOR) failures.push(`${a} / ${b}: ${min.toFixed(1)} (${vision})`);
    }
    // Every role the scheme changes still meets the AA pairs the default palette meets.
    const changed = ["--pnl-profit", "--pnl-loss", "--ds-positive", "--ds-negative", "--ds-status-ok", "--ds-status-breach"];
    for (const fg of changed) for (const bg of SURFACES) if (contrast(resolve(values, fg), resolve(values, bg)) < 4.5) failures.push(`${fg} on ${bg}`);
    for (const s of ["ok", "breach"]) {
      for (const fg of [`--ds-status-${s}`, "--ds-text-1", "--ds-text-2"]) {
        if (contrast(resolve(values, fg), resolve(values, `--ds-status-${s}-soft`)) < 4.5) failures.push(`${fg} on --ds-status-${s}-soft`);
      }
    }
    if (contrast(resolve(values, "--ds-on-negative"), resolve(values, "--ds-negative")) < 4.5) failures.push("--ds-on-negative on --ds-negative");
    assert.deepEqual(failures, []);
  });
}

