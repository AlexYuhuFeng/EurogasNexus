import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const css = readFileSync(new URL("../src/styles/app.css", import.meta.url), "utf8");

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

function resolveToken(value: string): string {
  const token = value.match(/^var\((--[^)]+)\)$/)?.[1];
  if (!token) return value;
  const declaration = new RegExp(`${token}:\\s*([^;]+);`).exec(css);
  assert.ok(declaration, `missing token declaration for ${token}`);
  return declaration[1].trim();
}

test("Constitution token foundation keeps the approved canonical values", () => {
  const tokens = {
    "--text-meta": "11px",
    "--text-body": "12px",
    "--text-control": "13px",
    "--text-panel-title": "14px",
    "--text-workspace-title": "18px",
    "--text-page-title": "20px",
    "--space-1": "4px",
    "--space-2": "8px",
    "--space-3": "12px",
    "--space-4": "16px",
    "--space-5": "24px",
    "--space-6": "32px",
    "--control-compact": "28px",
    "--control-standard": "32px",
    "--control-prominent": "36px",
    "--radius-control": "4px",
    "--radius-panel": "6px",
    "--radius-large": "8px",
    "--motion-none": "0ms",
    "--motion-fast": "120ms",
    "--motion-standard": "180ms",
    "--motion-emphasis": "240ms",
  };

  for (const [name, value] of Object.entries(tokens)) {
    assert.match(css, new RegExp(`${name}:\\s*${value.replace(".", "\\.")};`));
  }
});

test("shared shell surfaces use the token foundation at their ownership points", () => {
  assert.match(
    css,
    /\.cockpit-app \.cockpit-topbar \{[\s\S]*?gap: var\(--space-2\) var\(--space-3\);[\s\S]*?padding: var\(--space-3\) var\(--space-4\);/,
  );
  assert.match(
    css,
    /\.endpoint-error-banner \{[\s\S]*?gap: var\(--space-1\) var\(--space-3\);[\s\S]*?padding: var\(--space-2\) var\(--space-3\);/,
  );
  assert.match(
    css,
    /\.workspace-pill,[\s\S]*?\.topbar-search \{[\s\S]*?min-height: var\(--control-prominent\);/,
  );
  assert.match(css, /\.cockpit-app \.workspace-primary-tabs \{[\s\S]*?border-radius: var\(--radius-control\);/);
  assert.match(css, /\.workspace-menu \{[\s\S]*?border-radius: var\(--radius-panel\);/);
  assert.match(css, /\.endpoint-error-banner span \{[\s\S]*?font-size: var\(--text-meta\);/);
});

test("scoped shell declarations resolve to canonical active values", () => {
  assert.equal(resolveToken(activeDeclaration(".topbar-search", "border-radius")), "4px");
  assert.equal(
    resolveToken(activeDeclaration(".cockpit-app .header-controls select", "border-radius")),
    "4px",
  );
  assert.equal(
    resolveToken(activeDeclaration(".cockpit-app .status-badge", "border-radius")),
    "4px",
  );
  assert.equal(
    resolveToken(activeDeclaration(".cockpit-app .workspace-primary-tabs", "border-radius")),
    "4px",
  );
  assert.equal(activeDeclaration(".cockpit-app .panel", "padding"), "16px");
  assert.equal(activeDeclaration(".section-heading", "gap"), "12px");
});
