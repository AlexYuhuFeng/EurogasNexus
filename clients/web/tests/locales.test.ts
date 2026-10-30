import assert from "node:assert/strict";
import test from "node:test";

import { intlLocaleFor, LOCALES, localeFor } from "../src/i18n/locales.ts";
import { SUPPORTED_LANGUAGES } from "../src/i18n/language.ts";
import en from "../src/i18n/en.json" with { type: "json" };
import zh from "../src/i18n/zh.json" with { type: "json" };

test("one registry drives the supported languages and Intl locales", () => {
  assert.deepEqual([...SUPPORTED_LANGUAGES], LOCALES.map((locale) => locale.code));
  assert.equal(intlLocaleFor("en"), "en-GB");
  assert.equal(intlLocaleFor("zh-CN"), "zh-CN");
  assert.equal(localeFor("zh-Hans").code, "zh-CN");
  assert.equal(localeFor("fr").code, "en");
});

test("the translations cover the same keys", () => {
  const english = new Set(Object.keys(en));
  const chinese = new Set(Object.keys(zh));
  assert.deepEqual(Object.keys(zh).filter((key) => !english.has(key)), []);
  assert.deepEqual(Object.keys(en).filter((key) => !chinese.has(key)), []);
});
