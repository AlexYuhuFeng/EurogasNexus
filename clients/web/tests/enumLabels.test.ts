import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";

import { enumLabel, humanizeEnum, isEnumToken, sourceSystemLabel } from "../src/app/model/enumLabels.ts";

// Enums are said in words (UX_REFERENCE rule 21); the sweep's phone pass fails on a bare code.

test("an enum code reads as words, acronyms kept", () => {
  assert.equal(humanizeEnum("SUCCEEDED_WITH_WARNINGS"), "Succeeded with warnings");
  assert.equal(humanizeEnum("NOT_REQUIRED"), "Not required");
  assert.equal(humanizeEnum("PIPELINE_IMPORT"), "Pipeline import");
  assert.equal(humanizeEnum("ENTSOG_UMM"), "ENTSOG UMM");
  assert.ok(isEnumToken("AVAILABLE_NOW") && !isEnumToken("AVAILABLE") && !isEnumToken("TTF") && !isEnumToken("Not_an_enum"));
});

test("a locale label wins over the humanized code", () => {
  const t = (key: string, options?: Record<string, unknown>) => (key === "enum.not_required" ? "Not needed" : String(options?.defaultValue));
  assert.equal(enumLabel("NOT_REQUIRED", t), "Not needed");
  assert.equal(enumLabel("FEASIBLE_WITH_WARNINGS", t), "Feasible with warnings");
  assert.equal(enumLabel(null), "");
});

test("source systems read as the desk names them", () => {
  assert.equal(sourceSystemLabel("ICE_ENDEX"), "ICE Endex");
  assert.equal(sourceSystemLabel("NATIONAL_GAS_DEMAND"), "National Gas demand");
  assert.equal(sourceSystemLabel("ENTSOG"), "ENTSOG");
  assert.equal(sourceSystemLabel("SOME_NEW_FEED"), "Some new feed");
});

test("a capitalised status word is a code too, an acronym is not", async () => {
  const { isStatusCode } = await import("../src/app/model/enumLabels.ts");
  assert.ok(isStatusCode("AVAILABLE") && isStatusCode("UNKNOWN") && isStatusCode("NOT_REQUIRED"));
  assert.ok(!isStatusCode("TTF") && !isStatusCode("ENTSOG") && !isStatusCode("Ready"));
});

test("no '(s)' or '(es)' plural in either locale: counts use the i18n plural forms", () => {
  const en = JSON.parse(readFileSync(new URL("../src/i18n/en.json", import.meta.url), "utf8")) as Record<string, string>;
  const zh = JSON.parse(readFileSync(new URL("../src/i18n/zh.json", import.meta.url), "utf8")) as Record<string, string>;
  const offenders = Object.entries(en).filter(([, value]) => /[a-z]\((s|es)\)/i.test(value)).map(([key]) => key);
  assert.deepEqual(offenders, []);
  for (const key of Object.keys(en).filter((item) => item.endsWith("_one") && en[item.slice(0, -4)] !== undefined)) {
    const base = key.slice(0, -4);
    assert.ok(en[base], `${key} has a plural base`);
    assert.ok(zh[key] && zh[base], `zh carries ${key}`);
  }
});

test("a code quoted inside a sentence is said in words", async () => {
  const { enumWordsIn } = await import("../src/app/model/enumLabels.ts");
  assert.equal(enumWordsIn("route R-2: TARIFF_MISSING"), "route R-2: tariff missing");
  assert.equal(enumWordsIn("TARIFF_MISSING for PEG"), "Tariff missing for PEG");
  assert.equal(enumWordsIn("TTF and NBP stay"), "TTF and NBP stay");
  assert.equal(enumWordsIn("from ENTSOG_UMM"), "from ENTSOG UMM");
});
