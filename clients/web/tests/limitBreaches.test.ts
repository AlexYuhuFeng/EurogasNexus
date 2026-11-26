import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { breachSummary, breachText, parseBreach } from "../src/app/model/limitBreaches.ts";

const read = (path: string) => readFileSync(new URL(path, import.meta.url), "utf8");
const en = JSON.parse(read("../src/i18n/en.json")) as Record<string, string>;
const zh = JSON.parse(read("../src/i18n/zh.json")) as Record<string, string>;
const t = (key: string, options?: Record<string, unknown>) =>
  (zh[key] ?? key).replace(/\{\{(\w+)\}\}/g, (_, name: string) => String(options?.[name] ?? ""));

test("every breach sentence the risk engine writes is recognised and said in Chinese", () => {
  // One example per template in src/eurogas_nexus/domain/risk/limits.py.
  const samples = [
    "TTF is outside the mandate (demo-kestrel-uk-6)",
    "physical supply is not allowed (C-1)",
    "financial trades are not allowed (T-9)",
    "swap is not an allowed instrument (T-9)",
    "delivery to 2029-03 is beyond 24 months (C-1)",
    "net 1,208,449 MWh in NBP 2027-01 is over 1,000,000 MWh",
    "TTF 2027-01 hedged 81%, above 80%",
    "TTF 2027-01 hedged 0%, below 40%",
    "2027-01 hedged 92%, over the approved 80%",
    "2027-01 hedged -0%, under the approved 60%",
  ];
  for (const sample of samples) {
    const parsed = parseBreach(sample);
    assert.ok(parsed.kind, `not recognised: ${sample}`);
    assert.ok(en[`limits.breach.${parsed.kind}`] && zh[`limits.breach.${parsed.kind}`], parsed.kind);
    assert.match(breachText(sample, t), /\p{Script=Han}/u, sample);
  }
  // The engine's sentence templates are still the ones above.
  const engine = read("../../../src/eurogas_nexus/domain/risk/limits.py");
  for (const fragment of ["is outside the mandate (", "physical supply is not allowed (", "financial trades are not allowed (", "is not an allowed instrument (", "is beyond ", " is over ", "%, above ", "%, below ", "over the approved", "under the approved"]) {
    assert.ok(engine.includes(fragment), `limits.py no longer writes "${fragment}"; update limitBreaches.ts`);
  }
});

test("a contract reference is named, -0% reads 0%, and a band breached month after month is one line", () => {
  const names = new Map([["demo-kestrel-uk-6", "Kestrel UK leg"]]);
  assert.equal(breachText("TTF is outside the mandate (demo-kestrel-uk-6)", t, names), "TTF 不在授权范围内（Kestrel UK leg）");
  assert.equal(breachText("2027-01 hedged -0%, under the approved 60%", t), "2027-01 套保比例 0%，低于批准的 60%");
  const many = ["2026-11 hedged -0%, under the approved 60%", "2026-12 hedged 48%, under the approved 60%", "2027-01 hedged 0%, under the approved 60%"];
  assert.deepEqual(breachSummary(many, t), ["3 个月低于批准的 60%（2026-11 至 2027-01）"]);
  assert.deepEqual(breachSummary("something new; TTF is outside the mandate (X)", t), ["something new", "TTF 不在授权范围内（X）"]);
});

test("a hedge range reads in the reader's language", async () => {
  const { pctRangeText } = await import("../src/app/model/limitBreaches.ts");
  assert.equal(pctRangeText("0% to 44%", t), "0% 至 44%");
  assert.equal(pctRangeText("12%", t), "12%");
});
