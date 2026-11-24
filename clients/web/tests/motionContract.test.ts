/**
 * UX R10 (research/16B): one source of truth for motion durations, radii and control heights.
 * tokens.css is it; MOTION_SYSTEM.md and the UI constitution quote it, and this test fails when
 * a quote drifts. It also holds the motion rules R10 set: exits accelerate in about three
 * quarters of the entry, overlays have an exit, panels do not replay an entrance on a page
 * change (the page container fades once), and no converted stylesheet writes its own duration.
 */
import assert from "node:assert/strict";
import { readdirSync, readFileSync, statSync } from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const SRC = path.resolve(HERE, "../src");
const ROOT = path.resolve(HERE, "../../..");
const tokensCss = readFileSync(path.join(SRC, "styles/tokens.css"), "utf8").replace(/\/\*[\s\S]*?\*\//g, "");
const root = tokensCss.slice(tokensCss.indexOf(":root {"), tokensCss.indexOf("\n}", tokensCss.indexOf(":root {")));
const token = (name: string): string => {
  const m = root.match(new RegExp(`${name}:\\s*([^;]+);`));
  assert.ok(m, `${name} in tokens.css`);
  return m[1].trim();
};
const ms = (value: string): number => (value.endsWith("ms") ? Number.parseFloat(value) : Number.parseFloat(value) * 1000);

const motionDoc = readFileSync(path.join(ROOT, "docs/clients/MOTION_SYSTEM.md"), "utf8");
const constitution = readFileSync(path.join(ROOT, "docs/clients/PROFESSIONAL_UI_CONSTITUTION.md"), "utf8");

test("MOTION_SYSTEM.md quotes every duration and easing token as tokens.css defines it", () => {
  const names = ["fast", "base", "slow", "exit", "exit-slow", "flash", "map", "pulse", "loop"].map((n) => `--ds-duration-${n}`);
  for (const name of names) {
    const row = motionDoc.match(new RegExp(`\\| \`${name}\` \\| (\\d+)ms \\|`));
    assert.ok(row, `${name} has a row in MOTION_SYSTEM.md`);
    assert.equal(Number(row[1]), ms(token(name)), `${name} in MOTION_SYSTEM.md equals tokens.css`);
  }
  for (const name of ["--ds-ease-out", "--ds-ease-in", "--ds-ease-in-out"]) {
    assert.ok(motionDoc.includes(`| \`${name}\` | \`${token(name)}\` |`), `${name} curve quoted in MOTION_SYSTEM.md`);
  }
});

test("the constitution's radii, control heights and motion scale are the tokens", () => {
  for (const name of ["--ds-radius-sm", "--ds-radius-md", "--ds-radius-pill", "--ds-control-sm", "--ds-control", "--ds-control-touch"]) {
    assert.ok(constitution.includes(`\`${name}: ${token(name)}\``), `constitution quotes ${name}: ${token(name)}`);
  }
  const scale = ["fast", "base", "slow"].map((n) => ms(token(`--ds-duration-${n}`))).join("/");
  assert.ok(constitution.includes(`0/${scale}ms`), `constitution quotes the 0/${scale}ms scale`);
  const exits = ["exit", "exit-slow"].map((n) => ms(token(`--ds-duration-${n}`))).join("/");
  assert.ok(constitution.includes(`${exits}ms`), `constitution quotes the ${exits}ms exits`);
  // The retired values must not come back as rules.
  assert.doesNotMatch(constitution, /--radius-panel: 6px|--control-prominent: 36px|0\/120\/180\/240ms/);
});

test("an exit accelerates and takes about three quarters of its entry", () => {
  assert.equal(token("--ds-ease-in"), "cubic-bezier(0.4, 0, 1, 1)");
  for (const [exit, entry] of [["--ds-duration-exit", "--ds-duration-base"], ["--ds-duration-exit-slow", "--ds-duration-slow"]]) {
    const ratio = ms(token(exit)) / ms(token(entry));
    assert.ok(ratio >= 0.7 && ratio <= 0.8, `${exit} is ${ratio.toFixed(2)} of ${entry}`);
  }
});

test("dialogs, sheets and popovers close with an exit transition, and only when motion is allowed", () => {
  const controls = readFileSync(path.join(SRC, "components/ui/controls.css"), "utf8");
  const motion = controls.slice(controls.indexOf("@media (prefers-reduced-motion: no-preference)"));
  assert.match(motion, /\.ds-dialog:not\(\[open\]\),\s*\.ds-sheet:not\(\[open\]\) \{[\s\S]*?var\(--ds-duration-exit\) var\(--ds-ease-in\) allow-discrete/);
  assert.match(motion, /@supports selector\(:popover-open\) \{\s*\.ds-popover:not\(:popover-open\) \{[\s\S]*?display var\(--ds-duration-exit\) var\(--ds-ease-in\) allow-discrete/);
  for (const file of ["components/ui/Dialog.tsx", "components/ui/Popover.tsx"]) {
    const source = readFileSync(path.join(SRC, file), "utf8");
    assert.match(source, /usePresence\(open, /, `${file} keeps its content while it exits`);
    assert.doesNotMatch(source, /\{open && \(\s*<(div className="ds-dialog-frame"|div\s+ref=\{panelRef\})/, `${file} no longer drops its content at once`);
  }
});

test("a page change fades the page container once; panels play no entrance of their own", () => {
  const ds = readFileSync(path.join(SRC, "styles/design-system.css"), "utf8").replace(/\/\*[\s\S]*?\*\//g, "");
  assert.doesNotMatch(ds, /\.workspace-panel\s*\{\s*animation:/);
  const shell = readFileSync(path.join(SRC, "app/shell/AppShell.tsx"), "utf8");
  assert.match(shell, /usePageEnter\(mainRef, navigation\.activeWorkspace\)/);
  assert.match(shell, /<main className="app-main" ref=\{mainRef\}/);
  const hook = readFileSync(path.join(SRC, "app/shell/usePageEnter.ts"), "utf8");
  assert.match(hook, /prefers-reduced-motion: reduce/);
  assert.match(hook, /--ds-duration-base/);
  assert.match(hook, /\[\{ opacity: 0 \}, \{ opacity: 1 \}\]/, "opacity only: nothing moves under the pointer");
});

function cssFiles(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const full = path.join(dir, name);
    if (statSync(full).isDirectory()) return cssFiles(full);
    return name.endsWith(".css") ? [full] : [];
  });
}

test("no stylesheet but the tokens (and the unconverted app.css) writes its own duration", () => {
  const offenders: string[] = [];
  for (const file of cssFiles(SRC)) {
    const rel = path.relative(SRC, file);
    if (rel === "styles/tokens.css" || rel === "styles/app.css") continue;
    const text = readFileSync(file, "utf8").replace(/\/\*[\s\S]*?\*\//g, "");
    for (const m of text.matchAll(/(transition|animation)(-duration|-delay)?\s*:([^;]*);/g)) {
      const value = m[3].replace(/var\([^)]*\)/g, "");
      // The reduced-motion override (0.01ms !important) is the one allowed literal.
      if (/\b\d*\.?\d+m?s\b/.test(value) && !/^\s*0\.01ms !important\s*$/.test(value)) offenders.push(`${rel}: ${m[0]}`);
    }
  }
  assert.deepEqual(offenders, []);
});

test("usePresence reads a CSS duration in ms or s", async () => {
  const { parseDuration } = await import("../src/components/ui/usePresence.ts");
  assert.equal(parseDuration("120ms"), 120);
  assert.equal(parseDuration(" 0.18s "), 180);
  assert.equal(parseDuration(""), 0);
  assert.equal(parseDuration("auto"), 0);
});
