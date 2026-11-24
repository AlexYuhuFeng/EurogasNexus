/**
 * UX R4 (research/16B): shadows barely show on a dark ground, so in dark mode popovers, menus
 * and dialogs step lighter than the panels under them instead of sharing --ds-surface, and the
 * dark neutrals are tinted toward the brand navy at a chroma too low to colour any data.
 * Contrast on the new surfaces is held by tokenContrast.test.ts.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const SRC = new URL("../src/", import.meta.url);
const css = readFileSync(new URL("styles/tokens.css", SRC), "utf8").replace(/\/\*[\s\S]*?\*\//g, "");

function block(selector: string): Record<string, string> {
  const start = css.indexOf(`${selector} {`);
  assert.ok(start >= 0, `${selector} block in tokens.css`);
  const body = css.slice(css.indexOf("{", start) + 1, css.indexOf("\n}", start));
  return Object.fromEntries([...body.matchAll(/(--[\w-]+)\s*:\s*([^;]+);/g)].map((m) => [m[1], m[2].trim()]));
}

const light = block(":root");
const dark = { ...light, ...block(":root.dark") };

function oklch(hex: string): { l: number; c: number; h: number } {
  const lin = [1, 3, 5].map((i) => {
    const v = parseInt(hex.slice(i, i + 2), 16) / 255;
    return v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4;
  });
  const [r, g, b] = lin;
  const l = Math.cbrt(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b);
  const m = Math.cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b);
  const s = Math.cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b);
  const L = 0.2104542553 * l + 0.793617785 * m - 0.0040720468 * s;
  const A = 1.9779984951 * l - 2.428592205 * m + 0.4505937099 * s;
  const B = 0.0259040371 * l + 0.7827717662 * m - 0.808675766 * s;
  return { l: L, c: Math.hypot(A, B), h: ((Math.atan2(B, A) * 180) / Math.PI + 360) % 360 };
}

test("light: the elevated surfaces are the surface (the shadow lifts them)", () => {
  assert.equal(light["--ds-surface-raised"], "var(--ds-surface)");
  assert.equal(light["--ds-surface-overlay"], "var(--ds-surface)");
});

test("dark: each level is lighter than the one below it", () => {
  const order = ["--ds-bg", "--ds-surface", "--ds-surface-raised", "--ds-surface-overlay"];
  const lightness = order.map((name) => oklch(dark[name]).l);
  for (let i = 1; i < order.length; i += 1) {
    assert.ok(lightness[i] - lightness[i - 1] >= 0.02, `${order[i]} steps at least 0.02 L above ${order[i - 1]}`);
  }
});

test("dark: the elevated shadows carry a top highlight", () => {
  for (const name of ["--ds-shadow-pop", "--ds-shadow-modal"]) {
    assert.match(dark[name], /^inset 0 1px 0 color-mix\(in oklab, white 6%, transparent\),/);
  }
});

test("dark: the neutrals lean to the brand navy at a chroma that colours nothing", () => {
  const navy = oklch(light["--ds-brand-navy"]).h;
  const neutrals = ["--ds-bg", "--ds-surface", "--ds-surface-2", "--ds-surface-3", "--ds-surface-raised", "--ds-surface-overlay",
    "--ds-border-subtle", "--ds-border", "--ds-border-strong", "--ds-text-2", "--ds-text-3", "--ds-text-disabled"];
  for (const name of neutrals) {
    const { c, h } = oklch(dark[name]);
    assert.ok(c >= 0.005 && c <= 0.0135, `${name} chroma ${c.toFixed(4)} within 0.005..0.0135`);
    // 8-bit rounding moves the hue of so faint a colour by several degrees.
    assert.ok(Math.abs(h - navy) <= 12, `${name} hue ${h.toFixed(1)} within 12° of the navy's ${navy.toFixed(1)}`);
  }
});

test("popovers, menus, docked cards and dialogs draw on the elevated surfaces", () => {
  const sites: Array<[string, string, "raised" | "overlay"]> = [
    ["components/ui/controls.css", ".ds-popover {", "raised"],
    ["components/ui/controls.css", ".ds-sheet {", "overlay"],
    ["components/ui/primitives.css", ".first-use-hint {", "raised"],
    ["components/ui/primitives.css", '.converted-value[data-converted="hover"] {', "raised"],
    ["components/ui/instrumentPicker.css", ".ds-ipicker-panel {", "raised"],
    ["styles/design-system.css", ".map-detail-panel {", "raised"],
    ["styles/design-system.css", ".cockpit-app .app-header .topbar-context-disclosure-content {", "overlay"],
    ["styles/design-system.css", ".sign-in-shell {", "overlay"],
    ["styles/design-system.css", ".topbar-status-panel {", "raised"],
    ["styles/design-system.css", '[data-width-class="medium"] .app-header .topbar-context-disclosure-content {', "raised"],
    ["components/CommandPalette.css", ".command-palette {", "overlay"],
    ["components/WorkspaceTopBar.css", ".topbar-preferences-popover {", "raised"],
    ["components/WorkspaceTopBar.css", ".alert-drawer {", "raised"],
  ];
  for (const [file, selector, level] of sites) {
    const text = readFileSync(new URL(file, SRC), "utf8");
    const at = text.indexOf(`\n${selector}`) >= 0 ? text.indexOf(`\n${selector}`) : text.indexOf(`  ${selector}`);
    assert.ok(at >= 0, `${selector} in ${file}`);
    const body = text.slice(at, text.indexOf("}", at));
    assert.match(body, new RegExp(`background: var\\(--ds-surface-${level}\\);`), `${selector} uses --ds-surface-${level}`);
  }
});
