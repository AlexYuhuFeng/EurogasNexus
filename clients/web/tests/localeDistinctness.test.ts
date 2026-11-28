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
  // Desk → Board: placeholders and the desk's own codes only.
  "board.cell_title": "source · time · unit, all placeholders",
  "board.detail.price_title": "hub and contract codes, placeholders",
  "board.fund.flow.bbl": "pipeline name (BBL)",
  "board.fund.flow.iuk": "pipeline name (IUK)",
  "board.fund.lng_country": "LNG and a country code",
  "board.fund.title": "day · source, placeholders",
  "access.view.sso": "an acronym",
  "eod.detail.volume": "two figures and the unit MWh, no words",
  "eod.detail.price": "two figures and a currency per MWh, no words",
  "eod.detail.pair": "two values joined by a slash, no words",
  "answer.as_of_source": "a date and a source name joined by a separator, no words",
  "answer.convert.factor": "an equation of a figure and unit codes, no words",
  "answer.gasday.window": "two times joined by an arrow, no words",
  "answer.outages.top": "a list of facility names and figures, no words",
  "answer.spread.legs": "two hub codes with their prices and unit codes, no words",
  "answer.tag.lng": "an acronym",
  "glossary.cat.lng": "an acronym",
  "app.title": "the product's own name",
  "capacity.view_lng": "an acronym",
  "chart.csv": "a file format's name",
  "contracts.kind.slope_price": "a price formula of figures and unit codes, no words",
  "evidence.utc": "a time-basis token, the same in both locales",
  "experience.palette.group.ai": "an acronym",
  "nwe.lng": "an acronym",
  "fb.line.lng": "an acronym",
  "panel.lng": "an acronym in a vendor's own product name",
  "prices.board.reporting_plain": "a figure and its unit only, the same in both locales",
  "preferences.time_zone.utc": "the time standard's name, written UTC in both locales",
  "report.format_csv": "a file format's name",
  "tariffs.tso": "an acronym",
  "tariffBook.access.api": "an acronym",
  "today.gas_day.mw": "a number and the unit MW",
  "today.gas_day.until": "a cut-off name and a time, both translated before",
  "report.format_pdf": "a file format's name",
  "report.format_xlsx": "a product's own name",
  "settings.chinese": "a language named in its own language",
  "settings.english": "a language named in its own language",
  "sources.category.llm": "an acronym",
  "audit.word.ai": "an acronym",
  "audit.word.api": "an acronym",
  "audit.word.lng": "an acronym",
  "audit.word.mcp": "an acronym",
  "audit.word.pdf": "an acronym",
  "audit.word.tso": "an acronym",
  "setup.item.src-argus.name": "a provider's own name",
  "setup.item.src-eex.name": "a provider's own name",
  "setup.item.src-gie.name": "a provider's own name",
  "setup.item.src-ice-endex.name": "a provider's own name",
  "setup.item.src-ice-ocm.name": "a provider's own name",
  "setup.item.src-icis.name": "a provider's own name",
  "setup.item.src-ngx.name": "a provider's own name",
  "setup.item.src-platts.name": "a provider's own name",
  "setup.item.src-trayport.name": "a provider's own name",
  "setup.step.ai.title": "an acronym",
  "prompt.col.mwh": "a unit symbol",
  "cargo.form.hh": "a hub's own name, kept in Latin like the hub codes",
  "cargo.sens.hh": "a hub's own name, kept in Latin like the hub codes",
  "contracts.price.index_name.HH": "a hub's own name, kept in Latin like the hub codes",
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
