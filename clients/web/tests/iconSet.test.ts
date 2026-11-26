import assert from "node:assert/strict";
import { readdirSync, readFileSync, statSync } from "node:fs";
import path from "node:path";
import test, { after } from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { fileURLToPath } from "node:url";

import { closeApiStoreHarness, loadApiStore } from "./support/apiStoreHarness.ts";

after(closeApiStoreHarness);
type Ui = typeof import("../src/components/ui/index.ts");
async function ui(): Promise<Ui> {
  const { load } = await loadApiStore();
  return load<Ui>("/src/components/ui/index.ts");
}

// UX R9 (research/16B): one licensed icon set (Lucide, ISC) behind one Icon primitive. A bare
// "×", "▾", "▸", "›" or "‹" used as a control's whole content fails here: it is a mystery glyph
// whose size, weight and baseline follow the font, not the design system.
const SRC = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../src");
const ROOT = path.resolve(SRC, "../../..");
/** The Opportunities page is being reworked for live updates elsewhere; its close glyph moves then. */
const BASELINE: Record<string, number> = { "components/opportunities/OpportunityDetail.tsx": 1 };

function sources(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const full = path.join(dir, name);
    if (statSync(full).isDirectory()) return sources(full);
    return name.endsWith(".tsx") ? [full] : [];
  });
}

test("no control is a bare glyph: close, chevrons and carets come from Icon", () => {
  const glyph = "[×▾▸›‹]";
  const asText = new RegExp(`>\\s*${glyph}\\s*<`, "g");
  const asString = new RegExp(`["'\`]${glyph}\\s?["'\`]`, "g");
  const over: string[] = [];
  for (const file of sources(SRC)) {
    const text = readFileSync(file, "utf8").replace(/\/\*[\s\S]*?\*\/|\/\/.*$/gm, "");
    const count = (text.match(asText) ?? []).length + (text.match(asString) ?? []).length;
    const key = path.relative(SRC, file).split(path.sep).join("/");
    if (count > (BASELINE[key] ?? 0)) over.push(`${key}: ${count}`);
  }
  assert.deepEqual(over, []);
});

test("no component draws its own icon SVG; charts, the progress ring, the brand mark and map art are not icons", () => {
  const allowed = new Set(["components/ui/BrandMark.tsx", "components/ui/Spinner.tsx", "components/ui/charts/Chart.tsx", "components/ui/charts/Waterfall.tsx", "components/GasNetworkMap.tsx", "components/SignInScreen.tsx"]);
  const drawn = sources(SRC)
    .filter((file) => /<svg[\s>]/.test(readFileSync(file, "utf8")))
    .map((file) => path.relative(SRC, file).split(path.sep).join("/"))
    .filter((file) => !allowed.has(file));
  assert.deepEqual(drawn, []);
});

test("an icon is hidden from assistive technology and sized by the design system", async () => {
  const { Icon } = await ui();
  const html = renderToStaticMarkup(React.createElement(Icon, { name: "close", size: "md" }));
  assert.match(html, /^<svg [^>]*class="lucide lucide-x ds-icon-svg" data-icon="close" data-size="md" aria-hidden="true" focusable="false">/);
  const css = readFileSync(path.join(SRC, "components/ui/primitives.css"), "utf8");
  assert.match(css, /\.ds-icon-svg \{[^}]*stroke-width: var\(--ds-icon-stroke\);/);
  const tokens = readFileSync(path.join(SRC, "styles/tokens.css"), "utf8");
  for (const token of ["--ds-icon-xs: 12px", "--ds-icon-sm: 16px", "--ds-icon-md: 20px", "--ds-icon-stroke:"]) assert.ok(tokens.includes(token), token);
});

test("each status has its own shape", async () => {
  const { ICONS } = await ui();
  const shapes = ["ok", "watch", "breach", "stale", "simulated", "info"].map((tone) => ICONS[`status-${tone}` as keyof typeof ICONS]);
  assert.equal(new Set(shapes).size, shapes.length);
});

test("the icon set is a recorded, commercial-friendly dependency", () => {
  const pkg = JSON.parse(readFileSync(path.join(SRC, "../package.json"), "utf8")) as { dependencies: Record<string, string> };
  assert.match(pkg.dependencies["lucide-react"], /^\d+\.\d+\.\d+$/, "pinned exactly");
  const lock = JSON.parse(readFileSync(path.join(SRC, "../package-lock.json"), "utf8")) as { packages: Record<string, { license?: string }> };
  assert.equal(lock.packages["node_modules/lucide-react"].license, "ISC");
  const notices = readFileSync(path.join(ROOT, "THIRD_PARTY_NOTICES.md"), "utf8");
  assert.match(notices, new RegExp(`- lucide-react ${pkg.dependencies["lucide-react"].replace(/\./g, "\\.")} \\(ISC\\)`));
});
