/**
 * Bilingual locale discipline.
 *
 * Key parity and duplicate keys were already checked from the raw text in several places, but
 * nothing checked that a value had actually been *translated*: 24 `agents.*` keys carried their
 * English text as the Chinese value, so the whole agents workspace read as English to a Chinese
 * user while every existing check passed. This gate holds the two locales together and pins the
 * small set of values that are the same words in both locales by design, so an untranslated string
 * cannot arrive silently again.
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

function readLocale(name: "en" | "zh"): Record<string, string> {
  const raw = readFileSync(new URL(`../src/i18n/${name}.json`, import.meta.url), "utf8");
  return JSON.parse(raw) as Record<string, string>;
}

/**
 * Values that are identical in both locales because they are the same word in both: acronyms, proper
 * nouns, product names, a language's own name, and one identifier shape.
 *
 * Each entry states why, because "it happens to be the same" is not a reason.
 */
const IDENTICAL_BY_DESIGN: Readonly<Record<string, string>> = {
  "access.view.sso": "an acronym",
  "agents.run_id_placeholder": "an identifier shape, not prose",
  "app.title": "the product's own name",
  "capacity.view_lng": "an acronym",
  "evidence.utc": "a time-basis token, the same in both locales",
  "experience.palette.group.ai": "an acronym",
  "map.layer.lng": "an acronym",
  "panel.lng": "an acronym in a vendor's own product name",
  "settings.chinese": "a language named in its own language",
  "settings.english": "a language named in its own language",
  "sources.category.llm": "an acronym",
  "status.alembic": "a tool's own name",
  "strategy_lab.kpi": "an acronym",
};

test("the two locales declare exactly the same keys", () => {
  const en = readLocale("en");
  const zh = readLocale("zh");
  const onlyEnglish = Object.keys(en).filter((key) => !(key in zh)).sort();
  const onlyChinese = Object.keys(zh).filter((key) => !(key in en)).sort();
  assert.deepEqual(onlyEnglish, [], "declared in en only");
  assert.deepEqual(onlyChinese, [], "declared in zh only");
  assert.ok(Object.keys(en).length > 2000, "the locales are the product's vocabulary");
});

test("no value is left untranslated, and every deliberate sameness is declared", () => {
  const en = readLocale("en");
  const zh = readLocale("zh");
  const identical = Object.keys(en)
    .filter((key) => en[key] === zh[key])
    .sort();
  // A key that is the same in both locales is either declared here with its reason or it is an
  // untranslated string, and the second one is a defect rather than a style choice.
  assert.deepEqual(
    identical,
    Object.keys(IDENTICAL_BY_DESIGN).sort(),
    "identical values must be declared by design",
  );
  for (const [key, reason] of Object.entries(IDENTICAL_BY_DESIGN)) {
    assert.ok(en[key]?.trim(), `en ${key}`);
    assert.ok(zh[key]?.trim(), `zh ${key}`);
    assert.ok(reason.trim(), `reason for ${key}`);
  }
});

test("every declared value is non-empty in both locales", () => {
  const en = readLocale("en");
  const zh = readLocale("zh");
  for (const key of Object.keys(en)) {
    assert.ok(en[key].trim(), `en ${key} is empty`);
    assert.ok(zh[key].trim(), `zh ${key} is empty`);
  }
});
