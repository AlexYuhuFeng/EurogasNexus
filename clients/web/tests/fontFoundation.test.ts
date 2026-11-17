import assert from "node:assert/strict";
import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

// The interface face is bundled and no feature tag reaches a device font (DESIGN_TOKENS.md,
// "Typeface"). A phone's UI font turned every "B" and "%" into status-bar unit glyphs
// ("ᴮreaking", "NᴮP", "ᴳᴮP/MWh") because the page asked for stylistic sets ("ss01", "cv11")
// that only mean something in Inter, and Inter was not shipped, so the device font drew the text.
const SRC = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../src");
// Reports print with their own stack (reports.css); they are documents, not interface text.
const EXEMPT = new Set(["styles/reports.css"]);

function cssFiles(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const full = path.join(dir, name);
    if (statSync(full).isDirectory()) return cssFiles(full);
    return name.endsWith(".css") ? [full] : [];
  });
}

const sheets = cssFiles(SRC)
  .map((file) => ({ rel: path.relative(SRC, file).split(path.sep).join("/"), text: readFileSync(file, "utf8") }))
  .filter((sheet) => !EXEMPT.has(sheet.rel))
  .map((sheet) => ({ ...sheet, text: sheet.text.replace(/\/\*[\s\S]*?\*\//g, "") }));

function declarations(text: string, property: string): string[] {
  const re = new RegExp(`(?:^|[;{\\s])${property}\\s*:\\s*([^;}]+)`, "g");
  return [...text.matchAll(re)].map((match) => match[1].trim());
}

const tokens = readFileSync(path.join(SRC, "styles/tokens.css"), "utf8");
const fontsCss = readFileSync(path.join(SRC, "styles/fonts.css"), "utf8");
const designSystem = readFileSync(path.join(SRC, "styles/design-system.css"), "utf8");

test("the interface token names the bundled face first", () => {
  const match = tokens.match(/--ds-font-ui:\s*([^;]+);/);
  assert.ok(match, "--ds-font-ui is defined");
  const first = match[1].split(",")[0].trim().replace(/["']/g, "");
  assert.equal(first, "Inter");
  // ... and that face is one this client ships, from its own origin.
  const faces = [...fontsCss.matchAll(/@font-face\s*{([^}]*)}/g)].map((m) => m[1]);
  assert.ok(faces.length >= 1);
  for (const face of faces) {
    assert.match(face, /font-family:\s*"Inter"/);
    assert.match(face, /font-display:\s*swap/);
    const url = face.match(/url\("([^"]+)"\)/)?.[1] ?? "";
    assert.ok(url.startsWith("../assets/fonts/"), `self-hosted, not ${url}`);
    assert.ok(existsSync(path.resolve(SRC, "styles", url)), `${url} exists`);
    assert.doesNotMatch(face, /local\(/, "never a locally installed copy of unknown provenance");
  }
  assert.match(designSystem, /@import url\("\.\/fonts\.css"\);/);
});

test("no interface stylesheet starts a font stack with a system family", () => {
  const allowedFirst = /^(var\(--ds-font-(ui|mono)[,)]|inherit|"Inter")/;
  for (const sheet of sheets) {
    for (const value of declarations(sheet.text, "font-family")) {
      assert.match(value, allowedFirst, `${sheet.rel}: font-family: ${value}`);
    }
  }
});

test("no stylesheet turns ligatures, contextual alternates or stylistic sets back on", () => {
  for (const sheet of sheets) {
    for (const value of declarations(sheet.text, "font-variant-ligatures")) {
      assert.equal(value, "none", `${sheet.rel}: font-variant-ligatures: ${value}`);
    }
    for (const value of declarations(sheet.text, "font-feature-settings")) {
      // Only numeral features may be named; letter features mean whatever the drawing face says.
      const tags = [...value.matchAll(/"([a-z0-9]{4})"/g)].map((m) => m[1]);
      assert.ok(value === "normal" || tags.every((tag) => ["tnum", "lnum", "zero"].includes(tag)), `${sheet.rel}: font-feature-settings: ${value}`);
    }
    for (const value of declarations(sheet.text, "font-variant")) {
      assert.doesNotMatch(value, /common-ligatures|discretionary-ligatures|historical-ligatures|contextual/, sheet.rel);
    }
  }
  // The global switch is unlayered, so a layered `font:` shorthand cannot undo it.
  const unlayered = fontsCss.replace(/@layer[^{]*{[\s\S]*?}\s*}/g, "");
  assert.match(unlayered, /\*,\s*\*::before,\s*\*::after\s*{\s*font-variant-ligatures:\s*none;/);
});

test("TSX never sets a font family or feature inline", () => {
  const tsx = (dir: string): string[] =>
    readdirSync(dir).flatMap((name) => {
      const full = path.join(dir, name);
      if (statSync(full).isDirectory()) return tsx(full);
      return name.endsWith(".tsx") ? [full] : [];
    });
  for (const file of tsx(SRC)) {
    const text = readFileSync(file, "utf8");
    assert.doesNotMatch(text, /fontFeatureSettings|fontVariantLigatures/, file);
    assert.doesNotMatch(text, /fontFamily:\s*["'](?!var\(--ds-font)/, file);
  }
});
