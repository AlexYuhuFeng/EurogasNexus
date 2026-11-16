import assert from "node:assert/strict";
import { test } from "node:test";

import { ensureUsableLanguage, isUsableLocale } from "../src/components/ui/charts/uplotLoader.ts";

test("a language Intl rejects is recognised before the chart library reads it", () => {
  assert.equal(isUsableLocale("en-GB"), true);
  assert.equal(isUsableLocale("zh-CN"), true);
  // What a headless Chromium reports under the C/POSIX locale; it crashed the app on load.
  assert.equal(isUsableLocale("en-US@posix"), false);
  assert.equal(isUsableLocale(""), false);
  assert.equal(isUsableLocale(undefined), false);
});

test("an unusable browser language is replaced; a usable one is left alone", () => {
  const broken = { language: "en-US@posix" };
  ensureUsableLanguage(broken);
  assert.equal(broken.language, "en-US");
  assert.doesNotThrow(() => new Intl.NumberFormat(broken.language));

  const fine = { language: "de-DE" };
  ensureUsableLanguage(fine);
  assert.equal(fine.language, "de-DE");
});

test("the chart never imports the library statically", async () => {
  const { readFile } = await import("node:fs/promises");
  const chart = await readFile(new URL("../src/components/ui/charts/Chart.tsx", import.meta.url), "utf8");
  assert.doesNotMatch(chart, /^import uPlot from "uplot"/m);
  assert.match(chart, /import type uPlot from "uplot"/);
});
