import assert from "node:assert/strict";
import test from "node:test";

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
