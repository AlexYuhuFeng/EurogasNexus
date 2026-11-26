import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { serverWarningText } from "../src/app/warningLabel.ts";

const read = (path: string) => readFileSync(new URL(path, import.meta.url), "utf8");
const zh = JSON.parse(read("../src/i18n/zh.json")) as Record<string, string>;
const t = (key: string, options?: Record<string, unknown>) =>
  (zh[key] ?? key).replace(/\{\{(\w+)\}\}/g, (_, name: string) => String(options?.[name] ?? ""));

test("the server's English notes on the book are said in Chinese, contracts by name", () => {
  const names = new Map([["demo-tender-skarv", "Skarv West tender"]]);
  const samples = [
    "contract demo-tender-skarv: price floats with NBP day-ahead; volume only on the ladder",
    "contract demo-mspa-atlantic-cn07: an FOB cargo is not on a European hub until it is sold or discharged",
    "DEMO: marks are simulated demo prices, not market prices.",
    "Marks are simulated prices, not market prices.",
    "last 7 days -10.8% against DCQ",
    "deviates from nominations on more than 1 day in 5",
    "volatile delivery (CV above 15%)",
    "3 cargo(es) on the ladder from their plans and recorded hedges; volume only, not valued",
    "FX: derived (interest parity from SONIA, SOFR, flat rate), value date 2027-01-15",
    "FX: spot (ECB reference rate of 2026-11-24)",
    "ECB reference rate 2026-11-24",
  ];
  for (const sample of samples) assert.match(serverWarningText(sample, t, names), /\p{Script=Han}/u, sample);
  assert.equal(serverWarningText(samples[0], t, names), "Skarv West tender：价格随 NBP day-ahead 浮动；头寸阶梯仅计气量");
  assert.equal(serverWarningText("Something new.", t), "Something new.");
});

// That the server still writes these sentences is checked server-side
// (tests/unit/test_server_text_in_client_locales.py; a client source does not read the backend).

test("a simulated feed's identifier is never on screen; the quiet simulated mark is", async () => {
  const { sourceSystemLabel } = await import("../src/app/model/enumLabels.ts");
  assert.equal(sourceSystemLabel("DEMO_Sim", t), "模拟数据源");
  assert.equal(sourceSystemLabel("EEX_Sim", t), "模拟数据源");
  assert.equal(sourceSystemLabel("ICE_ENDEX", t), "ICE Endex");
});
