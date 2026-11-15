/**
 * The token foundation (UX-01): one token file, src/styles/tokens.css, defines the scales; the
 * legacy variable families the older stylesheets use are re-pointed there at steps of those
 * scales, and the shell's ownership points use the tokens directly.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const css = readFileSync(new URL("../src/styles/app.css", import.meta.url), "utf8");
const tokens = readFileSync(new URL("../src/styles/tokens.css", import.meta.url), "utf8");

function selectorBlocks(selector: string): string[] {
  return [...css.matchAll(/([^{}]+)\{([^{}]*)\}/g)]
    .filter(([, header]) => header.split(",").some((item) => item.trim() === selector))
    .map(([, , body]) => body);
}

function activeDeclaration(selector: string, property: string): string {
  const propertyPattern = new RegExp(`(?:^|;)\\s*${property}:\\s*([^;]+);`, "g");
  const values = selectorBlocks(selector).flatMap((body) =>
    [...body.matchAll(propertyPattern)].map(([, value]) => value.trim()),
  );
  assert.ok(values.length > 0, `missing ${property} for ${selector}`);
  return values.at(-1) as string;
}

/** A token's value in the light theme of tokens.css, following var() references. */
function resolveToken(value: string, depth = 0): string {
  const token = value.match(/^var\((--[^)]+)\)$/)?.[1];
  if (!token || depth > 8) return value;
  const declaration = new RegExp(`\\n\\s*${token}:\\s*([^;]+);`).exec(tokens);
  assert.ok(declaration, `missing token declaration for ${token}`);
  return resolveToken(declaration[1].trim(), depth + 1);
}

test("the token file defines the approved scales", () => {
  const scale = {
    "--ds-text-xs": "11px",
    "--ds-text-sm": "12px",
    "--ds-text-base": "13px",
    "--ds-text-md": "15px",
    "--ds-text-xl": "18px",
    "--ds-text-num": "20px",
    "--ds-space-05": "2px",
    "--ds-space-1": "4px",
    "--ds-space-2": "8px",
    "--ds-space-3": "12px",
    "--ds-space-4": "16px",
    "--ds-space-6": "24px",
    "--ds-space-8": "32px",
    "--ds-control-sm": "28px",
    "--ds-control": "32px",
    "--ds-control-touch": "44px",
    "--ds-radius-sm": "4px",
    "--ds-radius-md": "8px",
    "--ds-radius-pill": "999px",
    "--ds-duration-fast": "80ms",
    "--ds-duration-base": "160ms",
    "--ds-duration-slow": "240ms",
    "--ds-duration-map": "400ms",
  };
  for (const [name, value] of Object.entries(scale)) {
    assert.equal(resolveToken(`var(${name})`), value, name);
  }
  // Weights 400, 500, 600 only.
  assert.deepEqual(
    ["regular", "medium", "semibold"].map((w) => resolveToken(`var(--ds-weight-${w})`)),
    ["400", "500", "600"],
  );
});

test("legacy variable families resolve to steps of the scale", () => {
  const legacy = {
    "--text-meta": "11px",
    "--text-body": "13px",
    "--text-control": "13px",
    "--text-panel-title": "15px",
    "--text-page-title": "18px",
    "--space-5": "24px",
    "--control-compact": "28px",
    "--control-standard": "32px",
    "--control-prominent": "32px",
    "--radius-control": "4px",
    "--radius-panel": "8px",
    "--eg-radius-sm": "4px",
    "--eg-pill": "999px",
    "--ds-text-2xl": "18px",
    "--ds-radius-lg": "8px",
  };
  for (const [name, value] of Object.entries(legacy)) {
    assert.equal(resolveToken(`var(${name})`), value, name);
  }
});

test("shared shell surfaces use the tokens at their ownership points", () => {
  assert.match(
    css,
    /\.cockpit-app \.cockpit-topbar \{[\s\S]*?gap: var\(--ds-space-2\) var\(--ds-space-3\);[\s\S]*?padding: var\(--ds-space-3\) var\(--ds-space-4\);/,
  );
  assert.match(
    css,
    /\.endpoint-error-banner \{[\s\S]*?gap: var\(--ds-space-1\) var\(--ds-space-3\);[\s\S]*?padding: var\(--ds-space-2\) var\(--ds-space-3\);/,
  );
  assert.match(css, /\.workspace-pill,[\s\S]*?\.topbar-search \{[\s\S]*?min-height: var\(--ds-control\);/);
  assert.match(css, /\.cockpit-app \.workspace-primary-tabs \{[\s\S]*?border-radius: var\(--ds-radius-sm\);/);
  assert.match(css, /\.workspace-menu \{[\s\S]*?border-radius: var\(--ds-radius-md\);/);
  assert.match(css, /\.endpoint-error-banner span \{[\s\S]*?font-size: var\(--ds-text-xs\);/);
});

test("scoped shell declarations resolve to canonical active values", () => {
  assert.equal(resolveToken(activeDeclaration(".topbar-search", "border-radius")), "4px");
  assert.equal(resolveToken(activeDeclaration(".cockpit-app .header-controls select", "border-radius")), "4px");
  assert.equal(resolveToken(activeDeclaration(".cockpit-app .status-badge", "border-radius")), "4px");
  assert.equal(resolveToken(activeDeclaration(".cockpit-app .workspace-primary-tabs", "border-radius")), "4px");
  assert.equal(activeDeclaration(".cockpit-app .panel", "padding"), "16px");
  assert.equal(activeDeclaration(".section-heading", "gap"), "12px");
});
