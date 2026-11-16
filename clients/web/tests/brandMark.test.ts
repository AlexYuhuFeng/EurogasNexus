/**
 * The brand mark (docs/product/BRAND_MARK.md): one accessible image named "Eurogas Nexus" or
 * hidden beside the written name; the name is live text, the same in every language; the tone
 * is a class the token stylesheet keys on, and mono draws in currentColor so it follows the
 * theme. The geometry itself is checked in tests/unit/test_brand_mark.py.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test, { after } from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { closeApiStoreHarness, loadApiStore } from "./support/apiStoreHarness.ts";

after(closeApiStoreHarness);

type Ui = typeof import("../src/components/ui/index.ts");

async function ui(): Promise<Ui> {
  const { load } = await loadApiStore();
  return load<Ui>("/src/components/ui/index.ts");
}

const h = React.createElement;
const render = (element: React.ReactElement) => renderToStaticMarkup(element);

test("BrandMark: the mark alone is one named image, mono by default, in currentColor", async () => {
  const { BrandMark } = await ui();
  const html = render(h(BrandMark));
  assert.match(html, /^<span class="ds-brand ds-brand-mark ds-brand-mono ds-brand-md"><svg /);
  assert.match(html, /role="img"/);
  assert.match(html, /aria-label="Eurogas Nexus"/);
  assert.match(html, /focusable="false"/);
  assert.match(html, /viewBox="0 0 32 32" width="24" height="24"/);
  assert.match(html, /stroke="currentColor"/);
  assert.equal((html.match(/<path /g) ?? []).length, 3, "two hexagon halves and the wave");
  assert.doesNotMatch(html, /<text|<image|href=/, "no text outlines, rasters or external assets");
});

test("BrandMark: sizes are steps, a number sets the mark in px", async () => {
  const { BrandMark } = await ui();
  assert.match(render(h(BrandMark, { size: "sm" })), /width="20" height="20"/);
  assert.match(render(h(BrandMark, { size: "xl" })), /width="40" height="40"/);
  assert.match(render(h(BrandMark, { size: 16 })), /width="16" height="16"/);
});

test("BrandMark: lock-ups carry the name as live text and one accessible name", async () => {
  const { BrandMark } = await ui();
  const word = render(h(BrandMark, { variant: "wordmark", tone: "colour", size: "lg" }));
  assert.match(word, /^<span class="ds-brand ds-brand-wordmark ds-brand-colour ds-brand-lg" role="img" aria-label="Eurogas Nexus">/);
  assert.match(word, /<span class="ds-brand-name" aria-hidden="true">Eurogas <span class="ds-brand-accent">Nexus<\/span><\/span>/);
  // The glyph inside a named lock-up is hidden: the name is said once.
  assert.match(word, /<svg[^>]*aria-hidden="true"/);
  assert.doesNotMatch(word, /<svg[^>]*role="img"/);
  const mono = render(h(BrandMark, { variant: "monogram" }));
  assert.match(mono, /class="ds-brand ds-brand-monogram ds-brand-mono ds-brand-md"/);
  assert.match(mono, />E<span class="ds-brand-accent">N<\/span>/);
  assert.match(mono, /aria-label="Eurogas Nexus"/);
});

test("BrandMark: decorative beside the written name, hidden from assistive technology", async () => {
  const { BrandMark } = await ui();
  const html = render(h(BrandMark, { variant: "wordmark", tone: "reverse", decorative: true }));
  assert.match(html, /^<span class="ds-brand ds-brand-wordmark ds-brand-reverse ds-brand-md" aria-hidden="true">/);
  assert.doesNotMatch(html, /role="img"|aria-label/);
  const mark = render(h(BrandMark, { decorative: true }));
  assert.doesNotMatch(mark, /role="img"|aria-label/);
  assert.match(mark, /aria-hidden="true"/);
});

test("BrandMark: the name is not translated (\"Eurogas Nexus\" in English and Chinese)", () => {
  const source = readFileSync(new URL("../src/components/ui/BrandMark.tsx", import.meta.url), "utf8");
  assert.doesNotMatch(source, /\bt\(|i18n|useTranslation/);
});

test("brand tones take their colours from tokens; colour and reverse never draw in currentColor", () => {
  const css = readFileSync(new URL("../src/components/ui/brand.css", import.meta.url), "utf8");
  assert.match(css, /--brand-ink: var\(--ds-brand-navy\)/);
  assert.match(css, /--brand-flow: var\(--ds-brand-blue\)/);
  assert.match(css, /--brand-ink: var\(--ds-on-brand\)/);
  assert.match(css, /--brand-flow: var\(--ds-brand-blue-light\)/);
  assert.match(css, /:root\.dark \.ds-brand-auto/);
  assert.doesNotMatch(css, /#[0-9a-f]{3,8}\b/i);
  const tokens = readFileSync(new URL("../src/styles/tokens.css", import.meta.url), "utf8");
  for (const name of ["--ds-brand-navy", "--ds-brand-blue", "--ds-brand-blue-light", "--ds-on-brand"]) {
    assert.match(tokens, new RegExp(`${name}:\\s*#`), `${name} is a token`);
  }
});

test("the top bar and the sign-in screen use the mark, not a drawn copy", () => {
  const bar = readFileSync(new URL("../src/components/WorkspaceTopBar.tsx", import.meta.url), "utf8");
  assert.match(bar, /<BrandMark[\s\S]*?tone="mono"/);
  assert.match(bar, /widthClass === "wide" \? "wordmark" : "mark"/);
  const signIn = readFileSync(new URL("../src/components/SignInScreen.tsx", import.meta.url), "utf8");
  assert.match(signIn, /<BrandMark variant="wordmark" tone="reverse"/);
  assert.match(signIn, /<BrandMark variant="wordmark" tone="auto"/);
  assert.doesNotMatch(signIn, /<svg/);
});
